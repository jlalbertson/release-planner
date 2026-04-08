"""Tests for importer.py: spreadsheet import, column detection, key extraction."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import yaml

from release_planner.importer import SpreadsheetImporter


class TestSpreadsheetImporter:
    """Tests for SpreadsheetImporter."""

    @pytest.fixture
    def mock_workbook(self):
        """Create a mock openpyxl workbook."""
        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_ws.title = "3.5 Candidates"

        # Header row + 3 data rows
        mock_ws.iter_rows.return_value = [
            # Header
            (
                "Big Rock",
                "1-n Ranking",
                "Issue key",
                "Issue status",
                "Priority",
                "DP/TP/GA",
                "Title",
                "Team",
                "Component[s]",
                "Target Release",
                "RFE",
                "RFE Status",
                "PM",
                "Architect",
                "Delivery Owner",
                "Risk Flag",
            ),
            # Row with issue key
            (
                "MaaS",
                1,
                "RHOAIENG-12345",
                "In Progress",
                "Major",
                "GA",
                "Implement autoscaling",
                "Platform",
                "Model as a Service",
                "RHOAI 3.5",
                "RHAIRFE-100",
                "Approved",
                "Jane Doe",
                "John Smith",
                "Alice",
                "On Track",
            ),
            # Row with RFE key only
            (
                "MaaS",
                None,
                None,
                "New",
                "Major",
                "EA1",
                "RFE: Multi-model",
                None,
                "MaaS",
                None,
                "RHAIRFE-200",
                "New",
                "Bob",
                None,
                None,
                None,
            ),
            # Row with no keys (will be MANUAL)
            (
                "llm-d",
                None,
                None,
                None,
                "Minor",
                "GA",
                "Manual entry",
                "Inference",
                None,
                None,
                None,
                None,
                "Carol",
                None,
                None,
                None,
            ),
        ]

        mock_wb.sheetnames = ["3.5 Candidates", "Big Rocks"]
        mock_wb.__getitem__ = lambda self, name: mock_ws

        return mock_wb, mock_ws

    def test_import_with_issue_keys(self, tmp_path, mock_workbook):
        mock_wb, mock_ws = mock_workbook
        output_path = str(tmp_path / "overrides.yaml")

        importer = SpreadsheetImporter.__new__(SpreadsheetImporter)
        importer._wb = mock_wb
        importer._sheet_name = None
        importer._ws = mock_ws

        count = importer.import_to_overrides(output_path)

        assert count == 3

        with open(output_path) as f:
            data = yaml.safe_load(f)

        assert "RHOAIENG-12345" in data
        assert data["RHOAIENG-12345"]["pm"] == "Jane Doe"

    def test_import_rfe_only_keys(self, tmp_path, mock_workbook):
        mock_wb, mock_ws = mock_workbook
        output_path = str(tmp_path / "overrides.yaml")

        importer = SpreadsheetImporter.__new__(SpreadsheetImporter)
        importer._wb = mock_wb
        importer._sheet_name = None
        importer._ws = mock_ws

        importer.import_to_overrides(output_path)

        with open(output_path) as f:
            data = yaml.safe_load(f)

        # Row with RFE key but no issue key should use RFE key
        assert "RHAIRFE-200" in data

    def test_import_manual_entries(self, tmp_path, mock_workbook):
        mock_wb, mock_ws = mock_workbook
        output_path = str(tmp_path / "overrides.yaml")

        importer = SpreadsheetImporter.__new__(SpreadsheetImporter)
        importer._wb = mock_wb
        importer._sheet_name = None
        importer._ws = mock_ws

        importer.import_to_overrides(output_path)

        with open(output_path) as f:
            data = yaml.safe_load(f)

        # Row with no keys should generate MANUAL-001
        assert "MANUAL-001" in data
        assert data["MANUAL-001"]["source"] == "manual"


class TestColumnDetection:
    """Tests for SpreadsheetImporter._detect_columns()."""

    def test_standard_headers(self):
        importer = SpreadsheetImporter.__new__(SpreadsheetImporter)
        headers = ["Big Rock", "Issue key", "Priority", "Title", "PM"]
        result = importer._detect_columns(headers)
        assert result["big_rock"] == 0
        assert result["issue_key"] == 1
        assert result["priority"] == 2
        assert result["summary"] == 3
        assert result["pm"] == 4

    def test_case_insensitive(self):
        importer = SpreadsheetImporter.__new__(SpreadsheetImporter)
        headers = ["BIG ROCK", "issue KEY", "PRIORITY"]
        result = importer._detect_columns(headers)
        # Our column aliases are lowercase, this should still work
        # because we normalize to lowercase
        assert "big_rock" in result

    def test_empty_headers_skipped(self):
        importer = SpreadsheetImporter.__new__(SpreadsheetImporter)
        headers = ["", "Issue key", "", "Title"]
        result = importer._detect_columns(headers)
        assert "issue_key" in result
        assert "summary" in result


class TestExtractKey:
    """Tests for SpreadsheetImporter._extract_key()."""

    def test_direct_key(self):
        assert SpreadsheetImporter._extract_key("RHOAIENG-12345") == "RHOAIENG-12345"

    def test_url_format_key(self):
        result = SpreadsheetImporter._extract_key("https://issues.redhat.com/browse/RHOAIENG-12345")
        assert result == "RHOAIENG-12345"

    def test_atlassian_url_format(self):
        result = SpreadsheetImporter._extract_key(
            "https://redhat.atlassian.net/browse/RHAISTRAT-9066"
        )
        assert result == "RHAISTRAT-9066"

    def test_empty_value(self):
        assert SpreadsheetImporter._extract_key("") == ""
        assert SpreadsheetImporter._extract_key(None) == ""

    def test_non_key_text(self):
        assert SpreadsheetImporter._extract_key("not a key") == ""

    def test_numeric_value(self):
        assert SpreadsheetImporter._extract_key(12345) == ""
