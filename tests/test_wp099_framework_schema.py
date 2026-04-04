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


# ---------------------------------------------------------------------------
# Unit tests — init_knowledge_schema and config
# ---------------------------------------------------------------------------

def test_init_knowledge_schema_no_ctrl_embedding_idx():
    import inspect
    from scripts import init_knowledge_schema
    source = inspect.getsource(init_knowledge_schema)
    assert "ctrl_embedding_idx" not in source, "ctrl_embedding_idx must be removed from init_knowledge_schema"


def test_init_knowledge_schema_has_framework_embedding_idx():
    import inspect
    from scripts import init_knowledge_schema
    source = inspect.getsource(init_knowledge_schema)
    assert "framework_embedding_idx" in source
    assert "Framework" in source


def test_config_has_framework_index_capacity():
    from memory_service.config import Settings
    s = Settings()
    assert hasattr(s, "framework_index_capacity")
    assert s.framework_index_capacity == 5000


def test_config_no_ctrl_index_capacity():
    from memory_service.config import Settings
    s = Settings()
    assert not hasattr(s, "ctrl_index_capacity"), "ctrl_index_capacity must be renamed to framework_index_capacity"


def test_knowledge_constraints_no_control():
    from scripts.init_knowledge_schema import KNOWLEDGE_CONSTRAINTS
    labels = [label for label, _ in KNOWLEDGE_CONSTRAINTS]
    assert "Control" not in labels, "Control must be removed from KNOWLEDGE_CONSTRAINTS"


def test_migrate_embeddings_no_control_label():
    from scripts.migrate_embeddings import EMBEDDABLE_LABELS
    labels = [label for label, _ in EMBEDDABLE_LABELS]
    assert "Control" not in labels


def test_migrate_embeddings_has_framework_label():
    from scripts.migrate_embeddings import EMBEDDABLE_LABELS
    labels = [label for label, _ in EMBEDDABLE_LABELS]
    assert "Framework" in labels


# ---------------------------------------------------------------------------
# Unit tests — load_iso27001_chunks
# ---------------------------------------------------------------------------

def test_load_iso27001_chunks_no_controls_endpoint():
    import inspect
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "load_iso27001_chunks",
        "scripts/load_iso27001_chunks.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    source = inspect.getsource(mod)
    assert "/knowledge/controls" not in source, "load_iso27001_chunks must not call /knowledge/controls"


def test_load_iso27001_chunks_uses_framework_id_in_supports():
    import inspect
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "load_iso27001_chunks",
        "scripts/load_iso27001_chunks.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    source = inspect.getsource(mod)
    assert '"framework_id"' in source, "load_iso27001_chunks must use framework_id in SUPPORTS payload"
    assert '"control_id"' not in source, "load_iso27001_chunks must not use control_id"


