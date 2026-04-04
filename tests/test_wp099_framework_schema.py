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
