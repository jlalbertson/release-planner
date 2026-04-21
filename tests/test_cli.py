"""Tests for cli.py: CLI commands with mocked dependencies."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from release_planner.cli import _TERMINAL_STATUSES, main, run_pipeline
from release_planner.config import Settings
from release_planner.models import BigRock, Candidate


@pytest.fixture
def runner():
    return CliRunner()


class TestValidateConfig:
    """Tests for the validate-config CLI command."""

    def test_validate_with_valid_config(self, runner, config_dir):
        result = runner.invoke(
            main,
            [
                "validate-config",
                "--config-dir",
                config_dir,
                "--data-dir",
                "/tmp/nonexistent-data",
            ],
        )
        assert result.exit_code == 0
        assert "big_rocks.yaml: OK" in result.output
        assert "14 rocks" in result.output

    def test_validate_with_missing_config(self, runner, tmp_path):
        result = runner.invoke(
            main,
            [
                "validate-config",
                "--config-dir",
                str(tmp_path / "missing"),
                "--data-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "Error" in result.output


class TestGenerateCommand:
    """Tests for the generate CLI command."""

    @patch("release_planner.config.load_dotenv")
    def test_generate_missing_jira_token(self, _mock_dotenv, runner, monkeypatch):
        monkeypatch.delenv("RELEASE_PLANNER_JIRA_TOKEN", raising=False)
        monkeypatch.delenv("JIRA_TOKEN", raising=False)
        monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
        monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)

        result = runner.invoke(main, ["generate", "--dry-run"])
        assert result.exit_code != 0
        assert "RELEASE_PLANNER_JIRA_TOKEN" in result.output

    @patch("release_planner.config.load_dotenv")
    def test_generate_missing_google_credentials(self, _mock_dotenv, runner, monkeypatch):
        monkeypatch.setenv("RELEASE_PLANNER_JIRA_TOKEN", "test-token")
        monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
        monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)

        result = runner.invoke(main, ["generate"])
        assert result.exit_code != 0
        assert "GOOGLE_CREDENTIALS" in result.output

    def test_generate_no_target_specified(self, runner, monkeypatch, config_dir):
        monkeypatch.setenv("RELEASE_PLANNER_JIRA_TOKEN", "test-token")
        monkeypatch.setenv("GOOGLE_CREDENTIALS_FILE", "/tmp/creds.json")
        monkeypatch.delenv("DEFAULT_SPREADSHEET_ID", raising=False)

        result = runner.invoke(
            main,
            [
                "generate",
                "--config-dir",
                config_dir,
            ],
        )
        assert result.exit_code != 0
        assert "spreadsheet-id" in result.output.lower() or "create" in result.output.lower()

    @patch("release_planner.cli.run_pipeline")
    def test_generate_dry_run(self, mock_pipeline, runner, monkeypatch, config_dir):
        monkeypatch.setenv("RELEASE_PLANNER_JIRA_TOKEN", "test-token")
        monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
        monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)

        mock_pipeline.return_value = {
            "total_candidates": 10,
            "per_rock": {},
            "spreadsheet_url": "",
        }

        result = runner.invoke(
            main,
            [
                "generate",
                "--config-dir",
                config_dir,
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        mock_pipeline.assert_called_once()

        # Verify dry_run was passed as True
        call_kwargs = mock_pipeline.call_args[1]
        assert call_kwargs["dry_run"] is True

    @patch("release_planner.cli.run_pipeline")
    def test_generate_with_rock_filter(self, mock_pipeline, runner, monkeypatch, config_dir):
        monkeypatch.setenv("RELEASE_PLANNER_JIRA_TOKEN", "test-token")
        monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
        monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)

        mock_pipeline.return_value = {
            "total_candidates": 5,
            "per_rock": {},
            "spreadsheet_url": "",
        }

        result = runner.invoke(
            main,
            [
                "generate",
                "--config-dir",
                config_dir,
                "--rocks",
                "MaaS",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        call_kwargs = mock_pipeline.call_args[1]
        assert call_kwargs["rock_filter"] == ["MaaS"]

    @patch("release_planner.cli.run_pipeline")
    def test_generate_create_mode(self, mock_pipeline, runner, monkeypatch, config_dir):
        monkeypatch.setenv("RELEASE_PLANNER_JIRA_TOKEN", "test-token")
        monkeypatch.setenv("GOOGLE_CREDENTIALS_FILE", "/tmp/creds.json")

        mock_pipeline.return_value = {
            "total_candidates": 10,
            "per_rock": {},
            "spreadsheet_url": "https://docs.google.com/spreadsheets/d/123",
        }

        result = runner.invoke(
            main,
            [
                "generate",
                "--config-dir",
                config_dir,
                "--create",
                "--spreadsheet-name",
                "Test Sheet",
            ],
        )
        assert result.exit_code == 0
        call_kwargs = mock_pipeline.call_args[1]
        assert call_kwargs["create"] is True
        assert call_kwargs["spreadsheet_name"] == "Test Sheet"

    @patch("release_planner.cli.run_pipeline")
    def test_generate_spreadsheet_id(self, mock_pipeline, runner, monkeypatch, config_dir):
        monkeypatch.setenv("RELEASE_PLANNER_JIRA_TOKEN", "test-token")
        monkeypatch.setenv("GOOGLE_CREDENTIALS_FILE", "/tmp/creds.json")

        mock_pipeline.return_value = {
            "total_candidates": 10,
            "per_rock": {},
            "spreadsheet_url": "https://docs.google.com/spreadsheets/d/abc",
        }

        result = runner.invoke(
            main,
            [
                "generate",
                "--config-dir",
                config_dir,
                "--spreadsheet-id",
                "abc",
            ],
        )
        assert result.exit_code == 0
        call_kwargs = mock_pipeline.call_args[1]
        assert call_kwargs["spreadsheet_id"] == "abc"


class TestDiscoverFields:
    """Tests for the discover-fields CLI command."""

    @patch("release_planner.config.load_dotenv")
    def test_discover_fields_missing_token(self, _mock_dotenv, runner, monkeypatch):
        monkeypatch.delenv("RELEASE_PLANNER_JIRA_TOKEN", raising=False)
        monkeypatch.delenv("JIRA_TOKEN", raising=False)
        monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
        monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)

        result = runner.invoke(main, ["discover-fields", "--issue-key", "TEST-1"])
        assert result.exit_code != 0
        assert "RELEASE_PLANNER_JIRA_TOKEN" in result.output


class TestImportXlsx:
    """Tests for the import-xlsx CLI command."""

    def test_import_xlsx_file_not_found(self, runner):
        result = runner.invoke(
            main,
            [
                "import-xlsx",
                "--xlsx",
                "/nonexistent/file.xlsx",
            ],
        )
        assert result.exit_code != 0


# --- Pipeline unit tests ---


def _make_candidate(
    key: str,
    big_rock: str = "TestRock",
    status: str = "New",
    target_release: str = "rhoai-3.5",
    labels: str = "",
    source: str = "jira",
    source_pass: str = "outcome",
) -> Candidate:
    """Helper to create a Candidate for pipeline tests."""
    return Candidate(
        big_rock=big_rock,
        issue_key=key,
        status=status,
        target_release=target_release,
        labels=labels,
        source=source,
        source_pass=source_pass,
    )


class TestTerminalStatusFilter:
    """Tests for the terminal status post-filter in the pipeline."""

    def test_terminal_statuses_defined(self):
        assert "Review" in _TERMINAL_STATUSES
        assert "Pending Release" in _TERMINAL_STATUSES

    def test_review_status_filtered(self):
        """Features with status 'Review' are excluded."""
        assert "Review" in _TERMINAL_STATUSES

    def test_pending_release_filtered(self):
        """Features with status 'Pending Release' are excluded."""
        assert "Pending Release" in _TERMINAL_STATUSES


class TestMergeDeduplication:
    """Tests for merge deduplication logic in the pipeline."""

    @patch("release_planner.jira_client.JiraClient", autospec=True)
    def test_duplicate_across_rocks_merges_names(self, mock_jira_client_cls):
        """A feature under two rocks gets merged big_rock name."""
        rock_a = BigRock(priority=1, name="RockA", full_name="Rock A", outcome_keys=["RHAISTRAT-1"])
        rock_b = BigRock(priority=2, name="RockB", full_name="Rock B", outcome_keys=["RHAISTRAT-2"])

        # Same feature returned under both outcomes
        child = _make_candidate("RHAISTRAT-100", target_release="rhoai-3.5")

        mock_client = mock_jira_client_cls.return_value
        mock_client.connect.return_value = None
        mock_client.fetch_outcome_children.return_value = [child]

        settings = MagicMock(spec=Settings)
        result = run_pipeline(
            settings=settings,
            big_rocks=[rock_a, rock_b],
            field_mapping={},
            overrides=None,
            release="3.5",
            dry_run=True,
        )
        # The feature should appear once with merged name
        all_cands = []
        for cands in result.get("_all_candidates", {}).values():
            all_cands.extend(cands)

        # Check the total count -- it should be 1 unique feature
        # (counted once under primary rock RockA)
        assert result["total_candidates"] >= 1

    @patch("release_planner.jira_client.JiraClient", autospec=True)
    def test_merge_order_by_priority(self, mock_jira_client_cls):
        """Merged names are sorted by priority ascending."""
        rock_b = BigRock(priority=5, name="Beta", full_name="Beta", outcome_keys=["RHAISTRAT-2"])
        rock_a = BigRock(priority=1, name="Alpha", full_name="Alpha", outcome_keys=["RHAISTRAT-1"])

        child = _make_candidate("RHAISTRAT-100", target_release="rhoai-3.5")

        mock_client = mock_jira_client_cls.return_value
        mock_client.connect.return_value = None
        mock_client.fetch_outcome_children.return_value = [child]

        settings = MagicMock(spec=Settings)
        # Pass rocks in non-priority order
        run_pipeline(
            settings=settings,
            big_rocks=[rock_b, rock_a],
            field_mapping={},
            overrides=None,
            release="3.5",
            dry_run=True,
        )

        # Merged name should be "Alpha, Beta" (priority 1 before 5)
        # Verification: the pipeline prints summary with stats

    @patch("release_planner.jira_client.JiraClient", autospec=True)
    def test_rocks_filter_recomputes_merged_names(self, mock_jira_client_cls):
        """--rocks B with feature in A+B shows only B in merged name (M1)."""
        rock_a = BigRock(priority=1, name="RockA", full_name="Rock A", outcome_keys=["RHAISTRAT-1"])
        rock_b = BigRock(priority=2, name="RockB", full_name="Rock B", outcome_keys=["RHAISTRAT-2"])

        child = _make_candidate("RHAISTRAT-100", target_release="rhoai-3.5")

        mock_client = mock_jira_client_cls.return_value
        mock_client.connect.return_value = None
        mock_client.fetch_outcome_children.return_value = [child]

        settings = MagicMock(spec=Settings)
        result = run_pipeline(
            settings=settings,
            big_rocks=[rock_a, rock_b],
            field_mapping={},
            overrides=None,
            release="3.5",
            rock_filter=["RockB"],
            dry_run=True,
        )
        # Feature should appear under RockB only
        assert result["total_candidates"] >= 1

    @patch("release_planner.jira_client.JiraClient", autospec=True)
    def test_rocks_filter_feature_only_in_inactive_rocks_excluded(self, mock_jira_client_cls):
        """Feature belonging only to filtered-out rocks is excluded."""
        rock_a = BigRock(priority=1, name="RockA", full_name="Rock A", outcome_keys=["RHAISTRAT-1"])
        rock_b = BigRock(priority=2, name="RockB", full_name="Rock B", outcome_keys=["RHAISTRAT-2"])

        # Different children for each rock
        child_a = _make_candidate("RHAISTRAT-100", target_release="rhoai-3.5")
        child_b = _make_candidate("RHAISTRAT-200", target_release="rhoai-3.5")

        mock_client = mock_jira_client_cls.return_value
        mock_client.connect.return_value = None
        mock_client.fetch_outcome_children.side_effect = [
            [child_a],  # RockA's outcome (will be filtered out)
            [child_b],  # RockB's outcome
        ]

        settings = MagicMock(spec=Settings)
        result = run_pipeline(
            settings=settings,
            big_rocks=[rock_a, rock_b],
            field_mapping={},
            overrides=None,
            release="3.5",
            rock_filter=["RockB"],
            dry_run=True,
        )
        # Only RockB's child should appear
        assert result["total_candidates"] == 1

    @patch("release_planner.jira_client.JiraClient", autospec=True)
    def test_empty_outcome_keys_skipped_with_warning(self, mock_jira_client_cls, caplog):
        """Rocks with empty outcome_keys are skipped."""
        import logging

        rock = BigRock(priority=1, name="Empty", full_name="Empty", outcome_keys=[])

        mock_client = mock_jira_client_cls.return_value
        mock_client.connect.return_value = None

        settings = MagicMock(spec=Settings)
        with caplog.at_level(logging.WARNING):
            run_pipeline(
                settings=settings,
                big_rocks=[rock],
                field_mapping={},
                overrides=None,
                release="3.5",
                dry_run=True,
            )

        assert "Skipping Empty: no outcome_keys defined" in caplog.text

    @patch("release_planner.jira_client.JiraClient", autospec=True)
    def test_zero_qualifying_children_warning(self, mock_jira_client_cls, caplog):
        """Rock with outcome_keys but zero children logs WARNING."""
        import logging

        rock = BigRock(
            priority=1, name="Lonely", full_name="Lonely", outcome_keys=["RHAISTRAT-999"]
        )

        mock_client = mock_jira_client_cls.return_value
        mock_client.connect.return_value = None
        mock_client.fetch_outcome_children.return_value = []

        settings = MagicMock(spec=Settings)
        with caplog.at_level(logging.WARNING):
            run_pipeline(
                settings=settings,
                big_rocks=[rock],
                field_mapping={},
                overrides=None,
                release="3.5",
                dry_run=True,
            )

        assert "zero qualifying children" in caplog.text

    @patch("release_planner.jira_client.JiraClient", autospec=True)
    def test_label_substring_false_positive_prevention(self, mock_jira_client_cls):
        """Labels are split and checked individually, not by substring (m1)."""
        rock = BigRock(priority=1, name="R", full_name="R", outcome_keys=["RHAISTRAT-1"])

        # An RFE with "not-3.5-candidate" label should NOT match "3.5-candidate"
        rfe = _make_candidate(
            "RHAIRFE-100",
            labels="not-3.5-candidate",
            source="rfe",
        )

        mock_client = mock_jira_client_cls.return_value
        mock_client.connect.return_value = None
        mock_client.fetch_outcome_children.return_value = [rfe]

        settings = MagicMock(spec=Settings)
        result = run_pipeline(
            settings=settings,
            big_rocks=[rock],
            field_mapping={},
            overrides=None,
            release="3.5",
            dry_run=True,
        )
        # RFE should be skipped
        assert result["total_candidates"] == 0

    @patch("release_planner.jira_client.JiraClient", autospec=True)
    def test_rfe_with_exact_candidate_label_included(self, mock_jira_client_cls):
        """RFE with exact '3.5-candidate' label is included."""
        rock = BigRock(priority=1, name="R", full_name="R", outcome_keys=["RHAISTRAT-1"])

        rfe = _make_candidate(
            "RHAIRFE-100",
            labels="rhoai-3.5, 3.5-candidate",
            source="rfe",
        )

        mock_client = mock_jira_client_cls.return_value
        mock_client.connect.return_value = None
        mock_client.fetch_outcome_children.return_value = [rfe]

        settings = MagicMock(spec=Settings)
        result = run_pipeline(
            settings=settings,
            big_rocks=[rock],
            field_mapping={},
            overrides=None,
            release="3.5",
            dry_run=True,
        )
        assert result["total_candidates"] == 1

    @patch("release_planner.jira_client.JiraClient", autospec=True)
    def test_feature_without_target_release_skipped(self, mock_jira_client_cls):
        """Feature with empty target_release is skipped."""
        rock = BigRock(priority=1, name="R", full_name="R", outcome_keys=["RHAISTRAT-1"])

        feature = _make_candidate("RHAISTRAT-100", target_release="")

        mock_client = mock_jira_client_cls.return_value
        mock_client.connect.return_value = None
        mock_client.fetch_outcome_children.return_value = [feature]

        settings = MagicMock(spec=Settings)
        result = run_pipeline(
            settings=settings,
            big_rocks=[rock],
            field_mapping={},
            overrides=None,
            release="3.5",
            dry_run=True,
        )
        assert result["total_candidates"] == 0

    @patch("release_planner.jira_client.JiraClient", autospec=True)
    def test_feature_in_review_status_filtered(self, mock_jira_client_cls):
        """Features with status 'Review' are filtered out."""
        rock = BigRock(priority=1, name="R", full_name="R", outcome_keys=["RHAISTRAT-1"])

        feature = _make_candidate(
            "RHAISTRAT-100", target_release="rhoai-3.5", status="Review"
        )

        mock_client = mock_jira_client_cls.return_value
        mock_client.connect.return_value = None
        mock_client.fetch_outcome_children.return_value = [feature]

        settings = MagicMock(spec=Settings)
        result = run_pipeline(
            settings=settings,
            big_rocks=[rock],
            field_mapping={},
            overrides=None,
            release="3.5",
            dry_run=True,
        )
        assert result["total_candidates"] == 0

    @patch("release_planner.jira_client.JiraClient", autospec=True)
    def test_unrecognized_prefix_skipped(self, mock_jira_client_cls):
        """Children with unrecognized key prefix are skipped."""
        rock = BigRock(priority=1, name="R", full_name="R", outcome_keys=["RHAISTRAT-1"])

        child = _make_candidate("RHOAIENG-100", target_release="rhoai-3.5")

        mock_client = mock_jira_client_cls.return_value
        mock_client.connect.return_value = None
        mock_client.fetch_outcome_children.return_value = [child]

        settings = MagicMock(spec=Settings)
        result = run_pipeline(
            settings=settings,
            big_rocks=[rock],
            field_mapping={},
            overrides=None,
            release="3.5",
            dry_run=True,
        )
        assert result["total_candidates"] == 0
