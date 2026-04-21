"""Jira integration: outcome-driven traversal, field mapping, rate limiting."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from jira import JIRA, JIRAError

from release_planner.constants import (
    JIRA_MAX_RESULTS_PER_QUERY,
    JIRA_QUERY_DELAY_DEFAULT,
    JIRA_REQUEST_TIMEOUT,
    JIRA_RETRY_COUNT,
    JIRA_SERVER_DEFAULT,
)
from release_planner.models import Candidate

logger = logging.getLogger(__name__)


class JiraClient:
    """Client for Jira Server/DC (PAT) or Jira Cloud (email + API token)."""

    def __init__(
        self,
        server: str = JIRA_SERVER_DEFAULT,
        token: str = "",
        email: str | None = None,
        field_mapping: dict[str, str] | None = None,
        query_delay: float = JIRA_QUERY_DELAY_DEFAULT,
    ):
        """Initialize with server URL, credentials, custom field mapping, and rate limit delay.

        Args:
            server: Jira URL (e.g. https://issues.redhat.com or https://redhat.atlassian.net)
            token: PAT (Server/DC) or API token (Cloud)
            email: Email for Jira Cloud basic auth. If set, uses basic_auth instead of token_auth.
            field_mapping: Custom field ID mapping (from data/field_mapping.yaml)
            query_delay: Seconds to wait between API calls (default 1.0)
        """
        self._server = server
        self._token = token
        self._email = email
        self._field_mapping = field_mapping or {}
        self._query_delay = query_delay
        self._last_query_time: float = 0.0
        self._jira: JIRA | None = None
        self._is_cloud: bool = "atlassian.net" in server

    def connect(self) -> None:
        """Establish connection to Jira. Raises RuntimeError on auth failure."""
        try:
            if self._email:
                # Jira Cloud: email + API token via basic auth
                self._jira = JIRA(
                    server=self._server,
                    basic_auth=(self._email, self._token),
                    timeout=JIRA_REQUEST_TIMEOUT,
                )
            else:
                # Jira Server/DC: PAT via token auth
                self._jira = JIRA(
                    server=self._server,
                    token_auth=self._token,
                    timeout=JIRA_REQUEST_TIMEOUT,
                )
            # Test connection by fetching server info
            self._jira.server_info()
            logger.info("Connected to Jira at %s", self._server)
        except JIRAError as e:
            if e.status_code in (401, 403):
                raise RuntimeError(
                    f"Jira authentication failed (HTTP {e.status_code}). "
                    "Check that RELEASE_PLANNER_JIRA_TOKEN is a valid PAT for "
                    f"{self._server}. PAT auth uses: JIRA(server=url, token_auth=token)"
                ) from e
            raise RuntimeError(f"Failed to connect to Jira at {self._server}: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Jira at {self._server}: {e}") from e

    def _ensure_connected(self) -> JIRA:
        """Ensure Jira client is connected, connecting if needed."""
        if self._jira is None:
            self.connect()
        assert self._jira is not None
        return self._jira

    def search_issues(self, jql: str, max_results: int = JIRA_MAX_RESULTS_PER_QUERY) -> list[Any]:
        """Execute JQL and return raw Jira issue objects. Respects rate limiting.

        Uses enhanced_search_issues on Jira Cloud (required since the legacy
        search API is deprecated) and falls back to the classic search_issues
        on Jira Server/DC.

        Args:
            jql: JQL query string.
            max_results: Maximum number of results to return.

        Returns:
            List of Jira issue objects.
        """
        jira = self._ensure_connected()
        self._throttle()

        logger.debug("Executing JQL: %s (max_results=%d)", jql, max_results)

        if self._is_cloud:
            return self._search_issues_cloud(jira, jql, max_results)
        return self._search_issues_server(jira, jql, max_results)

    def _search_issues_cloud(
        self, jira: JIRA, jql: str, max_results: int
    ) -> list[Any]:
        """Execute JQL using the Cloud enhanced_search_issues API (token-paginated).

        Pass maxResults=0 to let the library auto-paginate through all results,
        then truncate to our max_results cap.
        """
        for attempt in range(1, JIRA_RETRY_COUNT + 1):
            try:
                # maxResults=0 tells the jira library to fetch ALL pages
                # (the Cloud API caps at 100/page, so a positive value only
                # fetches a single page). We truncate to our own cap afterward.
                results = jira.enhanced_search_issues(
                    jql,
                    maxResults=0,
                )
                issues = list(results)
                if len(issues) > max_results:
                    logger.warning(
                        "Hit max_results cap (%d). There may be more issues matching the query.",
                        max_results,
                    )
                    issues = issues[:max_results]
                logger.info("JQL returned %d issues (Cloud)", len(issues))
                return issues
            except JIRAError as e:
                if not self._handle_jira_error(e, jql, attempt):
                    raise
            except Exception as e:
                if not self._handle_connection_error(e, attempt):
                    raise
        raise RuntimeError(
            f"Jira query failed after {JIRA_RETRY_COUNT} retries"
        )

    def _search_issues_server(
        self, jira: JIRA, jql: str, max_results: int
    ) -> list[Any]:
        """Execute JQL using the Server/DC search_issues API (offset-paginated)."""
        all_issues: list[Any] = []
        start_at = 0
        page_size = min(100, max_results)

        while start_at < max_results:
            remaining = max_results - start_at
            current_page_size = min(page_size, remaining)
            results: list[Any] = []

            for attempt in range(1, JIRA_RETRY_COUNT + 1):
                try:
                    results = jira.search_issues(
                        jql,
                        startAt=start_at,
                        maxResults=current_page_size,
                    )
                    break
                except JIRAError as e:
                    if not self._handle_jira_error(e, jql, attempt):
                        raise
                    continue
                except Exception as e:
                    if not self._handle_connection_error(e, attempt):
                        raise
                    continue

            all_issues.extend(results)

            # Check if there are more results
            if len(results) < current_page_size:
                break
            start_at += len(results)
            if start_at < max_results:
                self._throttle()

        if len(all_issues) >= max_results:
            logger.warning(
                "Hit max_results cap (%d). There may be more issues matching the query.",
                max_results,
            )

        logger.info("JQL returned %d issues (Server/DC)", len(all_issues))
        return all_issues

    def _handle_jira_error(self, e: JIRAError, jql: str, attempt: int) -> bool:
        """Handle a JIRAError during search. Returns True if the caller should retry."""
        if e.status_code == 429:
            retry_after = self._get_retry_after(e)
            logger.warning(
                "Rate limited (429). Waiting %ds before retry %d/%d",
                retry_after,
                attempt,
                JIRA_RETRY_COUNT,
            )
            time.sleep(retry_after)
            if attempt >= JIRA_RETRY_COUNT:
                raise RuntimeError(
                    f"Jira rate limit (429) persisted after {JIRA_RETRY_COUNT} retries"
                ) from e
            return True
        if e.status_code == 400:
            logger.error("Bad JQL query (400): %s\nJQL: %s", e.text, jql)
            raise RuntimeError(
                f"Invalid JQL query. Check component names and syntax.\n"
                f"JQL: {jql}\nError: {e.text}"
            ) from e
        if e.status_code in (401, 403):
            raise RuntimeError(
                f"Jira authentication failed (HTTP {e.status_code}). "
                "Check that your PAT is valid and not expired."
            ) from e
        if attempt < JIRA_RETRY_COUNT:
            wait_time = 2**attempt
            logger.warning(
                "Jira error (HTTP %s), retrying in %ds (%d/%d): %s",
                e.status_code,
                wait_time,
                attempt,
                JIRA_RETRY_COUNT,
                e.text,
            )
            time.sleep(wait_time)
            return True
        raise RuntimeError(
            f"Jira query failed after {JIRA_RETRY_COUNT} retries: {e}"
        ) from e

    def _handle_connection_error(self, e: Exception, attempt: int) -> bool:
        """Handle a non-Jira exception during search. Returns True if the caller should retry."""
        if attempt < JIRA_RETRY_COUNT:
            wait_time = 2**attempt
            logger.warning(
                "Connection error, retrying in %ds (%d/%d): %s",
                wait_time,
                attempt,
                JIRA_RETRY_COUNT,
                e,
            )
            time.sleep(wait_time)
            return True
        raise RuntimeError(
            f"Jira query failed after {JIRA_RETRY_COUNT} retries: {e}"
        ) from e

    def map_to_candidate(
        self,
        raw_issue: Any,
        big_rock_name: str,
        source_pass: str = "",
    ) -> Candidate:
        """Map a raw Jira issue object to a Candidate model.

        Args:
            raw_issue: Jira issue object from search_issues().
            big_rock_name: Name of the BigRock this candidate belongs to.
            source_pass: Discovery pass tag ('committed', 'candidate', 'rfe').

        Returns:
            Candidate model instance.
        """
        fields = raw_issue.fields

        # Extract components
        components_list = []
        if hasattr(fields, "components") and fields.components:
            components_list = [c.name for c in fields.components]
        components_str = ", ".join(components_list)

        # Extract status
        status = ""
        if hasattr(fields, "status") and fields.status:
            status = fields.status.name

        # Extract priority
        priority = ""
        if hasattr(fields, "priority") and fields.priority:
            priority = fields.priority.name

        # Extract summary
        summary = getattr(fields, "summary", "") or ""

        # Extract labels
        labels = ""
        if hasattr(fields, "labels") and fields.labels:
            labels = ", ".join(fields.labels)

        # Extract target_release from Target Version (customfield_10855),
        # falling back to fixVersions
        target_release = ""
        tv_val = getattr(fields, "customfield_10855", None)
        if tv_val:
            if isinstance(tv_val, list):
                target_release = tv_val[0].name if tv_val and hasattr(tv_val[0], "name") else ""
            elif hasattr(tv_val, "name"):
                target_release = tv_val.name
            else:
                target_release = str(tv_val)
        if not target_release and hasattr(fields, "fixVersions") and fields.fixVersions:
            target_release = fields.fixVersions[0].name

        # Extract fix_version from fixVersions (independent of target_release)
        fix_version = ""
        if hasattr(fields, "fixVersions") and fields.fixVersions:
            fix_version = ", ".join(fv.name for fv in fields.fixVersions)

        # Extract team from custom field (via field_mapping)
        team = ""
        if "team" in self._field_mapping:
            custom_field = self._field_mapping["team"]
            team_val = getattr(fields, custom_field, None)
            if team_val:
                team = str(team_val) if not hasattr(team_val, "name") else team_val.name

        # Extract PM from Product Manager (customfield_10469)
        pm = ""
        pm_val = getattr(fields, "customfield_10469", None)
        if pm_val:
            pm = pm_val.displayName if hasattr(pm_val, "displayName") else str(pm_val)

        # Extract architect from custom field (via field_mapping)
        architect = ""
        if "architect" in self._field_mapping:
            custom_field = self._field_mapping["architect"]
            arch_val = getattr(fields, custom_field, None)
            if arch_val:
                architect = (
                    str(arch_val) if not hasattr(arch_val, "displayName") else arch_val.displayName
                )

        # Extract delivery owner from Assignee (standard field)
        delivery_owner = ""
        if hasattr(fields, "assignee") and fields.assignee:
            delivery_owner = (
                fields.assignee.displayName
                if hasattr(fields.assignee, "displayName")
                else str(fields.assignee)
            )

        # Extract phase from Release Type (customfield_10851)
        phase = ""
        phase_val = getattr(fields, "customfield_10851", None)
        if phase_val:
            phase = phase_val.value if hasattr(phase_val, "value") else str(phase_val)

        # Extract RFE link
        rfe_key, rfe_status = self.get_rfe_link(raw_issue)
        # For STRATs, also find parent RFE via Clones link or description
        if not rfe_key and raw_issue.key.startswith("RHAISTRAT-"):
            rfe_key = self._get_parent_rfe_key(raw_issue)

        # Determine source from issue key prefix (not source_pass)
        source = "rfe" if raw_issue.key.startswith("RHAIRFE-") else "jira"

        return Candidate(
            big_rock=big_rock_name,
            issue_key=raw_issue.key,
            status=status,
            priority=priority,
            summary=summary,
            components=components_str,
            labels=labels,
            target_release=target_release,
            fix_version=fix_version,
            team=team,
            pm=pm,
            architect=architect,
            delivery_owner=delivery_owner,
            phase=phase,
            rfe=rfe_key,
            rfe_status=rfe_status,
            jira_id=raw_issue.id if hasattr(raw_issue, "id") else "",
            source=source,
            source_pass=source_pass,
        )

    def get_rfe_link(self, issue: Any) -> tuple[str, str]:
        """Extract linked RFE key and status from issue links.

        Looks for links with type matching the configured rfe_link_type
        (default: 'is required by').

        Args:
            issue: Jira issue object.

        Returns:
            Tuple of (rfe_key, rfe_status). Empty strings if no RFE found.
        """
        rfe_link_type = self._field_mapping.get("rfe_link_type", "is required by")

        if not hasattr(issue.fields, "issuelinks") or not issue.fields.issuelinks:
            return ("", "")

        for link in issue.fields.issuelinks:
            link_type_name = ""
            linked_issue = None

            if hasattr(link, "type"):
                # Check both inward and outward link names
                if hasattr(link, "inwardIssue"):
                    link_type_name = getattr(link.type, "inward", "")
                    linked_issue = link.inwardIssue
                elif hasattr(link, "outwardIssue"):
                    link_type_name = getattr(link.type, "outward", "")
                    linked_issue = link.outwardIssue

            if linked_issue and rfe_link_type.lower() in link_type_name.lower():
                rfe_key = linked_issue.key
                # Try to get status from the linked issue
                rfe_status = ""
                if hasattr(linked_issue, "fields") and hasattr(linked_issue.fields, "status"):
                    if linked_issue.fields.status:
                        rfe_status = linked_issue.fields.status.name
                return (rfe_key, rfe_status)

        return ("", "")

    def discover_custom_fields(self, issue_key: str) -> dict[str, str]:
        """Fetch a single issue with all fields and return field ID -> name mapping.

        Used by the discover-fields CLI command to identify custom field IDs.

        Args:
            issue_key: Jira issue key (e.g. RHOAIENG-12345).

        Returns:
            Dict mapping field ID to field name and value for custom fields.
        """
        jira = self._ensure_connected()
        self._throttle()

        try:
            issue = jira.issue(issue_key)
        except JIRAError as e:
            raise RuntimeError(f"Failed to fetch issue {issue_key}: {e}") from e

        # Get all fields metadata
        all_fields = jira.fields()
        field_id_to_name = {f["id"]: f["name"] for f in all_fields}

        result: dict[str, str] = {}
        for field_id, field_name in sorted(field_id_to_name.items()):
            if field_id.startswith("customfield_"):
                value = getattr(issue.fields, field_id, None)
                if value is not None:
                    # Format value for display
                    if hasattr(value, "name"):
                        display_value = value.name
                    elif hasattr(value, "displayName"):
                        display_value = value.displayName
                    elif isinstance(value, list):
                        display_value = ", ".join(
                            str(v.name if hasattr(v, "name") else v) for v in value
                        )
                    else:
                        display_value = str(value)
                    result[field_id] = f"{field_name}: {display_value}"

        return result

    # Exclude closed/resolved statuses from all queries
    _CLOSED_STATUSES = ("Closed", "Done", "Resolved", "Cancelled")

    def fetch_outcome_children(
        self,
        outcome_key: str,
        big_rock_name: str,
    ) -> list[Candidate]:
        """Fetch all direct children of an Outcome issue.

        Uses JQL: parent = {outcome_key}
                  AND status NOT IN ("Closed", "Done", "Resolved", "Cancelled")
                  ORDER BY key ASC

        Args:
            outcome_key: Jira issue key of the Outcome (e.g. RHAISTRAT-1234).
            big_rock_name: Name of the BigRock this Outcome belongs to.

        Returns:
            List of Candidate models (unfiltered -- caller applies release/label filters).
        """
        closed_list = ", ".join(f'"{s}"' for s in self._CLOSED_STATUSES)
        jql = (
            f'parent = "{outcome_key}" '
            f"AND status NOT IN ({closed_list}) "
            f"ORDER BY key ASC"
        )

        logger.info("  Querying children of Outcome %s for %s", outcome_key, big_rock_name)

        try:
            raw_issues = self.search_issues(jql)
        except RuntimeError as e:
            logger.error("  Failed to query children of %s: %s", outcome_key, e)
            return []

        candidates = []
        for issue in raw_issues:
            candidate = self.map_to_candidate(issue, big_rock_name, source_pass="outcome")
            candidates.append(candidate)

        logger.info(
            "  Outcome %s returned %d children for %s",
            outcome_key,
            len(candidates),
            big_rock_name,
        )
        return candidates

    def fetch_outcome_summaries(
        self,
        outcome_keys: list[str],
    ) -> dict[str, str]:
        """Fetch the summary (title) for a batch of Outcome issues.

        Args:
            outcome_keys: List of Jira issue keys (e.g. ["RHAISTRAT-1234"]).

        Returns:
            Dict mapping outcome_key -> summary string.
        """
        if not outcome_keys:
            return {}

        keys_str = ", ".join(outcome_keys)
        jql = f"key in ({keys_str}) ORDER BY key ASC"

        logger.info("Fetching summaries for %d Outcome issues", len(outcome_keys))

        try:
            raw_issues = self.search_issues(jql)
        except RuntimeError as e:
            logger.error("Failed to fetch Outcome summaries: %s", e)
            return {}

        summaries: dict[str, str] = {}
        for issue in raw_issues:
            summary = getattr(issue.fields, "summary", "") or ""
            summaries[issue.key] = summary

        return summaries

    def fetch_tier2_features(
        self,
        release: str,
        exclude_keys: set[str],
    ) -> list[Candidate]:
        """Fetch Tier 2 features: RHAISTRAT with matching Target Release but not in Tier 1.

        JQL: project = RHAISTRAT AND type = Feature
             AND "Target Release" ~ "*{release}*"
             AND status NOT IN (closed statuses)

        Args:
            release: Release version string (e.g. "3.5").
            exclude_keys: Set of issue keys already discovered as Tier 1.

        Returns:
            List of Candidate models with empty big_rock.
        """
        closed_list = ", ".join(f'"{s}"' for s in self._CLOSED_STATUSES)
        jql = (
            f'project = RHAISTRAT AND type = Feature '
            f'AND "Target Release" ~ "*{release}*" '
            f"AND status NOT IN ({closed_list}) "
            f"ORDER BY key ASC"
        )

        logger.info("Fetching Tier 2 features for release %s", release)

        try:
            raw_issues = self.search_issues(jql)
        except RuntimeError as e:
            logger.error("Failed to fetch Tier 2 features: %s", e)
            return []

        candidates = []
        for issue in raw_issues:
            if issue.key in exclude_keys:
                continue
            candidate = self.map_to_candidate(issue, big_rock_name="", source_pass="tier2")
            candidates.append(candidate)

        logger.info("Found %d Tier 2 features for release %s", len(candidates), release)
        return candidates

    def fetch_tier2_rfes(
        self,
        release: str,
        exclude_keys: set[str],
    ) -> list[Candidate]:
        """Fetch Tier 2 RFEs: RHAIRFE with candidate label but not in Tier 1.

        JQL: project = RHAIRFE AND labels = "{release}-candidate"
             AND status NOT IN (closed statuses)
             AND status != "Approved"

        Approved RFEs are excluded because approval means a RHAISTRAT Feature
        has been cloned from the RFE and should appear in the Features list.

        Args:
            release: Release version string (e.g. "3.5").
            exclude_keys: Set of RFE keys already discovered as Tier 1.

        Returns:
            List of Candidate models with empty big_rock.
        """
        closed_list = ", ".join(f'"{s}"' for s in self._CLOSED_STATUSES)
        jql = (
            f'project = RHAIRFE AND labels = "{release}-candidate" '
            f"AND status NOT IN ({closed_list}) "
            f'AND status != "Approved" '
            f"ORDER BY key ASC"
        )

        logger.info("Fetching Tier 2 RFEs for release %s", release)

        try:
            raw_issues = self.search_issues(jql)
        except RuntimeError as e:
            logger.error("Failed to fetch Tier 2 RFEs: %s", e)
            return []

        candidates = []
        for issue in raw_issues:
            if issue.key in exclude_keys:
                continue
            candidate = self.map_to_candidate(issue, big_rock_name="", source_pass="tier2")
            candidates.append(candidate)

        logger.info("Found %d Tier 2 RFEs for release %s", len(candidates), release)
        return candidates

    def fetch_tier3_features(
        self,
        exclude_keys: set[str],
    ) -> list[Candidate]:
        """Fetch Tier 3 features: In Progress RHAISTRAT with no target release or fix version.

        JQL: project = RHAISTRAT AND type = Feature
             AND status = "In Progress"
             AND "Target Release" is EMPTY
             AND fixVersion is EMPTY

        Args:
            exclude_keys: Set of issue keys already discovered as Tier 1 or Tier 2.

        Returns:
            List of Candidate models with empty big_rock.
        """
        jql = (
            'project = RHAISTRAT AND type = Feature '
            'AND status = "In Progress" '
            'AND "Target Release" is EMPTY '
            'AND fixVersion is EMPTY '
            'ORDER BY key ASC'
        )

        logger.info("Fetching Tier 3 features")

        try:
            raw_issues = self.search_issues(jql)
        except RuntimeError as e:
            logger.error("Failed to fetch Tier 3 features: %s", e)
            return []

        candidates = []
        for issue in raw_issues:
            if issue.key in exclude_keys:
                continue
            candidate = self.map_to_candidate(issue, big_rock_name="", source_pass="tier3")
            candidates.append(candidate)

        logger.info("Found %d Tier 3 features", len(candidates))
        return candidates

    @staticmethod
    def _get_parent_rfe_key(issue: Any) -> str:
        """Find linked RHAIRFE key for a RHAISTRAT via Clones link or description.

        Checks:
        1. Issue links with Cloners type pointing to RHAIRFE-*
        2. Description text for 'Parent RFE' followed by an RHAIRFE key

        Args:
            issue: Raw Jira issue object (RHAISTRAT).

        Returns:
            Linked RHAIRFE key, or empty string if none found.
        """
        # Check issue links for Clones type pointing to RHAIRFE
        if hasattr(issue.fields, "issuelinks") and issue.fields.issuelinks:
            for link in issue.fields.issuelinks:
                if not hasattr(link, "type"):
                    continue
                link_type_name = getattr(link.type, "name", "")
                if "Clon" not in link_type_name:
                    continue

                linked_issue = None
                if hasattr(link, "inwardIssue"):
                    linked_issue = link.inwardIssue
                elif hasattr(link, "outwardIssue"):
                    linked_issue = link.outwardIssue

                if linked_issue and linked_issue.key.startswith("RHAIRFE-"):
                    return linked_issue.key

        # Fallback: check description for "Parent RFE" reference
        description = getattr(issue.fields, "description", "") or ""
        if not isinstance(description, str):
            description = str(description)
        match = re.search(r"Parent RFE.*?(RHAIRFE-\d+)", description, re.IGNORECASE)
        if match:
            return match.group(1)

        return ""

    def _throttle(self) -> None:
        """Sleep for query_delay seconds between API calls.

        Ensures we don't exceed Jira rate limits.
        """
        now = time.time()
        elapsed = now - self._last_query_time
        if elapsed < self._query_delay:
            sleep_time = self._query_delay - elapsed
            logger.debug("Throttling: sleeping %.2fs", sleep_time)
            time.sleep(sleep_time)
        self._last_query_time = time.time()

    @staticmethod
    def _get_retry_after(error: JIRAError) -> int:
        """Extract Retry-After value from a JIRAError response.

        Args:
            error: JIRAError with possible Retry-After header.

        Returns:
            Number of seconds to wait. Defaults to 60 if header is missing.
        """
        if hasattr(error, "response") and error.response is not None:
            retry_after = error.response.headers.get("Retry-After", "60")
            try:
                return int(retry_after)
            except ValueError:
                return 60
        return 60
