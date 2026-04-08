"""Jira integration: connection, three-pass query, field mapping, rate limiting."""

from __future__ import annotations

import logging
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
from release_planner.models import BigRock, Candidate

logger = logging.getLogger(__name__)


class JiraClient:
    """Client for Jira Server/DC using PAT authentication."""

    def __init__(
        self,
        server: str = JIRA_SERVER_DEFAULT,
        token: str = "",
        field_mapping: dict[str, str] | None = None,
        query_delay: float = JIRA_QUERY_DELAY_DEFAULT,
    ):
        """Initialize with server URL, PAT, custom field mapping, and rate limit delay.

        Args:
            server: Jira Server/DC URL (e.g. https://issues.redhat.com)
            token: Personal Access Token for authentication
            field_mapping: Custom field ID mapping (from data/field_mapping.yaml)
            query_delay: Seconds to wait between API calls (default 1.0)
        """
        self._server = server
        self._token = token
        self._field_mapping = field_mapping or {}
        self._query_delay = query_delay
        self._last_query_time: float = 0.0
        self._jira: JIRA | None = None

    def connect(self) -> None:
        """Establish connection to Jira. Raises RuntimeError on auth failure."""
        try:
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

        Args:
            jql: JQL query string.
            max_results: Maximum number of results to return.

        Returns:
            List of Jira issue objects.
        """
        jira = self._ensure_connected()
        self._throttle()

        logger.debug("Executing JQL: %s (max_results=%d)", jql, max_results)

        all_issues: list[Any] = []
        start_at = 0
        page_size = min(100, max_results)

        while start_at < max_results:
            remaining = max_results - start_at
            current_page_size = min(page_size, remaining)

            for attempt in range(1, JIRA_RETRY_COUNT + 1):
                try:
                    results = jira.search_issues(
                        jql,
                        startAt=start_at,
                        maxResults=current_page_size,
                    )
                    break
                except JIRAError as e:
                    if e.status_code == 429:
                        retry_after = self._get_retry_after(e)
                        logger.warning(
                            "Rate limited (429). Waiting %ds before retry %d/%d",
                            retry_after,
                            attempt,
                            JIRA_RETRY_COUNT,
                        )
                        time.sleep(retry_after)
                        continue
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
                        continue
                    raise RuntimeError(
                        f"Jira query failed after {JIRA_RETRY_COUNT} retries: {e}"
                    ) from e
                except Exception as e:
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
                        continue
                    raise RuntimeError(
                        f"Jira query failed after {JIRA_RETRY_COUNT} retries: {e}"
                    ) from e

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

        logger.info("JQL returned %d issues", len(all_issues))
        return all_issues

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

        # Extract fixVersions -> target_release
        target_release = ""
        if hasattr(fields, "fixVersions") and fields.fixVersions:
            target_release = fields.fixVersions[0].name
        elif "target_release" in self._field_mapping:
            custom_field = self._field_mapping["target_release"]
            target_release = str(getattr(fields, custom_field, "") or "")

        # Extract team from custom field
        team = ""
        if "team" in self._field_mapping:
            custom_field = self._field_mapping["team"]
            team_val = getattr(fields, custom_field, None)
            if team_val:
                team = str(team_val) if not hasattr(team_val, "name") else team_val.name

        # Extract PM from custom field
        pm = ""
        if "pm" in self._field_mapping:
            custom_field = self._field_mapping["pm"]
            pm_val = getattr(fields, custom_field, None)
            if pm_val:
                pm = str(pm_val) if not hasattr(pm_val, "displayName") else pm_val.displayName

        # Extract architect from custom field
        architect = ""
        if "architect" in self._field_mapping:
            custom_field = self._field_mapping["architect"]
            arch_val = getattr(fields, custom_field, None)
            if arch_val:
                architect = (
                    str(arch_val) if not hasattr(arch_val, "displayName") else arch_val.displayName
                )

        # Extract delivery owner from custom field
        delivery_owner = ""
        if "delivery_owner" in self._field_mapping:
            custom_field = self._field_mapping["delivery_owner"]
            do_val = getattr(fields, custom_field, None)
            if do_val:
                delivery_owner = (
                    str(do_val) if not hasattr(do_val, "displayName") else do_val.displayName
                )

        # Extract phase from custom field
        phase = ""
        if "phase" in self._field_mapping:
            custom_field = self._field_mapping["phase"]
            phase_val = getattr(fields, custom_field, None)
            if phase_val:
                phase = str(phase_val) if not hasattr(phase_val, "name") else phase_val.name

        # Extract RFE link
        rfe_key, rfe_status = self.get_rfe_link(raw_issue)

        # Determine source
        source = "rfe" if source_pass == "rfe" else "jira"

        return Candidate(
            big_rock=big_rock_name,
            issue_key=raw_issue.key,
            status=status,
            priority=priority,
            summary=summary,
            components=components_str,
            target_release=target_release,
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

    def fetch_candidates_for_rock(
        self,
        rock: BigRock,
        release: str,
        fix_versions: list[str],
        passes: list[int] | None = None,
        seen_keys: set[str] | None = None,
    ) -> list[Candidate]:
        """Execute three-pass discovery for a rock and return mapped Candidates.

        Args:
            rock: BigRock definition with jql, rfe_jql, exclude_keywords.
            release: Release version string (e.g. "3.5") for JQL substitution.
            fix_versions: List of fixVersion variants for Pass 1.
            passes: Which passes to run (default all three: [1, 2, 3]).
            seen_keys: Set of issue keys already discovered by higher-priority rocks.
                Keys found here will be excluded from results.

        Returns:
            List of Candidate models, each tagged with source_pass.
        """
        if passes is None:
            passes = [1, 2, 3]
        if seen_keys is None:
            seen_keys = set()

        candidates: list[Candidate] = []
        rock_keys: set[str] = set()

        # --- Pass 1: Committed issues (fixVersion-tagged) ---
        if 1 in passes:
            logger.info("  Pass 1 (committed): %s", rock.name)
            quoted_versions = ", ".join(f'"{fv}"' for fv in fix_versions)
            # Remove ORDER BY from base JQL to append fixVersion filter before it
            base_jql = rock.jql
            order_by = ""
            if "ORDER BY" in base_jql.upper():
                idx = base_jql.upper().index("ORDER BY")
                order_by = base_jql[idx:]
                base_jql = base_jql[:idx].rstrip()

            pass1_jql = f"{base_jql} AND fixVersion IN ({quoted_versions}) {order_by}"

            try:
                issues = self.search_issues(pass1_jql)
                for issue in issues:
                    key = issue.key
                    if key not in seen_keys and key not in rock_keys:
                        candidate = self.map_to_candidate(issue, rock.name, "committed")
                        candidates.append(candidate)
                        rock_keys.add(key)
                logger.info("    Pass 1 found %d committed issues", len(rock_keys))
            except RuntimeError as e:
                logger.warning("    Pass 1 failed for %s: %s", rock.name, e)

        # --- Pass 2: Candidate issues (component-based, no fixVersion) ---
        if 2 in passes:
            logger.info("  Pass 2 (candidates): %s", rock.name)
            pass2_count = 0
            try:
                issues = self.search_issues(rock.jql)
                for issue in issues:
                    key = issue.key
                    if key not in seen_keys and key not in rock_keys:
                        candidate = self.map_to_candidate(issue, rock.name, "candidate")
                        candidates.append(candidate)
                        rock_keys.add(key)
                        pass2_count += 1
                # Apply exclude_keywords filter
                if rock.exclude_keywords:
                    before = len(candidates)
                    candidates = self._apply_exclude_keywords(candidates, rock.exclude_keywords)
                    # Rebuild rock_keys from remaining candidates
                    rock_keys = {c.issue_key for c in candidates}
                    filtered = before - len(candidates)
                    if filtered > 0:
                        logger.info("    Filtered %d issues by exclude_keywords", filtered)
                logger.info("    Pass 2 found %d candidate issues", pass2_count)
            except RuntimeError as e:
                logger.warning("    Pass 2 failed for %s: %s", rock.name, e)

        # --- Pass 3: RFE issues (from RHAIRFE project) ---
        if 3 in passes and rock.rfe_jql:
            logger.info("  Pass 3 (RFE): %s", rock.name)
            pass3_count = 0
            try:
                issues = self.search_issues(rock.rfe_jql)
                for issue in issues:
                    key = issue.key
                    if key not in seen_keys and key not in rock_keys:
                        candidate = self.map_to_candidate(issue, rock.name, "rfe")
                        candidates.append(candidate)
                        rock_keys.add(key)
                        pass3_count += 1
                logger.info("    Pass 3 found %d RFE issues", pass3_count)
            except RuntimeError as e:
                logger.warning("    Pass 3 failed for %s: %s", rock.name, e)

        return candidates

    def _apply_exclude_keywords(
        self,
        candidates: list[Candidate],
        exclude_keywords: list[str],
    ) -> list[Candidate]:
        """Filter out candidates whose summary matches any exclude keyword.

        Args:
            candidates: List of candidates to filter.
            exclude_keywords: Keywords to match against (case-insensitive substring match).

        Returns:
            Filtered list of candidates.
        """
        if not exclude_keywords:
            return candidates

        filtered: list[Candidate] = []
        for candidate in candidates:
            summary_lower = candidate.summary.lower()
            excluded = False
            for keyword in exclude_keywords:
                if keyword.lower() in summary_lower:
                    logger.debug(
                        "Excluding %s (matched keyword '%s' in summary: %s)",
                        candidate.issue_key,
                        keyword,
                        candidate.summary[:80],
                    )
                    excluded = True
                    break
            if not excluded:
                filtered.append(candidate)

        return filtered

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
