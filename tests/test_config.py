"""Tests for config.py: settings loader, big rocks loader, field mapping."""

from unittest.mock import patch

import pytest

from release_planner.config import Settings, load_big_rocks, load_field_mapping


class TestSettings:
    """Tests for Settings.from_env()."""

    @patch("release_planner.config.load_dotenv")
    def test_from_env_with_release_planner_token(self, _mock_dotenv, tmp_path, monkeypatch):
        monkeypatch.setenv("RELEASE_PLANNER_JIRA_TOKEN", "test-token")
        monkeypatch.setenv("GOOGLE_CREDENTIALS_FILE", "/tmp/creds.json")
        monkeypatch.delenv("JIRA_TOKEN", raising=False)

        settings = Settings.from_env()
        assert settings.jira_token == "test-token"

    @patch("release_planner.config.load_dotenv")
    def test_from_env_falls_back_to_jira_token(self, _mock_dotenv, monkeypatch):
        monkeypatch.delenv("RELEASE_PLANNER_JIRA_TOKEN", raising=False)
        monkeypatch.setenv("JIRA_TOKEN", "fallback-token")
        monkeypatch.setenv("GOOGLE_CREDENTIALS_FILE", "/tmp/creds.json")

        settings = Settings.from_env()
        assert settings.jira_token == "fallback-token"

    @patch("release_planner.config.load_dotenv")
    def test_from_env_missing_token_raises(self, _mock_dotenv, monkeypatch):
        monkeypatch.delenv("RELEASE_PLANNER_JIRA_TOKEN", raising=False)
        monkeypatch.delenv("JIRA_TOKEN", raising=False)
        monkeypatch.setenv("GOOGLE_CREDENTIALS_FILE", "/tmp/creds.json")

        with pytest.raises(RuntimeError, match="RELEASE_PLANNER_JIRA_TOKEN"):
            Settings.from_env()

    @patch("release_planner.config.load_dotenv")
    def test_from_env_missing_google_credentials_raises(self, _mock_dotenv, monkeypatch):
        monkeypatch.setenv("RELEASE_PLANNER_JIRA_TOKEN", "test-token")
        monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
        monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)

        with pytest.raises(RuntimeError, match="GOOGLE_CREDENTIALS_FILE"):
            Settings.from_env(require_google=True)

    @patch("release_planner.config.load_dotenv")
    def test_from_env_google_credentials_not_required(self, _mock_dotenv, monkeypatch):
        monkeypatch.setenv("RELEASE_PLANNER_JIRA_TOKEN", "test-token")
        monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
        monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)

        settings = Settings.from_env(require_google=False)
        assert settings.jira_token == "test-token"
        assert settings.google_credentials_file is None

    @patch("release_planner.config.load_dotenv")
    def test_from_env_default_values(self, _mock_dotenv, monkeypatch):
        monkeypatch.setenv("RELEASE_PLANNER_JIRA_TOKEN", "token")
        monkeypatch.setenv("GOOGLE_CREDENTIALS_FILE", "/tmp/creds.json")
        monkeypatch.delenv("JIRA_SERVER", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.delenv("JIRA_QUERY_DELAY", raising=False)

        settings = Settings.from_env()
        assert settings.jira_server == "https://issues.redhat.com"
        assert settings.log_level == "INFO"
        assert settings.query_delay == 1.0

    @patch("release_planner.config.load_dotenv")
    def test_from_env_custom_query_delay(self, _mock_dotenv, monkeypatch):
        monkeypatch.setenv("RELEASE_PLANNER_JIRA_TOKEN", "token")
        monkeypatch.setenv("GOOGLE_CREDENTIALS_FILE", "/tmp/creds.json")
        monkeypatch.setenv("JIRA_QUERY_DELAY", "2.5")

        settings = Settings.from_env()
        assert settings.query_delay == 2.5

    @patch("release_planner.config.load_dotenv")
    def test_from_env_invalid_query_delay_uses_default(self, _mock_dotenv, monkeypatch):
        monkeypatch.setenv("RELEASE_PLANNER_JIRA_TOKEN", "token")
        monkeypatch.setenv("GOOGLE_CREDENTIALS_FILE", "/tmp/creds.json")
        monkeypatch.setenv("JIRA_QUERY_DELAY", "not-a-number")

        settings = Settings.from_env()
        assert settings.query_delay == 1.0

    @patch("release_planner.config.load_dotenv")
    def test_from_env_google_credentials_json(self, _mock_dotenv, monkeypatch):
        monkeypatch.setenv("RELEASE_PLANNER_JIRA_TOKEN", "token")
        monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
        monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", '{"type": "service_account"}')

        settings = Settings.from_env()
        assert settings.google_credentials_json == '{"type": "service_account"}'


class TestLoadBigRocks:
    """Tests for load_big_rocks()."""

    def test_load_big_rocks_from_config_dir(self, config_dir):
        rocks, config = load_big_rocks(config_dir)
        assert len(rocks) == 14
        assert config.release == "3.5"

    def test_all_rocks_present(self, config_dir):
        rocks, _ = load_big_rocks(config_dir)
        names = [r.name for r in rocks]
        expected_names = [
            "MaaS",
            "Gen AI Studio",
            "BYO Agent",
            "Tool Calling",
            "llm-d / xKS",
            "Upgrade Support",
            "Eval Hub",
            "AI Hub incl MCP",
            "Observability",
            "Multitenancy",
            "AutoRAG",
            "AI Safety",
            "vLLM Multimodal",
            "AutoML",
        ]
        assert names == expected_names

    def test_release_override(self, config_dir):
        rocks, config = load_big_rocks(config_dir, release="4.0")
        assert config.release == "4.0"

    def test_missing_config_dir_raises(self):
        with pytest.raises(FileNotFoundError):
            load_big_rocks("/nonexistent/dir")

    def test_priorities_are_sequential(self, config_dir):
        rocks, _ = load_big_rocks(config_dir)
        priorities = [r.priority for r in rocks]
        assert priorities == list(range(1, 15))

    def test_rocks_have_required_fields(self, config_dir):
        rocks, _ = load_big_rocks(config_dir)
        for rock in rocks:
            assert rock.name
            assert rock.full_name
            assert isinstance(rock.outcome_keys, list)
            assert rock.priority >= 1


class TestLoadFieldMapping:
    """Tests for load_field_mapping()."""

    def test_load_nonexistent_returns_empty(self, tmp_path):
        result = load_field_mapping(str(tmp_path))
        assert result == {}

    def test_load_valid_mapping(self, tmp_path):
        mapping_file = tmp_path / "field_mapping.yaml"
        mapping_file.write_text("target_release: customfield_12345\nteam: customfield_12346\n")
        result = load_field_mapping(str(tmp_path))
        assert result == {
            "target_release": "customfield_12345",
            "team": "customfield_12346",
        }

    def test_load_empty_mapping(self, tmp_path):
        mapping_file = tmp_path / "field_mapping.yaml"
        mapping_file.write_text("")
        result = load_field_mapping(str(tmp_path))
        assert result == {}
