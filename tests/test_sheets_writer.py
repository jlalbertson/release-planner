"""Tests for sheets_writer.py: Google Sheets output (mocked gspread)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from release_planner.constants import BIG_ROCK_COLUMNS, CANDIDATE_COLUMNS
from release_planner.models import BigRock
from release_planner.sheets_writer import SheetsWriter


@pytest.fixture
def writer_with_data(sample_big_rock, sample_candidates, mock_gspread_client):
    """Create a SheetsWriter with sample data and mocked gspread."""
    mock_gc, mock_spreadsheet, mock_candidates_ws, mock_big_rocks_ws = mock_gspread_client

    with patch("release_planner.sheets_writer.gspread") as mock_gspread_mod:
        mock_gspread_mod.authorize.return_value = mock_gc
        mock_gspread_mod.exceptions = MagicMock()
        mock_gspread_mod.exceptions.WorksheetNotFound = Exception

        mock_creds = MagicMock()
        writer = SheetsWriter(
            big_rocks=[sample_big_rock],
            candidates={"MaaS": sample_candidates},
            release="3.5",
            credentials=mock_creds,
        )
        # Replace the gc with our mock
        writer._gc = mock_gc

    return writer, mock_gc, mock_spreadsheet, mock_candidates_ws, mock_big_rocks_ws


class TestSheetsWriter:
    """Tests for SheetsWriter."""

    def test_write_opens_spreadsheet_by_id(self, writer_with_data):
        writer, mock_gc, mock_spreadsheet, _, _ = writer_with_data
        writer.write("test-spreadsheet-id")
        mock_gc.open_by_key.assert_called_once_with("test-spreadsheet-id")

    def test_write_returns_url(self, writer_with_data):
        writer, mock_gc, mock_spreadsheet, _, _ = writer_with_data
        url = writer.write("test-id")
        assert "docs.google.com" in url

    def test_create_and_write_creates_spreadsheet(self, writer_with_data):
        writer, mock_gc, mock_spreadsheet, _, _ = writer_with_data
        # Make worksheet() raise for Sheet1 deletion
        mock_spreadsheet.worksheet.side_effect = [
            MagicMock(),  # candidates
            MagicMock(),  # big rocks
            Exception("WorksheetNotFound"),  # Sheet1
        ]
        writer.create_and_write("Test Spreadsheet")
        mock_gc.create.assert_called_once_with("Test Spreadsheet")

    def test_create_and_write_shares_with_emails(self, writer_with_data):
        writer, mock_gc, mock_spreadsheet, _, _ = writer_with_data
        mock_spreadsheet.worksheet.side_effect = [
            MagicMock(),
            MagicMock(),
            Exception("not found"),
        ]
        writer.create_and_write("Test", share_with=["user@redhat.com"])
        mock_spreadsheet.share.assert_called_once_with(
            "user@redhat.com", perm_type="user", role="writer"
        )

    def test_candidates_worksheet_correct_column_count(self, writer_with_data):
        writer, _, mock_spreadsheet, mock_ws, _ = writer_with_data
        mock_spreadsheet.worksheet.return_value = mock_ws
        writer._write_candidates_worksheet(mock_spreadsheet)

        # Verify update was called with rows data
        mock_ws.update.assert_called_once()
        rows = mock_ws.update.call_args[0][0]

        # Header should have 20 columns
        assert len(rows[0]) == len(CANDIDATE_COLUMNS)
        assert len(rows[0]) == 20

    def test_candidates_worksheet_header_order(self, writer_with_data):
        writer, _, mock_spreadsheet, mock_ws, _ = writer_with_data
        mock_spreadsheet.worksheet.return_value = mock_ws
        writer._write_candidates_worksheet(mock_spreadsheet)

        rows = mock_ws.update.call_args[0][0]
        header = rows[0]
        assert header[0] == "Big Rock"
        assert header[1] == "Feature"
        assert header[2] == "Issue status"
        assert header[-1] == "RICE Score"

    def test_candidates_data_rows(self, writer_with_data, sample_candidates):
        writer, _, mock_spreadsheet, mock_ws, _ = writer_with_data
        mock_spreadsheet.worksheet.return_value = mock_ws
        writer._write_candidates_worksheet(mock_spreadsheet)

        rows = mock_ws.update.call_args[0][0]
        # 1 header + 3 candidates
        assert len(rows) == 4

    def test_big_rocks_worksheet_correct_column_count(self, writer_with_data):
        writer, _, mock_spreadsheet, _, mock_ws = writer_with_data
        mock_spreadsheet.worksheet.return_value = mock_ws
        writer._write_big_rocks_worksheet(mock_spreadsheet)

        mock_ws.update.assert_called_once()
        rows = mock_ws.update.call_args[0][0]
        assert len(rows[0]) == len(BIG_ROCK_COLUMNS)
        assert len(rows[0]) == 6

    def test_big_rocks_worksheet_header_order(self, writer_with_data):
        writer, _, mock_spreadsheet, _, mock_ws = writer_with_data
        mock_spreadsheet.worksheet.return_value = mock_ws
        writer._write_big_rocks_worksheet(mock_spreadsheet)

        rows = mock_ws.update.call_args[0][0]
        header = rows[0]
        assert header[0] == "Pillar"
        assert header[1] == "Priority"
        assert header[-1] == "Notes"

    def test_issue_key_hyperlink_formula(self, writer_with_data):
        writer, _, _, _, _ = writer_with_data
        formula = writer._build_hyperlink_formula("RHOAIENG-12345")
        expected = '=HYPERLINK("https://issues.redhat.com/browse/RHOAIENG-12345", "RHOAIENG-12345")'
        assert formula == expected

    def test_empty_hyperlink_formula(self, writer_with_data):
        writer, _, _, _, _ = writer_with_data
        assert writer._build_hyperlink_formula("") == ""

    def test_data_written_via_batch_update(self, writer_with_data):
        """Verify data is written via worksheet.update() (batch), not cell-by-cell."""
        writer, _, mock_spreadsheet, mock_ws, _ = writer_with_data
        mock_spreadsheet.worksheet.return_value = mock_ws
        writer._write_candidates_worksheet(mock_spreadsheet)

        # worksheet.update() should be called once (batch)
        assert mock_ws.update.call_count == 1
        # Should pass value_input_option for HYPERLINK formulas
        _, kwargs = mock_ws.update.call_args
        assert kwargs.get("value_input_option") == "USER_ENTERED"

    def test_formatting_via_batch_update(self, writer_with_data):
        """Verify formatting is applied via spreadsheet.batch_update()."""
        writer, _, mock_spreadsheet, _, _ = writer_with_data
        writer._apply_formatting(mock_spreadsheet)

        mock_spreadsheet.batch_update.assert_called_once()
        batch_body = mock_spreadsheet.batch_update.call_args[0][0]
        assert "requests" in batch_body
        requests = batch_body["requests"]
        assert len(requests) > 0

    def test_empty_rock_handled_gracefully(self):
        """A rock with no candidates should produce no data rows."""
        rock = BigRock(
            priority=1,
            name="Empty",
            full_name="Empty Rock",
            components=["Comp"],
            jql="project = TEST",
        )
        mock_creds = MagicMock()
        with patch("release_planner.sheets_writer.gspread") as mock_gspread:
            mock_gc = MagicMock()
            mock_gspread.authorize.return_value = mock_gc
            writer = SheetsWriter(
                big_rocks=[rock],
                candidates={"Empty": []},
                release="3.5",
                credentials=mock_creds,
            )
            writer._gc = mock_gc

        mock_ws = MagicMock()
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheet.return_value = mock_ws
        writer._write_candidates_worksheet(mock_spreadsheet)

        rows = mock_ws.update.call_args[0][0]
        # Only header, no data rows
        assert len(rows) == 1


class TestLoadCredentials:
    """Tests for SheetsWriter.load_credentials()."""

    def test_load_credentials_from_file(self, tmp_path, monkeypatch):
        creds_file = tmp_path / "creds.json"
        creds_file.write_text('{"type": "service_account", "project_id": "test"}')
        monkeypatch.setenv("GOOGLE_CREDENTIALS_FILE", str(creds_file))
        monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)

        with patch(
            "release_planner.sheets_writer.Credentials.from_service_account_file"
        ) as mock_from_file:
            mock_from_file.return_value = MagicMock()
            SheetsWriter.load_credentials()
            mock_from_file.assert_called_once()

    def test_load_credentials_from_json(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
        monkeypatch.setenv(
            "GOOGLE_CREDENTIALS_JSON",
            '{"type": "service_account", "project_id": "test"}',
        )

        with patch(
            "release_planner.sheets_writer.Credentials.from_service_account_info"
        ) as mock_from_info:
            mock_from_info.return_value = MagicMock()
            SheetsWriter.load_credentials()
            mock_from_info.assert_called_once()

    def test_load_credentials_missing_both_raises(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
        monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)

        with pytest.raises(RuntimeError, match="GOOGLE_CREDENTIALS_FILE"):
            SheetsWriter.load_credentials()

    def test_load_credentials_file_not_found(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CREDENTIALS_FILE", "/nonexistent/creds.json")
        monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)

        with pytest.raises(RuntimeError, match="not found"):
            SheetsWriter.load_credentials()

    def test_load_credentials_invalid_json(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
        monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", "not valid json")

        with pytest.raises(RuntimeError, match="Invalid JSON"):
            SheetsWriter.load_credentials()
