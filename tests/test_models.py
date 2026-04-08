"""Tests for Pydantic models: BigRock, Candidate, OverrideSet."""

import pytest

from release_planner.models import BigRock, Candidate, OverrideSet


class TestBigRock:
    """Tests for the BigRock model."""

    def test_valid_big_rock(self):
        rock = BigRock(
            priority=1,
            name="MaaS",
            full_name="MaaS (continue from 3.4)",
            components=["Model as a Service", "MaaS"],
            jql='project in (RHOAIENG) AND component = "MaaS" ORDER BY key ASC',
        )
        assert rock.priority == 1
        assert rock.name == "MaaS"
        assert len(rock.components) == 2

    def test_big_rock_defaults(self):
        rock = BigRock(
            priority=5,
            name="Test",
            full_name="Test Rock",
            components=["Comp"],
            jql="project = TEST",
        )
        assert rock.rfe_jql == ""
        assert rock.exclude_keywords == []
        assert rock.state == ""
        assert rock.pillar == ""
        assert rock.outcome == ""
        assert rock.owner == ""
        assert rock.notes == ""
        assert rock.description == ""

    def test_big_rock_priority_minimum(self):
        with pytest.raises(Exception):
            BigRock(
                priority=0,
                name="Bad",
                full_name="Bad Rock",
                components=["Comp"],
                jql="project = TEST",
            )

    def test_big_rock_priority_no_upper_bound(self):
        """Priority has no upper bound -- new rocks can be added freely."""
        rock = BigRock(
            priority=999,
            name="Future",
            full_name="Future Rock",
            components=["Comp"],
            jql="project = TEST",
        )
        assert rock.priority == 999

    def test_big_rock_with_exclude_keywords(self):
        rock = BigRock(
            priority=6,
            name="Tool Calling",
            full_name="Tool Calling Support",
            components=["vLLM Runtime"],
            jql="project = TEST",
            exclude_keywords=["multimodal", "multitenan"],
        )
        assert rock.exclude_keywords == ["multimodal", "multitenan"]


class TestCandidate:
    """Tests for the Candidate model."""

    def test_valid_candidate_full(self):
        c = Candidate(
            big_rock="MaaS",
            issue_key="RHOAIENG-12345",
            status="In Progress",
            priority="Major",
            summary="Implement feature X",
            components="Model as a Service, AI Core Dashboard",
            target_release="RHOAI 3.5",
            rfe="RHAIRFE-100",
            rfe_status="Approved",
            phase="GA",
            team="Platform",
            pm="Jane Doe",
            architect="John Smith",
            ranking=1,
            rice_score=85.0,
            source_pass="committed",
        )
        assert c.issue_key == "RHOAIENG-12345"
        assert c.ranking == 1
        assert c.rice_score == 85.0
        assert c.source_pass == "committed"

    def test_valid_candidate_minimal(self):
        c = Candidate(big_rock="MaaS", issue_key="RHOAIENG-1")
        assert c.status == ""
        assert c.priority == ""
        assert c.ranking is None
        assert c.rice_score is None
        assert c.source == "jira"
        assert c.source_pass == ""

    def test_issue_key_strips_whitespace(self):
        c = Candidate(big_rock="Test", issue_key="  RHOAIENG-123  ")
        assert c.issue_key == "RHOAIENG-123"

    def test_issue_key_extracts_from_url(self):
        c = Candidate(
            big_rock="Test",
            issue_key="https://redhat.atlassian.net/browse/RHAISTRAT-9066",
        )
        assert c.issue_key == "RHAISTRAT-9066"

    def test_issue_key_extracts_from_jira_server_url(self):
        c = Candidate(
            big_rock="Test",
            issue_key="https://issues.redhat.com/browse/RHOAIENG-12345",
        )
        assert c.issue_key == "RHOAIENG-12345"

    def test_source_pass_excluded_from_serialization(self):
        c = Candidate(
            big_rock="MaaS",
            issue_key="RHOAIENG-1",
            source_pass="committed",
            source="jira",
            jira_id="100001",
        )
        data = c.model_dump()
        assert "source_pass" not in data
        assert "source" not in data
        assert "jira_id" not in data

    def test_candidate_serialization_roundtrip(self):
        c = Candidate(
            big_rock="MaaS",
            issue_key="RHOAIENG-12345",
            status="In Progress",
            priority="Major",
            summary="Test summary",
            ranking=3,
            rice_score=42.5,
        )
        data = c.model_dump()
        c2 = Candidate(**data)
        assert c2.issue_key == c.issue_key
        assert c2.ranking == c.ranking
        assert c2.rice_score == c.rice_score


class TestOverrideSet:
    """Tests for the OverrideSet model."""

    def test_valid_override_set(self):
        os = OverrideSet(
            overrides={
                "RHOAIENG-123": {"pm": "Jane", "team": "Platform"},
                "RHAIRFE-456": {"phase": "EA1"},
            }
        )
        assert len(os.overrides) == 2
        assert os.overrides["RHOAIENG-123"]["pm"] == "Jane"

    def test_empty_override_set(self):
        os = OverrideSet(overrides={})
        assert len(os.overrides) == 0

    def test_override_set_with_none_values(self):
        os = OverrideSet(
            overrides={
                "RHOAIENG-123": {"pm": None, "team": "Platform"},
            }
        )
        assert os.overrides["RHOAIENG-123"]["pm"] is None

    def test_override_set_with_numeric_values(self):
        os = OverrideSet(
            overrides={
                "RHOAIENG-123": {"ranking": 1, "rice_score": 85.0},
            }
        )
        assert os.overrides["RHOAIENG-123"]["ranking"] == 1
        assert os.overrides["RHOAIENG-123"]["rice_score"] == 85.0
