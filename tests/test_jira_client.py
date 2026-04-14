"""Tests for jira_client.py: three-pass discovery, field mapping, error handling."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from release_planner.jira_client import JiraClient
from release_planner.models import BigRock, Candidate


@pytest.fixture
def jira_client():
    """A JiraClient with mocked connection (no real Jira needed)."""
    client = JiraClient(
        server="https://issues.redhat.com",
        token="test-token",
        field_mapping={
            "rfe_link_type": "is required by",
        },
        query_delay=0.0,  # No delay in tests
    )
    client._jira = MagicMock()
    client._jira.server_info.return_value = {"version": "8.0"}
    client._jira._is_cloud = False  # Route to Server/DC search path
    return client


class TestSearchIssues:
    """Tests for JiraClient.search_issues()."""

    def test_search_returns_results(self, jira_client, mock_jira_issues):
        jira_client._jira.search_issues.return_value = mock_jira_issues[:3]
        results = jira_client.search_issues("project = TEST")
        assert len(results) == 3

    def test_search_empty_results(self, jira_client):
        jira_client._jira.search_issues.return_value = []
        results = jira_client.search_issues("project = EMPTY")
        assert results == []

    def test_search_respects_max_results(self, jira_client, mock_jira_issues):
        jira_client._jira.search_issues.return_value = mock_jira_issues[:2]
        results = jira_client.search_issues("project = TEST", max_results=2)
        assert len(results) == 2

    def test_search_handles_400_error(self, jira_client):
        from jira import JIRAError

        error = JIRAError(status_code=400, text="Invalid JQL")
        error.response = None
        jira_client._jira.search_issues.side_effect = error

        with pytest.raises(RuntimeError, match="Invalid JQL"):
            jira_client.search_issues("bad query")

    def test_search_handles_401_error(self, jira_client):
        from jira import JIRAError

        error = JIRAError(status_code=401, text="Unauthorized")
        error.response = None
        jira_client._jira.search_issues.side_effect = error

        with pytest.raises(RuntimeError, match="authentication failed"):
            jira_client.search_issues("project = TEST")


class TestMapToCandidate:
    """Tests for JiraClient.map_to_candidate()."""

    def test_map_full_issue(self, jira_client, mock_jira_issues):
        issue = mock_jira_issues[0]  # RHOAIENG-12345
        candidate = jira_client.map_to_candidate(issue, "MaaS", "committed")

        assert candidate.issue_key == "RHOAIENG-12345"
        assert candidate.status == "In Progress"
        assert candidate.priority == "Major"
        assert candidate.summary == "Implement model serving autoscaling"
        assert "Model as a Service" in candidate.components
        assert candidate.target_release == "RHOAI 3.5"
        assert candidate.big_rock == "MaaS"
        assert candidate.source_pass == "committed"

    def test_map_minimal_issue(self, jira_client, mock_jira_issues):
        issue = mock_jira_issues[2]  # RHOAIENG-12347 (no components, no fixVersions)
        candidate = jira_client.map_to_candidate(issue, "Test", "candidate")

        assert candidate.issue_key == "RHOAIENG-12347"
        assert candidate.components == ""
        assert candidate.target_release == ""
        assert candidate.source_pass == "candidate"

    def test_map_rfe_issue(self, jira_client, mock_jira_issues):
        issue = mock_jira_issues[3]  # RHAIRFE-200
        candidate = jira_client.map_to_candidate(issue, "MaaS", "rfe")

        assert candidate.issue_key == "RHAIRFE-200"
        assert candidate.source == "rfe"
        assert candidate.source_pass == "rfe"


class TestGetRfeLink:
    """Tests for JiraClient.get_rfe_link()."""

    def test_rfe_link_inward(self, jira_client, mock_jira_issues):
        issue = mock_jira_issues[0]  # RHOAIENG-12345 has inward RFE link
        rfe_key, rfe_status = jira_client.get_rfe_link(issue)
        assert rfe_key == "RHAIRFE-100"
        assert rfe_status == "Approved"

    def test_no_rfe_link(self, jira_client, mock_jira_issues):
        issue = mock_jira_issues[1]  # RHOAIENG-12346 has no links
        rfe_key, rfe_status = jira_client.get_rfe_link(issue)
        assert rfe_key == ""
        assert rfe_status == ""

    def test_no_issuelinks_attribute(self, jira_client):
        issue = SimpleNamespace(
            key="TEST-1",
            fields=SimpleNamespace(issuelinks=None),
        )
        rfe_key, rfe_status = jira_client.get_rfe_link(issue)
        assert rfe_key == ""
        assert rfe_status == ""


class TestApplyExcludeKeywords:
    """Tests for JiraClient._apply_exclude_keywords()."""

    def test_exclude_keywords_filter(self, jira_client):
        candidates = [
            Candidate(big_rock="Test", issue_key="A-1", summary="Tool calling support"),
            Candidate(big_rock="Test", issue_key="A-2", summary="Multimodal inference"),
            Candidate(big_rock="Test", issue_key="A-3", summary="Basic model serving"),
        ]
        filtered = jira_client._apply_exclude_keywords(candidates, ["multimodal"])
        assert len(filtered) == 2
        keys = [c.issue_key for c in filtered]
        assert "A-2" not in keys
        assert "A-1" in keys
        assert "A-3" in keys

    def test_exclude_keywords_case_insensitive(self, jira_client):
        candidates = [
            Candidate(big_rock="Test", issue_key="A-1", summary="MULTIMODAL Support"),
        ]
        filtered = jira_client._apply_exclude_keywords(candidates, ["multimodal"])
        assert len(filtered) == 0

    def test_exclude_keywords_empty(self, jira_client):
        candidates = [
            Candidate(big_rock="Test", issue_key="A-1", summary="Some feature"),
        ]
        filtered = jira_client._apply_exclude_keywords(candidates, [])
        assert len(filtered) == 1


class TestFetchCandidatesForRock:
    """Tests for JiraClient.fetch_candidates_for_rock()."""

    def test_three_pass_discovery(self, jira_client, mock_jira_issues):
        # Pass 1 returns issue 0 (has fixVersion)
        # Pass 2 returns issues 0, 1 (0 already seen)
        # Pass 3 returns issue 3 (RFE)
        call_count = 0

        def mock_search(jql, **kwargs):
            nonlocal call_count
            call_count += 1
            if "fixVersion IN" in jql:
                return [mock_jira_issues[0]]  # Pass 1: committed
            elif "project = RHAIRFE" in jql:
                return [mock_jira_issues[3]]  # Pass 3: RFE
            else:
                return [mock_jira_issues[0], mock_jira_issues[1]]  # Pass 2: candidates

        jira_client._jira.search_issues.side_effect = mock_search

        rock = BigRock(
            priority=1,
            name="MaaS",
            full_name="MaaS",
            components=["MaaS"],
            jql='project in (RHOAIENG) AND component = "MaaS" ORDER BY priority ASC',
            rfe_jql='project = RHAIRFE AND component = "MaaS" ORDER BY priority ASC',
        )

        candidates = jira_client.fetch_candidates_for_rock(
            rock=rock,
            release="3.5",
            fix_versions=["RHOAI 3.5", "3.5"],
            passes=[1, 2, 3],
        )

        # Should have 3 unique candidates
        # (issue 0 from pass 1, issue 1 from pass 2, issue 3 from pass 3)
        assert len(candidates) == 3
        passes_found = {c.source_pass for c in candidates}
        assert "committed" in passes_found
        assert "candidate" in passes_found
        assert "rfe" in passes_found

    def test_single_pass_only(self, jira_client, mock_jira_issues):
        jira_client._jira.search_issues.return_value = [mock_jira_issues[0]]

        rock = BigRock(
            priority=1,
            name="MaaS",
            full_name="MaaS",
            components=["MaaS"],
            jql='project in (RHOAIENG) AND component = "MaaS" ORDER BY key ASC',
        )

        candidates = jira_client.fetch_candidates_for_rock(
            rock=rock,
            release="3.5",
            fix_versions=["RHOAI 3.5"],
            passes=[1],
        )

        assert len(candidates) == 1
        assert candidates[0].source_pass == "committed"

    def test_seen_keys_excluded(self, jira_client, mock_jira_issues):
        jira_client._jira.search_issues.return_value = [mock_jira_issues[0]]

        rock = BigRock(
            priority=1,
            name="MaaS",
            full_name="MaaS",
            components=["MaaS"],
            jql='project in (RHOAIENG) AND component = "MaaS" ORDER BY key ASC',
        )

        # Issue 0's key is already seen
        candidates = jira_client.fetch_candidates_for_rock(
            rock=rock,
            release="3.5",
            fix_versions=["RHOAI 3.5"],
            passes=[1],
            seen_keys={mock_jira_issues[0].key},
        )

        assert len(candidates) == 0


class TestThrottle:
    """Tests for rate limiting behavior."""

    def test_throttle_with_zero_delay(self, jira_client):
        jira_client._query_delay = 0.0
        start = time.time()
        jira_client._throttle()
        elapsed = time.time() - start
        assert elapsed < 0.1

    def test_get_retry_after_default(self):
        from jira import JIRAError

        error = JIRAError(status_code=429, text="Rate limited")
        error.response = None
        result = JiraClient._get_retry_after(error)
        assert result == 60

    def test_get_retry_after_from_header(self):
        from jira import JIRAError

        error = JIRAError(status_code=429, text="Rate limited")
        mock_response = MagicMock()
        mock_response.headers = {"Retry-After": "30"}
        error.response = mock_response
        result = JiraClient._get_retry_after(error)
        assert result == 30
