"""tests/test_wp099_framework_schema.py — WP-099: Framework hierarchy schema correction."""
import pytest
from pydantic import ValidationError


def test_framework_create_accepts_level_body_parent_id():
    from memory_service.knowledge_routes import FrameworkCreate
    fw = FrameworkCreate(
        id="iso-27001-2022.6",
        name="Clause 6 — Planning",
        level="clause",
        body="Requirements for planning in the ISMS context.",
        parent_id="iso-27001-2022",
    )
    assert fw.level == "clause"
    assert fw.body == "Requirements for planning in the ISMS context."
    assert fw.parent_id == "iso-27001-2022"


def test_framework_create_level_defaults_to_framework():
    from memory_service.knowledge_routes import FrameworkCreate
    fw = FrameworkCreate(id="iso-27001-2022", name="ISO/IEC 27001")
    assert fw.level == "framework"


def test_framework_create_body_optional():
    from memory_service.knowledge_routes import FrameworkCreate
    fw = FrameworkCreate(id="iso-27001-2022", name="ISO/IEC 27001")
    assert fw.body is None


def test_framework_response_includes_level_and_body():
    from memory_service.knowledge_routes import FrameworkResponse
    resp = FrameworkResponse(
        id="iso-27001-2022.6",
        name="Clause 6",
        level="clause",
        body="Some body text.",
        created_at="2026-04-04T00:00:00+00:00",
    )
    assert resp.level == "clause"
    assert resp.body == "Some body text."


def test_framework_search_request_has_query_and_limit():
    from memory_service.knowledge_routes import FrameworkSearchRequest
    req = FrameworkSearchRequest(query="access control requirements")
    assert req.query == "access control requirements"
    assert req.limit == 10
    assert req.framework_id is None


def test_supports_create_uses_framework_id():
    from memory_service.knowledge_routes import SupportsCreate
    req = SupportsCreate(
        chunk_id="chunk-001",
        framework_id="iso-27001-2022.a.5.1",
        confidence=0.9,
    )
    assert req.framework_id == "iso-27001-2022.a.5.1"


def test_supports_create_rejects_missing_framework_id():
    from memory_service.knowledge_routes import SupportsCreate
    with pytest.raises(ValidationError):
        SupportsCreate(chunk_id="chunk-001", confidence=0.9)


# ---------------------------------------------------------------------------
# Unit tests — knowledge_repo
# ---------------------------------------------------------------------------


def test_upsert_framework_sets_level_and_body():
    from unittest.mock import MagicMock
    from memory_service import knowledge_repo

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.single.return_value = {
        "id": "iso-27001-2022.6",
        "name": "Clause 6",
        "version": None,
        "description": None,
        "level": "clause",
        "body": "Planning requirements.",
        "created_at": "2026-04-04T00:00:00+00:00",
    }
    mock_session.run.return_value = mock_result

    class FakeReq:
        id = "iso-27001-2022.6"
        name = "Clause 6"
        version = None
        description = None
        level = "clause"
        body = "Planning requirements."
        parent_id = "iso-27001-2022"

    knowledge_repo.upsert_framework(mock_session, FakeReq(), "2026-04-04T00:00:00+00:00")
    assert mock_session.run.call_count == 2
    first_call_kwargs = mock_session.run.call_args_list[0][1]
    assert first_call_kwargs["level"] == "clause"
    assert first_call_kwargs["body"] == "Planning requirements."


def test_upsert_framework_no_parent_no_contains_edge():
    from unittest.mock import MagicMock
    from memory_service import knowledge_repo

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.single.return_value = {
        "id": "iso-27001-2022",
        "name": "ISO/IEC 27001",
        "version": "2022",
        "description": None,
        "level": "framework",
        "body": None,
        "created_at": "2026-04-04T00:00:00+00:00",
    }
    mock_session.run.return_value = mock_result

    class FakeReq:
        id = "iso-27001-2022"
        name = "ISO/IEC 27001"
        version = "2022"
        description = None
        level = "framework"
        body = None
        parent_id = None

    knowledge_repo.upsert_framework(mock_session, FakeReq(), "2026-04-04T00:00:00+00:00")
    assert mock_session.run.call_count == 1


def test_get_framework_returns_level_and_body():
    from unittest.mock import MagicMock
    from memory_service import knowledge_repo

    mock_session = MagicMock()
    record = {
        "id": "iso-27001-2022.6",
        "name": "Clause 6",
        "version": None,
        "description": None,
        "level": "clause",
        "body": "Planning requirements.",
        "created_at": "2026-04-04T00:00:00+00:00",
    }
    mock_session.run.return_value.single.return_value = record

    result = knowledge_repo.get_framework(mock_session, "iso-27001-2022.6")
    assert result["level"] == "clause"
    assert result["body"] == "Planning requirements."


def test_search_frameworks_calls_vector_search():
    from unittest.mock import MagicMock
    from memory_service import knowledge_repo

    mock_session = MagicMock()
    mock_session.run.return_value = []

    knowledge_repo.search_frameworks(mock_session, [0.1] * 384, limit=5, framework_id=None)
    cypher = mock_session.run.call_args[0][0]
    assert "framework_embedding_idx" in cypher


def test_create_supports_edge_framework_uses_framework_label():
    from unittest.mock import MagicMock
    from memory_service import knowledge_repo

    mock_session = MagicMock()
    mock_session.run.return_value.single.return_value = {
        "chunk_id": "c1",
        "framework_id": "fw1",
        "confidence": 0.9,
        "status": "auto-inferred",
        "created_at": "2026-04-04T00:00:00+00:00",
    }

    knowledge_repo.create_supports_edge_framework(
        mock_session, "c1", "fw1", 0.9, "auto-inferred", "2026-04-04T00:00:00+00:00"
    )
    cypher = mock_session.run.call_args[0][0]
    assert ":Framework" in cypher
    assert ":Control" not in cypher
