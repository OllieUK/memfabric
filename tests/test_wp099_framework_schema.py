"""tests/test_wp099_framework_schema.py — WP-099: Framework hierarchy schema correction."""
import pytest
from pydantic import ValidationError


def test_framework_create_accepts_level_body_parent_id():
    from cyber_knowledge.routes import FrameworkCreate
    fw = FrameworkCreate(
        id="iso-27001-2022.6",
        title="Clause 6 — Planning",
        level="clause",
        body="Requirements for planning in the ISMS context.",
        parent_id="iso-27001-2022",
    )
    assert fw.level == "clause"
    assert fw.body == "Requirements for planning in the ISMS context."
    assert fw.parent_id == "iso-27001-2022"


def test_framework_create_level_defaults_to_framework():
    from cyber_knowledge.routes import FrameworkCreate
    fw = FrameworkCreate(id="iso-27001-2022", title="ISO/IEC 27001")
    assert fw.level == "framework"


def test_framework_create_body_optional():
    from cyber_knowledge.routes import FrameworkCreate
    fw = FrameworkCreate(id="iso-27001-2022", title="ISO/IEC 27001")
    assert fw.body is None


def test_framework_response_includes_level_and_body():
    from cyber_knowledge.routes import FrameworkResponse
    resp = FrameworkResponse(
        id="iso-27001-2022.6",
        title="Clause 6",
        level="clause",
        body="Some body text.",
        created_at="2026-04-04T00:00:00+00:00",
    )
    assert resp.level == "clause"
    assert resp.body == "Some body text."


def test_framework_search_request_has_query_and_limit():
    from cyber_knowledge.routes import FrameworkSearchRequest
    req = FrameworkSearchRequest(query="access control requirements")
    assert req.query == "access control requirements"
    assert req.limit == 10
    assert req.framework_id is None


def test_supports_create_uses_framework_id():
    from cyber_knowledge.routes import SupportsCreate
    req = SupportsCreate(
        chunk_id="chunk-001",
        framework_id="iso-27001-2022.a.5.1",
        confidence=0.9,
    )
    assert req.framework_id == "iso-27001-2022.a.5.1"


def test_supports_create_rejects_missing_framework_id():
    from cyber_knowledge.routes import SupportsCreate
    with pytest.raises(ValidationError):
        SupportsCreate(chunk_id="chunk-001", confidence=0.9)


# ---------------------------------------------------------------------------
# Unit tests — knowledge_repo
# ---------------------------------------------------------------------------


def test_upsert_framework_sets_level_and_body():
    from unittest.mock import MagicMock
    from cyber_knowledge import repo as knowledge_repo

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
        title = "Clause 6"
        version = None
        level = "clause"
        body = "Planning requirements."
        parent_id = "iso-27001-2022"
        statement_type = None
        modality = None

    knowledge_repo.upsert_framework(mock_session, FakeReq(), "2026-04-04T00:00:00+00:00")
    assert mock_session.run.call_count == 2
    first_call_kwargs = mock_session.run.call_args_list[0][1]
    assert first_call_kwargs["level"] == "clause"
    assert first_call_kwargs["body"] == "Planning requirements."


def test_upsert_framework_no_parent_no_contains_edge():
    from unittest.mock import MagicMock
    from cyber_knowledge import repo as knowledge_repo

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
        title = "ISO/IEC 27001"
        version = "2022"
        level = "framework"
        body = None
        parent_id = None
        statement_type = None
        modality = None

    knowledge_repo.upsert_framework(mock_session, FakeReq(), "2026-04-04T00:00:00+00:00")
    assert mock_session.run.call_count == 1


def test_get_framework_returns_level_and_body():
    from unittest.mock import MagicMock
    from cyber_knowledge import repo as knowledge_repo

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
    from cyber_knowledge import repo as knowledge_repo

    mock_session = MagicMock()
    mock_session.run.return_value = []

    knowledge_repo.search_frameworks(mock_session, [0.1] * 384, limit=5, framework_id=None)
    cypher = mock_session.run.call_args[0][0]
    assert "framework_embedding_idx" in cypher


