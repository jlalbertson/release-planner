"""Google Sheets writer: writes Feature, RFE, and Big Rock data via gspread."""

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
    FEATURE_COLUMN_WIDTHS,
    FEATURE_COLUMNS,
    HEADER_BG_COLOR,
    HEADER_FONT_COLOR,
    JIRA_BROWSE_URL,
    PRIORITY_CRITICAL_COLOR,
    RFE_COLUMN_WIDTHS,
    RFE_COLUMNS,
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

    def __init__(
        self,
        big_rocks: list[BigRock],
        candidates: dict[str, list[Candidate]],
        release: str,
        credentials: Credentials,
        per_rock_stats: dict[str, dict[str, int]] | None = None,
        outcome_summaries: dict[str, str] | None = None,
    ):
        """Initialize the Sheets writer.

        Args:
            big_rocks: Ordered list of BigRock definitions.
            candidates: Map of big_rock_name -> list of Candidate, in display order.
            release: Release version string (e.g. "3.5") for worksheet naming.
            credentials: Google service account credentials (already scoped).
            per_rock_stats: Optional dict of rock_name -> {"features": N, "rfes": N}.
            outcome_summaries: Optional dict of outcome_key -> summary (title).
        """
        self._big_rocks = big_rocks
        self._candidates = candidates
        self._release = release
        self._gc = gspread.authorize(credentials)
        self._per_rock_stats = per_rock_stats or {}
        self._outcome_summaries = outcome_summaries or {}

        # Split candidates into features (RHAISTRAT) and RFEs (RHAIRFE)
        self._features: dict[str, list[Candidate]] = {}
        self._rfes: dict[str, list[Candidate]] = {}
        for rock_name, cands in self._candidates.items():
            self._features[rock_name] = [
                c for c in cands if not c.issue_key.startswith("RHAIRFE-")
            ]
            self._rfes[rock_name] = [
                c for c in cands if c.issue_key.startswith("RHAIRFE-")
            ]

    def write(self, spreadsheet_id: str) -> str:
        """Write data to an existing Google Spreadsheet.

        Args:
            spreadsheet_id: Google Sheets spreadsheet ID.

        Returns:
            The spreadsheet URL.
        """
        logger.info("Opening spreadsheet: %s", spreadsheet_id)
        spreadsheet = self._gc.open_by_key(spreadsheet_id)

        self._write_feature_worksheet(spreadsheet)
        self._write_rfe_worksheet(spreadsheet)
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

        self._write_feature_worksheet(spreadsheet)
        self._write_rfe_worksheet(spreadsheet)
        self._write_big_rocks_worksheet(spreadsheet)
        self._apply_formatting(spreadsheet)

        # Remove default Sheet1 if it exists and we created our own sheets
        try:
            default_sheet = spreadsheet.worksheet("Sheet1")
            spreadsheet.del_worksheet(default_sheet)
        except Exception:
            pass

        # Share with specified emails
        if share_with:
            for email in share_with:
                logger.info("Sharing spreadsheet with %s", email)
                spreadsheet.share(email, perm_type="user", role="writer")

        url = spreadsheet.url
        logger.info("Created spreadsheet: %s", url)
        return url

    def _write_feature_worksheet(self, spreadsheet: gspread.Spreadsheet) -> None:
        """Write the 'Proposed Features' worksheet (RHAISTRAT features)."""
        ws_name = "Proposed Features"
        worksheet = self._get_or_create_worksheet(spreadsheet, ws_name)

        rows: list[list[str | int | float | None]] = []
        rows.append(list(FEATURE_COLUMNS))

        for rock in self._big_rocks:
            for candidate in self._features.get(rock.name, []):
                rows.append(self._feature_to_row(candidate))
        # Tier 2 features (no Big Rock association)
        for candidate in self._features.get("", []):
            rows.append(self._feature_to_row(candidate))

        if rows:
            worksheet.clear()
            worksheet.update(rows, value_input_option="USER_ENTERED")
            logger.info("Wrote %d rows to '%s' worksheet", len(rows) - 1, ws_name)

    def _write_rfe_worksheet(self, spreadsheet: gspread.Spreadsheet) -> None:
        """Write the 'Proposed RFEs' worksheet (RHAIRFE issues)."""
        ws_name = "Proposed RFEs"
        worksheet = self._get_or_create_worksheet(spreadsheet, ws_name)

        rows: list[list[str | int | float | None]] = []
        rows.append(list(RFE_COLUMNS))

        for rock in self._big_rocks:
            for candidate in self._rfes.get(rock.name, []):
                rows.append(self._rfe_to_row(candidate))
        # Tier 2 RFEs (no Big Rock association)
        for candidate in self._rfes.get("", []):
            rows.append(self._rfe_to_row(candidate))

        if rows:
            worksheet.clear()
            worksheet.update(rows, value_input_option="USER_ENTERED")
            logger.info("Wrote %d rows to '%s' worksheet", len(rows) - 1, ws_name)

    def _write_big_rocks_worksheet(self, spreadsheet: gspread.Spreadsheet) -> None:
        """Write the 'Big Rocks' worksheet. Clears existing data first."""
        ws_name = "Big Rocks"
        worksheet = self._get_or_create_worksheet(spreadsheet, ws_name)

        rows: list[list[str | int | float | None]] = []
        rows.append(list(BIG_ROCK_COLUMNS))

        for rock in self._big_rocks:
            stats = self._per_rock_stats.get(rock.name, {})
            outcome_formula = ""
            if rock.outcome_keys:
                links = [self._build_hyperlink_formula(k) for k in rock.outcome_keys]
                if len(links) == 1:
                    outcome_formula = links[0]
                else:
                    outcome_formula = "=" + '&", "&'.join(
                        link.lstrip("=") for link in links
                    )
            outcome_desc_parts = [
                self._outcome_summaries.get(k, "") for k in rock.outcome_keys
            ]
            outcome_desc = "; ".join(d for d in outcome_desc_parts if d)
            row: list[str | int | float | None] = [
                rock.pillar,
                rock.priority,
                rock.name,
                outcome_formula,
                outcome_desc,
                rock.state,
                rock.owner,
                stats.get("features", 0),
                stats.get("rfes", 0),
                "",  # Notes left blank for now
            ]
            rows.append(row)

        if rows:
            worksheet.clear()
            worksheet.update(rows, value_input_option="USER_ENTERED")
            logger.info("Wrote %d rows to '%s' worksheet", len(rows) - 1, ws_name)

    def _apply_formatting(self, spreadsheet: gspread.Spreadsheet) -> None:
        """Apply header formatting, conditional formatting, column widths, and frozen rows."""
        requests: list[dict] = []

        features_ws_name = "Proposed Features"
        rfes_ws_name = "Proposed RFEs"
        big_rocks_ws_name = "Big Rocks"

        features_ws_id = None
        rfes_ws_id = None
        big_rocks_ws_id = None

        for ws in spreadsheet.worksheets():
            if ws.title == features_ws_name:
                features_ws_id = ws.id
            elif ws.title == rfes_ws_name:
                rfes_ws_id = ws.id
            elif ws.title == big_rocks_ws_name:
                big_rocks_ws_id = ws.id

        # --- Feature worksheet formatting ---
        if features_ws_id is not None:
            total_features = sum(
                len(self._features.get(r.name, [])) for r in self._big_rocks
            ) + len(self._features.get("", []))
            requests.extend(
                self._worksheet_formatting_requests(
                    ws_id=features_ws_id,
                    columns=FEATURE_COLUMNS,
                    column_widths=FEATURE_COLUMN_WIDTHS,
                    total_rows=1 + total_features,
                    status_col_name="Issue status",
                    priority_col_name="Priority",
                )
            )

        # --- RFE worksheet formatting ---
        if rfes_ws_id is not None:
            total_rfes = sum(
                len(self._rfes.get(r.name, [])) for r in self._big_rocks
            ) + len(self._rfes.get("", []))
            requests.extend(
                self._worksheet_formatting_requests(
                    ws_id=rfes_ws_id,
                    columns=RFE_COLUMNS,
                    column_widths=RFE_COLUMN_WIDTHS,
                    total_rows=1 + total_rfes,
                    status_col_name="RFE Status",
                    priority_col_name="Priority",
                )
            )

        # --- Big Rocks worksheet formatting ---
        if big_rocks_ws_id is not None:
            num_cols_br = len(BIG_ROCK_COLUMNS)

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

    @staticmethod
    def _worksheet_formatting_requests(
        ws_id: int,
        columns: list[str],
        column_widths: dict[str, int],
        total_rows: int,
        status_col_name: str,
        priority_col_name: str,
    ) -> list[dict]:
        """Build Sheets API formatting requests for a data worksheet."""
        requests: list[dict] = []
        num_cols = len(columns)

        # Freeze header row and first 2 columns
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": ws_id,
                        "gridProperties": {
                            "frozenRowCount": 1,
                            "frozenColumnCount": 2,
                        },
                    },
                    "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
                }
            }
        )

        # Header row formatting
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws_id,
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
        for i, col_name in enumerate(columns):
            width = column_widths.get(col_name, 100)
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": ws_id,
                            "dimension": "COLUMNS",
                            "startIndex": i,
                            "endIndex": i + 1,
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize",
                    }
                }
            )

        # Auto-filter
        requests.append(
            {
                "setBasicFilter": {
                    "filter": {
                        "range": {
                            "sheetId": ws_id,
                            "startRowIndex": 0,
                            "endRowIndex": total_rows,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols,
                        }
                    }
                }
            }
        )

        # Status conditional formatting
        if status_col_name in columns:
            status_col_idx = columns.index(status_col_name)

            for status_val, color in [
                ("Closed", STATUS_DONE_COLOR),
                ("Done", STATUS_DONE_COLOR),
                ("In Progress", STATUS_IN_PROGRESS_COLOR),
            ]:
                requests.append(
                    {
                        "addConditionalFormatRule": {
                            "rule": {
                                "ranges": [
                                    {
                                        "sheetId": ws_id,
                                        "startRowIndex": 1,
                                        "startColumnIndex": status_col_idx,
                                        "endColumnIndex": status_col_idx + 1,
                                    }
                                ],
                                "booleanRule": {
                                    "condition": {
                                        "type": "TEXT_EQ",
                                        "values": [{"userEnteredValue": status_val}],
                                    },
                                    "format": {"backgroundColor": color},
                                },
                            },
                            "index": 0,
                        }
                    }
                )

        # Priority conditional formatting
        if priority_col_name in columns:
            priority_col_idx = columns.index(priority_col_name)
            for priority_val in ("Blocker", "Critical"):
                requests.append(
                    {
                        "addConditionalFormatRule": {
                            "rule": {
                                "ranges": [
                                    {
                                        "sheetId": ws_id,
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
                            "sheetId": ws_id,
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

        return requests

    def _feature_to_row(self, candidate: Candidate) -> list[str | int | float | None]:
        """Convert a Candidate to a row matching FEATURE_COLUMNS order."""
        s = self._sanitize_cell
        return [
            s(candidate.big_rock),
            self._build_hyperlink_formula(candidate.issue_key),
            s(candidate.status),
            s(candidate.priority),
            s(candidate.phase),
            s(candidate.summary),
            s(candidate.components),
            s(candidate.target_release),
            s(candidate.fix_version),
            s(candidate.pm),
            s(candidate.delivery_owner),
            self._build_hyperlink_formula(candidate.rfe) if candidate.rfe else "",
            s(candidate.labels),
        ]

    def _rfe_to_row(self, candidate: Candidate) -> list[str | int | float | None]:
        """Convert a Candidate to a row matching RFE_COLUMNS order."""
        s = self._sanitize_cell
        return [
            s(candidate.big_rock),
            self._build_hyperlink_formula(candidate.issue_key),
            s(candidate.status),
            s(candidate.priority),
            s(candidate.summary),
            s(candidate.components),
            s(candidate.pm),
            s(candidate.labels),
        ]

    @staticmethod
    def _sanitize_cell(value: str) -> str:
        """Sanitize a string value to prevent formula injection in Google Sheets."""
        if isinstance(value, str) and value and value[0] in ("=", "+", "-", "@"):
            return f"'{value}"
        return value

    def _build_hyperlink_formula(self, issue_key: str) -> str:
        """Return a =HYPERLINK() formula for a Jira issue key."""
        if not issue_key:
            return ""
        if not self._ISSUE_KEY_RE.match(issue_key):
            logger.warning("Invalid issue key format, skipping hyperlink: %s", issue_key)
            return issue_key
        url = f"{JIRA_BROWSE_URL}/{issue_key}"
        return f'=HYPERLINK("{url}", "{issue_key}")'

    def _get_or_create_worksheet(
        self,
        spreadsheet: gspread.Spreadsheet,
        name: str,
    ) -> gspread.Worksheet:
        """Get an existing worksheet by name, or create a new one."""
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
