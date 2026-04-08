"""Tests for cli.py: CLI commands with mocked dependencies."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from release_planner.cli import main


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
        assert "15 rocks" in result.output

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

    def test_generate_missing_jira_token(self, runner, monkeypatch):
        monkeypatch.delenv("RELEASE_PLANNER_JIRA_TOKEN", raising=False)
        monkeypatch.delenv("JIRA_TOKEN", raising=False)
        monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
        monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)

        result = runner.invoke(main, ["generate", "--dry-run"])
        assert result.exit_code != 0
        assert "RELEASE_PLANNER_JIRA_TOKEN" in result.output

    def test_generate_missing_google_credentials(self, runner, monkeypatch):
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
    def test_generate_with_passes_filter(self, mock_pipeline, runner, monkeypatch, config_dir):
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
                "--passes",
                "1",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        call_kwargs = mock_pipeline.call_args[1]
        assert call_kwargs["passes"] == [1]

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

    def test_discover_fields_missing_token(self, runner, monkeypatch):
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
