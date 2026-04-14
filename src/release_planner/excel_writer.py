"""Excel (.xlsx) writer: writes candidate and Big Rock data via openpyxl."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from release_planner.constants import (
    BIG_ROCK_COLUMN_WIDTHS,
    BIG_ROCK_COLUMNS,
    CANDIDATE_COLUMN_WIDTHS,
    CANDIDATE_COLUMNS,
)
from release_planner.models import BigRock, Candidate

logger = logging.getLogger(__name__)

# Pixel-to-character width approximate conversion for openpyxl
_PX_TO_CHAR = 7.5


def _px_to_col_width(px: int) -> float:
    """Convert pixel width to openpyxl column width (character units)."""
    return px / _PX_TO_CHAR


# Header styling
_HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFF", bold=True)
_BAND_FILL = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
_STATUS_DONE_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
_STATUS_IN_PROGRESS_FILL = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
_PRIORITY_CRITICAL_FONT = Font(color="FF0000", bold=True)

# Valid Jira issue key pattern
_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")

# Jira browse URL base
JIRA_BROWSE_URL = "https://issues.redhat.com/browse"


class ExcelWriter:
    """Write release planning data to an Excel .xlsx file via openpyxl."""

    def __init__(
        self,
        big_rocks: list[BigRock],
        candidates: dict[str, list[Candidate]],
        release: str,
    ):
        """Initialize the Excel writer.

        Args:
            big_rocks: Ordered list of BigRock definitions.
            candidates: Map of big_rock_name -> list of Candidate, in display order.
            release: Release version string (e.g. "3.5") for worksheet naming.
        """
        self._big_rocks = big_rocks
        self._candidates = candidates
        self._release = release

    def write(self, output_path: str | Path) -> str:
        """Write data to an Excel .xlsx file.

        Args:
            output_path: Path for the output .xlsx file.

        Returns:
            The absolute path to the written file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        wb = Workbook()

        # Create Candidates worksheet (rename the default sheet)
        ws_candidates = wb.active
        ws_candidates.title = f"{self._release} Candidates"
        self._write_candidates_worksheet(ws_candidates)

        # Create Big Rocks worksheet
        ws_big_rocks = wb.create_sheet(title="Big Rocks")
        self._write_big_rocks_worksheet(ws_big_rocks)

        wb.save(str(output_path))
        abs_path = str(output_path.resolve())
        logger.info("Wrote Excel file: %s", abs_path)
        return abs_path

    def _write_candidates_worksheet(self, ws) -> None:
        """Write the '{release} Candidates' worksheet with formatting."""
        # Header row
        ws.append(list(CANDIDATE_COLUMNS))

        # Data rows
        row_count = 0
        for rock in self._big_rocks:
            rock_candidates = self._candidates.get(rock.name, [])
            for candidate in rock_candidates:
                row = self._candidate_to_row(candidate)
                ws.append(row)
                row_count += 1

        # Apply formatting
        self._format_header(ws, len(CANDIDATE_COLUMNS))
        self._set_column_widths(ws, CANDIDATE_COLUMNS, CANDIDATE_COLUMN_WIDTHS)
        self._apply_candidate_conditional_formatting(ws, row_count)
        self._apply_row_banding(ws, row_count, len(CANDIDATE_COLUMNS))
        self._apply_hyperlinks(ws, row_count)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(CANDIDATE_COLUMNS))}{row_count + 1}"

        logger.info("Wrote %d rows to '%s' worksheet", row_count, ws.title)

    def _write_big_rocks_worksheet(self, ws) -> None:
        """Write the 'Big Rocks' worksheet with formatting."""
        # Header row
        ws.append(list(BIG_ROCK_COLUMNS))

        # Data rows
        for rock in self._big_rocks:
            ws.append(
                [
                    rock.pillar,
                    rock.priority,
                    rock.name,
                    rock.state,
                    rock.owner,
                    "",  # Notes left blank for now
                ]
            )

        # Apply formatting
        self._format_header(ws, len(BIG_ROCK_COLUMNS))
        self._set_column_widths(ws, BIG_ROCK_COLUMNS, BIG_ROCK_COLUMN_WIDTHS)
        ws.freeze_panes = "A2"

        logger.info("Wrote %d rows to '%s' worksheet", len(self._big_rocks), ws.title)

    def _candidate_to_row(self, candidate: Candidate) -> list:
        """Convert a Candidate to a row of cell values matching CANDIDATE_COLUMNS order."""
        issue_key_cell = candidate.issue_key
        rfe_cell = candidate.rfe if candidate.rfe else ""

        # Add source_pass info to comments
        comments = candidate.comments
        if candidate.source_pass and candidate.source_pass not in (comments or ""):
            if comments:
                comments = f"{comments} [source: {candidate.source_pass}]"
            else:
                comments = f"[source: {candidate.source_pass}]"

        return [
            candidate.big_rock,
            issue_key_cell,
            candidate.status,
            candidate.priority,
            candidate.phase,
            candidate.summary,
            candidate.team,
            candidate.components,
            candidate.target_release,
            rfe_cell,
            candidate.rfe_status,
            candidate.pm,
            candidate.architect,
            candidate.delivery_owner,
            candidate.risk_flag,
            candidate.change_log,
            candidate.refinement_complete,
            candidate.refinement_notes,
            comments,
            candidate.rice_score if candidate.rice_score is not None else "",
        ]

    def _apply_hyperlinks(self, ws, row_count: int) -> None:
        """Add hyperlinks to issue key and RFE columns after data is written."""
        issue_key_col = CANDIDATE_COLUMNS.index("Issue key") + 1  # 1-based
        rfe_col = CANDIDATE_COLUMNS.index("RFE") + 1

        for row_idx in range(2, row_count + 2):  # skip header
            for col_idx in (issue_key_col, rfe_col):
                cell = ws.cell(row=row_idx, column=col_idx)
                key = cell.value
                if key and isinstance(key, str) and _ISSUE_KEY_RE.match(key):
                    cell.hyperlink = f"{JIRA_BROWSE_URL}/{key}"
                    cell.font = Font(color="0563C1", underline="single")

    @staticmethod
    def _format_header(ws, num_cols: int) -> None:
        """Apply header row formatting: dark background, white bold text."""
        for col_idx in range(1, num_cols + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = _HEADER_FILL
            cell.font = _HEADER_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    @staticmethod
    def _set_column_widths(ws, columns: list[str], widths: dict[str, int]) -> None:
        """Set column widths from the pixel-based width dict."""
        for i, col_name in enumerate(columns):
            px = widths.get(col_name, 100)
            col_letter = get_column_letter(i + 1)
            ws.column_dimensions[col_letter].width = _px_to_col_width(px)

    @staticmethod
    def _apply_candidate_conditional_formatting(ws, row_count: int) -> None:
        """Apply status and priority formatting to data rows."""
        status_col = CANDIDATE_COLUMNS.index("Issue status") + 1
        priority_col = CANDIDATE_COLUMNS.index("Priority") + 1

        for row_idx in range(2, row_count + 2):
            # Status formatting
            status_cell = ws.cell(row=row_idx, column=status_col)
            status_val = status_cell.value
            if status_val in ("Done", "Closed"):
                status_cell.fill = _STATUS_DONE_FILL
            elif status_val == "In Progress":
                status_cell.fill = _STATUS_IN_PROGRESS_FILL

            # Priority formatting
            priority_cell = ws.cell(row=row_idx, column=priority_col)
            priority_val = priority_cell.value
            if priority_val in ("Blocker", "Critical"):
                priority_cell.font = _PRIORITY_CRITICAL_FONT

    @staticmethod
    def _apply_row_banding(ws, row_count: int, num_cols: int) -> None:
        """Apply alternating row banding (light gray on even data rows)."""
        for row_idx in range(2, row_count + 2):
            if row_idx % 2 == 1:  # odd data rows (0-indexed: even rows in sheet)
                for col_idx in range(1, num_cols + 1):
                    cell = ws.cell(row=row_idx, column=col_idx)
                    if not cell.fill or cell.fill == PatternFill():
                        cell.fill = _BAND_FILL