def test_create_supports_edge_framework_uses_framework_label():
    from unittest.mock import MagicMock
    from cyber_knowledge import repo as knowledge_repo

    mock_session = MagicMock()
    mock_session.run.return_value.single.return_value = {
        "chunk_id": "c1",
        "framework_id": "fw1",
        "confidence": 0.9,
        "status": "auto-inferred",
        "created_at": "2026-04-04T00:00:00+00:00",
    }

    knowledge_repo.create_supports_edge_framework(
        mock_session, "c1", "fw1", 0.9, None, "auto-inferred", "2026-04-04T00:00:00+00:00"
    )
    cypher = mock_session.run.call_args[0][0]
    assert ":Framework" in cypher
    assert ":Control" not in cypher


# ---------------------------------------------------------------------------
# Unit tests — init_knowledge_schema and config
# ---------------------------------------------------------------------------

def test_init_knowledge_schema_has_ctrl_embedding_idx():
    import inspect
    from scripts import init_knowledge_schema
    source = inspect.getsource(init_knowledge_schema)
    assert "ctrl_embedding_idx" in source, "ctrl_embedding_idx must be present in init_knowledge_schema (added by WP-101)"


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


def test_config_has_ctrl_index_capacity():
    from memory_service.config import Settings
    s = Settings()
    assert hasattr(s, "ctrl_index_capacity"), "ctrl_index_capacity must be present in Settings (added by WP-101)"
    assert s.ctrl_index_capacity == 5000


def test_knowledge_constraints_has_control():
    from scripts.init_knowledge_schema import KNOWLEDGE_CONSTRAINTS
    labels = [label for label, _ in KNOWLEDGE_CONSTRAINTS]
    assert "Control" in labels, "Control must be in KNOWLEDGE_CONSTRAINTS (added by WP-101)"


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


def test_load_iso27001_chunks_has_classify_statement_type():
    """Loader must include the _classify_statement_type function."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "load_iso27001_chunks",
        "scripts/load_iso27001_chunks.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "_classify_statement_type"), "Loader must define _classify_statement_type"


def test_load_iso27001_chunks_no_chunk_creation():
    """Loader must not create Chunk or Document nodes for standard text."""
    import inspect
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "load_iso27001_chunks",
        "scripts/load_iso27001_chunks.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    source = inspect.getsource(mod)
    assert "/knowledge/chunks" not in source, "Loader must not create Chunk nodes for standard text"
    assert "/knowledge/documents" not in source, "Loader must not create Document nodes for standard text"


# ---------------------------------------------------------------------------
# Unit tests — _classify_statement_type
# ---------------------------------------------------------------------------

def _get_classify_fn():
    """Import _classify_statement_type from the loader script."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "load_iso27001_chunks",
        "scripts/load_iso27001_chunks.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._classify_statement_type


def test_classify_structural_no_body():
    classify = _get_classify_fn()
    assert classify("iso-27001-2022.4", None) == "structural"
    assert classify("iso-27001-2022.4", "") == "structural"


def test_classify_reference_clauses():
    classify = _get_classify_fn()
    assert classify("iso-27001-2022.1", "This document specifies...") == "reference"
    assert classify("iso-27001-2022.2", "Normative references...") == "reference"


def test_classify_definitional_clause():
    classify = _get_classify_fn()
    assert classify("iso-27001-2022.3", "Terms and definitions...") == "definitional"
    assert classify("iso-27001-2022.3.stmt-1", "For the purposes...") == "definitional"


def test_classify_informative_note():
    classify = _get_classify_fn()
    assert classify("iso-27001-2022.4.1", "NOTE Determining these issues refers to...") == "informative"
    assert classify("iso-27001-2022.6.2", "Note: this is additional guidance") == "informative"


