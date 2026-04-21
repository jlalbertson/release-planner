"""Tests for the extracted pipeline module.

Verifies:
- pipeline.py does NOT import click (AST check)
- PipelineError hierarchy
- PipelineResult dataclass fields
"""

from __future__ import annotations

import ast
from dataclasses import fields as dataclass_fields
from pathlib import Path

import pytest

from release_planner.pipeline import (
    ConfigError,
    JiraConnectionError,
    PipelineError,
    PipelineResult,
)


class TestNoCLickImport:
    """Verify that pipeline.py never imports click."""

    def test_pipeline_does_not_import_click(self):
        """Parse pipeline.py with AST and assert no click imports exist."""
        pipeline_path = (
            Path(__file__).parent.parent / "src" / "release_planner" / "pipeline.py"
        )
        source = pipeline_path.read_text()
        tree = ast.parse(source)

        click_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "click" or alias.name.startswith("click."):
                        click_imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module and (
                    node.module == "click" or node.module.startswith("click.")
                ):
                    click_imports.append(node.module)

        assert click_imports == [], (
            f"pipeline.py MUST NOT import click. Found: {click_imports}"
        )


class TestPipelineErrorHierarchy:
    """Verify the PipelineError exception hierarchy."""

    def test_pipeline_error_is_exception(self):
        assert issubclass(PipelineError, Exception)

    def test_jira_connection_error_is_pipeline_error(self):
        assert issubclass(JiraConnectionError, PipelineError)

    def test_config_error_is_pipeline_error(self):
        assert issubclass(ConfigError, PipelineError)

    def test_pipeline_error_message(self):
        err = PipelineError("something went wrong")
        assert str(err) == "something went wrong"

    def test_jira_connection_error_message(self):
        err = JiraConnectionError("connection refused")
        assert str(err) == "connection refused"

    def test_config_error_message(self):
        err = ConfigError("bad yaml")
        assert str(err) == "bad yaml"

    def test_catch_pipeline_error_catches_subclasses(self):
        """Catching PipelineError should also catch JiraConnectionError and ConfigError."""
        with pytest.raises(PipelineError):
            raise JiraConnectionError("test")

        with pytest.raises(PipelineError):
            raise ConfigError("test")


class TestPipelineResult:
    """Verify PipelineResult dataclass fields exist and have correct types."""

    def test_pipeline_result_is_dataclass(self):
        """PipelineResult should be a dataclass."""
        field_names = [f.name for f in dataclass_fields(PipelineResult)]
        assert len(field_names) > 0

    def test_required_fields_exist(self):
        field_names = {f.name for f in dataclass_fields(PipelineResult)}
        expected = {
            "candidates",
            "big_rocks",
            "fix_versions",
            "features",
            "rfes",
            "per_rock_stats",
            "outcome_summaries",
            "release",
            "skipped_count",
            "terminal_filtered_count",
            "rocks_without_outcomes",
        }
        assert expected.issubset(field_names), (
            f"Missing fields: {expected - field_names}"
        )

    def test_pipeline_result_construction(self):
        """PipelineResult can be constructed with valid arguments."""
        result = PipelineResult(
            candidates={},
            big_rocks=[],
            fix_versions=["rhoai-3.5"],
            features=[],
            rfes=[],
            per_rock_stats={},
            outcome_summaries={},
            release="3.5",
            skipped_count=0,
            terminal_filtered_count=0,
        )
        assert result.release == "3.5"
        assert result.candidates == {}
        assert result.fix_versions == ["rhoai-3.5"]
        assert result.rocks_without_outcomes == []  # default

    def test_pipeline_result_field_types(self):
        """PipelineResult fields are the expected types when constructed."""
        result = PipelineResult(
            candidates={"MaaS": []},
            big_rocks=[],
            fix_versions=["v1", "v2"],
            features=[],
            rfes=[],
            per_rock_stats={"MaaS": {"features": 5, "rfes": 2}},
            outcome_summaries={"KEY-1": "summary"},
            release="3.5",
            skipped_count=3,
            terminal_filtered_count=1,
            rocks_without_outcomes=[],
        )
        assert isinstance(result.candidates, dict)
        assert isinstance(result.big_rocks, list)
        assert isinstance(result.fix_versions, list)
        assert isinstance(result.features, list)
        assert isinstance(result.rfes, list)
        assert isinstance(result.per_rock_stats, dict)
        assert isinstance(result.outcome_summaries, dict)
        assert isinstance(result.release, str)
        assert isinstance(result.skipped_count, int)
        assert isinstance(result.terminal_filtered_count, int)
        assert isinstance(result.rocks_without_outcomes, list)
