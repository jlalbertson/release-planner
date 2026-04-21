"""Pipeline logic: Jira data fetching, filtering, dedup, overrides.

This module contains the core data pipeline, extracted from cli.py.
It MUST NOT import Click or any CLI framework.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from release_planner.config import Settings
from release_planner.models import BigRock, Candidate, OverrideSet

logger = logging.getLogger(__name__)


# ---- Exception hierarchy ----


class PipelineError(Exception):
    """Base exception for pipeline failures."""


class JiraConnectionError(PipelineError):
    """Jira is unreachable or returned an auth error."""


class ConfigError(PipelineError):
    """Config YAML is missing or malformed."""


# ---- Result dataclass ----


@dataclass
class PipelineResult:
    """Result of the data pipeline, before any output formatting."""

    # For ExcelWriter compatibility (C3) -- keyed by rock name
    candidates: dict[str, list[Candidate]]
    big_rocks: list[BigRock]  # Active rocks (filtered if --rocks used)
    fix_versions: list[str]  # Derived from release string

    # Flat lists for API serialization
    features: list[Candidate]  # RHAISTRAT only, deduplicated, sorted
    rfes: list[Candidate]  # RHAIRFE only, deduplicated, sorted

    # Tier counts
    tier1_features: int = 0
    tier1_rfes: int = 0
    tier2_features: int = 0
    tier2_rfes: int = 0

    # Stats and metadata
    per_rock_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    outcome_summaries: dict[str, str] = field(default_factory=dict)
    release: str = ""
    skipped_count: int = 0
    terminal_filtered_count: int = 0
    rocks_without_outcomes: list[BigRock] = field(default_factory=list)


# Terminal statuses not covered by JQL closed-status filter
_TERMINAL_STATUSES = {"Review", "Pending Release"}


def run_pipeline(
    settings: Settings,
    big_rocks: list[BigRock],
    field_mapping: dict[str, str],
    overrides: OverrideSet | None,
    release: str = "3.5",
    rock_filter: list[str] | None = None,
    jira_client: "JiraClient | None" = None,
) -> PipelineResult:
    """Execute the outcome-driven pipeline and return structured results.

    Steps:
    1. For each BigRock with outcome_keys, fetch children via parent traversal
    2. Classify: Features (RHAISTRAT + target_release contains release) and
       RFEs (RHAIRFE + release-candidate label)
    3. Post-filter: remove non-RFE features in terminal statuses
    4. Deduplicate: one row per issue_key, merge Big Rock names (ordered by priority)
    5. Apply overrides
    6. Return structured PipelineResult

    Args:
        settings: Application settings.
        big_rocks: List of BigRock definitions.
        field_mapping: Custom field mapping dict.
        overrides: Optional overrides to apply.
        release: Release version string (e.g. "3.5").
        rock_filter: Optional list of rock names/priorities to filter to.
        jira_client: Optional pre-connected JiraClient. If None, a new one
            is created and connected (CLI behavior). The web server passes
            a shared instance for connection reuse.

    Returns:
        PipelineResult with all data needed for CLI output, API response,
        and Excel export.

    Raises:
        PipelineError: If no matching rocks found for filter.
        JiraConnectionError: If Jira connection fails.
    """
    from release_planner.jira_client import JiraClient

    # Filter rocks if requested
    active_rocks = big_rocks
    if rock_filter:
        active_rocks = [
            r for r in big_rocks if r.name in rock_filter or str(r.priority) in rock_filter
        ]
        if not active_rocks:
            raise PipelineError(
                f"No matching rocks found for filter: {rock_filter}. "
                f"Available: {', '.join(r.name for r in big_rocks)}"
            )
        logger.info(
            "Filtered to %d rocks: %s",
            len(active_rocks),
            ", ".join(r.name for r in active_rocks),
        )

    # Skip rocks with no outcome_keys
    rocks_with_outcomes = [r for r in active_rocks if r.outcome_keys]
    rocks_without = [r for r in active_rocks if not r.outcome_keys]
    for r in rocks_without:
        logger.warning("Skipping %s: no outcome_keys defined", r.name)

    # Initialize Jira client if not provided (M1: dependency injection)
    if jira_client is None:
        jira_client = JiraClient(
            server=settings.jira_server,
            token=settings.jira_token,
            email=settings.jira_email,
            field_mapping=field_mapping,
            query_delay=settings.query_delay,
        )
        try:
            jira_client.connect()
        except RuntimeError as e:
            raise JiraConnectionError(str(e)) from e

    # Fetch Outcome summaries (titles) for the Big Rocks worksheet
    all_outcome_keys = []
    for rock in rocks_with_outcomes:
        all_outcome_keys.extend(rock.outcome_keys)
    outcome_summaries = jira_client.fetch_outcome_summaries(all_outcome_keys)

    # --- Phase A: Discover all children ---
    # Maps: issue_key -> (Candidate, set of (priority, rock_name))
    feature_map: dict[str, tuple[Candidate, set[tuple[int, str]]]] = {}
    rfe_map: dict[str, tuple[Candidate, set[tuple[int, str]]]] = {}
    skipped_count = 0
    terminal_filtered_count = 0

    for rock in rocks_with_outcomes:
        rock_child_count = 0
        for outcome_key in rock.outcome_keys:
            children = jira_client.fetch_outcome_children(outcome_key, rock.name)

            for child in children:
                key = child.issue_key

                if key.startswith("RHAISTRAT-"):
                    # Feature: check Target Release contains release string
                    if release not in child.target_release:
                        skipped_count += 1
                        logger.debug(
                            "Skipping %s: target_release '%s' does not contain '%s'",
                            key,
                            child.target_release,
                            release,
                        )
                        continue

                    # Post-filter: terminal statuses
                    if child.status in _TERMINAL_STATUSES:
                        terminal_filtered_count += 1
                        logger.debug(
                            "Skipping %s: terminal status '%s'",
                            key,
                            child.status,
                        )
                        continue

                    if key in feature_map:
                        feature_map[key][1].add((rock.priority, rock.name))
                    else:
                        feature_map[key] = (child, {(rock.priority, rock.name)})
                    rock_child_count += 1

                elif key.startswith("RHAIRFE-"):
                    # Approved RFEs have a cloned RHAISTRAT Feature, so skip
                    if child.status == "Approved":
                        skipped_count += 1
                        logger.debug(
                            "Skipping RFE %s: Approved (cloned Feature expected)",
                            key,
                        )
                        continue

                    # RFE: check for release-candidate label
                    # Split labels and check individual values to avoid
                    # substring false-positives
                    label_list = [
                        lbl.strip().lower() for lbl in child.labels.split(",") if lbl.strip()
                    ]
                    target_label = f"{release}-candidate"
                    if target_label not in label_list:
                        skipped_count += 1
                        logger.debug(
                            "Skipping RFE %s: no '%s' label (labels: %s)",
                            key,
                            target_label,
                            child.labels,
                        )
                        continue
                    if key in rfe_map:
                        rfe_map[key][1].add((rock.priority, rock.name))
                    else:
                        rfe_map[key] = (child, {(rock.priority, rock.name)})
                    rock_child_count += 1

                else:
                    # Unknown project prefix -- skip
                    skipped_count += 1
                    logger.debug("Skipping %s: unrecognized project prefix", key)

        # Warn if rock has outcome_keys but zero qualifying children
        if rock_child_count == 0:
            logger.warning(
                "Rock '%s' has outcome_keys %s but zero qualifying children "
                "(check that outcome keys are correct and children have "
                "the expected Target Release / labels)",
                rock.name,
                rock.outcome_keys,
            )

    if terminal_filtered_count:
        logger.info(
            "Filtered %d features with terminal status (Review/Pending Release)",
            terminal_filtered_count,
        )

    # --- Phase B: Merge Big Rock names ---
    # When --rocks filter is active, recompute merged names using only active rocks
    active_rock_names = {r.name for r in active_rocks} if rock_filter else None

    def merge_rock_names_filtered(
        rock_set: set[tuple[int, str]],
    ) -> str:
        """Merge names, restricting to active rocks when --rocks is used."""
        if active_rock_names is not None:
            rock_set = {(p, n) for p, n in rock_set if n in active_rock_names}
        return ", ".join(name for _, name in sorted(rock_set))

    # Build final candidate lists
    all_features: list[Candidate] = []
    for key, (candidate, rocks_set) in feature_map.items():
        merged_name = merge_rock_names_filtered(rocks_set)
        if not merged_name:
            # All rocks for this feature are filtered out by --rocks
            continue
        updated = candidate.model_copy(update={"big_rock": merged_name})
        all_features.append(updated)

    all_rfes: list[Candidate] = []
    for key, (candidate, rocks_set) in rfe_map.items():
        merged_name = merge_rock_names_filtered(rocks_set)
        if not merged_name:
            continue
        updated = candidate.model_copy(update={"big_rock": merged_name})
        all_rfes.append(updated)

    # Sort: features by Big Rock priority order, then issue_key
    rock_priority = {r.name: r.priority for r in big_rocks}
    all_features.sort(
        key=lambda c: (rock_priority.get(c.big_rock.split(", ")[0], 999), c.issue_key)
    )
    all_rfes.sort(
        key=lambda c: (rock_priority.get(c.big_rock.split(", ")[0], 999), c.issue_key)
    )

    # Build output dict keyed by rock name (for writer compatibility)
    all_candidates: dict[str, list[Candidate]] = {}
    for rock in rocks_with_outcomes:
        features_for_rock = [c for c in all_features if c.big_rock.split(", ")[0] == rock.name]
        rfes_for_rock = [c for c in all_rfes if c.big_rock.split(", ")[0] == rock.name]
        all_candidates[rock.name] = features_for_rock + rfes_for_rock

    # Apply overrides
    if overrides and overrides.overrides:
        from release_planner.overrides import OverrideLoader

        loader = OverrideLoader.__new__(OverrideLoader)
        loader._path = None  # type: ignore[assignment]
        loader._override_set = overrides

        for rock_name, candidates_list in all_candidates.items():
            all_candidates[rock_name] = loader.apply(candidates_list)

        # Add manual entries
        manual_entries = loader.get_manual_entries()
        for entry in manual_entries:
            rock_name = entry.big_rock
            if rock_name in all_candidates:
                all_candidates[rock_name].append(entry)
            else:
                logger.warning(
                    "Manual entry %s references unknown rock '%s'",
                    entry.issue_key,
                    rock_name,
                )

    # --- Stats ---
    per_rock_stats: dict[str, dict[str, int]] = {}
    for rock in rocks_with_outcomes:
        candidates_for_rock = all_candidates.get(rock.name, [])
        per_rock_stats[rock.name] = {
            "features": sum(1 for c in candidates_for_rock if c.source == "jira"),
            "rfes": sum(1 for c in candidates_for_rock if c.source == "rfe"),
            "manual": sum(1 for c in candidates_for_rock if c.source == "manual"),
        }

    # Derive fix_versions from release string for ExcelWriter
    derived_fix_versions = [
        f"rhoai-{release}",
        f"RHOAI {release}",
        release,
        f"{release}.0",
        f"RHAIIS-{release}",
    ]

    # Rebuild flat lists after overrides (overrides may have changed candidates)
    final_features: list[Candidate] = []
    final_rfes: list[Candidate] = []
    for rock in rocks_with_outcomes:
        for c in all_candidates.get(rock.name, []):
            if c.issue_key.startswith("RHAIRFE-"):
                final_rfes.append(c)
            else:
                final_features.append(c)

    tier1_feature_count = len(final_features)
    tier1_rfe_count = len(final_rfes)

    # --- Phase C: Tier 2 discovery ---
    tier1_feature_keys = {c.issue_key for c in final_features}
    tier1_rfe_keys = {c.issue_key for c in final_rfes}

    tier2_features = jira_client.fetch_tier2_features(release, tier1_feature_keys)
    tier2_rfes = jira_client.fetch_tier2_rfes(release, tier1_rfe_keys)

    # Post-filter terminal statuses on Tier 2 features
    filtered_t2_features: list[Candidate] = []
    for c in tier2_features:
        if c.status in _TERMINAL_STATUSES:
            terminal_filtered_count += 1
            logger.debug("Skipping Tier 2 %s: terminal status '%s'", c.issue_key, c.status)
            continue
        filtered_t2_features.append(c)

    logger.info(
        "Tier 2: %d features, %d RFEs",
        len(filtered_t2_features),
        len(tier2_rfes),
    )

    # Append Tier 2 after Tier 1 in flat lists
    final_features.extend(filtered_t2_features)
    final_rfes.extend(tier2_rfes)

    # Add Tier 2 to candidates dict under empty-string key for writer compatibility
    tier2_all = filtered_t2_features + tier2_rfes
    if tier2_all:
        all_candidates[""] = tier2_all

    return PipelineResult(
        candidates=all_candidates,
        big_rocks=active_rocks,
        fix_versions=derived_fix_versions,
        features=final_features,
        rfes=final_rfes,
        tier1_features=tier1_feature_count,
        tier1_rfes=tier1_rfe_count,
        tier2_features=len(filtered_t2_features),
        tier2_rfes=len(tier2_rfes),
        per_rock_stats=per_rock_stats,
        outcome_summaries=outcome_summaries,
        release=release,
        skipped_count=skipped_count,
        terminal_filtered_count=terminal_filtered_count,
        rocks_without_outcomes=rocks_without,
    )