def test_classify_normative_shall():
    classify = _get_classify_fn()
    assert classify("iso-27001-2022.4.1", "The organization shall determine external and internal issues") == "normative"
    assert classify("iso-27001-2022.5.1", "Top management shall demonstrate leadership") == "normative"


def test_classify_normative_must():
    classify = _get_classify_fn()
    assert classify("iso-27001-2022.6.1", "The organization must assess risks") == "normative"


def test_classify_unclassified_default():
    classify = _get_classify_fn()
    # Text without shall/must/NOTE and not in clauses 1-3
    assert classify("iso-27001-2022.4.3", "Scope of the ISMS") is None


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
            "title": "Test Root Framework",
            "level": "framework",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["level"] == "framework"
        assert data["body"] is None

        r = client.post("/knowledge/frameworks", json={
            "id": child_id,
            "title": "Test Child Clause",
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
            "title": "Test Framework for SUPPORTS",
            "level": "clause",
            "body": "Access control requirements.",
        })
        assert r.status_code == 200, r.text

        r = client.post("/knowledge/documents", json={
            "id": doc_id,
            "title": "Test Doc",
            "policy_level": "operational",
        })
        assert r.status_code == 200, r.text

        r = client.post("/knowledge/chunks", json={
            "id": chunk_id,
            "body": "All users must authenticate before accessing systems.",
            "sequence": 1,
            "doc_id": doc_id,
        })
        assert r.status_code == 200, r.text

        r = client.post("/knowledge/chunks/supports", json={
            "chunk_id": chunk_id,
            "framework_id": fw_id,
            "confidence": 0.95,
            "status": "auto-inferred",
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
            "title": "Test Root",
            "level": "framework",
        })
        assert r.status_code == 200, r.text

        r = client.post("/knowledge/frameworks", json={
            "id": fw_leaf_id,
            "title": "Access control policy",
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
def test_controls_endpoint_exists(client, test_driver):
    """POST /knowledge/controls creates an org Control node (re-added after WP-099 for org controls)."""
    ctrl_id = "test-wp099-ctrl-check"
    try:
        r = client.post("/knowledge/controls", json={
            "id": ctrl_id,
            "name": "Test Control WP-099",
            "framework_id": "iso-27001-2022",
        })
        assert r.status_code == 200, f"Expected 200 but got {r.status_code}: {r.text}"
        data = r.json()
        assert data["id"] == ctrl_id
    finally:
        with test_driver.session() as s:
            s.run("MATCH (c:Control {id: $id}) DETACH DELETE c", id=ctrl_id)


@pytest.mark.integration
def test_framework_statement_type_persisted(client, test_driver):
    """statement_type is accepted on create and returned on get."""
    fw_id = "test-wp099-statement-type-persisted"
    try:
        r = client.post("/knowledge/frameworks", json={
            "id": fw_id,
            "title": "Test Framework statement_type",
            "level": "clause",
            "body": "This clause defines normative requirements.",
            "statement_type": "normative",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["statement_type"] == "normative"

        r = client.get(f"/knowledge/frameworks/{fw_id}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["statement_type"] == "normative"

    finally:
        with test_driver.session() as s:
            s.run("MATCH (n:Framework {id: $id}) DETACH DELETE n", id=fw_id)


@pytest.mark.integration
def test_framework_modality_with_normative(client, test_driver):
    """modality is accepted when statement_type is normative."""
    fw_id = "test-wp099-modality-normative"
    try:
        r = client.post("/knowledge/frameworks", json={
            "id": fw_id,
            "title": "Test Framework modality",
            "level": "clause",
            "body": "All systems shall implement access control.",
            "statement_type": "normative",
            "modality": "shall",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["statement_type"] == "normative"
        assert data["modality"] == "shall"

        r = client.get(f"/knowledge/frameworks/{fw_id}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["statement_type"] == "normative"
        assert data["modality"] == "shall"

    finally:
        with test_driver.session() as s:
            s.run("MATCH (n:Framework {id: $id}) DETACH DELETE n", id=fw_id)


@pytest.mark.integration
def test_framework_invalid_statement_type_rejected(client):
    """Invalid statement_type returns 400."""
    r = client.post("/knowledge/frameworks", json={
        "id": "test-wp099-invalid-st",
        "title": "Test Invalid statement_type",
        "level": "clause",
        "body": "Some body text.",
        "statement_type": "invalid_type",
    })
    assert r.status_code == 400, f"Expected 400 but got {r.status_code}: {r.text}"


@pytest.mark.integration
def test_framework_modality_without_normative_rejected(client):
    """modality without statement_type='normative' returns 400."""
    r = client.post("/knowledge/frameworks", json={
        "id": "test-wp099-modality-no-normative",
        "title": "Test modality without normative",
        "level": "clause",
        "body": "This is informative text.",
        "statement_type": "informative",
        "modality": "shall",
    })
    assert r.status_code == 400, f"Expected 400 but got {r.status_code}: {r.text}"


@pytest.mark.integration
def test_framework_invalid_modality_rejected(client):
    """Invalid modality returns 400."""
    r = client.post("/knowledge/frameworks", json={
        "id": "test-wp099-invalid-modality",
        "title": "Test Invalid modality",
        "level": "clause",
        "body": "All systems must comply.",
        "statement_type": "normative",
        "modality": "invalid",
    })
    assert r.status_code == 400, f"Expected 400 but got {r.status_code}: {r.text}"


@pytest.mark.integration
def test_search_frameworks_with_statement_type_filter(client, test_driver):
    """Search with statement_type filter returns only matching results."""
    fw_normative_id = "test-wp099-search-normative"
    fw_informative_id = "test-wp099-search-informative"
    try:
        r = client.post("/knowledge/frameworks", json={
            "id": fw_normative_id,
            "title": "Normative Access Control Clause",
            "level": "clause",
            "body": "All systems shall implement role-based access control for user authentication.",
            "statement_type": "normative",
        })
        assert r.status_code == 200, r.text

        r = client.post("/knowledge/frameworks", json={
            "id": fw_informative_id,
            "title": "Informative Access Control Note",
            "level": "clause",
            "body": "This section provides guidance on implementing role-based access control approaches.",
            "statement_type": "informative",
        })
        assert r.status_code == 200, r.text

        r = client.post("/knowledge/search/frameworks", json={
            "query": "role-based access control user authentication",
            "limit": 10,
            "statement_type": "normative",
        })
        assert r.status_code == 200, r.text
        hits = r.json()
        ids = [h["id"] for h in hits]
        assert fw_normative_id in ids, f"Expected normative framework in results, got {ids}"
        assert fw_informative_id not in ids, f"Informative framework should not appear when filtering for normative"

    finally:
        with test_driver.session() as s:
            s.run("MATCH (n:Framework {id: $id}) DETACH DELETE n", id=fw_normative_id)
            s.run("MATCH (n:Framework {id: $id}) DETACH DELETE n", id=fw_informative_id)


@pytest.mark.integration
def test_framework_statement_type_defaults_none(client, test_driver):
    """Frameworks created without statement_type have None."""
    fw_id = "test-wp099-statement-type-default"
    try:
        r = client.post("/knowledge/frameworks", json={
            "id": fw_id,
            "title": "Test Framework no statement_type",
            "level": "clause",
            "body": "Some clause body without a statement type.",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["statement_type"] is None

        r = client.get(f"/knowledge/frameworks/{fw_id}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["statement_type"] is None

    finally:
        with test_driver.session() as s:
            s.run("MATCH (n:Framework {id: $id}) DETACH DELETE n", id=fw_id)


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
