"""Shared constants: column definitions, style constants, defaults, rate limiting."""

from enum import StrEnum


class BigRockColumn(StrEnum):
    """Column headers for the Big Rocks worksheet."""

    PILLAR = "Pillar"
    PRIORITY = "Priority"
    BIG_ROCK = "Big Rock"
    STATE = "State"
    OWNER = "Owner"
    NOTES = "Notes"


# Ordered list of big rock column headers (for worksheet generation)
BIG_ROCK_COLUMNS: list[str] = [col.value for col in BigRockColumn]

# Feature tab columns (Engineering Commitments) -- RHAISTRAT issues only
FEATURE_COLUMNS: list[str] = [
    "Big Rock",
    "Feature",
    "Issue status",
    "Priority",
    "DP/TP/GA",
    "Title",
    "Component[s]",
    "Target Release",
    "PM",
    "Delivery Owner",
    "RFE",
    "Comments",
]

# RFE tab columns -- RHAIRFE issues only
RFE_COLUMNS: list[str] = [
    "Big Rock",
    "RFE",
    "RFE Status",
    "Priority",
    "Title",
    "Component[s]",
    "PM",
    "Labels",
]

# Column widths in character units for the Feature tab (ExcelWriter)
FEATURE_COLUMN_WIDTHS_CHARS: dict[str, float] = {
    "Big Rock": 17.63,
    "Feature": 15.0,
    "Issue status": 12.5,
    "Priority": 12.13,
    "DP/TP/GA": 8.0,
    "Title": 21.38,
    "Component[s]": 21.25,
    "Target Release": 15.38,
    "PM": 11.0,
    "Delivery Owner": 14.13,
    "RFE": 15.0,
    "Comments": 38.25,
}

# Column widths in character units for the RFE tab (ExcelWriter)
RFE_COLUMN_WIDTHS_CHARS: dict[str, float] = {
    "Big Rock": 17.63,
    "RFE": 15.0,
    "RFE Status": 13.0,
    "Priority": 12.13,
    "Title": 21.38,
    "Component[s]": 21.25,
    "PM": 11.0,
    "Labels": 38.25,
}

# Column widths in pixels for the Feature tab (SheetsWriter)
FEATURE_COLUMN_WIDTHS: dict[str, int] = {
    "Big Rock": 132,
    "Feature": 98,
    "Issue status": 94,
    "Priority": 91,
    "DP/TP/GA": 60,
    "Title": 160,
    "Component[s]": 159,
    "Target Release": 115,
    "PM": 83,
    "Delivery Owner": 106,
    "RFE": 98,
    "Comments": 287,
}

# Column widths in pixels for the RFE tab (SheetsWriter)
RFE_COLUMN_WIDTHS: dict[str, int] = {
    "Big Rock": 132,
    "RFE": 98,
    "RFE Status": 98,
    "Priority": 91,
    "Title": 160,
    "Component[s]": 159,
    "PM": 83,
    "Labels": 287,
}

# Column widths in pixels for the Big Rocks worksheet (used by SheetsWriter)
BIG_ROCK_COLUMN_WIDTHS: dict[str, int] = {
    BigRockColumn.PILLAR: 146,
    BigRockColumn.PRIORITY: 86,
    BigRockColumn.BIG_ROCK: 152,
    BigRockColumn.STATE: 70,
    BigRockColumn.OWNER: 133,
    BigRockColumn.NOTES: 346,
}

# Column widths in character units for the Big Rocks worksheet (used by ExcelWriter)
# Values taken from the reference "Summit Big Rocks" sheet.
BIG_ROCK_COLUMN_WIDTHS_CHARS: dict[str, float] = {
    BigRockColumn.PILLAR: 19.5,
    BigRockColumn.PRIORITY: 11.5,
    BigRockColumn.BIG_ROCK: 20.25,
    BigRockColumn.STATE: 9.38,
    BigRockColumn.OWNER: 17.75,
    BigRockColumn.NOTES: 46.13,
}

# Data validation dropdown values for Excel output
VALIDATION_ISSUE_STATUS: list[str] = [
    "New",
    "Refinement",
    "In Progress",
    "Review",
    "Pending Release",
]
VALIDATION_PRIORITY: list[str] = [
    "Blocker",
    "Critical",
    "Major",
    "Normal",
    "Minor",
    "Undefined",
]
VALIDATION_RFE_STATUS: list[str] = [
    "New",
    "Stakeholder Review",
    "In Progress",
    "Approved",
    "Rejection Pending",
]

# Jira defaults
JIRA_SERVER_DEFAULT = "https://issues.redhat.com"
JIRA_BROWSE_URL = "https://redhat.atlassian.net/browse"
JIRA_MAX_RESULTS_PER_QUERY = 500
JIRA_REQUEST_TIMEOUT = 30
JIRA_RETRY_COUNT = 3
JIRA_QUERY_DELAY_DEFAULT = 1.0  # seconds between API calls

# Google Sheets styling (RGB float values 0.0-1.0 for Sheets API)
HEADER_BG_COLOR = {"red": 0.12, "green": 0.31, "blue": 0.47}  # #1F4E79
HEADER_FONT_COLOR = {"red": 1.0, "green": 1.0, "blue": 1.0}  # white
STATUS_DONE_COLOR = {"red": 0.78, "green": 0.94, "blue": 0.81}  # #C6EFCE
STATUS_IN_PROGRESS_COLOR = {"red": 1.0, "green": 0.92, "blue": 0.61}  # #FFEB9C
PRIORITY_CRITICAL_COLOR = {"red": 1.0, "green": 0.0, "blue": 0.0}  # red

# Google Sheets API rate limits
SHEETS_API_BATCH_SIZE = 1000  # max rows per update call
