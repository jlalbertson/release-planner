"""Tests for API model serialization.

Verifies:
- FeatureRow, RfeRow, RockSummary, CandidateResponse serialization
- Field mappings are correct
"""

from __future__ import annotations

from datetime import datetime, timezone

from release_planner.api_models import (
    CandidateResponse,
    FeatureRow,
    FilterOptions,
    PillarSummary,
    RfeRow,
    RockSummary,
    SummaryStats,
    TierSummary,
)


class TestFeatureRow:
    """Test FeatureRow serialization."""

    def test_create_feature_row(self):
        row = FeatureRow(
            big_rock="MaaS",
            issue_key="RHAISTRAT-1520",
            status="In Progress",
            priority="Major",
            phase="EA1",
            summary="Support vLLM multi-node inference",
            components="Serving",
            target_release="rhoai-3.5",
            fix_version="rhoai-3.5",
            pm="Jane Doe",
            delivery_owner="John Smith",
            rfe="RHAIRFE-456",
            labels="3.5-candidate",
        )
        assert row.big_rock == "MaaS"
        assert row.issue_key == "RHAISTRAT-1520"

    def test_feature_row_serialization(self):
        row = FeatureRow(
            big_rock="MaaS",
            issue_key="RHAISTRAT-1520",
            status="In Progress",
            priority="Major",
            phase="EA1",
            summary="Test feature",
            components="Serving",
            target_release="rhoai-3.5",
            fix_version="rhoai-3.5",
            pm="Jane",
            delivery_owner="John",
            rfe="",
            labels="",
        )
        data = row.model_dump()
        assert data["big_rock"] == "MaaS"
        assert data["issue_key"] == "RHAISTRAT-1520"
        assert data["status"] == "In Progress"
        assert data["priority"] == "Major"
        assert data["phase"] == "EA1"
        assert data["summary"] == "Test feature"
        assert data["components"] == "Serving"
        assert data["target_release"] == "rhoai-3.5"
        assert data["fix_version"] == "rhoai-3.5"
        assert data["pm"] == "Jane"
        assert data["delivery_owner"] == "John"
        assert data["rfe"] == ""
        assert data["labels"] == ""

    def test_feature_row_has_all_fields(self):
        field_names = set(FeatureRow.model_fields.keys())
        expected = {
            "big_rock", "issue_key", "status", "priority", "phase",
            "summary", "components", "target_release", "fix_version",
            "pm", "delivery_owner", "rfe", "labels",
        }
        assert field_names == expected


class TestRfeRow:
    """Test RfeRow serialization."""

    def test_create_rfe_row(self):
        row = RfeRow(
            big_rock="MaaS",
            issue_key="RHAIRFE-456",
            status="Approved",
            priority="Major",
            summary="Multi-node inference for large models",
            components="Serving",
            pm="Jane Doe",
            labels="3.5-candidate",
        )
        assert row.big_rock == "MaaS"
        assert row.issue_key == "RHAIRFE-456"

    def test_rfe_row_serialization(self):
        row = RfeRow(
            big_rock="Gen AI Studio",
            issue_key="RHAIRFE-500",
            status="Approved",
            priority="Critical",
            summary="Interactive prompt testing",
            components="GenAI Studio",
            pm="Sarah Lee",
            labels="3.5-candidate",
        )
        data = row.model_dump()
        assert data["big_rock"] == "Gen AI Studio"
        assert data["issue_key"] == "RHAIRFE-500"
        assert data["status"] == "Approved"
        assert data["priority"] == "Critical"
        assert data["summary"] == "Interactive prompt testing"
        assert data["components"] == "GenAI Studio"
        assert data["pm"] == "Sarah Lee"
        assert data["labels"] == "3.5-candidate"

    def test_rfe_row_has_all_fields(self):
        field_names = set(RfeRow.model_fields.keys())
        expected = {
            "big_rock", "issue_key", "status", "priority",
            "summary", "components", "pm", "labels",
        }
        assert field_names == expected


class TestRockSummary:
    """Test RockSummary serialization."""

    def test_create_rock_summary(self):
        rock = RockSummary(
            priority=1,
            name="MaaS",
            full_name="MaaS (continue from 3.4)",
            pillar="Inference",
            state="continue from 3.4",
            owner="Pat Johnson",
            outcome_keys=["RHAISTRAT-9001"],
            outcome_descriptions={"RHAISTRAT-9001": "Model as a Service enablement"},
            feature_count=5,
            rfe_count=2,
            notes="",
        )
        assert rock.name == "MaaS"
        assert rock.priority == 1

    def test_rock_summary_serialization(self):
        rock = RockSummary(
            priority=2,
            name="Gen AI Studio",
            full_name="Gen AI Studio / Prompt Lab",
            pillar="Agents",
            state="new for 3.5",
            owner="Morgan Lee",
            outcome_keys=["RHAISTRAT-9002", "RHAISTRAT-1313"],
            outcome_descriptions={
                "RHAISTRAT-9002": "Description 1",
                "RHAISTRAT-1313": "Description 2",
            },
            feature_count=4,
            rfe_count=1,
            notes="Some notes",
        )
        data = rock.model_dump()
        assert data["priority"] == 2
        assert data["name"] == "Gen AI Studio"
        assert data["pillar"] == "Agents"
        assert len(data["outcome_keys"]) == 2
        assert len(data["outcome_descriptions"]) == 2
        assert data["feature_count"] == 4
        assert data["rfe_count"] == 1
        assert data["notes"] == "Some notes"

    def test_rock_summary_has_all_fields(self):
        field_names = set(RockSummary.model_fields.keys())
        expected = {
            "priority", "name", "full_name", "pillar", "state", "owner",
            "outcome_keys", "outcome_descriptions", "feature_count",
            "rfe_count", "notes",
        }
        assert field_names == expected


