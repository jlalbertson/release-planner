"""Google Sheets writer: writes candidate and Big Rock data via gspread."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from release_planner.constants import (
    BIG_ROCK_COLUMN_WIDTHS,
    BIG_ROCK_COLUMNS,
    CANDIDATE_COLUMN_WIDTHS,
    CANDIDATE_COLUMNS,
    HEADER_BG_COLOR,
    HEADER_FONT_COLOR,
    PRIORITY_CRITICAL_COLOR,
    STATUS_DONE_COLOR,
    STATUS_IN_PROGRESS_COLOR,
)
from release_planner.models import BigRock, Candidate

logger = logging.getLogger(__name__)


class SheetsWriter:
    """Write release planning data to Google Sheets via gspread."""

    # Required OAuth scopes for Sheets API
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",  # needed for --create and --share-with
    ]

    # Pattern for valid Jira issue keys
    _ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")

    # Jira browse URL base for hyperlinks
    JIRA_BROWSE_URL = "https://issues.redhat.com/browse"

    def __init__(
        self,
        big_rocks: list[BigRock],
        candidates: dict[str, list[Candidate]],
        release: str,
        credentials: Credentials,
    ):
        """Initialize the Sheets writer.

        Args:
            big_rocks: Ordered list of BigRock definitions.
            candidates: Map of big_rock_name -> list of Candidate, in display order.
            release: Release version string (e.g. "3.5") for worksheet naming.
            credentials: Google service account credentials (already scoped).
        """
        self._big_rocks = big_rocks
        self._candidates = candidates
        self._release = release
        self._gc = gspread.authorize(credentials)

    def write(self, spreadsheet_id: str) -> str:
        """Write data to an existing Google Spreadsheet.

        Args:
            spreadsheet_id: Google Sheets spreadsheet ID.

        Returns:
            The spreadsheet URL.
        """
        logger.info("Opening spreadsheet: %s", spreadsheet_id)
        spreadsheet = self._gc.open_by_key(spreadsheet_id)

        self._write_candidates_worksheet(spreadsheet)
        self._write_big_rocks_worksheet(spreadsheet)
        self._apply_formatting(spreadsheet)

        url = spreadsheet.url
        logger.info("Spreadsheet updated: %s", url)
        return url

    def create_and_write(
        self,
        title: str,
        share_with: list[str] | None = None,
    ) -> str:
        """Create a new Google Spreadsheet, write data, optionally share.

        Args:
            title: Title for the new spreadsheet.
            share_with: List of email addresses to share the spreadsheet with as editors.

        Returns:
            The spreadsheet URL.
        """
        logger.info("Creating new spreadsheet: %s", title)
        spreadsheet = self._gc.create(title)

        self._write_candidates_worksheet(spreadsheet)
        self._write_big_rocks_worksheet(spreadsheet)
        self._apply_formatting(spreadsheet)

        # Remove default Sheet1 if it exists and we created our own sheets
        try:
            default_sheet = spreadsheet.worksheet("Sheet1")
            spreadsheet.del_worksheet(default_sheet)
        except Exception:
            # WorksheetNotFound or any other error -- Sheet1 may not exist
            pass

        # Share with specified emails
        if share_with:
            for email in share_with:
                logger.info("Sharing spreadsheet with %s", email)
                spreadsheet.share(email, perm_type="user", role="writer")

        url = spreadsheet.url
        logger.info("Created spreadsheet: %s", url)
        return url

    def _write_candidates_worksheet(self, spreadsheet: gspread.Spreadsheet) -> None:
        """Write the '{release} Candidates' worksheet. Clears existing data first."""
        ws_name = f"{self._release} Candidates"
        worksheet = self._get_or_create_worksheet(spreadsheet, ws_name)

        # Build all rows: header + data
        rows: list[list[str | int | float | None]] = []
        rows.append(list(CANDIDATE_COLUMNS))

        for rock in self._big_rocks:
            rock_candidates = self._candidates.get(rock.name, [])
            for candidate in rock_candidates:
                row = self._candidate_to_row(candidate)
                rows.append(row)

        # Write all data in a single batch update
        if rows:
            worksheet.clear()
            worksheet.update(rows, value_input_option="USER_ENTERED")
            logger.info("Wrote %d rows to '%s' worksheet", len(rows) - 1, ws_name)

    def _write_big_rocks_worksheet(self, spreadsheet: gspread.Spreadsheet) -> None:
        """Write the 'Big Rocks' worksheet. Clears existing data first."""
        ws_name = "Big Rocks"
        worksheet = self._get_or_create_worksheet(spreadsheet, ws_name)

        # Build all rows: header + data
        rows: list[list[str | int | float | None]] = []
        rows.append(list(BIG_ROCK_COLUMNS))

        for rock in self._big_rocks:
            row: list[str | int | float | None] = [
                rock.pillar,
                rock.priority,
                rock.name,
                rock.state,
                rock.owner,
                "",  # Notes left blank for now
            ]
            rows.append(row)

        # Write all data in a single batch update
        if rows:
            worksheet.clear()
            worksheet.update(rows, value_input_option="USER_ENTERED")
            logger.info("Wrote %d rows to '%s' worksheet", len(rows) - 1, ws_name)

    def _apply_formatting(self, spreadsheet: gspread.Spreadsheet) -> None:
        """Apply header formatting, conditional formatting, column widths, and frozen rows.

        Uses batch_update requests to the Sheets API for efficiency.
        """
        requests: list[dict] = []

        # Get worksheet IDs
        candidates_ws_name = f"{self._release} Candidates"
        big_rocks_ws_name = "Big Rocks"

        candidates_ws_id = None
        big_rocks_ws_id = None

        for ws in spreadsheet.worksheets():
            if ws.title == candidates_ws_name:
                candidates_ws_id = ws.id
            elif ws.title == big_rocks_ws_name:
                big_rocks_ws_id = ws.id

        # --- Candidates worksheet formatting ---
        if candidates_ws_id is not None:
            num_cols = len(CANDIDATE_COLUMNS)

            # Freeze header row
            requests.append(
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": candidates_ws_id,
                            "gridProperties": {"frozenRowCount": 1},
                        },
                        "fields": "gridProperties.frozenRowCount",
                    }
                }
            )

            # Header row formatting: bold, dark background, white text
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": candidates_ws_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": HEADER_BG_COLOR,
                                "textFormat": {
                                    "foregroundColor": HEADER_FONT_COLOR,
                                    "bold": True,
                                },
                            }
                        },
                        "fields": ("userEnteredFormat(backgroundColor,textFormat)"),
                    }
                }
            )

            # Column widths
            for i, col_name in enumerate(CANDIDATE_COLUMNS):
                width = CANDIDATE_COLUMN_WIDTHS.get(col_name, 100)
                requests.append(
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": candidates_ws_id,
                                "dimension": "COLUMNS",
                                "startIndex": i,
                                "endIndex": i + 1,
                            },
                            "properties": {"pixelSize": width},
                            "fields": "pixelSize",
                        }
                    }
                )

            # Auto-filter on all columns
            total_rows = 1 + sum(len(self._candidates.get(r.name, [])) for r in self._big_rocks)
            requests.append(
                {
                    "setBasicFilter": {
                        "filter": {
                            "range": {
                                "sheetId": candidates_ws_id,
                                "startRowIndex": 0,
                                "endRowIndex": total_rows,
                                "startColumnIndex": 0,
                                "endColumnIndex": num_cols,
                            }
                        }
                    }
                }
            )

            # Status-based conditional formatting: Done/Closed = green
            status_col_idx = CANDIDATE_COLUMNS.index("Issue status")
            requests.append(
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": candidates_ws_id,
                                    "startRowIndex": 1,
                                    "startColumnIndex": status_col_idx,
                                    "endColumnIndex": status_col_idx + 1,
                                }
                            ],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": "Closed"}],
                                },
                                "format": {
                                    "backgroundColor": STATUS_DONE_COLOR,
                                },
                            },
                        },
                        "index": 0,
                    }
                }
            )

            # Status: Done = green
            requests.append(
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": candidates_ws_id,
                                    "startRowIndex": 1,
                                    "startColumnIndex": status_col_idx,
                                    "endColumnIndex": status_col_idx + 1,
                                }
                            ],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": "Done"}],
                                },
                                "format": {
                                    "backgroundColor": STATUS_DONE_COLOR,
                                },
                            },
                        },
                        "index": 1,
                    }
                }
            )

            # Status: In Progress = yellow
            requests.append(
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": candidates_ws_id,
                                    "startRowIndex": 1,
                                    "startColumnIndex": status_col_idx,
                                    "endColumnIndex": status_col_idx + 1,
                                }
                            ],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": "In Progress"}],
                                },
                                "format": {
                                    "backgroundColor": STATUS_IN_PROGRESS_COLOR,
                                },
                            },
                        },
                        "index": 2,
                    }
                }
            )

            # Priority: Blocker/Critical = red text
            priority_col_idx = CANDIDATE_COLUMNS.index("Priority")
            for priority_val in ("Blocker", "Critical"):
                requests.append(
                    {
                        "addConditionalFormatRule": {
                            "rule": {
                                "ranges": [
                                    {
                                        "sheetId": candidates_ws_id,
                                        "startRowIndex": 1,
                                        "startColumnIndex": priority_col_idx,
                                        "endColumnIndex": priority_col_idx + 1,
                                    }
                                ],
                                "booleanRule": {
                                    "condition": {
                                        "type": "TEXT_EQ",
                                        "values": [{"userEnteredValue": priority_val}],
                                    },
                                    "format": {
                                        "textFormat": {
                                            "foregroundColor": PRIORITY_CRITICAL_COLOR,
                                            "bold": True,
                                        },
                                    },
                                },
                            },
                            "index": 0,
                        }
                    }
                )

            # Alternating row banding
            requests.append(
                {
                    "addBanding": {
                        "bandedRange": {
                            "range": {
                                "sheetId": candidates_ws_id,
                                "startRowIndex": 0,
                                "endRowIndex": total_rows,
                                "startColumnIndex": 0,
                                "endColumnIndex": num_cols,
                            },
                            "rowProperties": {
                                "headerColor": HEADER_BG_COLOR,
                                "firstBandColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                                "secondBandColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
                            },
                        }
                    }
                }
            )

        # --- Big Rocks worksheet formatting ---
        if big_rocks_ws_id is not None:
            num_cols_br = len(BIG_ROCK_COLUMNS)

            # Freeze header row
            requests.append(
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": big_rocks_ws_id,
                            "gridProperties": {"frozenRowCount": 1},
                        },
                        "fields": "gridProperties.frozenRowCount",
                    }
                }
            )

            # Header row formatting
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": big_rocks_ws_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols_br,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": HEADER_BG_COLOR,
                                "textFormat": {
                                    "foregroundColor": HEADER_FONT_COLOR,
                                    "bold": True,
                                },
                            }
                        },
                        "fields": ("userEnteredFormat(backgroundColor,textFormat)"),
                    }
                }
            )

            # Column widths
            for i, col_name in enumerate(BIG_ROCK_COLUMNS):
                width = BIG_ROCK_COLUMN_WIDTHS.get(col_name, 100)
                requests.append(
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": big_rocks_ws_id,
                                "dimension": "COLUMNS",
                                "startIndex": i,
                                "endIndex": i + 1,
                            },
                            "properties": {"pixelSize": width},
                            "fields": "pixelSize",
                        }
                    }
                )

        # Send all formatting in a single batch_update
        if requests:
            spreadsheet.batch_update({"requests": requests})
            logger.info("Applied formatting (%d requests)", len(requests))

    def _candidate_to_row(self, candidate: Candidate) -> list[str | int | float | None]:
        """Convert a Candidate to a row of cell values matching CANDIDATE_COLUMNS order.

        Issue key and RFE columns use =HYPERLINK() formulas.
        """
        issue_key_cell = self._build_hyperlink_formula(candidate.issue_key)
        rfe_cell = self._build_hyperlink_formula(candidate.rfe) if candidate.rfe else ""

        # Add source_pass info to comments if not already there
        comments = candidate.comments
        if candidate.source_pass and candidate.source_pass not in (comments or ""):
            if comments:
                comments = f"{comments} [source: {candidate.source_pass}]"
            else:
                comments = f"[source: {candidate.source_pass}]"

        s = self._sanitize_cell
        return [
            candidate.big_rock,
            issue_key_cell,
            candidate.status,
            candidate.priority,
            candidate.phase,
            s(candidate.summary),
            s(candidate.team),
            s(candidate.components),
            candidate.target_release,
            rfe_cell,
            candidate.rfe_status,
            s(candidate.pm),
            s(candidate.architect),
            s(candidate.delivery_owner),
            candidate.risk_flag,
            s(candidate.change_log),
            candidate.refinement_complete,
            s(candidate.refinement_notes),
            s(comments),
            candidate.rice_score if candidate.rice_score is not None else "",
        ]

    @staticmethod
    def _sanitize_cell(value: str) -> str:
        """Sanitize a string value to prevent formula injection in Google Sheets.

        Values starting with =, +, -, or @ could be interpreted as formulas
        when written with USER_ENTERED mode. Prefix with a single quote to force
        text interpretation.
        """
        if isinstance(value, str) and value and value[0] in ("=", "+", "-", "@"):
            return f"'{value}"
        return value

    def _build_hyperlink_formula(self, issue_key: str) -> str:
        """Return a =HYPERLINK() formula for a Jira issue key.

        Args:
            issue_key: Jira issue key (e.g. RHOAIENG-12345).

        Returns:
            Google Sheets HYPERLINK formula string, or plain text if key is invalid.
        """
        if not issue_key:
            return ""
        if not self._ISSUE_KEY_RE.match(issue_key):
            logger.warning("Invalid issue key format, skipping hyperlink: %s", issue_key)
            return issue_key
        url = f"{self.JIRA_BROWSE_URL}/{issue_key}"
        return f'=HYPERLINK("{url}", "{issue_key}")'

    def _get_or_create_worksheet(
        self,
        spreadsheet: gspread.Spreadsheet,
        name: str,
    ) -> gspread.Worksheet:
        """Get an existing worksheet by name, or create a new one.

        Args:
            spreadsheet: gspread Spreadsheet object.
            name: Worksheet name.

        Returns:
            gspread Worksheet object.
        """
        try:
            worksheet = spreadsheet.worksheet(name)
            logger.debug("Found existing worksheet: %s", name)
            return worksheet
        except gspread.exceptions.WorksheetNotFound:
            logger.info("Creating new worksheet: %s", name)
            return spreadsheet.add_worksheet(title=name, rows=1000, cols=30)

    @staticmethod
    def load_credentials() -> Credentials:
        """Load Google service account credentials from environment.

        Checks GOOGLE_CREDENTIALS_FILE first, then GOOGLE_CREDENTIALS_JSON.

        Returns:
            Scoped Google service account Credentials.

        Raises:
            RuntimeError: If neither env var is set or credentials are invalid.
        """
        creds_file = os.environ.get("GOOGLE_CREDENTIALS_FILE")
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")

        if creds_file:
            creds_path = Path(creds_file)
            if not creds_path.exists():
                raise RuntimeError(
                    f"Google credentials file not found: {creds_file}. "
                    "Check GOOGLE_CREDENTIALS_FILE env var."
                )
            credentials = Credentials.from_service_account_file(
                str(creds_path),
                scopes=SheetsWriter.SCOPES,
            )
            logger.info("Loaded Google credentials from file: %s", creds_file)
            return credentials

        if creds_json:
            try:
                creds_info = json.loads(creds_json)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Invalid JSON in GOOGLE_CREDENTIALS_JSON: {e}") from e
            credentials = Credentials.from_service_account_info(
                creds_info,
                scopes=SheetsWriter.SCOPES,
            )
            logger.info("Loaded Google credentials from inline JSON")
            return credentials

        raise RuntimeError(
            "GOOGLE_CREDENTIALS_FILE or GOOGLE_CREDENTIALS_JSON must be set. "
            "See the design doc Section 5.5 for setup instructions."
        )
