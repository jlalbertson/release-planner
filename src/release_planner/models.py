"""Pydantic v2 models: BigRock, Candidate, OverrideSet."""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class BigRock(BaseModel):
    """A strategic initiative for a release."""

    priority: int = Field(ge=1, description="Priority rank (no upper bound)")
    name: str = Field(
        description=(
            "Display name for column A, e.g. 'MaaS'. Must match spreadsheet convention exactly."
        )
    )
    full_name: str = Field(description="Full name with context, e.g. 'MaaS (continue from 3.4)'")
    components: list[str] = Field(description="Jira component names associated with this rock")
    jql: str = Field(
        description=("JQL query template for component-based discovery. Use {release} placeholder.")
    )
    rfe_jql: str = Field(
        default="",
        description=(
            "JQL for RFE-based discovery from RHAIRFE project. Use {release} placeholder."
        ),
    )
    issue_keys: list[str] = Field(
        default_factory=list,
        description="Curated list of Jira issue keys for this rock (skips JQL discovery when set)",
    )
    exclude_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords to exclude from results to disambiguate shared components",
    )
    state: str = Field(default="", description="E.g. 'continue from 3.4' or 'new for 3.5'")
    pillar: str = Field(
        default="", description="Organizational pillar: Inference, Agents, Data, Platform"
    )
    outcome: str = Field(default="", description="Target outcome description")
    owner: str = Field(default="", description="Big Rock owner")
    notes: str = Field(default="", description="Freeform notes")
    description: str = Field(default="", description="Detailed description")


class Candidate(BaseModel):
    """A Jira issue that is a candidate for release work under a Big Rock."""

    big_rock: str = Field(description="Big Rock name(s), may be comma-separated")
    ranking: int | None = Field(default=None, description="1-n ranking within Big Rock")
    issue_key: str = Field(description="Jira issue key, e.g. RHOAIENG-12345")
    status: str = Field(default="", description="Jira status name")
    priority: str = Field(default="", description="Jira priority name")
    phase: str = Field(default="", description="DP/TP/GA target phase")
    summary: str = Field(default="", description="Issue title/summary")
    team: str = Field(default="", description="Owning team")
    components: str = Field(default="", description="Comma-joined component names")
    target_release: str = Field(default="", description="Target release / fixVersion")
    rfe: str = Field(default="", description="Linked RFE issue key")
    rfe_status: str = Field(default="", description="Status of linked RFE")
    pm: str = Field(default="", description="Product Manager")
    architect: str = Field(default="", description="Assigned architect")
    delivery_owner: str = Field(default="", description="Delivery owner")
    risk_flag: str = Field(default="", description="Risk flag indicator")
    change_log: str = Field(default="", description="Change log notes")
    refinement_complete: str = Field(default="", description="Yes/No/Partial")
    refinement_notes: str = Field(default="", description="Refinement details")
    comments: str = Field(default="", description="Freeform comments")
    rice_score: float | None = Field(default=None, description="RICE prioritization score")

    # Internal tracking (not written to output)
    jira_id: str = Field(default="", exclude=True, description="Jira internal ID")
    source: str = Field(default="jira", exclude=True, description="'jira', 'rfe', or 'manual'")
    source_pass: str = Field(
        default="",
        exclude=True,
        description="'committed', 'candidate', 'rfe', or 'manual'",
    )

    @field_validator("issue_key", mode="before")
    @classmethod
    def clean_issue_key(cls, v: str) -> str:
        """Strip whitespace and extract key from full URLs."""
        v = v.strip()
        # Handle URL-format keys like https://redhat.atlassian.net/browse/RHAISTRAT-9066
        url_match = re.match(r"https?://.+/browse/([A-Z]+-\d+)", v)
        if url_match:
            logger.warning(
                "Issue key is a URL, extracted key: %s from %s",
                url_match.group(1),
                v,
            )
            return url_match.group(1)
        return v


class OverrideSet(BaseModel):
    """Collection of overrides keyed by issue key.

    Used for both Jira-sourced overrides and manual (MANUAL-xxx) entries.
    The previous FieldOverride model has been removed -- only OverrideSet
    is needed since overrides are always loaded and applied as a batch.
    """

    overrides: dict[str, dict[str, str | int | float | None]]
    # Structure: { "RHOAIENG-123": { "pm": "Jane Doe", "team": "Platform" } }
