# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Release Planner is a web dashboard and CLI tool for RHOAI release planning. It discovers candidate features and RFEs from Jira using outcome-driven traversal, classifies them into tiers, and presents them in an interactive dashboard with filtering, sorting, and export to Google Sheets.

## Commands

```bash
# Setup
cd release-planner
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # Add your Jira PAT

# Web server (port 9000; runs in demo mode without JIRA_TOKEN)
python -m release_planner serve
python -m release_planner serve --verbose  # debug logging

# CLI
python -m release_planner generate [--create] [--dry-run]
python -m release_planner discover-fields --issue-key RHOAIENG-XXXX
python -m release_planner validate-config
python -m release_planner import-xlsx --xlsx path/to/file.xlsx

# Tests
pytest                              # all unit tests
pytest tests/test_api.py            # single file
pytest -k "test_name"               # single test by name
pytest -m integration               # live Jira tests (excluded by default)

# Lint & format
ruff check src/ tests/
ruff format --check src/ tests/

# Container
make build                          # docker build
make run                            # run with JIRA_TOKEN from env
make run-demo                       # run without credentials (demo mode)
```

## Architecture

### Pipeline (pipeline.py)

The core data flow is a 3-phase pipeline reused by both CLI and API:

1. **Tier 1 discovery:** For each Big Rock's `outcome_keys`, queries `parent = <outcome_key>` to find children. Features (RHAISTRAT) filtered by Target Release; RFEs (RHAIRFE) by candidate label. Deduplicates across rocks, merging Big Rock names.
2. **Tier 2 discovery:** Features with matching Target Release/Fix Version but no Big Rock tie; RFEs with candidate label but no Big Rock.
3. **Tier 3 discovery:** In Progress features with no Target Release and no Fix Version (features only, no RFEs).

After discovery: terminal statuses (Review, Pending Release) are filtered out, YAML overrides are applied, then stats are computed. The pipeline takes a `JiraClient` via dependency injection (pre-connected for web, fresh for CLI).

### API (api.py)

FastAPI app with module-level singletons (Settings, JiraClient, cache). Key endpoints:

- `GET /api/releases` — scans `config/big_rocks*.yaml` files, cached 60 min
- `GET /api/releases/{version}/candidates` — runs pipeline, cached 15 min
- `POST /api/releases/{version}/refresh` — clears cache, 60s cooldown
- `POST /api/export` — creates Google Sheet via SheetsWriter

Without `RELEASE_PLANNER_JIRA_TOKEN`, the API serves sample data (demo mode). Auth via `RELEASE_PLANNER_API_KEY` (disabled if unset).

### Frontend (frontend/)

Vanilla JS/HTML/CSS single-page app served as static files. Three-tab view (Big Rocks, Features, RFEs) with tiered tables, filtering (Pillar, Big Rock, Status, Team, Priority, search), summary cards, and export button. No build step.

### Jira Integration (jira_client.py)

Supports both Server/DC (PAT auth, offset pagination) and Cloud (basic auth, token pagination). Retry logic with exponential backoff (3 attempts). Configurable rate limiting via `JIRA_QUERY_DELAY` (default 1s).

### Config (config/)

`big_rocks.yaml` (or versioned `big_rocks-{version}.yaml`) defines rocks with priority, outcome_keys, pillar, and owner. `data/field_mapping.yaml` maps custom Jira field IDs. `data/overrides.yaml` applies post-pipeline manual corrections.

## Code Style

- Python 3.11+, Ruff for lint/format, line length 100
- Ruff rules: E, F, I, N, W, UP
- Pydantic v2 models throughout
- Tests use pytest with `@pytest.mark.integration` for live Jira tests

## Key Environment Variables

| Variable | Purpose |
|---|---|
| `RELEASE_PLANNER_JIRA_TOKEN` | Jira PAT (falls back to `JIRA_TOKEN`) |
| `JIRA_SERVER` | Jira URL (default: `https://issues.redhat.com`) |
| `RELEASE_PLANNER_API_KEY` | Shared API key; auth disabled if unset |
| `GOOGLE_CREDENTIALS_FILE` | Google service account JSON key (CLI only) |
| `CONFIG_DIR` / `DATA_DIR` | Config and data directories (default: `./config`, `./data`) |

## CI

GitHub Actions (`ci.yml`): lint + unit tests on Python 3.11/3.12 for PRs and pushes to main. `build-image.yml`: builds and pushes Docker image to GHCR on main merges.
