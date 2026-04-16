"""Shared constants: column enums, style constants, defaults, rate limiting."""

from enum import StrEnum


class CandidateColumn(StrEnum):
    """Column headers for the {release} Candidates worksheet, in order."""

    BIG_ROCK = "Big Rock"
    ISSUE_KEY = "Feature"
    ISSUE_STATUS = "Issue status"
    PRIORITY = "Priority"
    PHASE = "DP/TP/GA"
    TITLE = "Title"
    TEAM = "Team"
    COMPONENTS = "Component[s]"
    TARGET_RELEASE = "Target Release"
    RFE = "RFE"
    RFE_STATUS = "RFE Status"
    PM = "PM"
    ARCHITECT = "Architect"
    DELIVERY_OWNER = "Delivery Owner"
    RISK_FLAG = "Risk Flag"
    CHANGE_LOG = "Change Log"
    REFINEMENT_COMPLETE = "Refinement complete"
    REFINEMENT_NOTES = "Refinement notes"
    COMMENTS = "Comments"
    RICE_SCORE = "RICE Score"


class BigRockColumn(StrEnum):
    """Column headers for the Big Rocks worksheet."""

    PILLAR = "Pillar"
    PRIORITY = "Priority"
    BIG_ROCK = "Big Rock"
    STATE = "State"
    OWNER = "Owner"
    NOTES = "Notes"


# Ordered list of candidate column headers (for worksheet generation)
CANDIDATE_COLUMNS: list[str] = [col.value for col in CandidateColumn]

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

# Column widths in pixels for the Candidates worksheet (used by SheetsWriter)
CANDIDATE_COLUMN_WIDTHS: dict[str, int] = {
    CandidateColumn.BIG_ROCK: 132,
    CandidateColumn.ISSUE_KEY: 98,
    CandidateColumn.ISSUE_STATUS: 94,
    CandidateColumn.PRIORITY: 91,
    CandidateColumn.PHASE: 60,
    CandidateColumn.TITLE: 160,
    CandidateColumn.TEAM: 128,
    CandidateColumn.COMPONENTS: 159,
    CandidateColumn.TARGET_RELEASE: 115,
    CandidateColumn.RFE: 98,
    CandidateColumn.RFE_STATUS: 98,
    CandidateColumn.PM: 83,
    CandidateColumn.ARCHITECT: 98,
    CandidateColumn.DELIVERY_OWNER: 106,
    CandidateColumn.RISK_FLAG: 113,
    CandidateColumn.CHANGE_LOG: 222,
    CandidateColumn.REFINEMENT_COMPLETE: 81,
    CandidateColumn.REFINEMENT_NOTES: 287,
    CandidateColumn.COMMENTS: 468,
    CandidateColumn.RICE_SCORE: 55,
}

# Column widths in character units for the Candidates worksheet (used by ExcelWriter)
# Values taken from the reference "Engineering Commitments 3.5" sheet.
CANDIDATE_COLUMN_WIDTHS_CHARS: dict[str, float] = {
    CandidateColumn.BIG_ROCK: 17.63,
    CandidateColumn.ISSUE_KEY: 13.0,
    CandidateColumn.ISSUE_STATUS: 12.5,
    CandidateColumn.PRIORITY: 12.13,
    CandidateColumn.PHASE: 8.0,
    CandidateColumn.TITLE: 21.38,
    CandidateColumn.TEAM: 17.0,
    CandidateColumn.COMPONENTS: 21.25,
    CandidateColumn.TARGET_RELEASE: 15.38,
    CandidateColumn.RFE: 13.0,
    CandidateColumn.RFE_STATUS: 13.0,
    CandidateColumn.PM: 11.0,
    CandidateColumn.ARCHITECT: 13.0,
    CandidateColumn.DELIVERY_OWNER: 14.13,
    CandidateColumn.RISK_FLAG: 15.0,
    CandidateColumn.CHANGE_LOG: 29.63,
    CandidateColumn.REFINEMENT_COMPLETE: 10.75,
    CandidateColumn.REFINEMENT_NOTES: 38.25,
    CandidateColumn.COMMENTS: 62.38,
    CandidateColumn.RICE_SCORE: 7.38,
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
VALIDATION_PHASE: list[str] = ["DP", "TP", "GA"]
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
SHEETS_API_QUOTA_DELAY = 1.0  # seconds between API calls if needed
