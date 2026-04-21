# Release Planner

Web dashboard and CLI tool for RHOAI release planning. Discovers candidate features and RFEs from Jira using outcome-driven traversal, classifies them into tiers, and presents them in an interactive dashboard with filtering, sorting, and export.

## Web Dashboard

The primary interface is a browser-based dashboard served by FastAPI.

```bash
# Setup
cd release-planner
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # Edit with your Jira PAT

# Start the web server
python -m release_planner serve

# With debug logging
python -m release_planner serve --verbose
```

Open http://localhost:9000 in your browser. Without a `RELEASE_PLANNER_JIRA_TOKEN`, the dashboard runs in **demo mode** with sample data.

### Dashboard Features

- **Three-tab view:** Big Rocks, Features, and RFEs with item counts in tab labels
- **Tiered classification:** items grouped into Tier 1 (Milestone Essentials), Tier 2 (Enhancements), and Tier 3 (Collaborative Support) with visual separator rows
- **Filtering:** by Pillar, Big Rock, Status, Team, Priority, and free-text search
- **Summary cards:** per-tier counts with release-aware labels
- **Release selector:** switch between configured releases
- **Export:** one-click export to Google Sheets
- **Auto-refresh:** data cached with configurable TTL; manual refresh via header button

### Tier Classification

| Tier | Name | What's Included |
|------|------|-----------------|
| **1** | Milestone Essentials | Features and RFEs tied to Big Rock outcomes, filtered by Target Release / candidate label |
| **2** | Enhancements | Features with a matching Target Release or Fix Version but not tied to a Big Rock; RFEs with a candidate label but no Big Rock |
| **3** | Collaborative Support | In Progress features with no Target Release or Fix Version set (features only, no RFEs) |

Within Tier 1, items are sorted by Big Rock priority, then by issue priority within each rock. Tiers 2 and 3 are sorted by issue priority only.

## Container Deployment

### Local (Podman/Docker)

```bash
# Build
podman build -t release-planner:local .

# Run (mount config, pass credentials from .env)
podman run -d \
  --name release-planner \
  -p 9000:9000 \
  -v ./config:/opt/app-root/config:ro \
  --env-file .env \
  -e RELEASE_PLANNER_HOST=0.0.0.0 \
  release-planner:local
```

Teammates on the same network can access the dashboard at `http://<your-ip>:9000`.

### OpenShift

Kubernetes manifests are in `k8s/`:

```
k8s/
  deployment.yaml
  service.yaml
  route.yaml
  secret.example.yaml
  configmap-config.yaml
  configmap-data.yaml
```

## CLI Commands

The CLI provides additional workflows beyond the web dashboard.

### `serve`

Start the web server.

```bash
python -m release_planner serve [--host HOST] [--port PORT] [-v]
```

### `generate`

Generate the release planning spreadsheet in Google Sheets.

```bash
python -m release_planner generate [OPTIONS]
```

Options:
- `--spreadsheet-id TEXT` -- Google Sheets ID to update
- `--spreadsheet-name TEXT` -- Name for new spreadsheet (requires `--create`)
- `--create` -- Create a new spreadsheet
- `--share-with TEXT` -- Email to share with (repeatable)
- `--dry-run` -- Query Jira only, skip output
- `--rocks TEXT` -- Filter to specific rocks (repeatable)
- `--no-overrides` -- Skip manual overrides
- `-v, --verbose` -- Debug logging

### `discover-fields`

Discover custom field IDs from a sample Jira issue.

```bash
python -m release_planner discover-fields --issue-key RHOAIENG-XXXX
```

### `validate-config`

Validate configuration files without querying Jira.

```bash
python -m release_planner validate-config
```

### `import-xlsx`

Import an existing `.xlsx` spreadsheet to bootstrap `overrides.yaml`.

