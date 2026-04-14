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
        assert "Engineering Commitments 3.5" in wb.sheetnames
        assert "Summit Big Rocks" in wb.sheetnames

    def test_candidates_worksheet_release_in_name(
        self, tmp_path, simple_big_rocks, simple_candidates
    ):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "4.0")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        assert "Engineering Commitments 4.0" in wb.sheetnames


class TestCandidatesWorksheet:
    """Test the Candidates worksheet content and formatting."""

    def test_correct_column_count(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        header_row = [cell.value for cell in ws[1] if cell.value is not None]
        assert len(header_row) == len(CANDIDATE_COLUMNS)

    def test_correct_header_order(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        headers = [ws.cell(row=1, column=i + 1).value for i in range(len(CANDIDATE_COLUMNS))]
        assert headers == CANDIDATE_COLUMNS

    def test_correct_data_row_count(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        # Header + 3 data rows
        data_rows = [row for row in ws.iter_rows(min_row=2) if row[0].value is not None]
        assert len(data_rows) == 3

    def test_data_values(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        # First data row: Big Rock, Issue key, ...
        assert ws.cell(row=2, column=1).value == "MaaS"
        assert ws.cell(row=2, column=2).value == "RHOAIENG-100"
        assert ws.cell(row=2, column=6).value == "Feature A"

    def test_issue_key_hyperlinks(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        cell = ws.cell(row=2, column=2)  # Issue key column
        assert cell.hyperlink is not None
        assert "RHOAIENG-100" in cell.hyperlink.target

    def test_rfe_hyperlinks(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        rfe_col = CANDIDATE_COLUMNS.index("RFE") + 1
        # Row 4 is the Gen AI Studio candidate with rfe="RHAIRFE-50"
        cell = ws.cell(row=4, column=rfe_col)
        assert cell.hyperlink is not None
        assert "RHAIRFE-50" in cell.hyperlink.target

    def test_frozen_header_row(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        assert ws.freeze_panes == "C2"

    def test_auto_filter(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        assert ws.auto_filter.ref is not None

    def test_header_formatting(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        header_cell = ws.cell(row=1, column=1)
        assert header_cell.font.bold is True

    def test_status_done_formatting(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        status_col = CANDIDATE_COLUMNS.index("Issue status") + 1
        # Row 3 has status "Closed"
        cell = ws.cell(row=3, column=status_col)
        assert cell.fill.start_color.rgb == "00C6EFCE"

    def test_priority_critical_formatting(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        priority_col = CANDIDATE_COLUMNS.index("Priority") + 1
        # Row 3 has priority "Critical"
        cell = ws.cell(row=3, column=priority_col)
        assert cell.font.bold is True

    def test_source_pass_in_comments(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        comments_col = CANDIDATE_COLUMNS.index("Comments") + 1
        cell = ws.cell(row=2, column=comments_col)
        assert "[source: committed]" in str(cell.value)


class TestBigRocksWorksheet:
    """Test the Big Rocks worksheet content."""

    def test_correct_column_count(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Summit Big Rocks"]
        header_row = [cell.value for cell in ws[1] if cell.value is not None]
        assert len(header_row) == len(BIG_ROCK_COLUMNS)

    def test_correct_header_order(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Summit Big Rocks"]
        headers = [ws.cell(row=1, column=i + 1).value for i in range(len(BIG_ROCK_COLUMNS))]
        assert headers == BIG_ROCK_COLUMNS

    def test_correct_data_row_count(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Summit Big Rocks"]
        data_rows = [row for row in ws.iter_rows(min_row=2) if row[0].value is not None]
        assert len(data_rows) == 2

    def test_notes_column_is_blank(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Summit Big Rocks"]
        notes_col = BIG_ROCK_COLUMNS.index("Notes") + 1
        notes = ws.cell(row=2, column=notes_col).value
        assert notes is None or notes == ""

    def test_frozen_header_row(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Summit Big Rocks"]
        assert ws.freeze_panes == "A2"


class TestDataValidations:
    """Test data validation dropdowns on the Candidates worksheet."""

    def test_data_validations_present(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        assert len(ws.data_validations.dataValidation) >= 5

    def test_big_rock_validation_values(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        # Find the Big Rock validation (column A)
        big_rock_dv = None
        for dv in ws.data_validations.dataValidation:
            if "A2:" in str(dv.sqref):
                big_rock_dv = dv
                break
        assert big_rock_dv is not None
        assert "MaaS" in big_rock_dv.formula1
        assert "Gen AI Studio" in big_rock_dv.formula1

    def test_issue_status_validation_values(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        status_col = CANDIDATE_COLUMNS.index("Issue status") + 1
        col_letter = chr(ord("A") + status_col - 1)
        status_dv = None
        for dv in ws.data_validations.dataValidation:
            if f"{col_letter}2:" in str(dv.sqref):
                status_dv = dv
                break
        assert status_dv is not None
        assert "In Progress" in status_dv.formula1
        assert "Pending Release" in status_dv.formula1

    def test_priority_validation_values(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        priority_col = CANDIDATE_COLUMNS.index("Priority") + 1
        col_letter = chr(ord("A") + priority_col - 1)
        priority_dv = None
        for dv in ws.data_validations.dataValidation:
            if f"{col_letter}2:" in str(dv.sqref):
                priority_dv = dv
                break
        assert priority_dv is not None
        assert "Blocker" in priority_dv.formula1
        assert "Minor" in priority_dv.formula1

    def test_phase_validation_values(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        phase_col = CANDIDATE_COLUMNS.index("DP/TP/GA") + 1
        col_letter = chr(ord("A") + phase_col - 1)
        phase_dv = None
        for dv in ws.data_validations.dataValidation:
            if f"{col_letter}2:" in str(dv.sqref):
                phase_dv = dv
                break
        assert phase_dv is not None
        assert "DP" in phase_dv.formula1
        assert "GA" in phase_dv.formula1

    def test_rfe_status_validation_values(self, tmp_path, simple_big_rocks, simple_candidates):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        rfe_col = CANDIDATE_COLUMNS.index("RFE Status") + 1
        col_letter = chr(ord("A") + rfe_col - 1)
        rfe_dv = None
        for dv in ws.data_validations.dataValidation:
            if f"{col_letter}2:" in str(dv.sqref):
                rfe_dv = dv
                break
        assert rfe_dv is not None
        assert "Approved" in rfe_dv.formula1
        assert "Rejection Pending" in rfe_dv.formula1

    def test_target_release_validation_when_fix_versions_provided(
        self, tmp_path, simple_big_rocks, simple_candidates
    ):
        fix_versions = ["RHOAI 3.5", "RHOAI-3.5", "RHAIIS-3.5"]
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5", fix_versions=fix_versions)
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        target_col = CANDIDATE_COLUMNS.index("Target Release") + 1
        col_letter = chr(ord("A") + target_col - 1)
        target_dv = None
        for dv in ws.data_validations.dataValidation:
            if f"{col_letter}2:" in str(dv.sqref):
                target_dv = dv
                break
        assert target_dv is not None
        assert "RHOAI 3.5" in target_dv.formula1

    def test_no_target_release_validation_without_fix_versions(
        self, tmp_path, simple_big_rocks, simple_candidates
    ):
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Engineering Commitments 3.5"]
        target_col = CANDIDATE_COLUMNS.index("Target Release") + 1
        col_letter = chr(ord("A") + target_col - 1)
        target_dv = None
        for dv in ws.data_validations.dataValidation:
            if f"{col_letter}2:" in str(dv.sqref):
                target_dv = dv
                break
        assert target_dv is None

    def test_no_validations_on_empty_data(self, tmp_path):
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
        ws = wb["Engineering Commitments 3.5"]
        assert len(ws.data_validations.dataValidation) == 0


class TestPillarMerging:
    """Test Pillar cell merging in the Summit Big Rocks worksheet."""

    @pytest.fixture
    def multi_pillar_rocks(self) -> list[BigRock]:
        """Multiple rocks with shared pillars for merge testing."""
        return [
            BigRock(
                priority=1,
                name="MaaS",
                full_name="MaaS",
                pillar="Inference",
                components=["Comp"],
                jql="project = TEST",
            ),
            BigRock(
                priority=2,
                name="Tool Calling",
                full_name="Tool Calling",
                pillar="Inference",
                components=["Comp"],
                jql="project = TEST",
            ),
            BigRock(
                priority=3,
                name="vLLM",
                full_name="vLLM",
                pillar="Inference",
                components=["Comp"],
                jql="project = TEST",
            ),
            BigRock(
                priority=4,
                name="Gen AI Studio",
                full_name="Gen AI Studio",
                pillar="Agents",
                components=["Comp"],
                jql="project = TEST",
            ),
            BigRock(
                priority=5,
                name="BYO Agent",
                full_name="BYO Agent",
                pillar="Agents",
                components=["Comp"],
                jql="project = TEST",
            ),
            BigRock(
                priority=6,
                name="AutoRAG",
                full_name="AutoRAG",
                pillar="Data",
                components=["Comp"],
                jql="project = TEST",
            ),
        ]

    def test_pillar_cells_are_merged(self, tmp_path, multi_pillar_rocks):
        candidates: dict[str, list[Candidate]] = {}
        writer = ExcelWriter(multi_pillar_rocks, candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Summit Big Rocks"]
        merged = [str(r) for r in ws.merged_cells.ranges]
        # Inference: rows 2-4, Agents: rows 5-6
        assert "A2:A4" in merged
        assert "A5:A6" in merged

    def test_single_pillar_not_merged(self, tmp_path, multi_pillar_rocks):
        candidates: dict[str, list[Candidate]] = {}
        writer = ExcelWriter(multi_pillar_rocks, candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Summit Big Rocks"]
        merged = [str(r) for r in ws.merged_cells.ranges]
        # Data has only 1 row (row 7), should NOT be merged
        assert "A7:A7" not in merged

    def test_merged_cell_alignment(self, tmp_path, multi_pillar_rocks):
        candidates: dict[str, list[Candidate]] = {}
        writer = ExcelWriter(multi_pillar_rocks, candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Summit Big Rocks"]
        # Merged cell should have vertical center alignment
        cell = ws.cell(row=2, column=1)
        assert cell.alignment.vertical == "center"

    def test_no_merge_with_single_rock(self, tmp_path, simple_big_rocks, simple_candidates):
        # simple_big_rocks has 2 rocks with different pillars (Inference, Agents)
        writer = ExcelWriter(simple_big_rocks, simple_candidates, "3.5")
        writer.write(tmp_path / "test.xlsx")
        wb = load_workbook(tmp_path / "test.xlsx")
        ws = wb["Summit Big Rocks"]
        merged = [str(r) for r in ws.merged_cells.ranges]
        assert len(merged) == 0


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
        ws = wb["Engineering Commitments 3.5"]
        # Only header row, no data rows
        data_rows = [row for row in ws.iter_rows(min_row=2) if row[0].value is not None]
        assert len(data_rows) == 0
