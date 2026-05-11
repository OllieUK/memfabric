"""WP-102 housekeeping unit tests.

Covers:
- URL rename: /knowledge/chunks/supports (plural) replaces /knowledge/chunk/supports
- 503 guards on knowledge route handlers
"""
import os
import importlib

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable

os.environ["ENABLE_KNOWLEDGE_LAYER"] = "true"

from cyber_knowledge.routes import router as knowledge_router


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Isolated FastAPI app with knowledge router and mock driver."""
    app = FastAPI()
    app.include_router(knowledge_router)

    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__ = lambda s: mock_session
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
    app.state.driver = mock_driver

    return TestClient(app), mock_session, mock_driver


# ---------------------------------------------------------------------------
# Item 1 — URL rename
# ---------------------------------------------------------------------------


class TestChunksSupportsUrl:
    def test_new_plural_url_is_registered(self, client):
        """POST /knowledge/chunks/supports must exist (not 404/405)."""
        test_client, mock_session, _ = client
        with patch("cyber_knowledge.repo.get_chunk", return_value={"id": "c1"}), \
             patch("cyber_knowledge.repo.get_framework", return_value={"id": "fw1"}), \
             patch("cyber_knowledge.repo.create_supports_edge_framework", return_value={
                 "chunk_id": "c1", "framework_id": "fw1", "confidence": 0.9,
                 "raw_score": None, "status": "auto-inferred",
                 "created_at": "2026-01-01T00:00:00+00:00",
             }):
            resp = test_client.post("/knowledge/chunks/supports", json={
                "chunk_id": "c1", "framework_id": "fw1", "confidence": 0.9,
            })
        assert resp.status_code == 200

    def test_old_singular_url_returns_404_or_405(self, client):
        """POST /knowledge/chunk/supports (singular) must NOT be a registered route."""
        test_client, _, _ = client
        resp = test_client.post("/knowledge/chunk/supports", json={
            "chunk_id": "c1", "framework_id": "fw1", "confidence": 0.9,
        })
        assert resp.status_code in (404, 405)


# ---------------------------------------------------------------------------
# Item 2 — 503 guards
# ---------------------------------------------------------------------------


def _make_unavailable_driver():
    """Return a driver whose session raises ServiceUnavailable on entry."""
    driver = MagicMock()
    cm = MagicMock()
    cm.__enter__ = MagicMock(side_effect=ServiceUnavailable("db down"))
    cm.__exit__ = MagicMock(return_value=False)
    driver.session.return_value = cm
    return driver


@pytest.fixture
def unavailable_client():
    """Isolated FastAPI app whose driver raises ServiceUnavailable."""
    app = FastAPI()
    app.include_router(knowledge_router)
    app.state.driver = _make_unavailable_driver()
    return TestClient(app, raise_server_exceptions=False)


class Test503Guards:
    def test_post_frameworks_returns_503(self, unavailable_client):
        resp = unavailable_client.post("/knowledge/frameworks", json={
            "id": "fw-1", "title": "Test Framework",
        })
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Memgraph unavailable"

    def test_get_frameworks_returns_503(self, unavailable_client):
        resp = unavailable_client.get("/knowledge/frameworks/fw-1")
        assert resp.status_code == 503

    def test_post_chunks_returns_503(self, unavailable_client):
        with patch("cyber_knowledge.routes.get_embedding", return_value=[0.1] * 10):
            resp = unavailable_client.post("/knowledge/chunks", json={
                "id": "ch-1", "body": "text", "sequence": 0, "doc_id": "doc-1",
            })
        assert resp.status_code == 503

    def test_post_chunks_supports_returns_503(self, unavailable_client):
        resp = unavailable_client.post("/knowledge/chunks/supports", json={
            "chunk_id": "c1", "framework_id": "fw1", "confidence": 0.9,
        })
        assert resp.status_code == 503

    def test_get_controls_trace_up_returns_503(self, unavailable_client):
        resp = unavailable_client.get("/knowledge/controls/c1/trace-up")
        assert resp.status_code == 503

    def test_post_gap_analysis_returns_503(self, unavailable_client):
        resp = unavailable_client.post("/knowledge/gap-analysis", json={
            "control_ids": [], "org_id": None,
        })
        assert resp.status_code == 503

    def test_get_norms_returns_503(self, unavailable_client):
        resp = unavailable_client.get("/knowledge/norms")
        assert resp.status_code == 503

    def test_get_documents_returns_503(self, unavailable_client):
        resp = unavailable_client.get("/knowledge/documents")
        assert resp.status_code == 503
