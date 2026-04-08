# Release Planner

RHOAI release planning spreadsheet generator. Queries `issues.redhat.com` (Jira Server/DC) to discover candidate issues for each Big Rock, and writes the results to a Google Spreadsheet with two worksheets: **"{release} Candidates"** and **"Big Rocks"**.

## Features

- **Three-pass discovery strategy:** fixVersion-tagged (committed), component-based (candidates), RFE-based
- **15 Big Rocks** with configurable JQL queries and component mappings
- **Google Sheets output** via service account authentication
- **Manual overrides** via YAML for fields not available in Jira
- **Spreadsheet import** (`import-xlsx`) to bootstrap overrides from existing `.xlsx` files
- **Field discovery** command to find custom field IDs on `issues.redhat.com`
- **Rate limiting** and retry logic for Jira API calls

## Quick Start

```bash
# Setup
cd release-planner
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # Edit with your PAT and Google credentials path

# Discover Jira custom fields (first-time setup)
python -m release_planner discover-fields --issue-key RHOAIENG-XXXX

# Validate configuration
python -m release_planner validate-config

# Generate to a new Google Spreadsheet
python -m release_planner generate --create --spreadsheet-name "RHOAI 3.5 Candidates" --verbose

# Generate to an existing spreadsheet
python -m release_planner generate --spreadsheet-id YOUR_SPREADSHEET_ID --verbose

# Dry run (query Jira but don't write to Google Sheets)
python -m release_planner generate --dry-run --verbose

# Import existing spreadsheet to bootstrap overrides
pip install release-planner[import]
python -m release_planner import-xlsx --xlsx ~/Downloads/planning-3.5.xlsx
```

## Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `RELEASE_PLANNER_JIRA_TOKEN` | Yes | -- | PAT for `issues.redhat.com`. Falls back to `JIRA_TOKEN`. |
| `GOOGLE_CREDENTIALS_FILE` | Yes* | -- | Path to Google service account JSON key file |
| `GOOGLE_CREDENTIALS_JSON` | Yes* | -- | Inline Google service account JSON (for CI/containers) |
| `DEFAULT_SPREADSHEET_ID` | No | -- | Default spreadsheet ID when `--spreadsheet-id` is not passed |
| `JIRA_SERVER` | No | `https://issues.redhat.com` | Jira Server/DC instance URL |
| `JIRA_QUERY_DELAY` | No | `1.0` | Seconds between Jira API queries |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity |
| `CONFIG_DIR` | No | `./config` | Config directory for YAML files |
| `DATA_DIR` | No | `./data` | Data directory for overrides and field mapping |

*One of `GOOGLE_CREDENTIALS_FILE` or `GOOGLE_CREDENTIALS_JSON` is required.

## Google Service Account Setup

1. Create or select a Google Cloud project
2. Enable the **Google Sheets API**
3. Create a **service account** (APIs & Services > Credentials)
4. Download the JSON key file
5. Set `GOOGLE_CREDENTIALS_FILE=/path/to/service-account.json`
6. Share your target spreadsheet with the service account email (as Editor)

See the design doc (Section 5.5) for detailed instructions.

## CLI Commands

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
- `--passes TEXT` -- Comma-separated passes: 1,2,3 (default: all)
- `--duplicate-mode [first|all]` -- Cross-rock dedup mode (default: first)
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

## Three-Pass Discovery Strategy

| Pass | JQL Filter | Tag | Purpose |
|------|-----------|-----|---------|
| 1 | fixVersion + component | `committed` | Issues already tagged for the release |
| 2 | Component-only | `candidate` | Untagged issues in matching components |
| 3 | RHAIRFE project | `rfe` | RFE-only entries with no RHAISTRAT/RHOAIENG key |

Pass 2 intentionally produces a superset. The `source_pass` tag lets users see which issues are committed vs. candidates vs. RFE-only.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ -v --cov=release_planner --cov-report=term-missing

# Lint
ruff check src/ tests/
ruff format --check src/ tests/
```

## Project Structure

```
release-planner/
  src/release_planner/
    cli.py              # Click CLI commands
    config.py           # Settings loader, YAML config parser
    models.py           # Pydantic v2 models
    jira_client.py      # Jira connection and three-pass discovery
    sheets_writer.py    # Google Sheets writer via gspread
    overrides.py        # YAML override loader and merger
    importer.py         # .xlsx import for bootstrapping overrides
    constants.py        # Column enums, style constants
  config/
    big_rocks.yaml      # 15 Big Rock definitions with JQL
  data/
    overrides.yaml      # Manual overrides (gitignored)
  tests/
    ...
```
