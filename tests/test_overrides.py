"""Tests for overrides.py: override loading, merging, manual entries."""

import pytest

from release_planner.models import Candidate
from release_planner.overrides import OverrideLoader


class TestOverrideLoader:
    """Tests for OverrideLoader."""

    def test_load_valid_overrides(self, tmp_path):
        overrides_file = tmp_path / "overrides.yaml"
        overrides_file.write_text("RHOAIENG-123:\n  pm: Jane Doe\n  team: Platform\n")
        loader = OverrideLoader(str(overrides_file))
        result = loader.load()
        assert len(result.overrides) == 1
        assert result.overrides["RHOAIENG-123"]["pm"] == "Jane Doe"

    def test_load_empty_file(self, tmp_path):
        overrides_file = tmp_path / "overrides.yaml"
        overrides_file.write_text("")
        loader = OverrideLoader(str(overrides_file))
        result = loader.load()
        assert len(result.overrides) == 0

    def test_load_nonexistent_file(self, tmp_path):
        loader = OverrideLoader(str(tmp_path / "missing.yaml"))
        result = loader.load()
        assert len(result.overrides) == 0

    def test_load_malformed_yaml(self, tmp_path):
        overrides_file = tmp_path / "overrides.yaml"
        overrides_file.write_text("{{{{not yaml")
        loader = OverrideLoader(str(overrides_file))
        with pytest.raises(RuntimeError, match="Failed to parse"):
            loader.load()

    def test_load_non_dict_yaml(self, tmp_path):
        overrides_file = tmp_path / "overrides.yaml"
        overrides_file.write_text("- item1\n- item2\n")
        loader = OverrideLoader(str(overrides_file))
        with pytest.raises(RuntimeError, match="must be a mapping"):
            loader.load()

    def test_load_from_fixture(self):
        from pathlib import Path

        fixture_path = Path(__file__).parent / "fixtures" / "sample_overrides.yaml"
        loader = OverrideLoader(str(fixture_path))
        result = loader.load()
        assert len(result.overrides) == 3
        assert "RHOAIENG-12345" in result.overrides
        assert "RHAIRFE-200" in result.overrides
        assert "MANUAL-001" in result.overrides


class TestOverrideApply:
    """Tests for OverrideLoader.apply()."""

    def test_apply_override_to_candidate(self, tmp_path):
        overrides_file = tmp_path / "overrides.yaml"
        overrides_file.write_text("RHOAIENG-123:\n  pm: Jane Doe\n  team: Platform\n  ranking: 1\n")
        loader = OverrideLoader(str(overrides_file))
        loader.load()

        candidates = [
            Candidate(big_rock="MaaS", issue_key="RHOAIENG-123", summary="Test"),
            Candidate(big_rock="MaaS", issue_key="RHOAIENG-456", summary="Other"),
        ]
        result = loader.apply(candidates)

        # First candidate should have overrides applied
        assert result[0].pm == "Jane Doe"
        assert result[0].team == "Platform"
        assert result[0].ranking == 1

        # Second candidate should be unchanged
        assert result[1].pm == ""
        assert result[1].team == ""

    def test_apply_does_not_mutate_original(self, tmp_path):
        overrides_file = tmp_path / "overrides.yaml"
        overrides_file.write_text("RHOAIENG-123:\n  pm: Jane Doe\n")
        loader = OverrideLoader(str(overrides_file))
        loader.load()

        original = Candidate(big_rock="MaaS", issue_key="RHOAIENG-123", pm="Original")
        result = loader.apply([original])
        assert result[0].pm == "Jane Doe"
        assert original.pm == "Original"  # Original unchanged

    def test_apply_empty_string_clears_field(self, tmp_path):
        overrides_file = tmp_path / "overrides.yaml"
        overrides_file.write_text('RHOAIENG-123:\n  pm: ""\n')
        loader = OverrideLoader(str(overrides_file))
        loader.load()

        candidates = [
            Candidate(big_rock="MaaS", issue_key="RHOAIENG-123", pm="Old PM"),
        ]
        result = loader.apply(candidates)
        assert result[0].pm == ""

    def test_apply_with_no_matching_overrides(self, tmp_path):
        overrides_file = tmp_path / "overrides.yaml"
        overrides_file.write_text("RHOAIENG-999:\n  pm: Jane\n")
        loader = OverrideLoader(str(overrides_file))
        loader.load()

        candidates = [
            Candidate(big_rock="MaaS", issue_key="RHOAIENG-123"),
        ]
        result = loader.apply(candidates)
        assert result[0].pm == ""

    def test_apply_with_empty_overrides(self, tmp_path):
        overrides_file = tmp_path / "overrides.yaml"
        overrides_file.write_text("")
        loader = OverrideLoader(str(overrides_file))
        loader.load()

        candidates = [
            Candidate(big_rock="MaaS", issue_key="RHOAIENG-123"),
        ]
        result = loader.apply(candidates)
        assert len(result) == 1


class TestManualEntries:
    """Tests for OverrideLoader.get_manual_entries()."""

    def test_get_manual_entries(self, tmp_path):
        overrides_file = tmp_path / "overrides.yaml"
        overrides_file.write_text(
            "MANUAL-001:\n"
            '  big_rock: "MaaS"\n'
            '  summary: "Manual entry"\n'
            '  priority: "Major"\n'
            '  phase: "GA"\n'
        )
        loader = OverrideLoader(str(overrides_file))
        loader.load()

        entries = loader.get_manual_entries()
        assert len(entries) == 1
        assert entries[0].issue_key == "MANUAL-001"
        assert entries[0].big_rock == "MaaS"
        assert entries[0].source == "manual"
        assert entries[0].source_pass == "manual"

    def test_manual_entries_without_big_rock_skipped(self, tmp_path):
        overrides_file = tmp_path / "overrides.yaml"
        overrides_file.write_text('MANUAL-001:\n  summary: "No big rock"\n')
        loader = OverrideLoader(str(overrides_file))
        loader.load()

        entries = loader.get_manual_entries()
        assert len(entries) == 0

    def test_regular_overrides_not_in_manual_entries(self, tmp_path):
        overrides_file = tmp_path / "overrides.yaml"
        overrides_file.write_text(
            'RHOAIENG-123:\n  pm: Jane\nMANUAL-001:\n  big_rock: "MaaS"\n  summary: "Test"\n'
        )
        loader = OverrideLoader(str(overrides_file))
        loader.load()

        entries = loader.get_manual_entries()
        assert len(entries) == 1
        assert entries[0].issue_key == "MANUAL-001"