# ---------------------------------------------------------------------------
# Integration tests — live Memgraph + FastAPI
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_framework_upsert_with_level_body_parent(client, test_driver):
    """POST /knowledge/frameworks creates Framework with level+body, CONTAINS edge from parent."""
    parent_id = "test-wp099-fw-root"
    child_id = "test-wp099-fw-child"
    try:
        r = client.post("/knowledge/frameworks", json={
            "id": parent_id,
            "name": "Test Root Framework",
            "level": "framework",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["level"] == "framework"
        assert data["body"] is None

        r = client.post("/knowledge/frameworks", json={
            "id": child_id,
            "name": "Test Child Clause",
            "level": "clause",
            "body": "This clause requires organisations to do X.",
            "parent_id": parent_id,
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["level"] == "clause"
        assert data["body"] == "This clause requires organisations to do X."

        with test_driver.session() as s:
            result = s.run(
                """
                MATCH (:Framework {id: $pid})-[:CONTAINS]->(c:Framework {id: $cid})
                RETURN c.id AS id
                """,
                pid=parent_id, cid=child_id,
            ).single()
        assert result is not None, "CONTAINS edge not created"

        r = client.get(f"/knowledge/frameworks/{child_id}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["level"] == "clause"
        assert data["body"] == "This clause requires organisations to do X."

    finally:
        with test_driver.session() as s:
            s.run("MATCH (n:Framework {id: $id}) DETACH DELETE n", id=parent_id)
            s.run("MATCH (n:Framework {id: $id}) DETACH DELETE n", id=child_id)


@pytest.mark.integration
def test_supports_edge_chunk_to_framework(client, test_driver):
    """POST /knowledge/chunk/supports creates SUPPORTS edge Chunk→Framework."""
    fw_id = "test-wp099-fw-supports"
    doc_id = "test-wp099-doc-supports"
    chunk_id = "test-wp099-chunk-supports"
    try:
        r = client.post("/knowledge/frameworks", json={
            "id": fw_id,
            "name": "Test Framework for SUPPORTS",
            "level": "clause",
            "body": "Access control requirements.",
        })
        assert r.status_code == 200, r.text

        r = client.post("/knowledge/documents", json={
            "id": doc_id,
            "title": "Test Doc",
            "doc_type": "standard",
        })
        assert r.status_code == 200, r.text

        r = client.post("/knowledge/chunks", json={
            "id": chunk_id,
            "text": "All users must authenticate before accessing systems.",
            "sequence": 1,
            "doc_id": doc_id,
        })
        assert r.status_code == 200, r.text

        r = client.post("/knowledge/chunk/supports", json={
            "chunk_id": chunk_id,
            "framework_id": fw_id,
            "confidence": 0.95,
            "status": "human-reviewed",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["framework_id"] == fw_id
        assert data["confidence"] == 0.95

        with test_driver.session() as s:
            result = s.run(
                """
                MATCH (:Chunk {id: $cid})-[s:SUPPORTS]->(f:Framework {id: $fid})
                RETURN s.confidence AS confidence
                """,
                cid=chunk_id, fid=fw_id,
            ).single()
        assert result is not None, "SUPPORTS edge not created"
        assert result["confidence"] == 0.95

    finally:
        with test_driver.session() as s:
            s.run("MATCH (n:Framework {id: $id}) DETACH DELETE n", id=fw_id)
            s.run("MATCH (n:Document {id: $id}) DETACH DELETE n", id=doc_id)
            s.run("MATCH (n:Chunk {id: $id}) DETACH DELETE n", id=chunk_id)


@pytest.mark.integration
def test_framework_search_returns_body_nodes(client, test_driver):
    """POST /knowledge/search/frameworks returns Framework nodes with body text."""
    fw_root_id = "test-wp099-fw-search-root"
    fw_leaf_id = "test-wp099-fw-search-leaf"
    try:
        r = client.post("/knowledge/frameworks", json={
            "id": fw_root_id,
            "name": "Test Root",
            "level": "framework",
        })
        assert r.status_code == 200, r.text

        r = client.post("/knowledge/frameworks", json={
            "id": fw_leaf_id,
            "name": "Access control policy",
            "level": "clause",
            "body": "User access rights must be defined and reviewed periodically.",
            "parent_id": fw_root_id,
        })
        assert r.status_code == 200, r.text

        r = client.post("/knowledge/search/frameworks", json={
            "query": "user access rights review",
            "limit": 5,
        })
        assert r.status_code == 200, r.text
        hits = r.json()
        ids = [h["id"] for h in hits]
        assert fw_leaf_id in ids, f"Expected {fw_leaf_id} in search results, got {ids}"
        assert fw_root_id not in ids, "Root (no body) should not appear in search results"

    finally:
        with test_driver.session() as s:
            s.run("MATCH (n:Framework {id: $id}) DETACH DELETE n", id=fw_root_id)
            s.run("MATCH (n:Framework {id: $id}) DETACH DELETE n", id=fw_leaf_id)


@pytest.mark.integration
def test_controls_endpoint_removed(client):
    """POST /knowledge/controls must return 404 or 405 — route removed."""
    r = client.post("/knowledge/controls", json={
        "id": "test-ctrl",
        "name": "Test Control",
        "framework_id": "iso-27001-2022",
    })
    assert r.status_code in (404, 405), f"Expected 404/405 but got {r.status_code}"


@pytest.mark.integration
def test_init_knowledge_schema_creates_framework_embedding_idx(test_driver):
    """After running init_knowledge_schema, framework_embedding_idx must exist on Framework."""
    from scripts.init_knowledge_schema import main as init_main
    rc = init_main()
    assert rc == 0

    with test_driver.session() as session:
        result = session.run("SHOW INDEX INFO;")
        found = False
        for record in result:
            label = record.get("label") or record.get("Label") or ""
            prop = record.get("property") or record.get("Property") or ""
            index_type = str(record.get("index type") or record.get("type") or "")
            if label == "Framework" and prop == "embedding" and "vector" in index_type.lower():
                found = True
        assert found, "framework_embedding_idx not found after init_knowledge_schema"
