"""Tests for jira_client.py: outcome-driven traversal, field mapping, error handling."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from release_planner.jira_client import JiraClient


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
        candidate = jira_client.map_to_candidate(issue, "MaaS", "outcome")

        assert candidate.issue_key == "RHAIRFE-200"
        assert candidate.source == "rfe"  # derived from key prefix, not source_pass
        assert candidate.source_pass == "outcome"

    def test_map_source_derived_from_key_prefix(self, jira_client, mock_jira_issues):
        """source is derived from key prefix, not from source_pass arg (M5)."""
        # RHOAIENG-12345 is not RHAIRFE -> source should be "jira"
        issue = mock_jira_issues[0]
        candidate = jira_client.map_to_candidate(issue, "MaaS", "outcome")
        assert candidate.source == "jira"

        # RHAIRFE-200 -> source should be "rfe" regardless of source_pass
        rfe_issue = mock_jira_issues[3]
        candidate2 = jira_client.map_to_candidate(rfe_issue, "MaaS", "outcome")
        assert candidate2.source == "rfe"


class TestFetchOutcomeChildren:
    """Tests for JiraClient.fetch_outcome_children()."""

    def test_returns_all_children(self, jira_client, mock_jira_issues):
        jira_client._jira.search_issues.return_value = mock_jira_issues[:3]
        children = jira_client.fetch_outcome_children("RHAISTRAT-9001", "MaaS")
        assert len(children) == 3

    def test_empty_outcome(self, jira_client):
        jira_client._jira.search_issues.return_value = []
        children = jira_client.fetch_outcome_children("RHAISTRAT-9999", "Test")
        assert children == []

    def test_failed_query_returns_empty(self, jira_client):
        from jira import JIRAError

        error = JIRAError(status_code=400, text="Bad query")
        error.response = None
        jira_client._jira.search_issues.side_effect = error
        children = jira_client.fetch_outcome_children("BAD-KEY", "Test")
        assert children == []  # graceful degradation

    def test_source_pass_is_outcome(self, jira_client, mock_jira_issues):
        jira_client._jira.search_issues.return_value = [mock_jira_issues[0]]
        children = jira_client.fetch_outcome_children("RHAISTRAT-9001", "MaaS")
        assert len(children) == 1
        assert children[0].source_pass == "outcome"

    def test_jql_contains_parent_key(self, jira_client):
        jira_client._jira.search_issues.return_value = []
        jira_client.fetch_outcome_children("RHAISTRAT-9001", "MaaS")
        call_args = jira_client._jira.search_issues.call_args
        jql = call_args[0][0]
        assert 'parent = "RHAISTRAT-9001"' in jql
        assert "status NOT IN" in jql

    def test_jql_excludes_closed_statuses(self, jira_client):
        jira_client._jira.search_issues.return_value = []
        jira_client.fetch_outcome_children("RHAISTRAT-9001", "MaaS")
        call_args = jira_client._jira.search_issues.call_args
        jql = call_args[0][0]
        for status in ("Closed", "Done", "Resolved", "Cancelled"):
            assert f'"{status}"' in jql


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


class TestCloudDetection:
    """Tests for Cloud vs Server detection."""

    def test_atlassian_net_detected_as_cloud(self):
        client = JiraClient(
            server="https://redhat.atlassian.net",
            token="test-token",
        )
        assert client._is_cloud is True

    def test_issues_redhat_detected_as_server(self):
        client = JiraClient(
            server="https://issues.redhat.com",
            token="test-token",
        )
        assert client._is_cloud is False

    def test_custom_server_detected_as_server(self):
        client = JiraClient(
            server="https://jira.example.com",
            token="test-token",
        )
        assert client._is_cloud is False


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
