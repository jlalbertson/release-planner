"""Tests for FastAPI endpoints.

Uses FastAPI's TestClient to test the API in demo mode
(no JIRA_TOKEN set, so sample data is returned).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Ensure no JIRA_TOKEN is set so the app runs in demo mode."""
    monkeypatch.delenv("JIRA_TOKEN", raising=False)
    monkeypatch.delenv("RELEASE_PLANNER_JIRA_TOKEN", raising=False)
    monkeypatch.delenv("RELEASE_PLANNER_API_KEY", raising=False)

    # Ensure the api module is in demo mode regardless of when it was imported
    import release_planner.api as api_module
    import release_planner.auth as auth_module
    monkeypatch.setattr(auth_module, "_api_key", "")

    # Ensure _settings has no jira_token (demo mode)
    if hasattr(api_module, "_settings") and api_module._settings.jira_token:
        monkeypatch.setattr(api_module._settings, "jira_token", "")


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app."""
    from release_planner import cache
    cache.clear()

    from release_planner.api import app
    return TestClient(app)


class TestStatusEndpoint:
    """Test GET /api/status."""

    def test_status_returns_200(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200

    def test_status_returns_demo_mode(self, client):
        resp = client.get("/api/status")
        data = resp.json()
        assert "demo_mode" in data
        # Without JIRA_TOKEN, should be demo mode
        assert data["demo_mode"] is True

    def test_status_no_auth_required(self, client):
        """Status endpoint should work without any auth."""
        resp = client.get("/api/status")
        assert resp.status_code == 200


class TestHealthzEndpoint:
    """Test GET /healthz."""

    def test_healthz_returns_ok(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestReleasesEndpoint:
    """Test GET /api/releases."""

    def test_releases_returns_200(self, client):
        resp = client.get("/api/releases")
        assert resp.status_code == 200

    def test_releases_returns_list(self, client):
        resp = client.get("/api/releases")
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_release_has_version_and_label(self, client):
        resp = client.get("/api/releases")
        data = resp.json()
        for release in data:
            assert "version" in release
            assert "label" in release


class TestCandidatesEndpoint:
    """Test GET /api/releases/{version}/candidates."""

    def test_candidates_returns_data_in_demo_mode(self, client):
        # First get available releases
        releases_resp = client.get("/api/releases")
        releases = releases_resp.json()
        assert len(releases) > 0

        version = releases[0]["version"]
        resp = client.get(f"/api/releases/{version}/candidates")
        assert resp.status_code == 200

    def test_candidates_response_structure(self, client):
        releases_resp = client.get("/api/releases")
        version = releases_resp.json()[0]["version"]

        resp = client.get(f"/api/releases/{version}/candidates")
        data = resp.json()

        assert "version" in data
        assert "jira_base_url" in data
        assert "last_refreshed" in data
        assert "summary" in data
        assert "big_rocks" in data
        assert "features" in data
        assert "rfes" in data
        assert "filter_options" in data

    def test_candidates_summary_stats(self, client):
        releases_resp = client.get("/api/releases")
        version = releases_resp.json()[0]["version"]

        resp = client.get(f"/api/releases/{version}/candidates")
        summary = resp.json()["summary"]

        assert "total_features" in summary
        assert "total_rfes" in summary
        assert "total_big_rocks" in summary
        assert "rocks_with_data" in summary
        assert "tier1" in summary
        assert "tier2" in summary
        assert "per_rock" in summary

    def test_candidates_filter_options(self, client):
        releases_resp = client.get("/api/releases")
        version = releases_resp.json()[0]["version"]

        resp = client.get(f"/api/releases/{version}/candidates")
        opts = resp.json()["filter_options"]

        assert "pillars" in opts
        assert "rocks" in opts
        assert "statuses" in opts
        assert "teams" in opts
        assert "priorities" in opts
        assert isinstance(opts["pillars"], list)

    def test_candidates_demo_mode_flag(self, client):
        releases_resp = client.get("/api/releases")
        version = releases_resp.json()[0]["version"]

        resp = client.get(f"/api/releases/{version}/candidates")
        data = resp.json()
        assert data.get("demo_mode") is True

    def test_candidates_features_have_required_fields(self, client):
        releases_resp = client.get("/api/releases")
        version = releases_resp.json()[0]["version"]

        resp = client.get(f"/api/releases/{version}/candidates")
        features = resp.json()["features"]
        if len(features) > 0:
            feat = features[0]
            required_fields = [
                "big_rock", "issue_key", "status", "priority", "phase",
                "summary", "components", "target_release", "fix_version",
                "pm", "delivery_owner", "rfe", "labels",
            ]
            for field in required_fields:
                assert field in feat, f"Missing field: {field}"

    def test_candidates_rfes_have_required_fields(self, client):
        releases_resp = client.get("/api/releases")
        version = releases_resp.json()[0]["version"]

        resp = client.get(f"/api/releases/{version}/candidates")
        rfes = resp.json()["rfes"]
        if len(rfes) > 0:
            rfe = rfes[0]
            required_fields = [
                "big_rock", "issue_key", "status", "priority",
                "summary", "components", "pm", "labels",
            ]
            for field in required_fields:
                assert field in rfe, f"Missing field: {field}"


class TestNotFoundRelease:
    """Test 404 for unknown release version."""

    def test_unknown_version_in_demo_mode(self, client):
        """In demo mode, any version returns sample data (demo mode serves anything)."""
        # The sample_data module returns data for any version string
        resp = client.get("/api/releases/99.99/candidates")
        # In demo mode, it generates sample data for any version
        assert resp.status_code == 200


class TestAuthMiddleware:
    """Test auth middleware behavior when API key is set."""

    def test_auth_required_when_key_is_set(self, monkeypatch):
        """When RELEASE_PLANNER_API_KEY is set, auth is required."""
        import release_planner.auth as auth_module

        # Patch the module-level _api_key variable directly
        monkeypatch.setattr(auth_module, "_api_key", "test-secret-key")

        from release_planner import cache
        cache.clear()

        from release_planner.api import app
        test_client = TestClient(app)

        # Request without auth should get 401 or 403
        resp = test_client.get("/api/releases")
        assert resp.status_code in (401, 403)

        # Request with correct auth should succeed
        resp = test_client.get(
            "/api/releases",
            headers={"Authorization": "Bearer test-secret-key"},
        )
        assert resp.status_code == 200

    def test_wrong_key_returns_401(self, monkeypatch):
        """Wrong API key should return 401."""
        import release_planner.auth as auth_module
        monkeypatch.setattr(auth_module, "_api_key", "correct-key")

        from release_planner.api import app
        test_client = TestClient(app)

        resp = test_client.get(
            "/api/releases",
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert resp.status_code == 401

    def test_status_endpoint_no_auth_even_with_key(self, monkeypatch):
        """Status endpoint should not require auth even when API key is set."""
        import release_planner.auth as auth_module
        monkeypatch.setattr(auth_module, "_api_key", "test-key")

        from release_planner.api import app
        test_client = TestClient(app)

        # Status endpoint should NOT require auth
        resp = test_client.get("/api/status")
        assert resp.status_code == 200
