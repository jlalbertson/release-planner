"""Shared fixtures: mock Jira responses, sample configs, mock gspread client."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from release_planner.models import BigRock, Candidate, OverrideSet

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


@pytest.fixture
def sample_jira_response() -> list[dict]:
    """Load the sample Jira response fixture."""
    with open(FIXTURES_DIR / "sample_jira_response.json") as f:
        return json.load(f)


@pytest.fixture
def sample_big_rock() -> BigRock:
    """A sample BigRock for testing."""
    return BigRock(
        priority=1,
        name="MaaS",
        full_name="MaaS (continue from 3.4)",
        pillar="Inference",
        state="continue from 3.4",
        components=["Model as a Service", "MaaS", "AI Core Dashboard"],
        jql=(
            "project in (RHAISTRAT, RHAIRFE, AIPCC, KONFLUX, RHOAIENG, PSX) "
            'AND component in ("Model as a Service", "MaaS", "AI Core Dashboard") '
            "ORDER BY priority ASC, key ASC"
        ),
        rfe_jql=(
            "project = RHAIRFE "
            'AND component in ("Model as a Service", "MaaS", "AI Core Dashboard") '
            "ORDER BY priority ASC, key ASC"
        ),
        exclude_keywords=[],
    )


@pytest.fixture
def sample_big_rock_with_exclusions() -> BigRock:
    """A BigRock with exclude_keywords for testing negative filtering."""
    return BigRock(
        priority=6,
        name="Tool Calling Support",
        full_name="Tool Calling Support (new for 3.5)",
        pillar="Inference",
        state="new for 3.5",
        components=["AI Core Platform", "AI Platform DevOps", "llm-d", "vLLM Runtime"],
        jql=(
            "project in (RHAISTRAT, RHAIRFE, AIPCC, KONFLUX, RHOAIENG, PSX) "
            'AND component in ("AI Core Platform", "AI Platform DevOps", "llm-d", "vLLM Runtime") '
            'AND (summary ~ "tool call*" OR labels = "tool-calling") '
            "ORDER BY priority ASC, key ASC"
        ),
        rfe_jql=(
            "project = RHAIRFE "
            'AND component in ("AI Core Platform", "AI Platform DevOps", "llm-d", "vLLM Runtime") '
            'AND (summary ~ "tool call*" OR labels = "tool-calling") '
            "ORDER BY priority ASC, key ASC"
        ),
        exclude_keywords=["multimodal", "multitenan"],
    )


@pytest.fixture
def sample_candidates() -> list[Candidate]:
    """Sample list of Candidates for testing."""
    return [
        Candidate(
            big_rock="MaaS",
            issue_key="RHOAIENG-12345",
            status="In Progress",
            priority="Major",
            summary="Implement model serving autoscaling",
            components="Model as a Service, AI Core Dashboard",
            target_release="RHOAI 3.5",
            rfe="RHAIRFE-100",
            rfe_status="Approved",
            source_pass="committed",
        ),
        Candidate(
            big_rock="MaaS",
            issue_key="RHOAIENG-12346",
            status="New",
            priority="Critical",
            summary="Dashboard latency improvements",
            components="AI Core Dashboard",
            source_pass="candidate",
        ),
        Candidate(
            big_rock="MaaS",
            issue_key="RHAIRFE-200",
            status="New",
            priority="Major",
            summary="RFE: Support multi-model deployments",
            components="MaaS",
            source="rfe",
            source_pass="rfe",
        ),
    ]


@pytest.fixture
def sample_override_set() -> OverrideSet:
    """Sample OverrideSet for testing."""
    return OverrideSet(
        overrides={
            "RHOAIENG-12345": {
                "pm": "Jane Doe",
                "architect": "John Smith",
                "team": "Platform",
                "ranking": 1,
            },
            "MANUAL-001": {
                "big_rock": "MaaS",
                "summary": "External model catalog GA readiness",
                "priority": "Major",
                "phase": "GA",
                "pm": "Jane Doe",
            },
        }
    )


@pytest.fixture
def config_dir() -> str:
    """Path to the project's config directory."""
    return str(CONFIG_DIR)