class TestCandidateResponse:
    """Test CandidateResponse serialization."""

    def _make_response(self) -> CandidateResponse:
        return CandidateResponse(
            version="3.5",
            jira_base_url="https://redhat.atlassian.net/browse",
            last_refreshed=datetime(2026, 4, 21, 14, 30, 0, tzinfo=timezone.utc),
            demo_mode=False,
            summary=SummaryStats(
                total_features=2,
                total_rfes=1,
                total_big_rocks=1,
                rocks_with_data=1,
                tier1=TierSummary(features=2, rfes=1, description="Tier 1"),
                tier2=TierSummary(features=0, rfes=0, description="Tier 2"),
                per_rock={"MaaS": PillarSummary(features=2, rfes=1)},
            ),
            big_rocks=[
                RockSummary(
                    priority=1,
                    name="MaaS",
                    full_name="MaaS (continue from 3.4)",
                    pillar="Inference",
                    state="continue from 3.4",
                    owner="Pat Johnson",
                    outcome_keys=["RHAISTRAT-9001"],
                    outcome_descriptions={"RHAISTRAT-9001": "Model as a Service"},
                    feature_count=2,
                    rfe_count=1,
                    notes="",
                )
            ],
            features=[
                FeatureRow(
                    big_rock="MaaS",
                    issue_key="RHAISTRAT-1520",
                    status="In Progress",
                    priority="Major",
                    phase="EA1",
                    summary="Feature 1",
                    components="Serving",
                    target_release="rhoai-3.5",
                    fix_version="rhoai-3.5",
                    pm="Jane",
                    delivery_owner="John",
                    rfe="",
                    labels="",
                )
            ],
            rfes=[
                RfeRow(
                    big_rock="MaaS",
                    issue_key="RHAIRFE-456",
                    status="Approved",
                    priority="Major",
                    summary="RFE 1",
                    components="Serving",
                    pm="Jane",
                    labels="3.5-candidate",
                )
            ],
            filter_options=FilterOptions(
                pillars=["Inference"],
                rocks=["MaaS"],
                statuses=["Approved", "In Progress"],
                teams=["Serving"],
                priorities=["Major"],
            ),
        )

    def test_candidate_response_creation(self):
        resp = self._make_response()
        assert resp.version == "3.5"
        assert resp.demo_mode is False
        assert len(resp.big_rocks) == 1
        assert len(resp.features) == 1
        assert len(resp.rfes) == 1

    def test_candidate_response_serialization(self):
        resp = self._make_response()
        data = resp.model_dump()
        assert data["version"] == "3.5"
        assert data["jira_base_url"] == "https://redhat.atlassian.net/browse"
        assert "summary" in data
        assert data["summary"]["total_features"] == 2
        assert data["summary"]["total_rfes"] == 1
        assert len(data["big_rocks"]) == 1
        assert len(data["features"]) == 1
        assert len(data["rfes"]) == 1
        assert "filter_options" in data
        assert data["filter_options"]["pillars"] == ["Inference"]

    def test_candidate_response_json_round_trip(self):
        resp = self._make_response()
        json_str = resp.model_dump_json()
        restored = CandidateResponse.model_validate_json(json_str)
        assert restored.version == resp.version
        assert restored.summary.total_features == resp.summary.total_features
        assert len(restored.features) == len(resp.features)

    def test_demo_mode_flag(self):
        resp = self._make_response()
        assert resp.demo_mode is False

        data = resp.model_dump()
        data["demo_mode"] = True
        demo_resp = CandidateResponse.model_validate(data)
        assert demo_resp.demo_mode is True


class TestPillarSummary:
    """Test PillarSummary model."""

    def test_create(self):
        ps = PillarSummary(features=10, rfes=3)
        assert ps.features == 10
        assert ps.rfes == 3

    def test_serialization(self):
        ps = PillarSummary(features=5, rfes=2)
        data = ps.model_dump()
        assert data == {"features": 5, "rfes": 2}


class TestSummaryStats:
    """Test SummaryStats model."""

    def test_create(self):
        stats = SummaryStats(
            total_features=42,
            total_rfes=18,
            total_big_rocks=14,
            rocks_with_data=10,
            tier1=TierSummary(features=30, rfes=12, description="Tier 1"),
            tier2=TierSummary(features=12, rfes=6, description="Tier 2"),
            per_rock={},
        )
        assert stats.total_features == 42
        assert stats.total_rfes == 18

    def test_serialization_with_nested(self):
        stats = SummaryStats(
            total_features=10,
            total_rfes=5,
            total_big_rocks=3,
            rocks_with_data=2,
            tier1=TierSummary(features=7, rfes=3, description="Tier 1"),
            tier2=TierSummary(features=3, rfes=2, description="Tier 2"),
            per_rock={"MaaS": PillarSummary(features=5, rfes=3)},
        )
        data = stats.model_dump()
        assert data["tier1"]["features"] == 7
        assert data["tier2"]["features"] == 3
        assert data["per_rock"]["MaaS"]["rfes"] == 3


class TestFilterOptions:
    """Test FilterOptions model."""

    def test_create(self):
        opts = FilterOptions(
            pillars=["Inference", "Agents"],
            rocks=["MaaS"],
            statuses=["New", "In Progress"],
            teams=["Serving"],
            priorities=["Major", "Critical"],
        )
        assert len(opts.pillars) == 2
        assert "MaaS" in opts.rocks

    def test_empty_options(self):
        opts = FilterOptions(
            pillars=[],
            rocks=[],
            statuses=[],
            teams=[],
            priorities=[],
        )
        data = opts.model_dump()
        assert data["pillars"] == []
