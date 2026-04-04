"""
tests/test_wp069_knowledge_schema.py — Tests for WP-069 + WP-094: knowledge layer schema.

Unit tests verify enum values, allowlists, and schema constants without a live DB.
Integration tests (require live Memgraph + FastAPI) verify that constraints and vector
indexes are created correctly and that the separation invariant holds.
"""

import pytest

from memory_service import main as service_main
from memory_service.knowledge_schemas import (
    CONTROL_DOMAINS,
    CONTROL_RELATIONSHIP_TYPES,
    DOCUMENT_POLICY_LEVELS,
    JURISDICTION_TYPES,
    ORGANISATION_TYPES,
    SABSA_LAYERS,
)
from scripts import dump_db, restore_db


# ---------------------------------------------------------------------------
# Unit tests — config new settings (WP-094)
# ---------------------------------------------------------------------------

def test_config_has_knowledge_embedding_model():
    from memory_service.config import Settings
    s = Settings()
    assert s.knowledge_embedding_model == "paraphrase-multilingual-MiniLM-L12-v2"


def test_config_has_enable_knowledge_layer_default_false():
    import os
    from memory_service.config import Settings
    # Temporarily unset env var and bypass .env to test the code default value
    env_backup = os.environ.pop("ENABLE_KNOWLEDGE_LAYER", None)
    try:
        s = Settings(_env_file=None)
        assert s.enable_knowledge_layer is False
    finally:
        if env_backup is not None:
            os.environ["ENABLE_KNOWLEDGE_LAYER"] = env_backup


# ---------------------------------------------------------------------------
# Unit tests — migrate_embeddings (WP-094)
# ---------------------------------------------------------------------------

def test_migrate_embeddings_does_not_include_memory_label():
    """Memory nodes must not be in EMBEDDABLE_LABELS — episodic migration is independent."""
    from scripts.migrate_embeddings import EMBEDDABLE_LABELS
    labels = [label for label, _ in EMBEDDABLE_LABELS]
    assert "Memory" not in labels, "Memory must not be in EMBEDDABLE_LABELS after WP-094"


def test_migrate_embeddings_includes_knowledge_labels():
    """Framework and Chunk nodes must be in EMBEDDABLE_LABELS."""
    from scripts.migrate_embeddings import EMBEDDABLE_LABELS
    labels = [label for label, _ in EMBEDDABLE_LABELS]
    assert "Framework" in labels
    assert "Chunk" in labels


# ---------------------------------------------------------------------------
# Unit tests — knowledge_schemas constants
# ---------------------------------------------------------------------------

def test_sabsa_layers_non_empty():
    assert len(SABSA_LAYERS) > 0


def test_sabsa_layers_expected_values():
    assert SABSA_LAYERS == {"contextual", "conceptual", "logical", "physical", "component", "operational"}


def test_control_domains_non_empty():
    assert len(CONTROL_DOMAINS) >= 10


def test_control_relationship_types():
    assert CONTROL_RELATIONSHIP_TYPES == {"context", "evidence", "gap"}


def test_document_policy_levels():
    assert DOCUMENT_POLICY_LEVELS == {"strategic", "tactical", "operational", "procedure"}


def test_jurisdiction_types():
    assert JURISDICTION_TYPES == {"geographic", "sectoral"}


def test_organisation_types():
    assert ORGANISATION_TYPES == {"employer", "client", "regulatory-body", "standards-body"}


# ---------------------------------------------------------------------------
# Unit tests — NodeLabel enum
# ---------------------------------------------------------------------------

def test_node_label_has_all_knowledge_labels():
    NodeLabel = service_main.NodeLabel
    knowledge_labels = {"Framework", "Control", "Document", "Chunk", "BusinessAttribute", "Organisation", "Jurisdiction"}
    existing = {e.value for e in NodeLabel}
    assert knowledge_labels.issubset(existing), f"Missing from NodeLabel: {knowledge_labels - existing}"