def _make_mock_issue(issue_data: dict) -> Any:
    """Convert a dict from sample_jira_response.json to a mock Jira issue object.

    Returns a SimpleNamespace tree that mimics the jira library's issue objects.
    """
    fields_data = issue_data.get("fields", {})

    # Build components
    components = [SimpleNamespace(name=c["name"]) for c in fields_data.get("components", [])]

    # Build fixVersions
    fix_versions = [SimpleNamespace(name=fv["name"]) for fv in fields_data.get("fixVersions", [])]

    # Build status
    status = None
    if "status" in fields_data and fields_data["status"]:
        status = SimpleNamespace(name=fields_data["status"]["name"])

    # Build priority
    priority = None
    if "priority" in fields_data and fields_data["priority"]:
        priority = SimpleNamespace(name=fields_data["priority"]["name"])

    # Build issuelinks
    issuelinks = []
    for link_data in fields_data.get("issuelinks", []):
        link_type = SimpleNamespace(
            inward=link_data["type"]["inward"],
            outward=link_data["type"]["outward"],
        )
        link = SimpleNamespace(type=link_type)

        if "inwardIssue" in link_data:
            inward = link_data["inwardIssue"]
            inward_status = None
            if "fields" in inward and "status" in inward["fields"]:
                inward_status = SimpleNamespace(name=inward["fields"]["status"]["name"])
            link.inwardIssue = SimpleNamespace(
                key=inward["key"],
                fields=SimpleNamespace(status=inward_status),
            )

        if "outwardIssue" in link_data:
            outward = link_data["outwardIssue"]
            outward_status = None
            if "fields" in outward and "status" in outward["fields"]:
                outward_status = SimpleNamespace(name=outward["fields"]["status"]["name"])
            link.outwardIssue = SimpleNamespace(
                key=outward["key"],
                fields=SimpleNamespace(status=outward_status),
            )

        issuelinks.append(link)

    fields = SimpleNamespace(
        summary=fields_data.get("summary", ""),
        status=status,
        priority=priority,
        components=components,
        fixVersions=fix_versions,
        issuelinks=issuelinks,
    )

    return SimpleNamespace(
        id=issue_data["id"],
        key=issue_data["key"],
        fields=fields,
    )


@pytest.fixture
def mock_jira_issues(sample_jira_response) -> list[Any]:
    """Convert sample_jira_response to mock Jira issue objects."""
    return [_make_mock_issue(issue) for issue in sample_jira_response]


@pytest.fixture
def mock_gspread_client():
    """Create a mock gspread client for testing SheetsWriter."""
    mock_gc = MagicMock()
    mock_spreadsheet = MagicMock()
    mock_spreadsheet.url = "https://docs.google.com/spreadsheets/d/test-id/edit"

    # Mock worksheets
    mock_features_ws = MagicMock()
    mock_features_ws.id = 0
    mock_features_ws.title = "Engineering Commitments 3.5"

    mock_rfes_ws = MagicMock()
    mock_rfes_ws.id = 1
    mock_rfes_ws.title = "RFEs 3.5"

    mock_big_rocks_ws = MagicMock()
    mock_big_rocks_ws.id = 2
    mock_big_rocks_ws.title = "Summit Big Rocks"

    mock_spreadsheet.worksheets.return_value = [
        mock_features_ws, mock_rfes_ws, mock_big_rocks_ws
    ]

    def worksheet_side_effect(name):
        if "Engineering Commitments" in name:
            return mock_features_ws
        elif "RFEs" in name:
            return mock_rfes_ws
        elif name == "Summit Big Rocks":
            return mock_big_rocks_ws
        raise Exception(f"Unexpected worksheet name: {name}")

    mock_spreadsheet.worksheet.side_effect = worksheet_side_effect

    mock_gc.open_by_key.return_value = mock_spreadsheet
    mock_gc.create.return_value = mock_spreadsheet

    return mock_gc, mock_spreadsheet, mock_features_ws, mock_rfes_ws, mock_big_rocks_ws
