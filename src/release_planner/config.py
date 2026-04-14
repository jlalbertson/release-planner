"""Configuration management: settings loader, Big Rock loader, field mapping loader."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

from release_planner.constants import JIRA_QUERY_DELAY_DEFAULT, JIRA_SERVER_DEFAULT
from release_planner.models import BigRock

logger = logging.getLogger(__name__)


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    jira_server: str = JIRA_SERVER_DEFAULT
    jira_token: str = field(default="", repr=False)
    jira_email: str | None = None
    google_credentials_file: str | None = None
    google_credentials_json: str | None = field(default=None, repr=False)
    default_spreadsheet_id: str | None = None
    config_dir: str = "./config"
    data_dir: str = "./data"
    log_level: str = "INFO"
    query_delay: float = JIRA_QUERY_DELAY_DEFAULT

    @classmethod
    def from_env(cls, require_google: bool = True) -> Settings:
        """Load from environment with python-dotenv.

        Checks RELEASE_PLANNER_JIRA_TOKEN first, falls back to JIRA_TOKEN.
        Raises RuntimeError if neither is set.
        Checks for Google credentials (file or inline JSON) if require_google is True.

        Args:
            require_google: If True, raise if no Google credentials are set.
                Set to False for commands that don't need Google Sheets access
                (e.g. discover-fields, validate-config).
        """
        load_dotenv()

        token = os.environ.get("RELEASE_PLANNER_JIRA_TOKEN") or os.environ.get("JIRA_TOKEN")
        if not token:
            raise RuntimeError(
                "RELEASE_PLANNER_JIRA_TOKEN (or JIRA_TOKEN) must be set. "
                "See .env.example for details."
            )

        google_creds_file = os.environ.get("GOOGLE_CREDENTIALS_FILE")
        google_creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
        if require_google and not google_creds_file and not google_creds_json:
            raise RuntimeError(
                "GOOGLE_CREDENTIALS_FILE or GOOGLE_CREDENTIALS_JSON must be set. "
                "See the design doc Section 5.5 for setup instructions."
            )

        query_delay_str = os.environ.get("JIRA_QUERY_DELAY", "")
        try:
            query_delay = float(query_delay_str) if query_delay_str else JIRA_QUERY_DELAY_DEFAULT
        except ValueError:
            logger.warning(
                "Invalid JIRA_QUERY_DELAY value '%s', using default %s",
                query_delay_str,
                JIRA_QUERY_DELAY_DEFAULT,
            )
            query_delay = JIRA_QUERY_DELAY_DEFAULT

        return cls(
            jira_server=os.environ.get("JIRA_SERVER", JIRA_SERVER_DEFAULT),
            jira_token=token,
            jira_email=os.environ.get("JIRA_EMAIL"),
            google_credentials_file=google_creds_file,
            google_credentials_json=google_creds_json,
            default_spreadsheet_id=os.environ.get("DEFAULT_SPREADSHEET_ID"),
            config_dir=os.environ.get("CONFIG_DIR", "./config"),
            data_dir=os.environ.get("DATA_DIR", "./data"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            query_delay=query_delay,
        )


@dataclass
class BigRockConfig:
    """Parsed big_rocks.yaml configuration."""

    release: str
    fix_versions: list[str]
    projects: str
    big_rocks: list[BigRock]


def load_big_rocks_config(config_dir: str) -> BigRockConfig:
    """Parse big_rocks.yaml into a BigRockConfig with raw (unsubstituted) data.

    Returns:
        BigRockConfig with raw YAML data. Call substitute_release() to fill placeholders.
    """
    config_path = Path(config_dir) / "big_rocks.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Big Rocks config not found: {config_path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    release = raw.get("release", "")
    projects = raw.get("projects", "")
    fix_versions_raw = raw.get("fix_versions", [])

    rocks_raw = raw.get("big_rocks", [])
    rocks: list[BigRock] = []
    for rock_data in rocks_raw:
        rocks.append(BigRock(**rock_data))

    return BigRockConfig(
        release=release,
        fix_versions=fix_versions_raw,
        projects=projects,
        big_rocks=rocks,
    )


def load_big_rocks(
    config_dir: str, release: str | None = None
) -> tuple[list[BigRock], BigRockConfig]:
    """Parse big_rocks.yaml and substitute {release} and {projects} placeholders.

    Args:
        config_dir: Path to config directory containing big_rocks.yaml.
        release: Override release version. If None, uses the value from YAML.

    Returns:
        Tuple of (list of BigRock models with substituted JQL, BigRockConfig).
    """
    config = load_big_rocks_config(config_dir)

    effective_release = release or config.release
    projects = config.projects

    # Substitute placeholders in fix_versions
    fix_versions = [fv.replace("{release}", effective_release) for fv in config.fix_versions]

    # Substitute placeholders in each rock's JQL
    substituted_rocks: list[BigRock] = []
    for rock in config.big_rocks:
        jql = rock.jql.replace("{release}", effective_release).replace("{projects}", projects)
        rfe_jql = rock.rfe_jql.replace("{release}", effective_release).replace(
            "{projects}", projects
        )
        substituted = rock.model_copy(update={"jql": jql, "rfe_jql": rfe_jql})
        substituted_rocks.append(substituted)

    config.release = effective_release
    config.fix_versions = fix_versions
    config.big_rocks = substituted_rocks

    return substituted_rocks, config


def load_field_mapping(data_dir: str) -> dict[str, str]:
    """Parse data/field_mapping.yaml into field name -> custom field ID dict.

    Returns an empty dict if the file does not exist (field mapping is optional).
    """
    mapping_path = Path(data_dir) / "field_mapping.yaml"
    if not mapping_path.exists():
        logger.info("No field mapping file found at %s, using defaults", mapping_path)
        return {}

    with open(mapping_path) as f:
        raw = yaml.safe_load(f)

    if not raw or not isinstance(raw, dict):
        logger.warning("Field mapping file %s is empty or invalid", mapping_path)
        return {}

    return {str(k): str(v) for k, v in raw.items()}
