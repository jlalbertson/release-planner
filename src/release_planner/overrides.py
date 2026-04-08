"""Override loader and merger: loads manual field overrides from YAML."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from release_planner.models import Candidate, OverrideSet

logger = logging.getLogger(__name__)


class OverrideLoader:
    """Load, validate, and merge manual overrides from YAML onto Jira-sourced candidates."""

    def __init__(self, overrides_path: str):
        """Initialize with path to overrides YAML file.

        Args:
            overrides_path: Path to the overrides YAML file (e.g. data/overrides.yaml).
        """
        self._path = Path(overrides_path)
        self._override_set: OverrideSet | None = None

    def load(self) -> OverrideSet:
        """Parse YAML and return validated OverrideSet.

        Returns an empty OverrideSet if the file does not exist.

        Raises:
            RuntimeError: If the YAML file is malformed.
        """
        if not self._path.exists():
            logger.info("No overrides file found at %s", self._path)
            self._override_set = OverrideSet(overrides={})
            return self._override_set

        try:
            with open(self._path) as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise RuntimeError(f"Failed to parse overrides YAML at {self._path}: {e}") from e

        if raw is None:
            # Empty YAML file
            self._override_set = OverrideSet(overrides={})
            return self._override_set

        if not isinstance(raw, dict):
            raise RuntimeError(
                f"Overrides YAML at {self._path} must be a mapping (dict), got {type(raw).__name__}"
            )

        # Validate and normalize the overrides
        overrides: dict[str, dict[str, str | int | float | None]] = {}
        for key, fields in raw.items():
            key_str = str(key).strip()
            if not isinstance(fields, dict):
                logger.warning(
                    "Override for key '%s' is not a dict (got %s), skipping",
                    key_str,
                    type(fields).__name__,
                )
                continue
            # Normalize field values
            normalized: dict[str, str | int | float | None] = {}
            for field_name, field_value in fields.items():
                if field_value is None:
                    normalized[str(field_name)] = None
                elif isinstance(field_value, (int, float)):
                    normalized[str(field_name)] = field_value
                else:
                    normalized[str(field_name)] = str(field_value)
            overrides[key_str] = normalized

        self._override_set = OverrideSet(overrides=overrides)
        logger.info("Loaded %d overrides from %s", len(overrides), self._path)
        return self._override_set

    def apply(self, candidates: list[Candidate]) -> list[Candidate]:
        """Merge overrides onto candidates. Returns new list (does not mutate originals).

        Merge rules:
        1. If overrides has a key matching a Candidate's issue_key, each specified field
           in the override replaces the Jira-sourced value.
        2. Override fields that are empty strings ("") clear the Jira value (intentional blanking).
        3. Override fields that are absent are left unchanged from Jira.
        4. MANUAL-xxx entries are NOT applied here -- use get_manual_entries() instead.

        Args:
            candidates: List of Candidate models from Jira.

        Returns:
            New list of Candidate models with overrides applied.
        """
        if self._override_set is None:
            self.load()
        assert self._override_set is not None

        if not self._override_set.overrides:
            return list(candidates)

        result: list[Candidate] = []
        applied_count = 0

        for candidate in candidates:
            override_data = self._override_set.overrides.get(candidate.issue_key)
            if override_data:
                # Build update dict, excluding MANUAL-specific fields and internal fields
                update: dict[str, str | int | float | None] = {}
                for field_name, field_value in override_data.items():
                    if field_name in ("source",):
                        continue  # Don't override internal fields via YAML
                    # Check if the field exists on the Candidate model
                    if field_name in Candidate.model_fields:
                        update[field_name] = field_value

                if update:
                    merged = candidate.model_copy(update=update)
                    result.append(merged)
                    applied_count += 1
                    logger.debug("Applied %d overrides to %s", len(update), candidate.issue_key)
                else:
                    result.append(candidate)
            else:
                result.append(candidate)

        if applied_count > 0:
            logger.info("Applied overrides to %d candidates", applied_count)

        return result

    def get_manual_entries(self) -> list[Candidate]:
        """Return Candidates created purely from overrides (no Jira source).

        Manual entries have keys starting with 'MANUAL-'.

        Returns:
            List of Candidate models with source='manual' and source_pass='manual'.
        """
        if self._override_set is None:
            self.load()
        assert self._override_set is not None

        manual_entries: list[Candidate] = []

        for key, fields in self._override_set.overrides.items():
            if key.upper().startswith("MANUAL-"):
                # Build a Candidate from the override fields
                candidate_data: dict[str, str | int | float | None] = {
                    "issue_key": key,
                    "source": "manual",
                    "source_pass": "manual",
                }
                for field_name, field_value in fields.items():
                    if field_name in Candidate.model_fields:
                        candidate_data[field_name] = field_value

                # Ensure big_rock is set
                if "big_rock" not in candidate_data or not candidate_data["big_rock"]:
                    logger.warning("Manual entry %s has no big_rock field, skipping", key)
                    continue

                try:
                    candidate = Candidate(**candidate_data)  # type: ignore[arg-type]
                    manual_entries.append(candidate)
                    logger.debug("Created manual entry: %s", key)
                except Exception as e:
                    logger.error("Failed to create manual entry %s: %s", key, e)

        if manual_entries:
            logger.info("Created %d manual entries from overrides", len(manual_entries))

        return manual_entries
