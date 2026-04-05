"""WP-073 Tasks 1 & 2: route-level and repo-level unit tests for SUPPORTS edge endpoints.

All tests are unit tests using mocked driver/session.
No live Memgraph required.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from memory_service.knowledge_routes import router as knowledge_router


@pytest.fixture
def client():
    """Create an isolated FastAPI app with the knowledge router registered.

    Uses a fresh app instance per test to avoid contaminating the global singleton.
    """
    test_app = FastAPI()
    test_app.include_router(knowledge_router)

    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__ = lambda s: mock_session
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
    test_app.state.driver = mock_driver

    return TestClient(test_app), mock_session


# ---------------------------------------------------------------------------
# Route-level tests: POST /knowledge/chunks/supports
# ---------------------------------------------------------------------------


def test_create_supports_returns_200(client):
    test_client, mock_session = client
    record = {
        "chunk_id": "chunk-1",
        "framework_id": "fw-1",
        "confidence": 0.85,
        "raw_score": None,
        "status": "auto-inferred",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    with patch("memory_service.knowledge_repo.get_chunk", return_value={"id": "chunk-1"}), \
         patch("memory_service.knowledge_repo.get_framework", return_value={"id": "fw-1"}), \
         patch("memory_service.knowledge_repo.create_supports_edge_framework", return_value=record):
        resp = test_client.post("/knowledge/chunks/supports", json={
            "chunk_id": "chunk-1",
            "framework_id": "fw-1",
            "confidence": 0.85,
            "status": "auto-inferred",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["chunk_id"] == "chunk-1"
    assert data["framework_id"] == "fw-1"
    assert data["confidence"] == 0.85
    assert data["status"] == "auto-inferred"


def test_create_supports_missing_chunk_404(client):
    test_client, mock_session = client
    with patch("memory_service.knowledge_repo.get_chunk", return_value=None), \
         patch("memory_service.knowledge_repo.get_framework", return_value={"id": "fw-1"}):
        resp = test_client.post("/knowledge/chunks/supports", json={
            "chunk_id": "nonexistent-chunk",
            "framework_id": "fw-1",
            "confidence": 0.5,
        })
    assert resp.status_code == 404
    assert "nonexistent-chunk" in resp.json()["detail"]


def test_create_supports_missing_framework_404(client):
    test_client, mock_session = client
    with patch("memory_service.knowledge_repo.get_chunk", return_value={"id": "chunk-1"}), \
         patch("memory_service.knowledge_repo.get_framework", return_value=None):
        resp = test_client.post("/knowledge/chunks/supports", json={
            "chunk_id": "chunk-1",
            "framework_id": "nonexistent-fw",
            "confidence": 0.5,
        })
    assert resp.status_code == 404
    assert "nonexistent-fw" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Route-level tests: GET /knowledge/controls/{control_id}/chunks
# ---------------------------------------------------------------------------


def test_get_chunks_for_control_returns_list(client):
    test_client, mock_session = client
    chunks = [
        {
            "id": "chunk-1", "body": "text one", "sequence": 0,
            "doc_id": "doc-1", "created_at": "2026-01-01T00:00:00+00:00",
            "confidence": 0.9, "status": "auto-inferred",
        },
        {
            "id": "chunk-2", "body": "text two", "sequence": 1,
            "doc_id": "doc-1", "created_at": "2026-01-01T00:00:00+00:00",
            "confidence": 0.7, "status": "auto-inferred",
        },
    ]
    with patch("memory_service.knowledge_repo.get_control", return_value={"id": "ctrl-1"}), \
         patch("memory_service.knowledge_repo.get_chunks_for_control", return_value=chunks):
        resp = test_client.get("/knowledge/controls/ctrl-1/chunks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["id"] == "chunk-1"
    assert data[1]["id"] == "chunk-2"


def test_get_chunks_for_control_missing_control_404(client):
    test_client, mock_session = client
    with patch("memory_service.knowledge_repo.get_control", return_value=None):
        resp = test_client.get("/knowledge/controls/ghost-ctrl/chunks")
    assert resp.status_code == 404
    assert "ghost-ctrl" in resp.json()["detail"]


def test_get_chunks_for_control_empty(client):
    test_client, mock_session = client
    with patch("memory_service.knowledge_repo.get_control", return_value={"id": "ctrl-1"}), \
         patch("memory_service.knowledge_repo.get_chunks_for_control", return_value=[]):
        resp = test_client.get("/knowledge/controls/ctrl-1/chunks")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Repo-level unit tests (mocked session)
# ---------------------------------------------------------------------------


def test_create_supports_edge_framework_calls_session_run():
    from memory_service import knowledge_repo

    mock_session = MagicMock()
    record_data = {
        "chunk_id": "chunk-1",
        "framework_id": "fw-1",
        "confidence": 0.85,
        "raw_score": None,
        "status": "auto-inferred",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    mock_record = MagicMock()
    mock_record.__iter__ = MagicMock(return_value=iter(record_data.items()))
    mock_record.keys.return_value = record_data.keys()
    mock_record.__getitem__ = lambda self, k: record_data[k]
    mock_session.run.return_value.single.return_value = mock_record

    result = knowledge_repo.create_supports_edge_framework(
        mock_session, "chunk-1", "fw-1", 0.85, None, "auto-inferred", "2026-01-01T00:00:00+00:00"
    )

    mock_session.run.assert_called_once()
    call_kwargs = mock_session.run.call_args
    assert call_kwargs[1]["chunk_id"] == "chunk-1"
    assert call_kwargs[1]["framework_id"] == "fw-1"
    assert call_kwargs[1]["confidence"] == 0.85
    assert result is not None


def test_create_supports_edge_framework_returns_none_when_no_match():
    from memory_service import knowledge_repo

    mock_session = MagicMock()
    mock_session.run.return_value.single.return_value = None

    result = knowledge_repo.create_supports_edge_framework(
        mock_session, "bad-chunk", "bad-fw", 0.5, None, "auto-inferred", "2026-01-01T00:00:00+00:00"
    )

    assert result is None


def test_get_chunks_for_control_repo_returns_list():
    from memory_service import knowledge_repo

    mock_session = MagicMock()
    row1 = {
        "id": "chunk-1", "text": "text", "sequence": 0,
        "doc_id": "doc-1", "created_at": "2026-01-01T00:00:00+00:00",
        "confidence": 0.9, "status": "auto-inferred",
    }
    row2 = {
        "id": "chunk-2", "text": "more text", "sequence": 1,
        "doc_id": "doc-1", "created_at": "2026-01-01T00:00:00+00:00",
        "confidence": 0.7, "status": "auto-inferred",
    }

    def make_mock_record(data):
        r = MagicMock()
        r.keys.return_value = data.keys()
        r.__getitem__ = lambda self, k: data[k]
        r.__iter__ = MagicMock(return_value=iter(data.items()))
        return r

    mock_session.run.return_value.__iter__ = MagicMock(
        return_value=iter([make_mock_record(row1), make_mock_record(row2)])
    )

    results = knowledge_repo.get_chunks_for_control(mock_session, "ctrl-1")

    mock_session.run.assert_called_once()
    assert len(results) == 2


# ---------------------------------------------------------------------------
# Ingest script unit tests (Task 4)
# These mock httpx.Client helpers — no live stack required.
# ---------------------------------------------------------------------------


def _make_chunk_response(chunk_id: str, seq: int) -> dict:
    return {
        "id": chunk_id,
        "text": "some text content for chunk",
        "sequence": seq,
        "doc_id": "doc-test",
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def _make_md_file(tmp_path, content: str) -> str:
    """Write a temporary markdown file and return its path."""
    f = tmp_path / "test_doc.md"
    f.write_text(content)
    return str(f)


def _mock_http_response(json_data):
    """Return a mock httpx.Response that returns json_data on .json()."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _make_main_argv(tmp_path, content: str = "## Section\n" + "x" * 100) -> tuple[str, list[str]]:
    """Create a markdown file and return (file_path, sys.argv list)."""
    md_path = _make_md_file(tmp_path, content)
    return md_path, [
        "ingest_document.py", md_path,
        "--doc-id", "doc-test-1",
        "--title", "Test Doc",
        "--doc-type", "policy",
    ]


