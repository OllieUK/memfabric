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


# ---------------------------------------------------------------------------
# POST /memory — strand_ids in response
# ---------------------------------------------------------------------------

class TestAddMemoryStrandIdsResponse:
    def test_response_includes_strand_ids_field(self):
        from memory_service.main import app
        with TestClient(app) as c:
            resp = c.post("/memory", json={
                "fact": "test memory for strand_ids response",
                "type": "fact",
                "agent_id": "test-agent-wp084",
                "strand_ids": [],
            })
        assert resp.status_code == 200
        assert "strand_ids" in resp.json()

    def test_empty_strand_ids_returns_empty_list(self):
        from memory_service.main import app
        with TestClient(app) as c:
            resp = c.post("/memory", json={
                "fact": "test memory no strands",
                "type": "fact",
                "agent_id": "test-agent-wp084",
            })
        assert resp.status_code == 200
        assert resp.json()["strand_ids"] == []

    def test_strand_ids_echoed_in_response(self):
        from memory_service.main import app
        import uuid
        suffix = str(uuid.uuid4())
        with TestClient(app) as c:
            resp = c.post("/memory", json={
                "fact": f"test memory with strand {suffix}",
                "type": "fact",
                "agent_id": "test-agent-wp084",
                "strand_ids": ["strand-core-health"],
            })
        assert resp.status_code == 200
        assert resp.json()["strand_ids"] == ["strand-core-health"]

    def test_deduplicated_response_has_empty_strand_ids(self):
        """When a memory is deduplicated, strand_ids in response is []."""
        from memory_service.main import app
        from unittest.mock import patch, MagicMock
        existing_id = "existing-mem-id-001"
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

        with patch("memory_service.main.memory_repo") as mock_repo, \
             patch("memory_service.main.get_embedding", return_value=[0.1] * 384):
            mock_repo.find_duplicate_memory.return_value = existing_id
            mock_repo.reinforce_memory.return_value = None
            with TestClient(app) as c:
                original = app.state.driver
                app.state.driver = mock_driver
                try:
                    resp = c.post("/memory", json={
                        "fact": "duplicate memory test",
                        "type": "fact",
                        "agent_id": "test-agent-wp084",
                        "strand_ids": ["strand-core-health"],
                    })
                finally:
                    app.state.driver = original
        assert resp.status_code == 200
        data = resp.json()
        assert data["deduplicated"] is True
        assert data["strand_ids"] == []