def test_node_label_preserves_original_labels():
    NodeLabel = service_main.NodeLabel
    original = {"Memory", "Strand", "Agent", "Person", "Project"}
    existing = {e.value for e in NodeLabel}
    assert original.issubset(existing)


# ---------------------------------------------------------------------------
# Unit tests — dump_db / restore_db edge allowlists
# ---------------------------------------------------------------------------

_KNOWLEDGE_EDGE_TYPES = {
    "MAPPED_TO", "SUPPORTS", "HAS_CHUNK",
    "IMPLEMENTS", "ADDRESSES", "OWNED_BY", "APPLIES_IN",
    "OPERATES_IN", "ABOUT_CONTROL", "CITES_DOC",
    "CONTAINS",
}

def test_dump_db_query_includes_knowledge_edge_types():
    """The dump_db edge query must cover all knowledge-layer edge types."""
    import inspect
    source = inspect.getsource(dump_db)
    for etype in _KNOWLEDGE_EDGE_TYPES:
        assert etype in source, f"dump_db missing edge type: {etype}"


def test_restore_db_allowlist_includes_knowledge_edge_types():
    """The restore_db ALLOWED_EDGE_TYPES set must cover all knowledge-layer edge types."""
    import inspect
    source = inspect.getsource(restore_db)
    for etype in _KNOWLEDGE_EDGE_TYPES:
        assert etype in source, f"restore_db missing edge type: {etype}"


# ---------------------------------------------------------------------------
# Unit tests — config index capacity settings
# ---------------------------------------------------------------------------

def test_config_has_index_capacity_settings():
    from memory_service.config import Settings
    s = Settings()
    assert s.memory_index_capacity == 5000
    assert s.framework_index_capacity == 5000
    assert s.chunk_index_capacity == 10000


# ---------------------------------------------------------------------------
# Integration tests — live Memgraph
# ---------------------------------------------------------------------------

_KNOWLEDGE_CONSTRAINTS = [
    ("Framework", "id"),
    ("Norm", "id"),
    ("Document", "id"),
    ("Chunk", "id"),
    ("BusinessAttribute", "id"),
    ("Organisation", "id"),
    ("Jurisdiction", "code"),
]


def _get_constraints(driver) -> set[tuple[str, str]]:
    """Return set of (label, property) for all UNIQUE constraints."""
    with driver.session() as session:
        result = session.run("SHOW CONSTRAINT INFO;")
        constraints = set()
        for record in result:
            label = record.get("label") or record.get("Label") or ""
            ctype = str(
                record.get("constraint type")
                or record.get("type")
                or record.get("Type")
                or ""
            )
            props = record.get("properties") or record.get("property") or record.get("Property") or []
            if isinstance(props, str):
                props = [props]
            if "unique" in ctype.lower() and label:
                for prop in props:
                    constraints.add((label, prop))
        return constraints


def _get_vector_indexes(driver) -> dict[str, tuple[str, str]]:
    """Return {label: (property, index_type)} for all vector indexes."""
    with driver.session() as session:
        result = session.run("SHOW INDEX INFO;")
        indexes = {}
        for record in result:
            label = record.get("label") or record.get("Label") or ""
            prop = record.get("property") or record.get("Property") or ""
            index_type = str(
                record.get("index type")
                or record.get("type")
                or record.get("Type")
                or ""
            )
            if "vector" in index_type.lower() and label:
                indexes[label] = (prop, index_type)
        return indexes


@pytest.mark.integration
def test_knowledge_schema_constraints_created(test_driver):
    """All 7 knowledge layer uniqueness constraints must exist after init_knowledge_schema."""
    from scripts.init_knowledge_schema import main as init_main
    rc = init_main()
    assert rc == 0, "init_knowledge_schema.py returned non-zero exit code"

    constraints = _get_constraints(test_driver)
    for label, prop in _KNOWLEDGE_CONSTRAINTS:
        assert (label, prop) in constraints, f"Missing constraint: {label}.{prop} IS UNIQUE"