def test_review_mode_prevents_edge_creation(tmp_path, capsys):
    """With ingest_chunk_review_mode=True, _post_supports must never be called."""
    from scripts.ingest_document import main

    md_path, argv = _make_main_argv(tmp_path)
    doc_resp = {"id": "doc-test-1", "title": "Test Doc", "doc_type": "policy",
                "source_url": None, "created_at": "2026-01-01T00:00:00+00:00"}
    chunk_resp = {"id": "chunk-uuid-1", "doc_id": "doc-test-1", "text": "x" * 100,
                  "sequence": 0, "created_at": "2026-01-01T00:00:00+00:00", "embedding": None}
    search_resp = [{"id": "ctrl-abc", "name": "C", "description": None,
                    "framework_id": "fw-1", "created_at": "2026-01-01T00:00:00+00:00",
                    "distance": 0.10}]

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.side_effect = [
        _mock_http_response(doc_resp),
        _mock_http_response(chunk_resp),
        _mock_http_response(search_resp),
    ]

    import sys
    with patch("sys.argv", argv), \
         patch("httpx.Client", return_value=mock_client), \
         patch("scripts.ingest_document.IngestSettings") as mock_cfg:
        cfg = mock_cfg.return_value
        cfg.api_base_url = "http://localhost:8000"
        cfg.ingest_chunk_size = 2000
        cfg.ingest_chunk_overlap = 200
        cfg.ingest_min_chunk_chars = 10
        cfg.ingest_auto_supports = True
        cfg.ingest_auto_supports_threshold = 0.20
        cfg.ingest_chunk_review_mode = True  # <-- review mode ON
        main()

    # Verify: POST was called for document and chunk but NOT for supports
    calls = [str(c) for c in mock_client.post.call_args_list]
    assert any("/knowledge/documents" in c for c in calls)
    assert not any("/knowledge/chunks/supports" in c for c in calls)

    captured = capsys.readouterr()
    assert "Review mode" in captured.out


