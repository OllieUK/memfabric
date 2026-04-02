"""Unit tests for WP-084: /health version/build fields and add_memory strand_ids response."""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# /health — version and build fields
# ---------------------------------------------------------------------------

class TestHealthVersionBuild:
    def test_health_includes_version_field(self):
        from memory_service.main import app
        with TestClient(app) as c:
            resp = c.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0

    def test_health_includes_build_field(self):
        from memory_service.main import app
        with TestClient(app) as c:
            resp = c.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "build" in data
        assert isinstance(data["build"], str)
        assert len(data["build"]) > 0

    def test_health_build_is_7_chars_or_unknown(self):
        from memory_service.main import app
        with TestClient(app) as c:
            resp = c.get("/health")
        build = resp.json()["build"]
        assert build == "unknown" or len(build) == 7

    def test_health_still_returns_status_ok(self):
        from memory_service.main import app
        with TestClient(app) as c:
            resp = c.get("/health")
        assert resp.json()["status"] == "ok"
