"""Tests for the Excel (.xlsx) writer."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import load_workbook

from release_planner.constants import BIG_ROCK_COLUMNS, CANDIDATE_COLUMNS
from release_planner.excel_writer import ExcelWriter
from release_planner.models import BigRock, Candidate


@pytest.fixture
def simple_big_rocks() -> list[BigRock]:
    """Two BigRocks for testing."""
    return [
        BigRock(
            priority=1,
            name="MaaS",
            full_name="MaaS (continue from 3.4)",
            pillar="Inference",
            state="continue from 3.4",
            components=["Model as a Service"],
            jql="project = RHAISTRAT",
        ),
        BigRock(
            priority=2,
            name="Gen AI Studio",
            full_name="Gen AI Studio",
            pillar="Agents",
            state="new for 3.5",
            components=["AI Core Dashboard"],
            jql="project = RHAISTRAT",
        ),
    ]


@pytest.fixture
def simple_candidates() -> dict[str, list[Candidate]]:
    """Candidates mapped by rock name."""
    return {
        "MaaS": [
            Candidate(
                big_rock="MaaS",
                issue_key="RHOAIENG-100",
                status="In Progress",
                priority="Major",
                summary="Feature A",
                source_pass="committed",
            ),
            Candidate(
                big_rock="MaaS",
                issue_key="RHOAIENG-101",
                status="Closed",
                priority="Critical",
                summary="Feature B",
                source_pass="candidate",
            ),
        ],
        "Gen AI Studio": [
            Candidate(
                big_rock="Gen AI Studio",
                issue_key="RHOAIENG-200",
                status="New",
                priority="Blocker",
                summary="Feature C",
                rfe="RHAIRFE-50",
                source_pass="rfe",
            ),
        ],
    }


class TestExcelWriter:
    """Test ExcelWriter output."""

    def test_write_creates_file(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        out = tmp_path / "test.xlsx"
        result = writer.write(out)
        assert Path(result).exists()

    def test_write_returns_absolute_path(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        out = tmp_path / "test.xlsx"
        result = writer.write(out)
        assert Path(result).is_absolute()

    def test_creates_parent_directories(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        out = tmp_path / "nested" / "dir" / "test.xlsx"
        result = writer.write(out)
        assert Path(result).exists()

    def test_two_worksheets_created(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        assert len(wb.sheetnames) == 2
        assert "3.5 Candidates" in wb.sheetnames
        assert "Big Rocks" in wb.sheetnames

    def test_candidates_worksheet_release_in_name(
        self, tmp_path, simple_big_rocks, simple_candidates
    ):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "4.0")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        assert "4.0 Candidates" in wb.sheetnames


class TestCandidatesWorksheet:
    """Test the Candidates worksheet content and formatting."""

    def test_correct_column_count(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["3.5 Candidates"]
        header_row = [cell.value for cell in ws[1] if cell.value is not None]
        assert len(header_row) == len(CANDIDATE_COLUMNS)

    def test_correct_header_order(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["3.5 Candidates"]
        headers = [ws.cell(row=1, column=i + 1).value for i in range(len(CANDIDATE_COLUMNS))]
        assert headers == CANDIDATE_COLUMNS

    def test_correct_data_row_count(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["3.5 Candidates"]
        # Header + 3 data rows
        data_rows = [row for row in ws.iter_rows(min_row=2) if row[0].value is not None]
        assert len(data_rows) == 3

    def test_data_values(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["3.5 Candidates"]
        # First data row: Big Rock, Issue key, ...
        assert ws.cell(row=2, column=1).value == "MaaS"
        assert ws.cell(row=2, column=2).value == "RHOAIENG-100"
        assert ws.cell(row=2, column=6).value == "Feature A"

    def test_issue_key_hyperlinks(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["3.5 Candidates"]
        cell = ws.cell(row=2, column=2)  # Issue key column
        assert cell.hyperlink is not None
        assert "RHOAIENG-100" in cell.hyperlink.target

    def test_rfe_hyperlinks(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["3.5 Candidates"]
        rfe_col = CANDIDATE_COLUMNS.index("RFE") + 1
        # Row 4 is the Gen AI Studio candidate with rfe="RHAIRFE-50"
        cell = ws.cell(row=4, column=rfe_col)
        assert cell.hyperlink is not None
        assert "RHAIRFE-50" in cell.hyperlink.target

    def test_frozen_header_row(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["3.5 Candidates"]
        assert ws.freeze_panes == "A2"

    def test_auto_filter(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["3.5 Candidates"]
        assert ws.auto_filter.ref is not None

    def test_header_formatting(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["3.5 Candidates"]
        header_cell = ws.cell(row=1, column=1)
        assert header_cell.font.bold is True

    def test_status_done_formatting(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["3.5 Candidates"]
        status_col = CANDIDATE_COLUMNS.index("Issue status") + 1
        # Row 3 has status "Closed"
        cell = ws.cell(row=3, column=status_col)
        assert cell.fill.start_color.rgb == "00C6EFCE"

    def test_priority_critical_formatting(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["3.5 Candidates"]
        priority_col = CANDIDATE_COLUMNS.index("Priority") + 1
        # Row 3 has priority "Critical"
        cell = ws.cell(row=3, column=priority_col)
        assert cell.font.bold is True

    def test_source_pass_in_comments(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["3.5 Candidates"]
        comments_col = CANDIDATE_COLUMNS.index("Comments") + 1
        cell = ws.cell(row=2, column=comments_col)
        assert "[source: committed]" in str(cell.value)


class TestBigRocksWorksheet:
    """Test the Big Rocks worksheet content."""

    def test_correct_column_count(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Big Rocks"]
        header_row = [cell.value for cell in ws[1] if cell.value is not None]
        assert len(header_row) == len(BIG_ROCK_COLUMNS)

    def test_correct_header_order(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Big Rocks"]
        headers = [ws.cell(row=1, column=i + 1).value for i in range(len(BIG_ROCK_COLUMNS))]
        assert headers == BIG_ROCK_COLUMNS

    def test_correct_data_row_count(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Big Rocks"]
        data_rows = [row for row in ws.iter_rows(min_row=2) if row[0].value is not None]
        assert len(data_rows) == 2

    def test_notes_column_is_blank(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Big Rocks"]
        notes_col = BIG_ROCK_COLUMNS.index("Notes") + 1
        notes = ws.cell(row=2, column=notes_col).value
        assert notes is None or notes == ""

    def test_frozen_header_row(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Big Rocks"]
        assert ws.freeze_panes == "A2"


class TestEmptyRock:
    """Test handling of a rock with no candidates."""

    def test_empty_rock_handled_gracefully(self, tmp_path):
        rocks = [
            BigRock(
                priority=1,
                name="EmptyRock",
                full_name="Empty Rock",
                components=["Nothing"],
                jql="project = NONE",
            ),
        ]
        candidates: dict[str, list[Candidate]] = {"EmptyRock": []}
        writer = ExcelWriter(rocks, candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["3.5 Candidates"]
        # Only header row, no data rows
        data_rows = [row for row in ws.iter_rows(min_row=2) if row[0].value is not None]
        assert len(data_rows) == 0
