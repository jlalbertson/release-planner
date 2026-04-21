"""Click CLI: parse args, orchestrate pipeline."""

from __future__ import annotations

import logging

import click

from release_planner.config import Settings, load_big_rocks, load_field_mapping
from release_planner.models import BigRock, Candidate, OverrideSet
from release_planner.pipeline import PipelineError, PipelineResult
from release_planner.pipeline import run_pipeline as _run_pipeline

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


# Terminal statuses not covered by JQL closed-status filter
_TERMINAL_STATUSES = {"Review", "Pending Release"}


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
    rock_filter: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Execute the outcome-driven pipeline (thin wrapper over pipeline.run_pipeline).

    Delegates data pipeline to pipeline.run_pipeline(), then handles CLI-specific
    output: click.echo() summary, Excel/Sheets writing.

    Returns summary dict with candidate counts and output path/URL.
    """
    try:
        result: PipelineResult = _run_pipeline(
            settings=settings,
            big_rocks=big_rocks,
            field_mapping=field_mapping,
            overrides=overrides,
            release=release,
            rock_filter=rock_filter,
        )
    except PipelineError as e:
        raise click.ClickException(str(e)) from e

    # Unpack stats for display
    rocks_with_outcomes = [r for r in result.big_rocks if r.outcome_keys]
    rocks_without = result.rocks_without_outcomes

    # Calculate totals
    total_candidates = sum(len(c) for c in result.candidates.values())

    # Print summary
    click.echo(f"\n{'=' * 60}")
    click.echo(f"Release Planner Summary ({result.release})")
    click.echo(f"{'=' * 60}")
    for rock in rocks_with_outcomes:
        stats = result.per_rock_stats.get(rock.name, {})
        click.echo(
            f"  {rock.name}: {stats.get('features', 0)} features, "
            f"{stats.get('rfes', 0)} RFEs"
        )
    for rock in rocks_without:
        click.echo(f"  {rock.name}: skipped (no outcome_keys)")
    if result.skipped_count:
        click.echo(
            f"  Skipped: {result.skipped_count} children "
            f"(no matching target release or label)"
        )
    if result.terminal_filtered_count:
        click.echo(
            f"  Filtered: {result.terminal_filtered_count} features "
            f"(terminal status: Review/Pending Release)"
        )
    click.echo(
        f"\nTotal features: "
        f"{sum(s.get('features', 0) for s in result.per_rock_stats.values())}"
    )
    click.echo(
        f"Total RFEs: {sum(s.get('rfes', 0) for s in result.per_rock_stats.values())}"
    )
    click.echo(
        f"Rocks processed: {len(rocks_with_outcomes)} "
        f"({len(rocks_without)} skipped)"
    )
    click.echo(f"{'=' * 60}")

    summary = {
        "total_candidates": total_candidates,
        "per_rock": result.per_rock_stats,
        "output": "",
    }

    if dry_run:
        click.echo("\n[DRY RUN] Skipping output.")
        return summary

    # Excel output mode
    if output:
        from release_planner.excel_writer import ExcelWriter

        writer = ExcelWriter(
            big_rocks=result.big_rocks,
            candidates=result.candidates,
            release=result.release,
            fix_versions=result.fix_versions,
            per_rock_stats=result.per_rock_stats,
            outcome_summaries=result.outcome_summaries,
        )
        abs_path = writer.write(output)
        summary["output"] = abs_path
        click.echo(f"\nExcel file written: {abs_path}")
        return summary

    # Google Sheets output mode
    from release_planner.sheets_writer import SheetsWriter

    credentials = SheetsWriter.load_credentials()
    sheets_writer = SheetsWriter(
        big_rocks=result.big_rocks,
        candidates=result.candidates,
        release=result.release,
        credentials=credentials,
        per_rock_stats=result.per_rock_stats,
        outcome_summaries=result.outcome_summaries,
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

    summary["output"] = url
    click.echo(f"\nSpreadsheet URL: {url}")
    return summary


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
    except Exception as e:
        raise click.ClickException(f"Failed to load config: {e}") from e

    release = br_config.release

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
            rock_filter=list(rocks) if rocks else None,
            dry_run=dry_run,
        )
    except click.ClickException:
        raise
    except Exception as e:
        logger.error("Pipeline failed: %s", e)
        raise click.ClickException(f"Pipeline error: {e}") from e


@main.command()
@click.option("--host", default=None, help="Bind address (default: 127.0.0.1)")
@click.option("--port", default=None, type=int, help="Port (default: 9000)")
@click.option("--verbose", "-v", is_flag=True, help="Debug logging")
def serve(host, port, verbose):
    """Start the web server.

    Serves the release planner dashboard on the specified host and port.
    Default: 127.0.0.1:9000
    """
    import os
    from pathlib import Path

    from release_planner.logging_config import configure_logging

    from release_planner.constants import DEFAULT_WEB_HOST, DEFAULT_WEB_PORT

    # Resolve host and port from CLI args -> env vars -> defaults
    effective_host = host or os.environ.get("RELEASE_PLANNER_HOST", DEFAULT_WEB_HOST)
    effective_port = port or int(os.environ.get("RELEASE_PLANNER_PORT", str(DEFAULT_WEB_PORT)))

    # Determine log format
    json_format = os.environ.get("RELEASE_PLANNER_LOG_FORMAT") == "json"
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    configure_logging(json_format=json_format, level="DEBUG" if verbose else log_level)

    # Resolve config_dir and data_dir to absolute paths (m5 fix)
    config_dir = Path(os.environ.get("CONFIG_DIR", "./config")).resolve()
    data_dir = Path(os.environ.get("DATA_DIR", "./data")).resolve()
    os.environ["CONFIG_DIR"] = str(config_dir)
    os.environ["DATA_DIR"] = str(data_dir)

    import uvicorn

    from release_planner.api import app  # noqa: F811

    click.echo(f"Starting Release Planner web server on {effective_host}:{effective_port}")
    uvicorn.run(app, host=effective_host, port=effective_port)


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
    import re as _re

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
            errors.append("Duplicate priorities found in big_rocks.yaml")

        # Check outcome_keys format
        outcome_pattern = _re.compile(r"^RHAISTRAT-\d+$")
        for rock in big_rocks_list:
            if not rock.outcome_keys:
                warnings.append(
                    f"Rock '{rock.name}' has no outcome_keys "
                    f"(will be skipped during generation)"
                )
            else:
                for key in rock.outcome_keys:
                    if not outcome_pattern.match(key):
                        errors.append(
                            f"Rock '{rock.name}': outcome key '{key}' "
                            f"does not match RHAISTRAT-\\d+ pattern"
                        )

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