def test_review_mode_prints_summary(tmp_path, capsys):
    """With ingest_chunk_review_mode=True, stdout must contain candidate control_id."""
    from scripts.ingest_document import main

    md_path, argv = _make_main_argv(tmp_path)
    doc_resp = {"id": "doc-test-1", "title": "Test Doc", "doc_type": "policy",
                "source_url": None, "created_at": "2026-01-01T00:00:00+00:00"}
    chunk_resp = {"id": "chunk-uuid-1", "doc_id": "doc-test-1", "text": "x" * 100,
                  "sequence": 0, "created_at": "2026-01-01T00:00:00+00:00", "embedding": None}
    search_resp = [{"id": "ctrl-visible", "name": "C", "description": None,
                    "framework_id": "fw-1", "created_at": "2026-01-01T00:00:00+00:00",
                    "distance": 0.10}]

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.side_effect = [
        _mock_http_response(doc_resp),
        _mock_http_response(chunk_resp),
        _mock_http_response(search_resp),
    ]

    with patch("sys.argv", argv), \
         patch("httpx.Client", return_value=mock_client), \
         patch("scripts.ingest_document.IngestSettings") as mock_cfg:
        cfg = mock_cfg.return_value
        cfg.api_base_url = "http://localhost:8000"
        cfg.ingest_chunk_size = 2000
        cfg.ingest_chunk_overlap = 200
        cfg.ingest_min_chunk_chars = 10
        cfg.ingest_auto_supports = True
        cfg.ingest_auto_supports_threshold = 0.20
        cfg.ingest_chunk_review_mode = True
        main()

    captured = capsys.readouterr()
    assert "Review mode" in captured.out
    assert "ctrl-visible" in captured.out


