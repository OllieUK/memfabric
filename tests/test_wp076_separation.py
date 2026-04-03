"""WP-076 T2: autouse separation enforcement tests.

These tests assert the ADR-001 invariant: the memory layer and knowledge layer
must never expose each other's nodes through their respective search APIs, and
the long-rest maintenance endpoint must not touch knowledge graph edges.

Unit test:
  - test_import_audit_knowledge_bridge_is_sole_cross_layer_importer

Integration tests (require live Memgraph + FastAPI):
  - test_memory_search_returns_zero_knowledge_nodes
  - test_knowledge_search_returns_zero_memory_nodes
  - test_long_rest_does_not_modify_knowledge_edges
"""
import os

import pytest

os.environ["ENABLE_KNOWLEDGE_LAYER"] = "true"


# ---------------------------------------------------------------------------
# Seed / teardown fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def separation_data(test_driver, knowledge_client):
    """Seed test data across both layers; yield ID maps; clean up on teardown.

    Depends on `test_driver` which calls pytest.skip() when Memgraph is
    unreachable — this fixture inherits that skip behaviour automatically.
    """
    prefix = "test-wp076-sep-"

    framework_id = f"{prefix}fw-001"
    control_ids = [f"{prefix}ctrl-{i:03d}" for i in range(1, 21)]
    doc_ids = [f"{prefix}doc-{i:03d}" for i in range(1, 5)]
    chunk_ids = [f"{prefix}chunk-{i:03d}" for i in range(1, 51)]
    memory_ids = []

    # -- Framework --
    knowledge_client.post(
        "/knowledge/frameworks",
        json={"id": framework_id, "name": "WP-076 Separation Test Framework"},
    )

    # -- 20 Controls --
    for ctrl_id in control_ids:
        knowledge_client.post(
            "/knowledge/controls",
            json={
                "id": ctrl_id,
                "name": f"separation test control {ctrl_id}",
                "framework_id": framework_id,
            },
        )

    # -- 4 Documents --
    for doc_id in doc_ids:
        knowledge_client.post(
            "/knowledge/documents",
            json={
                "id": doc_id,
                "title": f"separation test document {doc_id}",
                "doc_type": "policy",
            },
        )

    # -- 50 Chunks (12-13 per doc, distributed across 4 docs) --
    doc_cycle = [doc_ids[i % 4] for i in range(50)]
    for idx, chunk_id in enumerate(chunk_ids):
        knowledge_client.post(
            "/knowledge/chunks",
            json={
                "id": chunk_id,
                "text": f"separation test chunk {chunk_id}",
                "sequence": idx,
                "doc_id": doc_cycle[idx],
            },
        )

    # -- SUPPORTS edges: first 5 chunks → first 5 controls --
    for i in range(5):
        knowledge_client.post(
            "/knowledge/chunk/supports",
            json={
                "chunk_id": chunk_ids[i],
                "control_id": control_ids[i],
                "confidence": 0.9,
            },
        )

    # -- 5 Memory nodes --
    for i in range(1, 6):
        resp = knowledge_client.post(
            "/memory",
            json={
                "fact": f"separation test knowledge memory node {i}",
                "type": "fact",
                "importance": 3,
            },
        )
        if resp.status_code == 200:
            memory_ids.append(resp.json()["memory_id"])

    yield {
        "prefix": prefix,
        "framework_id": framework_id,
        "control_ids": control_ids,
        "doc_ids": doc_ids,
        "chunk_ids": chunk_ids,
        "memory_ids": memory_ids,
    }

    # Teardown: delete all seeded nodes by prefix and Memory nodes by stored UUID ids
    with test_driver.session() as session:
        session.run(
            "MATCH (n) WHERE n.id STARTS WITH $prefix DETACH DELETE n",
            prefix=prefix,
        )
        for mid in memory_ids:
            session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mid)


# ---------------------------------------------------------------------------
# Integration tests — separation assertions
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_memory_search_returns_zero_knowledge_nodes(knowledge_client, separation_data):
    """POST /memory/search must not return Control/Chunk/Document/Norm nodes."""
    resp = knowledge_client.post(
        "/memory/search",
        json={"query": "separation test knowledge control", "limit": 100},
    )
    assert resp.status_code == 200
    hits = resp.json()["memories"]
    knowledge_ids = (
        separation_data["control_ids"]
        + separation_data["chunk_ids"]
        + separation_data["doc_ids"]
    )
    returned_ids = {h["id"] for h in hits}
    overlap = returned_ids & set(knowledge_ids)
    assert len(overlap) == 0, f"Memory search leaked knowledge nodes: {overlap}"


@pytest.mark.integration
def test_knowledge_search_returns_zero_memory_nodes(knowledge_client, separation_data):
    """POST /knowledge/search/controls must not return Memory nodes."""
    resp = knowledge_client.post(
        "/knowledge/search/controls",
        json={"query": "separation test knowledge control", "limit": 100},
    )
    assert resp.status_code == 200
    hits = resp.json()
    memory_ids = set(separation_data["memory_ids"])
    returned_ids = {h["id"] for h in hits}
    overlap = returned_ids & memory_ids
    assert len(overlap) == 0, f"Knowledge search leaked memory nodes: {overlap}"


@pytest.mark.integration
def test_long_rest_does_not_modify_knowledge_edges(
    test_driver, knowledge_client, separation_data
):
    """POST /memory/maintenance/long-rest must not modify SUPPORTS.confidence."""
    prefix = separation_data["prefix"]

    with test_driver.session() as session:
        before = {
            r["chunk_id"]: r["confidence"]
            for r in session.run(
                "MATCH (ch:Chunk)-[s:SUPPORTS]->(c:Control) "
                "WHERE ch.id STARTS WITH $prefix "
                "RETURN ch.id AS chunk_id, s.confidence AS confidence",
                prefix=prefix,
            )
        }

    resp = knowledge_client.post("/memory/maintenance/long-rest")
    assert resp.status_code == 200

    with test_driver.session() as session:
        after = {
            r["chunk_id"]: r["confidence"]
            for r in session.run(
                "MATCH (ch:Chunk)-[s:SUPPORTS]->(c:Control) "
                "WHERE ch.id STARTS WITH $prefix "
                "RETURN ch.id AS chunk_id, s.confidence AS confidence",
                prefix=prefix,
            )
        }

    assert before == after, (
        f"long_rest modified SUPPORTS.confidence: "
        f"{set(before.items()) ^ set(after.items())}"
    )


# ---------------------------------------------------------------------------
# Static import audit (no live stack required)
# ---------------------------------------------------------------------------


def test_import_audit_knowledge_bridge_is_sole_cross_layer_importer():
    """knowledge_bridge.py must be the only module importing from both memory_repo and knowledge_repo."""
    import ast
    import pathlib

    src = pathlib.Path(__file__).parent.parent / "memory_service"
    violations = []
    for py_file in sorted(src.glob("*.py")):
        if py_file.name == "knowledge_bridge.py":
            continue
        tree = ast.parse(py_file.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
        has_memory = any("memory_repo" in m for m in imported)
        has_knowledge = any("knowledge_repo" in m for m in imported)
        if has_memory and has_knowledge:
            violations.append(py_file.name)

    assert violations == [], (
        f"These files import from both memory_repo and knowledge_repo — "
        f"only knowledge_bridge.py is permitted to cross the layer boundary: {violations}"
    )