```bash
python -m release_planner import-xlsx --xlsx path/to/file.xlsx [-o output.yaml]
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/healthz` | No | Health check |
| `GET` | `/api/status` | No | Server status and demo mode flag |
| `GET` | `/api/releases` | Yes* | List configured releases |
| `GET` | `/api/releases/{version}/candidates` | Yes* | Full candidate data, summary stats, and filter options |
| `POST` | `/api/releases/{version}/refresh` | Yes* | Clear cache and re-fetch from Jira |

*Auth is only enforced when `RELEASE_PLANNER_API_KEY` is set.

## Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `RELEASE_PLANNER_JIRA_TOKEN` | Yes | -- | Jira API token (falls back to `JIRA_TOKEN`) |
| `JIRA_SERVER` | No | `https://issues.redhat.com` | Jira instance URL |
| `JIRA_EMAIL` | No | -- | Email for Jira Cloud basic auth |
| `RELEASE_PLANNER_HOST` | No | `127.0.0.1` | Server bind address (`0.0.0.0` for containers) |
| `RELEASE_PLANNER_PORT` | No | `9000` | Server port |
| `RELEASE_PLANNER_API_KEY` | No | -- | Shared API key; auth disabled if unset |
| `RELEASE_PLANNER_LOG_FORMAT` | No | `text` | Log format (`text` or `json`) |
| `GOOGLE_CREDENTIALS_FILE` | CLI only | -- | Path to Google service account JSON key |
| `GOOGLE_CREDENTIALS_JSON` | CLI only | -- | Inline Google service account JSON |
| `DEFAULT_SPREADSHEET_ID` | No | -- | Default spreadsheet ID for `generate` |
| `JIRA_QUERY_DELAY` | No | `1.0` | Seconds between Jira API queries |
| `CONFIG_DIR` | No | `./config` | Config directory for YAML files |
| `DATA_DIR` | No | `./data` | Data directory for overrides |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity |

## How It Works

Each Big Rock in `config/big_rocks.yaml` declares Jira Outcome keys. The pipeline:

1. **Tier 1 discovery:** queries `parent = <outcome_key>` for each Big Rock outcome to find direct children. Features (`RHAISTRAT-*`) are included if Target Release matches; RFEs (`RHAIRFE-*`) if they carry the release candidate label. Terminal statuses (Review, Pending Release) are filtered out. Duplicates across Big Rocks are merged into a single row.
2. **Tier 2 discovery:** finds Features with a matching Target Release or Fix Version and RFEs with a candidate label that were not discovered in Tier 1.
3. **Tier 3 discovery:** finds In Progress Features with no Target Release and no Fix Version (features only). A post-filter catches items where the JQL field name differs from the custom field mapping.
4. **Overrides:** optional YAML overrides can modify or add entries.
5. **Output:** structured result served via API, rendered in the dashboard, or written to Google Sheets.

## Development

```bash
pip install -e ".[dev]"

# Run tests
pytest

# Run a single test file
pytest tests/test_api.py

# Lint and format
ruff check src/ tests/
ruff format --check src/ tests/
```

## Project Structure

```
release-planner/
  src/release_planner/
    api.py              # FastAPI endpoints and static file serving
    api_models.py       # Pydantic response models for the API
    auth.py             # API key authentication middleware
    cache.py            # In-memory cache with TTL
    cli.py              # Click CLI commands
    config.py           # Settings loader, YAML config parser
    constants.py        # Column enums, URLs, cache TTLs
    excel_writer.py     # Excel (.xlsx) writer
    importer.py         # .xlsx import for bootstrapping overrides
    jira_client.py      # Jira connection and issue discovery
    logging_config.py   # Structured logging setup
    models.py           # Pydantic v2 data models
    overrides.py        # YAML override loader and merger
    pipeline.py         # Core data pipeline (fetch, classify, deduplicate)
    sample_data.py      # Demo mode sample data generator
    sheets_writer.py    # Google Sheets writer via gspread
  frontend/
    index.html          # Dashboard HTML
    app.js              # Dashboard logic (vanilla JS)
    style.css           # Dashboard styles
  config/
    big_rocks.yaml      # Big Rock definitions with outcome keys
  k8s/                  # OpenShift/Kubernetes manifests
  tests/
  Dockerfile
```
