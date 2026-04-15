"""Click CLI: parse args, orchestrate pipeline."""

from __future__ import annotations

import logging

import click

from release_planner.config import Settings, load_big_rocks, load_field_mapping
from release_planner.models import BigRock, Candidate, OverrideSet

logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool = False, log_level: str | None = None) -> None:
    """Configure logging for the CLI."""
    if verbose:
        level = logging.DEBUG
    else:
        level = getattr(logging, (log_level or "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def run_pipeline(
    settings: Settings,
    big_rocks: list[BigRock],
    field_mapping: dict[str, str],
    overrides: OverrideSet | None,
    output: str | None = None,
    spreadsheet_id: str | None = None,
    create: bool = False,
    spreadsheet_name: str | None = None,
    share_with: list[str] | None = None,
    release: str = "3.5",
    fix_versions: list[str] | None = None,
    rock_filter: list[str] | None = None,
    passes: list[int] | None = None,
    dry_run: bool = False,
    duplicate_mode: str = "first",
    exclude_fix_version_patterns: list[str] | None = None,
) -> dict:
    """Execute the full pipeline with three-pass discovery.

    Returns summary dict with candidate counts and output path/URL.
    """
    from release_planner.jira_client import JiraClient
    from release_planner.overrides import OverrideLoader

    if passes is None:
        passes = [1, 2, 3]
    if fix_versions is None:
        fix_versions = []

    # Filter rocks if requested
    active_rocks = big_rocks
    if rock_filter:
        active_rocks = [
            r for r in big_rocks if r.name in rock_filter or str(r.priority) in rock_filter
        ]
        if not active_rocks:
            raise click.ClickException(
                f"No matching rocks found for filter: {rock_filter}. "
                f"Available: {', '.join(r.name for r in big_rocks)}"
            )
        logger.info(
            "Filtered to %d rocks: %s",
            len(active_rocks),
            ", ".join(r.name for r in active_rocks),
        )

    # Initialize Jira client
    jira_client = JiraClient(
        server=settings.jira_server,
        token=settings.jira_token,
        email=settings.jira_email,
        field_mapping=field_mapping,
        query_delay=settings.query_delay,
    )
    jira_client.connect()

    # Fetch candidates for each rock
    all_candidates: dict[str, list[Candidate]] = {}
    seen_keys: set[str] = set()
    per_rock_stats: dict[str, dict[str, int]] = {}

    for rock in active_rocks:
        logger.info("Processing rock: %s (priority %d)", rock.name, rock.priority)
        candidates = jira_client.fetch_candidates_for_rock(
            rock=rock,
            release=release,
            fix_versions=fix_versions,
            passes=passes,
            seen_keys=seen_keys if duplicate_mode == "first" else None,
        )

        # Filter out features (non-RHAIRFE) targeting excluded fix versions
        if exclude_fix_version_patterns:
            before_count = len(candidates)
            candidates = [
                c
                for c in candidates
                if c.issue_key.startswith("RHAIRFE-")
                or not any(p in c.target_release for p in exclude_fix_version_patterns)
            ]
            filtered_count = before_count - len(candidates)
            if filtered_count:
                logger.info(
                    "  Filtered %d features with excluded target versions (*%s*)",
                    filtered_count,
                    ", ".join(exclude_fix_version_patterns),
                )

        # Filter out features (non-RHAIRFE) in terminal states
        _terminal_statuses = {"Closed", "Review", "Pending Release"}
        before_count = len(candidates)
        candidates = [
            c
            for c in candidates
            if c.issue_key.startswith("RHAIRFE-") or c.status not in _terminal_statuses
        ]
        filtered_count = before_count - len(candidates)
        if filtered_count:
            logger.info(
                "  Filtered %d features with terminal status (Closed/Review/Pending Release)",
                filtered_count,
            )

        # Track stats
        stats = {
            "committed": sum(1 for c in candidates if c.source_pass == "committed"),
            "candidate": sum(1 for c in candidates if c.source_pass == "candidate"),
            "rfe": sum(1 for c in candidates if c.source_pass == "rfe"),
            "manual": 0,
        }
        per_rock_stats[rock.name] = stats

        # Update seen_keys for deduplication across rocks
        for c in candidates:
            seen_keys.add(c.issue_key)

        all_candidates[rock.name] = candidates
        logger.info(
            "  %s: %d total (committed=%d, candidate=%d, rfe=%d)",
            rock.name,
            len(candidates),
            stats["committed"],
            stats["candidate"],
            stats["rfe"],
        )

    # Handle cross-rock deduplication for duplicate_mode="first"
    if duplicate_mode == "first":
        _deduplicate_candidates(all_candidates, active_rocks)

    # Apply overrides
    if overrides and overrides.overrides:
        from release_planner.overrides import OverrideLoader

        loader = OverrideLoader.__new__(OverrideLoader)
        loader._path = None  # type: ignore[assignment]
        loader._override_set = overrides

        for rock_name, candidates in all_candidates.items():
            all_candidates[rock_name] = loader.apply(candidates)

        # Add manual entries
        manual_entries = loader.get_manual_entries()
        for entry in manual_entries:
            rock_name = entry.big_rock
            if rock_name in all_candidates:
                all_candidates[rock_name].append(entry)
                per_rock_stats.setdefault(
                    rock_name, {"committed": 0, "candidate": 0, "rfe": 0, "manual": 0}
                )
                per_rock_stats[rock_name]["manual"] += 1
            else:
                logger.warning(
                    "Manual entry %s references unknown rock '%s'",
                    entry.issue_key,
                    rock_name,
                )

    # Calculate totals
    total_candidates = sum(len(c) for c in all_candidates.values())

    # Print summary
    click.echo(f"\n{'=' * 60}")
    click.echo(f"Release Planner Summary ({release})")
    click.echo(f"{'=' * 60}")
    for rock in active_rocks:
        stats = per_rock_stats.get(rock.name, {})
        total = len(all_candidates.get(rock.name, []))
        click.echo(
            f"  {rock.name}: {total} total "
            f"(committed={stats.get('committed', 0)}, "
            f"candidate={stats.get('candidate', 0)}, "
            f"rfe={stats.get('rfe', 0)}, "
            f"manual={stats.get('manual', 0)})"
        )
    click.echo(f"\nTotal candidates: {total_candidates}")
    click.echo(f"Rocks processed: {len(active_rocks)}")

    result = {
        "total_candidates": total_candidates,
        "per_rock": per_rock_stats,
        "output": "",
    }

    if dry_run:
        click.echo("\n[DRY RUN] Skipping output.")
        return result

    # Excel output mode
    if output:
        from release_planner.excel_writer import ExcelWriter

        writer = ExcelWriter(
            big_rocks=active_rocks,
            candidates=all_candidates,
            release=release,
        )
        abs_path = writer.write(output)
        result["output"] = abs_path
        click.echo(f"\nExcel file written: {abs_path}")
        return result

    # Google Sheets output mode
    from release_planner.sheets_writer import SheetsWriter

    credentials = SheetsWriter.load_credentials()
    sheets_writer = SheetsWriter(
        big_rocks=active_rocks,
        candidates=all_candidates,
        release=release,
        credentials=credentials,
    )

    if create:
        title = spreadsheet_name or f"RHOAI {release} Candidates"
        url = sheets_writer.create_and_write(
            title, share_with=list(share_with) if share_with else None
        )
    elif spreadsheet_id:
        url = sheets_writer.write(spreadsheet_id)
    else:
        raise click.ClickException(
            "Must specify --output, --spreadsheet-id, DEFAULT_SPREADSHEET_ID env var, "
            "or --create. See --help for details."
        )

    result["output"] = url
    click.echo(f"\nSpreadsheet URL: {url}")
    return result


def _deduplicate_candidates(
    all_candidates: dict[str, list[Candidate]],
    rocks: list[BigRock],
) -> None:
    """Handle cross-rock deduplication.

    For issues appearing under multiple rocks:
    - The issue row appears under the highest-priority rock only.
    - The big_rock field is set to comma-joined rock names.
    - A note is added to comments about other rocks.
    """
    # Build mapping of issue_key -> list of rock names
    key_to_rocks: dict[str, list[str]] = {}
    for rock in rocks:
        for candidate in all_candidates.get(rock.name, []):
            key_to_rocks.setdefault(candidate.issue_key, []).append(rock.name)

    # Find duplicates
    duplicates = {k: v for k, v in key_to_rocks.items() if len(v) > 1}

    if not duplicates:
        return

    logger.info("Found %d cross-rock duplicates", len(duplicates))

    # Process duplicates: keep under highest-priority rock, remove from others
    rock_priority = {r.name: r.priority for r in rocks}

    for issue_key, rock_names in duplicates.items():
        # Sort by priority (lowest number = highest priority)
        sorted_rocks = sorted(rock_names, key=lambda r: rock_priority.get(r, 999))
        primary_rock = sorted_rocks[0]
        other_rocks = sorted_rocks[1:]

        # Update the primary rock's candidate with multi-rock info
        for i, candidate in enumerate(all_candidates.get(primary_rock, [])):
            if candidate.issue_key == issue_key:
                combined_name = ", ".join(sorted_rocks)
                comments = candidate.comments
                note = f"Also in: {', '.join(other_rocks)}"
                if comments:
                    comments = f"{comments} | {note}"
                else:
                    comments = note
                all_candidates[primary_rock][i] = candidate.model_copy(
                    update={"big_rock": combined_name, "comments": comments}
                )
                break

        # Remove from other rocks
        for other_rock in other_rocks:
            all_candidates[other_rock] = [
                c for c in all_candidates.get(other_rock, []) if c.issue_key != issue_key
            ]


@click.group()
def main():
    """RHOAI Release Planner -- generate planning spreadsheets from Jira to Google Sheets."""


@main.command()
@click.option(
    "--spreadsheet-id",
    default=None,
    help="Google Sheets spreadsheet ID to update (overrides DEFAULT_SPREADSHEET_ID)",
)
@click.option(
    "--spreadsheet-name",
    default=None,
    help="Name for new spreadsheet (requires --create)",
)
@click.option(
    "--create",
    is_flag=True,
    help="Create a new Google Spreadsheet instead of updating an existing one",
)
@click.option(
    "--share-with",
    multiple=True,
    help="Email addresses to share newly created spreadsheet with (repeatable)",
)
@click.option(
    "-o",
    "--output",
    default=None,
    type=click.Path(),
    help="Write to a local Excel (.xlsx) file instead of Google Sheets",
)
@click.option("--config-dir", default="./config", help="Config directory")
@click.option("--data-dir", default="./data", help="Data directory (overrides, field mapping)")
@click.option("--dry-run", is_flag=True, help="Query Jira but skip output")
@click.option(
    "--rocks",
    multiple=True,
    help="Generate only specific rocks (by name or number, repeatable)",
)
@click.option("--no-overrides", is_flag=True, help="Skip manual overrides")
@click.option(
    "--passes",
    default="1,2,3",
    help="Comma-separated list of discovery passes to run (default: 1,2,3)",
)
@click.option(
    "--duplicate-mode",
    default="all",
    type=click.Choice(["first", "all"]),
    help="'first' (show under highest-priority rock) or 'all' (show under every rock)",
)
@click.option("--verbose", "-v", is_flag=True, help="Debug logging")
def generate(
    spreadsheet_id,
    spreadsheet_name,
    create,
    share_with,
    output,
    config_dir,
    data_dir,
    dry_run,
    rocks,
    no_overrides,
    passes,
    duplicate_mode,
    verbose,
):
    """Generate the release planning spreadsheet.

    Outputs to a local Excel file (--output) or Google Sheets (--spreadsheet-id / --create).
    """
    # Only require Google credentials if outputting to Google Sheets
    require_google = not dry_run and not output
    try:
        settings = Settings.from_env(require_google=require_google)
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e

    _setup_logging(verbose=verbose, log_level=settings.log_level)

    # Use CLI-provided dirs or fall back to settings
    effective_config_dir = config_dir if config_dir != "./config" else settings.config_dir
    effective_data_dir = data_dir if data_dir != "./data" else settings.data_dir

    # Load config
    try:
        big_rocks_list, br_config = load_big_rocks(effective_config_dir)
    except (FileNotFoundError, Exception) as e:
        raise click.ClickException(f"Failed to load config: {e}") from e

    release = br_config.release
    fix_versions = br_config.fix_versions
    exclude_fix_version_patterns = br_config.exclude_fix_version_patterns

    # Load field mapping
    field_mapping = load_field_mapping(effective_data_dir)

    # Load overrides
    overrides = None
    if not no_overrides:
        from release_planner.overrides import OverrideLoader

        overrides_path = f"{effective_data_dir}/overrides.yaml"
        loader = OverrideLoader(overrides_path)
        try:
            overrides = loader.load()
        except RuntimeError as e:
            raise click.ClickException(f"Failed to load overrides: {e}") from e

    # Parse passes
    try:
        pass_list = [int(p.strip()) for p in passes.split(",")]
    except ValueError:
        raise click.ClickException(
            f"Invalid --passes value: '{passes}'. Use comma-separated integers (e.g. 1,2,3)"
        )

    # Resolve spreadsheet_id from settings if not provided
    effective_spreadsheet_id = spreadsheet_id or settings.default_spreadsheet_id

    # Validate that we have a target
    if not output and not create and not effective_spreadsheet_id and not dry_run:
        raise click.ClickException(
            "Must specify --output, --spreadsheet-id, set DEFAULT_SPREADSHEET_ID env var, "
            "or use --create. Run with --dry-run to skip output."
        )

    # Run the pipeline
    try:
        run_pipeline(
            settings=settings,
            big_rocks=big_rocks_list,
            field_mapping=field_mapping,
            overrides=overrides,
            output=output,
            spreadsheet_id=effective_spreadsheet_id,
            create=create,
            spreadsheet_name=spreadsheet_name,
            share_with=list(share_with) if share_with else None,
            release=release,
            fix_versions=fix_versions,
            rock_filter=list(rocks) if rocks else None,
            passes=pass_list,
            dry_run=dry_run,
            duplicate_mode=duplicate_mode,
            exclude_fix_version_patterns=exclude_fix_version_patterns,
        )
    except click.ClickException:
        raise
    except Exception as e:
        logger.error("Pipeline failed: %s", e)
        raise click.ClickException(f"Pipeline error: {e}") from e


@main.command("discover-fields")
@click.option("--issue-key", required=True, help="Sample issue key to inspect fields")
@click.option("--verbose", "-v", is_flag=True, help="Debug logging")
def discover_fields(issue_key, verbose):
    """Discover custom field IDs from a sample Jira issue. Prints field mapping."""
    try:
        settings = Settings.from_env(require_google=False)
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e

    _setup_logging(verbose=verbose, log_level=settings.log_level)

    from release_planner.jira_client import JiraClient

    client = JiraClient(
        server=settings.jira_server,
        token=settings.jira_token,
        email=settings.jira_email,
        query_delay=settings.query_delay,
    )

    try:
        client.connect()
        fields = client.discover_custom_fields(issue_key)
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e

    click.echo(f"\nCustom fields on {issue_key}:")
    click.echo(f"{'=' * 60}")
    for field_id, description in sorted(fields.items()):
        click.echo(f"  {field_id}: {description}")
    click.echo(f"\nTotal custom fields with values: {len(fields)}")
    click.echo(
        "\nCopy relevant field IDs to data/field_mapping.yaml. "
        "See config/field_mapping.example.yaml for the template."
    )


@main.command("validate-config")
@click.option("--config-dir", default="./config", help="Config directory")
@click.option("--data-dir", default="./data", help="Data directory")
@click.option("--verbose", "-v", is_flag=True, help="Debug logging")
def validate_config(config_dir, data_dir, verbose):
    """Validate big_rocks.yaml and overrides.yaml without querying Jira."""
    _setup_logging(verbose=verbose)

    errors: list[str] = []
    warnings: list[str] = []

    # Validate big_rocks.yaml
    try:
        big_rocks_list, br_config = load_big_rocks(config_dir)
        click.echo(f"big_rocks.yaml: OK ({len(big_rocks_list)} rocks, release={br_config.release})")

        # Check for duplicate priorities
        priorities = [r.priority for r in big_rocks_list]
        if len(priorities) != len(set(priorities)):
            warnings.append("Duplicate priorities found in big_rocks.yaml")

        # Check for empty JQL
        for rock in big_rocks_list:
            if not rock.jql.strip():
                errors.append(f"Rock '{rock.name}' has empty JQL")
            if not rock.components:
                warnings.append(f"Rock '{rock.name}' has no components")

        # Check fix_versions
        if not br_config.fix_versions:
            warnings.append("No fix_versions defined")
        else:
            click.echo(f"fix_versions: {br_config.fix_versions}")

    except FileNotFoundError:
        errors.append(f"big_rocks.yaml not found in {config_dir}")
    except Exception as e:
        errors.append(f"big_rocks.yaml parse error: {e}")

    # Validate field_mapping
    field_mapping = load_field_mapping(data_dir)
    if field_mapping:
        click.echo(f"field_mapping.yaml: OK ({len(field_mapping)} mappings)")
    else:
        warnings.append(
            f"No field_mapping.yaml found in {data_dir}. Run discover-fields to create one."
        )

    # Validate overrides
    from release_planner.overrides import OverrideLoader

    overrides_path = f"{data_dir}/overrides.yaml"
    try:
        loader = OverrideLoader(overrides_path)
        override_set = loader.load()
        click.echo(f"overrides.yaml: OK ({len(override_set.overrides)} entries)")
    except RuntimeError as e:
        errors.append(f"overrides.yaml parse error: {e}")
    except FileNotFoundError:
        warnings.append(f"overrides.yaml not found at {overrides_path} (optional)")

    # Report
    click.echo("")
    if warnings:
        click.echo("Warnings:")
        for w in warnings:
            click.echo(f"  - {w}")

    if errors:
        click.echo("\nErrors:")
        for e in errors:
            click.echo(f"  - {e}")
        raise click.ClickException("Validation failed")

    click.echo("\nValidation passed.")


@main.command("import-xlsx")
@click.option(
    "--xlsx",
    required=True,
    type=click.Path(exists=True),
    help="Path to existing spreadsheet",
)
@click.option(
    "-o",
    "--output",
    default="./data/overrides.yaml",
    help="Output overrides YAML path",
)
@click.option(
    "--sheet-name",
    default=None,
    help="Sheet name to import (default: auto-detect)",
)
@click.option("--verbose", "-v", is_flag=True, help="Debug logging")
def import_xlsx(xlsx, output, sheet_name, verbose):
    """Import an existing spreadsheet to bootstrap overrides.yaml."""
    _setup_logging(verbose=verbose)

    try:
        from release_planner.importer import SpreadsheetImporter
    except ImportError as e:
        raise click.ClickException(str(e)) from e

    try:
        importer = SpreadsheetImporter(xlsx, sheet_name=sheet_name)
        count = importer.import_to_overrides(output)
        click.echo(f"\nImported {count} entries to {output}")
    except (ValueError, FileNotFoundError, ImportError) as e:
        raise click.ClickException(str(e)) from e
    except Exception as e:
        logger.exception("Import failed")
        raise click.ClickException(f"Import error: {e}") from e