def test_auto_supports_below_threshold_creates_edge(tmp_path):
    """With review_mode=False and distance < threshold, supports POST must be called."""
    from scripts.ingest_document import main

    md_path, argv = _make_main_argv(tmp_path)
    doc_resp = {"id": "doc-test-1", "title": "Test Doc", "doc_type": "policy",
                "source_url": None, "created_at": "2026-01-01T00:00:00+00:00"}
    chunk_resp = {"id": "chunk-uuid-1", "doc_id": "doc-test-1", "text": "x" * 100,
                  "sequence": 0, "created_at": "2026-01-01T00:00:00+00:00", "embedding": None}
    search_resp = [{"id": "ctrl-abc", "name": "C", "description": None,
                    "framework_id": "fw-1", "created_at": "2026-01-01T00:00:00+00:00",
                    "distance": 0.15}]  # below 0.20 threshold
    supports_resp = {"chunk_id": "chunk-uuid-1", "control_id": "ctrl-abc",
                     "confidence": 0.85, "status": "auto-inferred",
                     "created_at": "2026-01-01T00:00:00+00:00"}

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.side_effect = [
        _mock_http_response(doc_resp),
        _mock_http_response(chunk_resp),
        _mock_http_response(search_resp),
        _mock_http_response(supports_resp),
    ]

    with patch("sys.argv", argv), \
         patch("httpx.Client", return_value=mock_client), \
         patch("scripts.ingest_document.IngestSettings") as mock_cfg:
        cfg = mock_cfg.return_value
        cfg.api_base_url = "http://localhost:8000"
        cfg.ingest_chunk_size = 2000
        cfg.ingest_chunk_overlap = 200
        cfg.ingest_min_chunk_chars = 10
        cfg.ingest_auto_supports = True
        cfg.ingest_auto_supports_threshold = 0.20
        cfg.ingest_chunk_review_mode = False  # <-- apply mode
        main()

    calls = [str(c) for c in mock_client.post.call_args_list]
    assert any("/knowledge/chunks/supports" in c for c in calls), \
        "Expected POST to /knowledge/chunks/supports but got: " + str(calls)


def test_auto_supports_above_threshold_skipped(tmp_path):
    """With distance > threshold, supports POST must NOT be called."""
    from scripts.ingest_document import main

    md_path, argv = _make_main_argv(tmp_path)
    doc_resp = {"id": "doc-test-1", "title": "Test Doc", "doc_type": "policy",
                "source_url": None, "created_at": "2026-01-01T00:00:00+00:00"}
    chunk_resp = {"id": "chunk-uuid-1", "doc_id": "doc-test-1", "text": "x" * 100,
                  "sequence": 0, "created_at": "2026-01-01T00:00:00+00:00", "embedding": None}
    search_resp = [{"id": "ctrl-abc", "name": "C", "description": None,
                    "framework_id": "fw-1", "created_at": "2026-01-01T00:00:00+00:00",
                    "distance": 0.25}]  # above 0.20 threshold

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.side_effect = [
        _mock_http_response(doc_resp),
        _mock_http_response(chunk_resp),
        _mock_http_response(search_resp),
    ]

    with patch("sys.argv", argv), \
         patch("httpx.Client", return_value=mock_client), \
         patch("scripts.ingest_document.IngestSettings") as mock_cfg:
        cfg = mock_cfg.return_value
        cfg.api_base_url = "http://localhost:8000"
        cfg.ingest_chunk_size = 2000
        cfg.ingest_chunk_overlap = 200
        cfg.ingest_min_chunk_chars = 10
        cfg.ingest_auto_supports = True
        cfg.ingest_auto_supports_threshold = 0.20
        cfg.ingest_chunk_review_mode = False
        main()

    calls = [str(c) for c in mock_client.post.call_args_list]
    assert not any("/knowledge/chunks/supports" in c for c in calls), \
        "Expected NO POST to /knowledge/chunks/supports but got: " + str(calls)