@pytest.mark.integration
def test_knowledge_schema_vector_indexes_created(test_driver):
    """framework_embedding_idx and chunk_embedding_idx must exist with correct label+property."""
    from scripts.init_knowledge_schema import main as init_main
    init_main()

    indexes = _get_vector_indexes(test_driver)
    assert "Framework" in indexes, "framework_embedding_idx (Framework) not found"
    assert indexes["Framework"][0] == "embedding"
    assert "Chunk" in indexes, "chunk_embedding_idx (Chunk) not found"
    assert indexes["Chunk"][0] == "embedding"


@pytest.mark.integration
def test_knowledge_schema_idempotent(test_driver):
    """Running init_knowledge_schema twice must not error."""
    from scripts.init_knowledge_schema import main as init_main
    assert init_main() == 0
    assert init_main() == 0


@pytest.mark.integration
def test_knowledge_schema_uses_knowledge_embedding_model(test_driver):
    """init_knowledge_schema must use knowledge_embedding_model, not embedding_model.

    Verifies ADR-001 guardrail 2: independent embedding models per layer.
    We patch embedding_model to a non-existent model name; init must still succeed
    because it only reads knowledge_embedding_model.
    """
    from unittest.mock import patch
    from memory_service.config import Settings
    from scripts.init_knowledge_schema import main as init_main

    # If init_knowledge_schema incorrectly used settings.embedding_model, it would
    # attempt to load "nonexistent-model-xyz" and fail. Patching Settings ensures
    # a fresh instance is created inside main() with our overrides.
    with patch.dict("os.environ", {
        "EMBEDDING_MODEL": "nonexistent-model-xyz",
        "KNOWLEDGE_EMBEDDING_MODEL": Settings().knowledge_embedding_model,
    }):
        rc = init_main()
    assert rc == 0, "init_knowledge_schema failed — it may be using EMBEDDING_MODEL instead of KNOWLEDGE_EMBEDDING_MODEL"


@pytest.mark.integration
def test_separation_memory_search_excludes_knowledge_nodes(client, test_driver):
    """POST /memory/search must never return Control or Chunk nodes.

    This is the separation baseline test — the label-scoped vector index means
    knowledge-layer nodes are structurally invisible to episodic memory search.
    We seed a Control and Chunk node directly (bypassing the API since the write
    endpoints don't exist yet) and confirm search still returns zero knowledge nodes.
    """
    control_id = "test-wp069-ctrl-001"
    chunk_id = "test-wp069-chunk-001"
    try:
        from memory_service.embeddings import get_embedding
        emb = get_embedding("access control policy user authentication")
        with test_driver.session() as s:
            s.run(
                """
                MERGE (c:Control {id: $id})
                SET c.code = 'A.9.1.1', c.title = 'Access control policy',
                    c.body = 'User authentication requirements',
                    c.embedding = $emb
                """,
                id=control_id, emb=emb,
            )
            s.run(
                """
                MERGE (ch:Chunk {id: $id})
                SET ch.heading = 'Access Control', ch.body = 'User authentication requirements',
                    ch.embedding = $emb
                """,
                id=chunk_id, emb=emb,
            )

        r = client.post("/memory/search", json={"query": "access control user authentication", "limit": 20})
        assert r.status_code == 200, r.text
        ids = [h["id"] for h in r.json()["memories"]]
        assert control_id not in ids, "Control node leaked into memory search results"
        assert chunk_id not in ids, "Chunk node leaked into memory search results"
    finally:
        with test_driver.session() as s:
            s.run("MATCH (n:Control {id: $id}) DETACH DELETE n", id=control_id)
            s.run("MATCH (n:Chunk {id: $id}) DETACH DELETE n", id=chunk_id)
