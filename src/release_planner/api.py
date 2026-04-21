"""FastAPI web application: endpoints, static file mounting, error handling."""

from __future__ import annotations

import asyncio
import glob as glob_module
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from release_planner import cache
from release_planner.api_models import (
    CandidateResponse,
    ErrorResponse,
    FeatureRow,
    FilterOptions,
    PillarSummary,
    ReleaseInfo,
    RfeRow,
    RockSummary,
    SummaryStats,
    TierSummary,
)
from release_planner.auth import require_auth
from release_planner.constants import CACHE_TTL_CANDIDATES, CACHE_TTL_RELEASES
from release_planner.config import Settings, load_big_rocks, load_field_mapping
from release_planner.constants import JIRA_BROWSE_URL
from release_planner.pipeline import (
    ConfigError,
    JiraConnectionError,
    PipelineError,
    PipelineResult,
    run_pipeline,
)
from release_planner.sample_data import get_sample_response

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"^[0-9]+(\.[0-9]+){0,2}$")

# ---- Application setup ----

app = FastAPI(
    title="Release Planner",
    description="RHOAI Release Planning Dashboard",
    version="0.1.0",
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'"
    return response


# ---- Module-level state (initialized at import time) ----

_settings: Settings = Settings.for_web()
_jira_client = None  # Lazy-initialized on first pipeline run
_last_refresh_times: dict[str, float] = {}  # version -> timestamp for rate limiting
_REFRESH_COOLDOWN = 60  # seconds
_MAX_REFRESH_ENTRIES = 100


def _validate_version(version: str) -> None:
    """Reject version strings that don't match semver-like patterns (H1)."""
    if not _VERSION_RE.match(version):
        raise HTTPException(status_code=400, detail="Invalid release version format")


def _is_demo_mode() -> bool:
    """Check if the server is running in demo mode (no Jira credentials)."""
    return not _settings.jira_token


def _resolve_frontend_dir() -> Path:
    """Resolve the frontend/ directory using the fallback chain (M3).

    1. RELEASE_PLANNER_FRONTEND_DIR env var
    2. Path(__file__).parent.parent.parent / "frontend" (dev installs)
    3. Raise ConfigError with a clear message
    """
    env_dir = os.environ.get("RELEASE_PLANNER_FRONTEND_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.is_dir():
            return p
        raise ConfigError(
            f"RELEASE_PLANNER_FRONTEND_DIR={env_dir} is not a valid directory"
        )

    dev_path = Path(__file__).parent.parent.parent / "frontend"
    if dev_path.is_dir():
        return dev_path

    raise ConfigError(
        "frontend/ directory not found. Set RELEASE_PLANNER_FRONTEND_DIR "
        "to the path containing index.html, app.js, and style.css."
    )


def _get_jira_client():
    """Get or create a shared JiraClient instance (M1: dependency injection)."""
    global _jira_client
    if _jira_client is not None:
        return _jira_client

    if _is_demo_mode():
        return None

    from release_planner.jira_client import JiraClient

    _jira_client = JiraClient(
        server=_settings.jira_server,
        token=_settings.jira_token,
        email=_settings.jira_email,
        field_mapping=_load_field_mapping(),
        query_delay=_settings.query_delay,
    )
    _jira_client.connect()
    return _jira_client


def _load_field_mapping() -> dict[str, str]:
    """Load field mapping from the data directory."""
    return load_field_mapping(_settings.data_dir)


def _load_overrides():
    """Load overrides from the data directory."""
    from release_planner.overrides import OverrideLoader

    overrides_path = f"{_settings.data_dir}/overrides.yaml"
    loader = OverrideLoader(overrides_path)
    try:
        return loader.load()
    except RuntimeError:
        logger.warning("Failed to load overrides from %s", overrides_path)
        return None


def _discover_releases() -> list[ReleaseInfo]:
    """Scan the config directory for big_rocks*.yaml files.

    Returns a list of ReleaseInfo objects, one per discovered config file.
    The bare big_rocks.yaml is always included as the default release.
    """
    cached = cache.get("releases", ttl=CACHE_TTL_RELEASES)
    if cached is not None:
        return cached

    config_dir = _settings.config_dir
    releases: list[ReleaseInfo] = []

    # Always include the default big_rocks.yaml
    default_path = Path(config_dir) / "big_rocks.yaml"
    if default_path.exists():
        try:
            with open(default_path) as f:
                raw = yaml.safe_load(f)
            version = raw.get("release", "")
            if version:
                releases.append(
                    ReleaseInfo(version=version, label=f"rhoai-{version}")
                )
        except Exception as e:
            logger.error("Failed to parse %s: %s", default_path, e)

    # Scan for big_rocks-*.yaml (dash required)
    pattern = str(Path(config_dir) / "big_rocks-*.yaml")
    for filepath in sorted(glob_module.glob(pattern)):
        try:
            with open(filepath) as f:
                raw = yaml.safe_load(f)
            version = raw.get("release", "")
            if version and not any(r.version == version for r in releases):
                releases.append(
                    ReleaseInfo(version=version, label=f"rhoai-{version}")
                )
        except Exception as e:
            logger.error("Failed to parse %s: %s", filepath, e)

    # If no releases found, add a default for demo mode
    if not releases:
        releases.append(ReleaseInfo(version="3.5", label="rhoai-3.5"))

    cache.put("releases", releases)
    return releases


def _find_config_file_for_version(version: str) -> str | None:
    """Find the config file for a given release version.

    Returns the filename (not full path) or None if not found.
    """
    config_dir = _settings.config_dir

    # Check versioned file first
    versioned = f"big_rocks-{version}.yaml"
    if (Path(config_dir) / versioned).exists():
        return versioned

    # Check default file
    default_path = Path(config_dir) / "big_rocks.yaml"
    if default_path.exists():
        try:
            with open(default_path) as f:
                raw = yaml.safe_load(f)
            if raw.get("release") == version:
                return "big_rocks.yaml"
        except Exception:
            pass

    return None


def _build_candidate_response(
    result: PipelineResult, version: str, demo_mode: bool = False
) -> CandidateResponse:
    """Convert a PipelineResult into a CandidateResponse for the API.

    Args:
        result: Pipeline result with raw data.
        version: Release version string.
        demo_mode: Whether this is sample data.

    Returns:
        CandidateResponse ready for JSON serialization.
    """
    # Build RockSummary list
    rock_summaries: list[RockSummary] = []
    for rock in result.big_rocks:
        stats = result.per_rock_stats.get(rock.name, {})
        outcome_descs = {
            k: result.outcome_summaries.get(k, "") for k in rock.outcome_keys
        }
        rock_summaries.append(
            RockSummary(
                priority=rock.priority,
                name=rock.name,
                full_name=rock.full_name,
                pillar=rock.pillar,
                state=rock.state,
                owner=rock.owner,
                outcome_keys=rock.outcome_keys,
                outcome_descriptions=outcome_descs,
                feature_count=stats.get("features", 0),
                rfe_count=stats.get("rfes", 0),
                notes=rock.notes,
            )
        )

    # Build FeatureRow list
    feature_rows: list[FeatureRow] = []
    for c in result.features:
        feature_rows.append(
            FeatureRow(
                big_rock=c.big_rock,
                issue_key=c.issue_key,
                status=c.status,
                priority=c.priority,
                phase=c.phase,
                summary=c.summary,
                components=c.components,
                target_release=c.target_release,
                fix_version=c.fix_version,
                pm=c.pm,
                delivery_owner=c.delivery_owner,
                rfe=c.rfe,
                labels=c.labels,
            )
        )

    # Build RfeRow list
    rfe_rows: list[RfeRow] = []
    for c in result.rfes:
        rfe_rows.append(
            RfeRow(
                big_rock=c.big_rock,
                issue_key=c.issue_key,
                status=c.status,
                priority=c.priority,
                summary=c.summary,
                components=c.components,
                pm=c.pm,
                labels=c.labels,
            )
        )

    # Build summary stats
    per_rock: dict[str, PillarSummary] = {}

    for rock in result.big_rocks:
        stats = result.per_rock_stats.get(rock.name, {})
        feat_count = stats.get("features", 0)
        rfe_count = stats.get("rfes", 0)
        per_rock[rock.name] = PillarSummary(features=feat_count, rfes=rfe_count)

    rocks_with_data = sum(
        1
        for r in result.big_rocks
        if result.per_rock_stats.get(r.name, {}).get("features", 0) > 0
        or result.per_rock_stats.get(r.name, {}).get("rfes", 0) > 0
    )

    tier1 = TierSummary(
        features=result.tier1_features,
        rfes=result.tier1_rfes,
        description="Big Rock-associated features and RFEs that PM has identified as essential for this release.",
    )
    tier2 = TierSummary(
        features=result.tier2_features,
        rfes=result.tier2_rfes,
        description="Features and RFEs not tied to Big Rocks, but PM believes are important for customers or represent significant usability improvements.",
    )

    summary = SummaryStats(
        total_features=len(feature_rows),
        total_rfes=len(rfe_rows),
        total_big_rocks=len(result.big_rocks),
        rocks_with_data=rocks_with_data,
        tier1=tier1,
        tier2=tier2,
        per_rock=per_rock,
    )

    # Build filter options
    all_statuses = sorted(
        {f.status for f in feature_rows if f.status}
        | {r.status for r in rfe_rows if r.status}
    )
    all_teams = sorted({f.components for f in feature_rows if f.components})
    all_priorities = sorted(
        {f.priority for f in feature_rows if f.priority}
        | {r.priority for r in rfe_rows if r.priority}
    )

    filter_options = FilterOptions(
        pillars=sorted({r.pillar for r in result.big_rocks if r.pillar}),
        rocks=[r.name for r in result.big_rocks],
        statuses=all_statuses,
        teams=all_teams,
        priorities=all_priorities,
    )

    return CandidateResponse(
        version=version,
        jira_base_url=JIRA_BROWSE_URL,
        last_refreshed=datetime.now(timezone.utc),
        demo_mode=demo_mode,
        summary=summary,
        big_rocks=rock_summaries,
        features=feature_rows,
        rfes=rfe_rows,
        filter_options=filter_options,
    )


async def _get_or_run_pipeline(version: str) -> CandidateResponse:
    """Get cached result or run pipeline in a background thread (M2).

    Args:
        version: Release version string.

    Returns:
        CandidateResponse with data for the requested release.

    Raises:
        HTTPException: If the release is not found or pipeline fails.
    """
    # Check cache first
    cache_key = f"candidates:{version}"
    cached = cache.get(cache_key, ttl=CACHE_TTL_CANDIDATES)
    if cached is not None:
        return cached

    # Demo mode: return sample data
    if _is_demo_mode():
        response = get_sample_response(version)
        cache.put(cache_key, response)
        return response

    # Find config file for this version
    config_file = _find_config_file_for_version(version)
    if config_file is None:
        raise HTTPException(
            status_code=404,
            detail=f"No configuration found for release {version}",
        )

    # Load config
    try:
        big_rocks, br_config = load_big_rocks(
            _settings.config_dir, config_file=config_file
        )
    except FileNotFoundError as e:
        logger.error("Config file not found for release %s: %s", version, e)
        raise HTTPException(
            status_code=404,
            detail=f"Configuration not found for release {version}",
        ) from e
    except Exception as e:
        logger.error("Config error for release %s: %s", version, e)
        raise HTTPException(
            status_code=500,
            detail="Failed to load release configuration",
        ) from e

    field_mapping = _load_field_mapping()
    overrides = _load_overrides()
    jira_client = _get_jira_client()

    # Run blocking pipeline in thread pool (M2)
    try:
        result = await asyncio.to_thread(
            run_pipeline,
            settings=_settings,
            big_rocks=big_rocks,
            field_mapping=field_mapping,
            overrides=overrides,
            release=version,
            jira_client=jira_client,
        )
    except JiraConnectionError as e:
        logger.error("Jira connection error: %s", e)
        raise HTTPException(status_code=502, detail="Failed to connect to upstream data source") from e
    except ConfigError as e:
        logger.error("Pipeline config error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to load release configuration") from e
    except PipelineError as e:
        logger.error("Pipeline error: %s", e)
        raise HTTPException(status_code=500, detail="Pipeline execution failed") from e

    response = _build_candidate_response(result, version)
    cache.put(cache_key, response)
    return response


# ---- Exception handlers (M7) ----


@app.exception_handler(PipelineError)
async def pipeline_error_handler(request: Request, exc: PipelineError) -> JSONResponse:
    """Handle PipelineError and subclasses with appropriate HTTP status codes."""
    logger.error("Pipeline error: %s", exc)
    if isinstance(exc, JiraConnectionError):
        return JSONResponse(
            status_code=502,
            content={"error": "jira_upstream_error", "detail": "Failed to connect to upstream data source"},
        )
    if isinstance(exc, ConfigError):
        return JSONResponse(
            status_code=500,
            content={"error": "config_error", "detail": "Failed to load release configuration"},
        )
    return JSONResponse(
        status_code=500,
        content={"error": "pipeline_error", "detail": "Pipeline execution failed"},
    )


@app.exception_handler(Exception)
async def general_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions. Log details, return generic message."""
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": "An unexpected error occurred."},
    )


# ---- API Endpoints ----


@app.get("/api/status")
async def get_status():
    """Public health check (no auth). Returns demo mode flag."""
    return {"demo_mode": _is_demo_mode(), "authenticated": True}


@app.get("/healthz")
async def healthz():
    """Kubernetes liveness/readiness probe."""
    return {"status": "ok"}


@app.get("/api/releases", response_model=list[ReleaseInfo])
async def get_releases(_auth: str = Depends(require_auth)):
    """List available releases derived from config directory."""
    return _discover_releases()


@app.get("/api/releases/{version}/candidates", response_model=CandidateResponse)
async def get_candidates(version: str, _auth: str = Depends(require_auth)):
    """Get the full dataset for a release.

    Returns Big Rocks, Features, RFEs, summary stats, and filter options.
    Data is cached for 15 minutes.
    """
    _validate_version(version)
    return await _get_or_run_pipeline(version)


@app.post("/api/releases/{version}/export")
async def export_sheets(version: str, _auth: str = Depends(require_auth)):
    """Create a Google Spreadsheet with the release data and return its URL.

    Uses the existing SheetsWriter (same format as CLI --sheets).
    Requires GOOGLE_CREDENTIALS_FILE or GOOGLE_CREDENTIALS_JSON to be configured.
    """
    _validate_version(version)
    response = await _get_or_run_pipeline(version)

    if response.demo_mode:
        raise HTTPException(
            status_code=400,
            detail="Google Sheets export is not available in demo mode. "
            "Configure JIRA_TOKEN for live data.",
        )

    config_file = _find_config_file_for_version(version)
    if config_file is None:
        raise HTTPException(status_code=404, detail=f"Release {version} not found")

    big_rocks, _ = load_big_rocks(_settings.config_dir, config_file=config_file)
    field_mapping = _load_field_mapping()
    overrides = _load_overrides()
    jira_client = _get_jira_client()

    try:
        result = await asyncio.to_thread(
            run_pipeline,
            settings=_settings,
            big_rocks=big_rocks,
            field_mapping=field_mapping,
            overrides=overrides,
            release=version,
            jira_client=jira_client,
        )
    except PipelineError as e:
        logger.error("Pipeline error during export: %s", e)
        raise HTTPException(status_code=500, detail="Pipeline execution failed") from e

    from release_planner.sheets_writer import SheetsWriter

    try:
        credentials = SheetsWriter.load_credentials()
    except RuntimeError as e:
        logger.error("Google credentials not configured: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Google Sheets credentials are not configured. "
            "Set GOOGLE_CREDENTIALS_FILE or GOOGLE_CREDENTIALS_JSON.",
        ) from e

    title = f"RHOAI {version} Release Candidates"

    try:
        writer = SheetsWriter(
            big_rocks=result.big_rocks,
            candidates=result.candidates,
            release=result.release,
            credentials=credentials,
            per_rock_stats=result.per_rock_stats,
            outcome_summaries=result.outcome_summaries,
        )
        url = await asyncio.to_thread(writer.create_and_write, title)
    except Exception as e:
        logger.error("Google Sheets export failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to create Google Spreadsheet",
        ) from e

    return {"url": url}


@app.post("/api/releases/{version}/refresh", response_model=CandidateResponse)
async def refresh_release(version: str, _auth: str = Depends(require_auth)):
    """Force-clear cache and re-fetch data from Jira.

    Rate limited: rejects requests for the same release within 60 seconds.
    """
    _validate_version(version)
    now = time.time()
    last_refresh = _last_refresh_times.get(version, 0)
    if now - last_refresh < _REFRESH_COOLDOWN:
        remaining = int(_REFRESH_COOLDOWN - (now - last_refresh))
        raise HTTPException(
            status_code=429,
            detail=f"Try again in {remaining}s.",
        )

    logger.info("Manual refresh triggered for release %s", version)
    if len(_last_refresh_times) >= _MAX_REFRESH_ENTRIES:
        oldest_key = min(_last_refresh_times, key=_last_refresh_times.get)
        del _last_refresh_times[oldest_key]
    _last_refresh_times[version] = now

    # Invalidate cache
    cache.invalidate(f"candidates:{version}")

    # Re-run pipeline
    return await _get_or_run_pipeline(version)


# ---- Static file mounting ----

try:
    _frontend_dir = _resolve_frontend_dir()
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
    logger.info("Serving frontend from %s", _frontend_dir)
except ConfigError as e:
    logger.warning("Frontend not available: %s", e)
