"""Shared constants: column enums, style constants, defaults, rate limiting."""

from enum import StrEnum


class CandidateColumn(StrEnum):
    """Column headers for the {release} Candidates worksheet, in order."""

    BIG_ROCK = "Big Rock"
    RANKING = "1-n Ranking"
    ISSUE_KEY = "Issue key"
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
    COMPONENT = "Component"
    OUTCOME = "Outcome"
    STATE = "State"
    DESCRIPTION = "Description"
    OWNER = "Owner"
    NOTES = "Notes"


# Ordered list of candidate column headers (for worksheet generation)
CANDIDATE_COLUMNS: list[str] = [col.value for col in CandidateColumn]

# Ordered list of big rock column headers (for worksheet generation)
BIG_ROCK_COLUMNS: list[str] = [col.value for col in BigRockColumn]

# Column widths in pixels for the Candidates worksheet
CANDIDATE_COLUMN_WIDTHS: dict[str, int] = {
    CandidateColumn.BIG_ROCK: 150,
    CandidateColumn.RANKING: 75,
    CandidateColumn.ISSUE_KEY: 135,
    CandidateColumn.ISSUE_STATUS: 110,
    CandidateColumn.PRIORITY: 90,
    CandidateColumn.PHASE: 75,
    CandidateColumn.TITLE: 450,
    CandidateColumn.TEAM: 150,
    CandidateColumn.COMPONENTS: 225,
    CandidateColumn.TARGET_RELEASE: 110,
    CandidateColumn.RFE: 135,
    CandidateColumn.RFE_STATUS: 110,
    CandidateColumn.PM: 150,
    CandidateColumn.ARCHITECT: 150,
    CandidateColumn.DELIVERY_OWNER: 150,
    CandidateColumn.RISK_FLAG: 90,
    CandidateColumn.CHANGE_LOG: 225,
    CandidateColumn.REFINEMENT_COMPLETE: 135,
    CandidateColumn.REFINEMENT_NOTES: 225,
    CandidateColumn.COMMENTS: 300,
    CandidateColumn.RICE_SCORE: 90,
}

# Column widths in pixels for the Big Rocks worksheet
BIG_ROCK_COLUMN_WIDTHS: dict[str, int] = {
    BigRockColumn.PILLAR: 150,
    BigRockColumn.PRIORITY: 75,
    BigRockColumn.COMPONENT: 260,
    BigRockColumn.OUTCOME: 300,
    BigRockColumn.STATE: 150,
    BigRockColumn.DESCRIPTION: 375,
    BigRockColumn.OWNER: 150,
    BigRockColumn.NOTES: 300,
}

# Jira defaults
JIRA_SERVER_DEFAULT = "https://issues.redhat.com"
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
