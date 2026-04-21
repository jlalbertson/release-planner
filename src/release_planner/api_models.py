"""Pydantic response models for the web API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ReleaseInfo(BaseModel):
    """Available release in the release selector."""

    version: str
    label: str


class RockSummary(BaseModel):
    """Big Rock summary for the Big Rocks tab."""

    priority: int
    name: str
    full_name: str
    pillar: str
    state: str
    owner: str
    outcome_keys: list[str]
    outcome_descriptions: dict[str, str]
    feature_count: int
    rfe_count: int
    notes: str


class FeatureRow(BaseModel):
    """Serializable subset of Candidate for the Features tab.

    Field-to-column mapping:
        big_rock       -> "Big Rock"
        issue_key      -> "Feature"
        status         -> "Issue status"
        priority       -> "Priority"
        phase          -> "DP/TP/GA"
        summary        -> "Title"
        components     -> "Component[s]"
        target_release -> "Target Release"
        fix_version    -> "Fix Version (Committed)"
        pm             -> "PM"
        delivery_owner -> "Delivery Owner"
        rfe            -> "RFE"
        labels         -> "Comments"
    """

    big_rock: str
    issue_key: str
    status: str
    priority: str
    phase: str
    summary: str
    components: str
    target_release: str
    fix_version: str
    pm: str
    delivery_owner: str
    rfe: str
    labels: str


class RfeRow(BaseModel):
    """Serializable subset of Candidate for the RFEs tab.

    Field-to-column mapping:
        big_rock   -> "Big Rock"
        issue_key  -> "RFE"
        status     -> "RFE Status"  (Candidate.status, NOT rfe_status)
        priority   -> "Priority"
        summary    -> "Title"
        components -> "Component[s]"
        pm         -> "PM"
        labels     -> "Labels"
    """

    big_rock: str
    issue_key: str
    status: str
    priority: str
    summary: str
    components: str
    pm: str
    labels: str


class PillarSummary(BaseModel):
    """Feature and RFE counts for a pillar or rock."""

    features: int
    rfes: int


class SummaryStats(BaseModel):
    """Aggregated statistics for the summary cards."""

    total_features: int
    total_rfes: int
    total_big_rocks: int
    rocks_with_data: int
    per_pillar: dict[str, PillarSummary]
    per_rock: dict[str, PillarSummary]


class FilterOptions(BaseModel):
    """Available filter values derived from the current dataset."""

    pillars: list[str]
    rocks: list[str]
    statuses: list[str]
    teams: list[str]
    priorities: list[str]


class CandidateResponse(BaseModel):
    """Full response for GET /api/releases/{version}/candidates."""

    version: str
    jira_base_url: str
    last_refreshed: datetime
    demo_mode: bool = False
    summary: SummaryStats
    big_rocks: list[RockSummary]
    features: list[FeatureRow]
    rfes: list[RfeRow]
    filter_options: FilterOptions


class ErrorResponse(BaseModel):
    """Standard error response shape."""

    error: str
    detail: str
