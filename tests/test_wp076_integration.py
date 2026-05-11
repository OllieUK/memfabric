"""WP-076 T3: integration tests for knowledge layer schema, write, and search operations.

All tests require live Memgraph + FastAPI. Mark: @pytest.mark.integration.
ID prefix convention: test-wp076-wr- (write), test-wp076-sr- (search), test-wp076-sc- (schema).
"""
import os

import pytest
from tests.conftest import edge_exists, get_edge_props, get_memory_node, node_exists


# ---------------------------------------------------------------------------
# TestKnowledgeSchemaIntegration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestKnowledgeSchemaIntegration:
    """Verify that init_knowledge_schema.py has been run and the schema is present.

    Uses test_driver directly (no HTTP). No data written.
    """

    def _constraint_exists(self, constraints: list, label: str, prop: str) -> bool:
        """Check if a unique constraint on label.prop exists.

        Handles both single-property string field ('property') and
        list field ('properties') returned by different Memgraph versions.
        """
        for r in constraints:
            r_label = r.get("label") or r.get("Label") or ""
            if r_label != label:
                continue
            # Some Memgraph versions return 'property' (str), others 'properties' (list)
            r_prop = r.get("property") or r.get("Property") or ""
            r_props = r.get("properties") or r.get("Properties") or []
            if r_prop == prop:
                return True
            if prop in r_props:
                return True
        return False

    def test_framework_unique_constraint_exists(self, test_driver):
        with test_driver.session() as session:
            result = session.run("SHOW CONSTRAINT INFO")
            constraints = [dict(r) for r in result]
        found = self._constraint_exists(constraints, "Framework", "id")
        assert found, f"Expected UNIQUE constraint on Framework.id. Got: {constraints}"

    def test_control_vector_index_exists(self, test_driver):
        with test_driver.session() as session:
            result = session.run("SHOW INDEX INFO")
            indexes = [dict(r) for r in result]
        found = any(
            (r.get("index name") or r.get("index_name") or r.get("name") or "") == "ctrl_embedding_idx"
            or (
                (r.get("label") or r.get("Label") or "") == "Control"
                and (r.get("property") or r.get("Property") or "") == "embedding"
                and "vector" in str(r.get("index type") or r.get("type") or r.get("Type") or "").lower()
            )
            for r in indexes
        )
        assert found, f"Expected vector index ctrl_embedding_idx on Control(embedding). Got: {indexes}"

    def test_chunk_vector_index_exists(self, test_driver):
        with test_driver.session() as session:
            result = session.run("SHOW INDEX INFO")
            indexes = [dict(r) for r in result]
        found = any(
            (r.get("index name") or r.get("index_name") or r.get("name") or "") == "chunk_embedding_idx"
            or (
                (r.get("label") or r.get("Label") or "") == "Chunk"
                and (r.get("property") or r.get("Property") or "") == "embedding"
                and "vector" in str(r.get("index type") or r.get("type") or r.get("Type") or "").lower()
            )
            for r in indexes
        )
        assert found, f"Expected vector index chunk_embedding_idx on Chunk(embedding). Got: {indexes}"

    def test_norm_unique_constraint_exists(self, test_driver):
        with test_driver.session() as session:
            result = session.run("SHOW CONSTRAINT INFO")
            constraints = [dict(r) for r in result]
        found = self._constraint_exists(constraints, "Norm", "id")
        assert found, f"Expected UNIQUE constraint on Norm.id. Got: {constraints}"


# ---------------------------------------------------------------------------
# TestKnowledgeWriteIntegration
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def wr_cleanup(test_driver):
    with test_driver.session() as s:
        s.run("MATCH (n) WHERE n.id STARTS WITH 'test-wp076-wr-' DETACH DELETE n")
    yield
    with test_driver.session() as s:
        s.run("MATCH (n) WHERE n.id STARTS WITH 'test-wp076-wr-' DETACH DELETE n")


@pytest.mark.integration
class TestKnowledgeWriteIntegration:
    """End-to-end write tests against the live stack."""

    def test_upsert_framework_roundtrip(self, knowledge_client, test_driver):
        fw_id = "test-wp076-wr-fw-001"
        resp = knowledge_client.post("/knowledge/frameworks", json={
            "id": fw_id, "name": "WP076 Test Framework", "version": "1.0",
            "description": "Integration test framework"
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == fw_id
        assert body["name"] == "WP076 Test Framework"

        get_resp = knowledge_client.get(f"/knowledge/frameworks/{fw_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["version"] == "1.0"
        assert node_exists(test_driver, "Framework", fw_id)

    def test_upsert_control_roundtrip(self, knowledge_client, test_driver):
        ctrl_id = "test-wp076-wr-ctrl-001"
        resp = knowledge_client.post("/knowledge/controls", json={
            "id": ctrl_id, "name": "Access Control Policy WP076",
            "framework_id": "test-wp076-wr-fw-001",
            "description": "Test control for WP-076"
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == ctrl_id
        assert body["framework_id"] == "test-wp076-wr-fw-001"

        get_resp = knowledge_client.get(f"/knowledge/controls/{ctrl_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Access Control Policy WP076"
        assert node_exists(test_driver, "Control", ctrl_id)

    def test_upsert_control_idempotent(self, knowledge_client, test_driver):
        ctrl_id = "test-wp076-wr-ctrl-idem-001"
        payload = {
            "id": ctrl_id, "name": "Idempotent Control WP076",
            "framework_id": "test-wp076-wr-fw-001"
        }
        resp1 = knowledge_client.post("/knowledge/controls", json=payload)
        assert resp1.status_code == 200, resp1.text
        resp2 = knowledge_client.post("/knowledge/controls", json=payload)
        assert resp2.status_code == 200, resp2.text

        with test_driver.session() as s:
            result = s.run(
                "MATCH (c:Control {id: $id}) RETURN count(c) AS cnt",
                id=ctrl_id
            )
            count = result.single()["cnt"]
        assert count == 1, f"Expected exactly 1 Control node, got {count}"

    def test_upsert_control_with_parent_creates_contains_edge(self, knowledge_client, test_driver):
        parent_id = "test-wp076-wr-ctrl-parent-001"
        child_id = "test-wp076-wr-ctrl-child-001"

        knowledge_client.post("/knowledge/controls", json={
            "id": parent_id, "name": "Parent Control WP076",
            "framework_id": "test-wp076-wr-fw-001"
        })
        resp = knowledge_client.post("/knowledge/controls", json={
            "id": child_id, "name": "Child Control WP076",
            "framework_id": "test-wp076-wr-fw-001",
            "parent_id": parent_id
        })
        assert resp.status_code == 200, resp.text
        assert edge_exists(test_driver, parent_id, "CONTAINS", child_id)

    def test_upsert_norm_roundtrip(self, knowledge_client, test_driver):
        norm_id = "test-wp076-wr-norm-001"
        resp = knowledge_client.post("/knowledge/norms", json={
            "id": norm_id, "name": "Norm WP076",
            "text": "All access must be authenticated for WP076 test",
            "status": "active"
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == norm_id
        assert body["status"] == "active"

        get_resp = knowledge_client.get(f"/knowledge/norms/{norm_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Norm WP076"
        assert node_exists(test_driver, "Norm", norm_id)

    def test_upsert_norm_creates_implements_edge(self, knowledge_client, test_driver):
        ctrl_id = "test-wp076-wr-ctrl-for-norm-001"
        norm_id = "test-wp076-wr-norm-impl-001"

        knowledge_client.post("/knowledge/controls", json={
            "id": ctrl_id, "name": "Control For Norm WP076",
            "framework_id": "test-wp076-wr-fw-001"
        })
        resp = knowledge_client.post("/knowledge/norms", json={
            "id": norm_id, "name": "Implements Norm WP076",
            "text": "Must implement password policy for WP076",
            "control_id": ctrl_id
        })
        assert resp.status_code == 200, resp.text
        assert edge_exists(test_driver, norm_id, "IMPLEMENTS", ctrl_id)

    def test_upsert_norm_creates_sourced_from_edge(self, knowledge_client, test_driver):
        doc_id = "test-wp076-wr-doc-for-norm-001"
        norm_id = "test-wp076-wr-norm-src-001"

        knowledge_client.post("/knowledge/documents", json={
            "id": doc_id, "title": "Source Doc WP076", "doc_type": "policy"
        })
        resp = knowledge_client.post("/knowledge/norms", json={
            "id": norm_id, "name": "Sourced Norm WP076",
            "text": "Security policy requirement from source document WP076",
            "doc_id": doc_id
        })
        assert resp.status_code == 200, resp.text
        assert edge_exists(test_driver, norm_id, "SOURCED_FROM", doc_id)

    def test_upsert_document_roundtrip(self, knowledge_client, test_driver):
        doc_id = "test-wp076-wr-doc-001"
        resp = knowledge_client.post("/knowledge/documents", json={
            "id": doc_id, "title": "Policy Doc WP076",
            "doc_type": "policy", "source_url": "https://example.com/wp076"
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == doc_id
        assert body["doc_type"] == "policy"

        get_resp = knowledge_client.get(f"/knowledge/documents/{doc_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["title"] == "Policy Doc WP076"
        assert node_exists(test_driver, "Document", doc_id)

    def test_upsert_chunk_roundtrip(self, knowledge_client, test_driver):
        doc_id = "test-wp076-wr-doc-for-chunk-001"
        chunk_id = "test-wp076-wr-chunk-001"

        knowledge_client.post("/knowledge/documents", json={
            "id": doc_id, "title": "Doc For Chunk WP076", "doc_type": "standard"
        })
        resp = knowledge_client.post("/knowledge/chunks", json={
            "id": chunk_id, "text": "Chapter 1 access control requirements for WP076",
            "sequence": 0, "doc_id": doc_id
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == chunk_id
        assert body["doc_id"] == doc_id

        get_resp = knowledge_client.get(f"/knowledge/chunks/{chunk_id}")
        assert get_resp.status_code == 200
        assert node_exists(test_driver, "Chunk", chunk_id)
        assert edge_exists(test_driver, doc_id, "HAS_CHUNK", chunk_id)

    def test_upsert_chunk_with_prev_creates_has_next_edge(self, knowledge_client, test_driver):
        doc_id = "test-wp076-wr-doc-chain-001"
        chunk1_id = "test-wp076-wr-chunk-chain-001"
        chunk2_id = "test-wp076-wr-chunk-chain-002"

        knowledge_client.post("/knowledge/documents", json={
            "id": doc_id, "title": "Chain Doc WP076", "doc_type": "guideline"
        })
        knowledge_client.post("/knowledge/chunks", json={
            "id": chunk1_id, "text": "First chunk for chain test WP076",
            "sequence": 0, "doc_id": doc_id
        })
        resp = knowledge_client.post("/knowledge/chunks", json={
            "id": chunk2_id, "text": "Second chunk for chain test WP076",
            "sequence": 1, "doc_id": doc_id, "prev_chunk_id": chunk1_id
        })
        assert resp.status_code == 200, resp.text
        assert edge_exists(test_driver, chunk1_id, "HAS_NEXT", chunk2_id)

    def test_upsert_chunk_idempotent(self, knowledge_client, test_driver):
        doc_id = "test-wp076-wr-doc-idem-001"
        chunk_id = "test-wp076-wr-chunk-idem-001"

        knowledge_client.post("/knowledge/documents", json={
            "id": doc_id, "title": "Idem Doc WP076", "doc_type": "procedure"
        })
        payload = {
            "id": chunk_id, "text": "Idempotent chunk content for WP076",
            "sequence": 0, "doc_id": doc_id
        }
        resp1 = knowledge_client.post("/knowledge/chunks", json=payload)
        assert resp1.status_code == 200, resp1.text
        resp2 = knowledge_client.post("/knowledge/chunks", json=payload)
        assert resp2.status_code == 200, resp2.text

        with test_driver.session() as s:
            result = s.run(
                "MATCH (ch:Chunk {id: $id}) RETURN count(ch) AS cnt",
                id=chunk_id
            )
            count = result.single()["cnt"]
        assert count == 1, f"Expected exactly 1 Chunk node, got {count}"

    def test_create_supports_edge(self, knowledge_client, test_driver):
        doc_id = "test-wp076-wr-doc-sup-001"
        chunk_id = "test-wp076-wr-chunk-sup-001"
        ctrl_id = "test-wp076-wr-ctrl-sup-001"

        knowledge_client.post("/knowledge/frameworks", json={
            "id": "test-wp076-wr-fw-sup-001", "name": "Sup Framework WP076"
        })
        knowledge_client.post("/knowledge/controls", json={
            "id": ctrl_id, "name": "Supported Control WP076",
            "framework_id": "test-wp076-wr-fw-sup-001"
        })
        knowledge_client.post("/knowledge/documents", json={
            "id": doc_id, "title": "Sup Doc WP076", "doc_type": "standard"
        })
        knowledge_client.post("/knowledge/chunks", json={
            "id": chunk_id, "text": "Evidence chunk for supports edge WP076",
            "sequence": 0, "doc_id": doc_id
        })

        resp = knowledge_client.post("/knowledge/chunk/supports", json={
            "chunk_id": chunk_id, "control_id": ctrl_id,
            "confidence": 0.85, "status": "manual"
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["confidence"] == 0.85
        assert body["status"] == "manual"

        assert edge_exists(test_driver, chunk_id, "SUPPORTS", ctrl_id)
        props = get_edge_props(test_driver, chunk_id, "SUPPORTS", ctrl_id)
        assert abs(props["confidence"] - 0.85) < 1e-6

    def test_get_chunks_for_control(self, knowledge_client, test_driver):
        doc_id = "test-wp076-wr-doc-getchunks-001"
        chunk_id_a = "test-wp076-wr-chunk-getchunks-001"
        chunk_id_b = "test-wp076-wr-chunk-getchunks-002"
        ctrl_id = "test-wp076-wr-ctrl-getchunks-001"

        knowledge_client.post("/knowledge/frameworks", json={
            "id": "test-wp076-wr-fw-getchunks-001", "name": "GetChunks Framework WP076"
        })
        knowledge_client.post("/knowledge/controls", json={
            "id": ctrl_id, "name": "GetChunks Control WP076",
            "framework_id": "test-wp076-wr-fw-getchunks-001"
        })
        knowledge_client.post("/knowledge/documents", json={
            "id": doc_id, "title": "GetChunks Doc WP076", "doc_type": "policy"
        })
        knowledge_client.post("/knowledge/chunks", json={
            "id": chunk_id_a, "text": "First evidence chunk for get_chunks WP076",
            "sequence": 0, "doc_id": doc_id
        })
        knowledge_client.post("/knowledge/chunks", json={
            "id": chunk_id_b, "text": "Second evidence chunk for get_chunks WP076",
            "sequence": 1, "doc_id": doc_id
        })
        knowledge_client.post("/knowledge/chunk/supports", json={
            "chunk_id": chunk_id_a, "control_id": ctrl_id, "confidence": 0.9
        })
        knowledge_client.post("/knowledge/chunk/supports", json={
            "chunk_id": chunk_id_b, "control_id": ctrl_id, "confidence": 0.7
        })

        resp = knowledge_client.get(f"/knowledge/controls/{ctrl_id}/chunks")
        assert resp.status_code == 200, resp.text
        chunks = resp.json()
        returned_ids = {c["id"] for c in chunks}
        assert chunk_id_a in returned_ids
        assert chunk_id_b in returned_ids


# ---------------------------------------------------------------------------
# TestKnowledgeSearchIntegration
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def sr_cleanup(test_driver):
    with test_driver.session() as s:
        s.run("MATCH (n) WHERE n.id STARTS WITH 'test-wp076-sr-' DETACH DELETE n")
    yield
    with test_driver.session() as s:
        s.run("MATCH (n) WHERE n.id STARTS WITH 'test-wp076-sr-' DETACH DELETE n")


@pytest.fixture(scope="module")
def seed_search_data(knowledge_client):
    """Seed all data required by search tests. Module-scoped so seeding runs once."""
    knowledge_client.post("/knowledge/frameworks", json={
        "id": "test-wp076-sr-fw-A", "name": "Search Framework A WP076"
    })
    knowledge_client.post("/knowledge/frameworks", json={
        "id": "test-wp076-sr-fw-B", "name": "Search Framework B WP076"
    })

    for ctrl in [
        ("test-wp076-sr-ctrl-A1", "access control policy for test-wp076-sr framework A first", "test-wp076-sr-fw-A"),
        ("test-wp076-sr-ctrl-A2", "encryption standard for test-wp076-sr framework A second", "test-wp076-sr-fw-A"),
        ("test-wp076-sr-ctrl-A3", "vulnerability management for test-wp076-sr framework A third", "test-wp076-sr-fw-A"),
        ("test-wp076-sr-ctrl-B1", "incident response plan for test-wp076-sr framework B first", "test-wp076-sr-fw-B"),
        ("test-wp076-sr-ctrl-B2", "business continuity for test-wp076-sr framework B second", "test-wp076-sr-fw-B"),
    ]:
        knowledge_client.post("/knowledge/controls", json={"id": ctrl[0], "name": ctrl[1], "framework_id": ctrl[2]})

    knowledge_client.post("/knowledge/documents", json={
        "id": "test-wp076-sr-doc-A", "title": "Search Doc A WP076", "doc_type": "policy"
    })
    knowledge_client.post("/knowledge/documents", json={
        "id": "test-wp076-sr-doc-B", "title": "Search Doc B WP076", "doc_type": "standard"
    })

    for chunk in [
        ("test-wp076-sr-chunk-A1", "access control requirements for test-wp076-sr document A chunk one", 0, "test-wp076-sr-doc-A"),
        ("test-wp076-sr-chunk-A2", "password policy specification for test-wp076-sr document A chunk two", 1, "test-wp076-sr-doc-A"),
        ("test-wp076-sr-chunk-A3", "multi-factor authentication rules for test-wp076-sr document A chunk three", 2, "test-wp076-sr-doc-A"),
        ("test-wp076-sr-chunk-B1", "incident handling procedures for test-wp076-sr document B chunk one", 0, "test-wp076-sr-doc-B"),
        ("test-wp076-sr-chunk-B2", "crisis management protocols for test-wp076-sr document B chunk two", 1, "test-wp076-sr-doc-B"),
    ]:
        knowledge_client.post("/knowledge/chunks", json={"id": chunk[0], "text": chunk[1], "sequence": chunk[2], "doc_id": chunk[3]})

    for norm in [
        ("test-wp076-sr-norm-001", "SR Norm Alpha WP076", "Norm alpha text for test-wp076-sr"),
        ("test-wp076-sr-norm-002", "SR Norm Beta WP076", "Norm beta text for test-wp076-sr"),
        ("test-wp076-sr-norm-003", "SR Norm Gamma WP076", "Norm gamma text for test-wp076-sr"),
    ]:
        knowledge_client.post("/knowledge/norms", json={"id": norm[0], "name": norm[1], "text": norm[2]})


@pytest.mark.integration
class TestKnowledgeSearchIntegration:
    """Vector search and list endpoint tests against the live stack.

    Seed data: 3 controls in framework A, 2 controls in framework B;
    3 chunks in doc A, 2 chunks in doc B. Seeded by module-scoped seed_search_data fixture.
    """

    def test_search_controls_returns_seeded_controls(self, knowledge_client, seed_search_data):
        resp = knowledge_client.post("/knowledge/search/controls", json={
            "query": "access control policy test-wp076-sr", "limit": 20
        })
        assert resp.status_code == 200, resp.text
        hits = resp.json()
        assert len(hits) > 0, "Expected at least one search result"
        hit_ids = {h["id"] for h in hits}
        assert "test-wp076-sr-ctrl-A1" in hit_ids, f"ctrl-A1 not found. Hit IDs: {hit_ids}"
        # All hits must have a distance field
        for h in hits:
            assert "distance" in h, f"Missing distance in hit: {h}"

    def test_search_controls_framework_filter(self, knowledge_client, seed_search_data):
        resp = knowledge_client.post("/knowledge/search/controls", json={
            "query": "test-wp076-sr", "limit": 20,
            "framework_id": "test-wp076-sr-fw-B"
        })
        assert resp.status_code == 200, resp.text
        hits = resp.json()
        # All returned controls must belong to fw-B
        for h in hits:
            assert h["framework_id"] == "test-wp076-sr-fw-B", (
                f"Control {h['id']} has framework_id {h['framework_id']}, expected fw-B"
            )

    def test_search_chunks_returns_seeded_chunks(self, knowledge_client, seed_search_data):
        resp = knowledge_client.post("/knowledge/search/chunks", json={
            "query": "access control requirements test-wp076-sr", "limit": 20
        })
        assert resp.status_code == 200, resp.text
        hits = resp.json()
        assert len(hits) > 0, "Expected at least one chunk search result"
        hit_ids = {h["id"] for h in hits}
        assert "test-wp076-sr-chunk-A1" in hit_ids, f"chunk-A1 not found. Hit IDs: {hit_ids}"
        for h in hits:
            assert "distance" in h

    def test_search_chunks_doc_filter(self, knowledge_client, seed_search_data):
        resp = knowledge_client.post("/knowledge/search/chunks", json={
            "query": "test-wp076-sr", "limit": 20,
            "doc_id": "test-wp076-sr-doc-B"
        })
        assert resp.status_code == 200, resp.text
        hits = resp.json()
        for h in hits:
            assert h["doc_id"] == "test-wp076-sr-doc-B", (
                f"Chunk {h['id']} has doc_id {h['doc_id']}, expected doc-B"
            )

    def test_search_controls_knowledge_only_mode(self, knowledge_client, test_driver):
        """Search returns results even with zero Memory nodes — ADR-001 standalone mode."""
        with test_driver.session() as s:
            result = s.run("MATCH (m:Memory) RETURN count(m) AS cnt")
            mem_count = result.single()["cnt"]

        resp = knowledge_client.post("/knowledge/search/controls", json={
            "query": "test-wp076-sr framework", "limit": 20
        })
        assert resp.status_code == 200, resp.text
        hits = resp.json()
        # If there are seeded controls, search should return them regardless of Memory count
        if mem_count == 0:
            assert len(hits) > 0, (
                "Search returned no results with zero Memory nodes — ADR-001 knowledge-only mode broken"
            )

    def test_list_norms_returns_all(self, knowledge_client, seed_search_data):
        resp = knowledge_client.get("/knowledge/norms")
        assert resp.status_code == 200, resp.text
        norms = resp.json()
        norm_ids = {n["id"] for n in norms}
        assert "test-wp076-sr-norm-001" in norm_ids
        assert "test-wp076-sr-norm-002" in norm_ids
        assert "test-wp076-sr-norm-003" in norm_ids

    def test_list_documents_returns_all(self, knowledge_client, seed_search_data):
        resp = knowledge_client.get("/knowledge/documents")
        assert resp.status_code == 200, resp.text
        docs = resp.json()
        doc_ids = {d["id"] for d in docs}
        assert "test-wp076-sr-doc-A" in doc_ids
        assert "test-wp076-sr-doc-B" in doc_ids


# ---------------------------------------------------------------------------
# TestCrossLayerIntegration
# ---------------------------------------------------------------------------


def _cl_wipe(s):
    """Delete all test-wp076-cl-* nodes and any orphaned Memory nodes from this test class."""
    s.run("MATCH (n) WHERE n.id STARTS WITH 'test-wp076-cl-' DETACH DELETE n")
    s.run(
        "MATCH (m:Memory)-[:PRODUCED_BY]->(a:Agent {id: $agent_id}) DETACH DELETE m",
        agent_id="test-wp076-cl-agent",
    )
    # Catch fact-text-prefixed orphans (created when validation returns 400 before PRODUCED_BY edge)
    s.run("MATCH (m:Memory) WHERE m.fact STARTS WITH 'wp076-cl-' DETACH DELETE m")
    s.run("MATCH (m:Memory) WHERE m.fact STARTS WITH 'test-wp076-cl' DETACH DELETE m")
    # Catch by test tag (safety net)
    s.run("MATCH (m:Memory) WHERE 'test' IN m.tags AND m.fact CONTAINS 'wp076' DETACH DELETE m")


@pytest.fixture(scope="module", autouse=True)
def cl_cleanup(test_driver):
    with test_driver.session() as s:
        _cl_wipe(s)
    yield
    with test_driver.session() as s:
        _cl_wipe(s)


@pytest.mark.integration
class TestCrossLayerIntegration:
    """Cross-layer edge tests: ABOUT_CONTROL and CITES_DOC edges on Memory nodes."""

    @pytest.fixture(scope="class")
    def cl_data(self, knowledge_client):
        """Seed 1 Framework, 2 Controls, 2 Documents shared by all tests in the class."""
        fw_id = "test-wp076-cl-fw-001"
        ctrl1_id = "test-wp076-cl-ctrl-001"
        ctrl2_id = "test-wp076-cl-ctrl-002"
        doc1_id = "test-wp076-cl-doc-001"
        doc2_id = "test-wp076-cl-doc-002"

        knowledge_client.post("/knowledge/frameworks", json={
            "id": fw_id, "name": "CL Framework WP076",
        })
        knowledge_client.post("/knowledge/controls", json={
            "id": ctrl1_id, "name": "CL Control One WP076",
            "framework_id": fw_id,
        })
        knowledge_client.post("/knowledge/controls", json={
            "id": ctrl2_id, "name": "CL Control Two WP076",
            "framework_id": fw_id,
        })
        knowledge_client.post("/knowledge/documents", json={
            "id": doc1_id, "title": "CL Document One WP076", "doc_type": "policy",
        })
        knowledge_client.post("/knowledge/documents", json={
            "id": doc2_id, "title": "CL Document Two WP076", "doc_type": "standard",
        })

        return {
            "fw_id": fw_id,
            "ctrl1_id": ctrl1_id,
            "ctrl2_id": ctrl2_id,
            "doc1_id": doc1_id,
            "doc2_id": doc2_id,
        }

    def test_add_memory_with_control_ids_creates_about_control_edge(
        self, client, knowledge_client, test_driver, cl_data
    ):
        """POST /memory with control_ids creates ABOUT_CONTROL edge in graph."""
        memory_id = None
        try:
            resp = client.post("/memory", json={
                "fact": "test-wp076-cl add memory control edge fact",
                "type": "fact",
                "agent_id": "test-wp076-cl-agent",
                "control_ids": [cl_data["ctrl1_id"]],
                "tags": ["test"],
                "ephemeral": True,
            })
            assert resp.status_code == 200, resp.text
            memory_id = resp.json()["memory_id"]
            assert edge_exists(test_driver, memory_id, "ABOUT_CONTROL", cl_data["ctrl1_id"])
        finally:
            if memory_id:
                from tests.conftest import cleanup_nodes
                cleanup_nodes(test_driver, memory_id)

    def test_add_memory_about_control_stores_relationship_type(
        self, client, knowledge_client, test_driver, cl_data
    ):
        """ABOUT_CONTROL edge stores relationship_type property."""
        memory_id = None
        try:
            resp = client.post("/memory", json={
                "fact": "test-wp076-cl relationship type evidence fact",
                "type": "fact",
                "agent_id": "test-wp076-cl-agent",
                "control_ids": [cl_data["ctrl1_id"]],
                "control_relationship_type": "evidence",
                "tags": ["test"],
                "ephemeral": True,
            })
            assert resp.status_code == 200, resp.text
            memory_id = resp.json()["memory_id"]
            props = get_edge_props(test_driver, memory_id, "ABOUT_CONTROL", cl_data["ctrl1_id"])
            assert props.get("relationship_type") == "evidence"
        finally:
            if memory_id:
                from tests.conftest import cleanup_nodes
                cleanup_nodes(test_driver, memory_id)

    def test_add_memory_about_control_stores_org_id(
        self, client, knowledge_client, test_driver, cl_data
    ):
        """ABOUT_CONTROL edge stores org_id property."""
        memory_id = None
        try:
            resp = client.post("/memory", json={
                "fact": "test-wp076-cl org id edge fact",
                "type": "fact",
                "agent_id": "test-wp076-cl-agent",
                "control_ids": [cl_data["ctrl1_id"]],
                "org_id": "test-wp076-cl-org-eu",
                "tags": ["test"],
                "ephemeral": True,
            })
            assert resp.status_code == 200, resp.text
            memory_id = resp.json()["memory_id"]
            props = get_edge_props(test_driver, memory_id, "ABOUT_CONTROL", cl_data["ctrl1_id"])
            assert props.get("org_id") == "test-wp076-cl-org-eu"
        finally:
            if memory_id:
                from tests.conftest import cleanup_nodes
                cleanup_nodes(test_driver, memory_id)

    def test_update_memory_replaces_control_edges(
        self, client, knowledge_client, test_driver, cl_data
    ):
        """PATCH /memory/{id} with new control_ids replaces ABOUT_CONTROL edges."""
        memory_id = None
        try:
            resp = client.post("/memory", json={
                "fact": "test-wp076-cl update control edges fact",
                "type": "fact",
                "agent_id": "test-wp076-cl-agent",
                "control_ids": [cl_data["ctrl1_id"]],
                "tags": ["test"],
                "ephemeral": True,
            })
            assert resp.status_code == 200, resp.text
            memory_id = resp.json()["memory_id"]
            assert edge_exists(test_driver, memory_id, "ABOUT_CONTROL", cl_data["ctrl1_id"])

            patch_resp = client.patch(f"/memory/{memory_id}", json={
                "control_ids": [cl_data["ctrl2_id"]],
            })
            assert patch_resp.status_code == 200, patch_resp.text

            assert not edge_exists(test_driver, memory_id, "ABOUT_CONTROL", cl_data["ctrl1_id"])
            assert edge_exists(test_driver, memory_id, "ABOUT_CONTROL", cl_data["ctrl2_id"])
        finally:
            if memory_id:
                from tests.conftest import cleanup_nodes
                cleanup_nodes(test_driver, memory_id)

    def test_update_memory_replaces_doc_edges(
        self, client, knowledge_client, test_driver, cl_data
    ):
        """PATCH /memory/{id} with new doc_ids replaces CITES_DOC edges."""
        memory_id = None
        try:
            resp = client.post("/memory", json={
                "fact": "test-wp076-cl update doc edges fact",
                "type": "fact",
                "agent_id": "test-wp076-cl-agent",
                "doc_ids": [cl_data["doc1_id"]],
                "tags": ["test"],
                "ephemeral": True,
            })
            assert resp.status_code == 200, resp.text
            memory_id = resp.json()["memory_id"]
            assert edge_exists(test_driver, memory_id, "CITES_DOC", cl_data["doc1_id"])

            patch_resp = client.patch(f"/memory/{memory_id}", json={
                "doc_ids": [cl_data["doc2_id"]],
            })
            assert patch_resp.status_code == 200, patch_resp.text

            assert not edge_exists(test_driver, memory_id, "CITES_DOC", cl_data["doc1_id"])
            assert edge_exists(test_driver, memory_id, "CITES_DOC", cl_data["doc2_id"])
        finally:
            if memory_id:
                from tests.conftest import cleanup_nodes
                cleanup_nodes(test_driver, memory_id)

    def test_add_memory_with_doc_ids_creates_cites_doc_edge(
        self, client, knowledge_client, test_driver, cl_data
    ):
        """POST /memory with doc_ids creates CITES_DOC edge."""
        memory_id = None
        try:
            resp = client.post("/memory", json={
                "fact": "test-wp076-cl add memory doc edge fact",
                "type": "fact",
                "agent_id": "test-wp076-cl-agent",
                "doc_ids": [cl_data["doc1_id"]],
                "tags": ["test"],
                "ephemeral": True,
            })
            assert resp.status_code == 200, resp.text
            memory_id = resp.json()["memory_id"]
            assert edge_exists(test_driver, memory_id, "CITES_DOC", cl_data["doc1_id"])
        finally:
            if memory_id:
                from tests.conftest import cleanup_nodes
                cleanup_nodes(test_driver, memory_id)

    def test_add_memory_missing_control_returns_400(
        self, knowledge_client, test_driver
    ):
        """POST /memory with nonexistent control_id returns HTTP 400."""
        import uuid as _uuid
        resp = knowledge_client.post("/memory", json={
            "fact": f"wp076-cl-ctrl-missing-validation-sentinel-{_uuid.uuid4()}",
            "type": "fact",
            "agent_id": "test-wp076-cl-agent",
            "control_ids": ["test-wp076-cl-nonexistent-ctrl"],
            "tags": ["test"],
        })
        assert resp.status_code == 400, resp.text
        assert "test-wp076-cl-nonexistent-ctrl" in resp.json()["detail"]

    def test_add_memory_missing_doc_returns_400(
        self, knowledge_client, test_driver
    ):
        """POST /memory with nonexistent doc_id returns HTTP 400."""
        import uuid as _uuid
        resp = knowledge_client.post("/memory", json={
            "fact": f"wp076-cl-doc-missing-validation-sentinel-{_uuid.uuid4()}",
            "type": "fact",
            "agent_id": "test-wp076-cl-agent",
            "doc_ids": ["test-wp076-cl-nonexistent-doc"],
            "tags": ["test"],
        })
        assert resp.status_code == 400, resp.text
        assert "test-wp076-cl-nonexistent-doc" in resp.json()["detail"]

    def test_search_memory_hydrates_controls(
        self, client, knowledge_client, test_driver, cl_data
    ):
        """POST /memory/search returns controls[] in MemoryHit for memory linked to a control."""
        memory_id = None
        try:
            resp = client.post("/memory", json={
                "fact": "test-wp076-cl hydrate controls search fact",
                "type": "fact",
                "agent_id": "test-wp076-cl-agent",
                "control_ids": [cl_data["ctrl1_id"]],
                "tags": ["test"],
            })
            assert resp.status_code == 200, resp.text
            memory_id = resp.json()["memory_id"]

            search_resp = client.post("/memory/search", json={
                "query": "test-wp076-cl hydrate controls search fact",
                "limit": 10,
            })
            assert search_resp.status_code == 200, search_resp.text
            hits = search_resp.json()["memories"]
            hit = next((h for h in hits if h["id"] == memory_id), None)
            assert hit is not None, f"Memory {memory_id} not found in search results"
            ctrl_ids = [c["id"] for c in hit.get("controls", [])]
            assert cl_data["ctrl1_id"] in ctrl_ids, (
                f"Expected {cl_data['ctrl1_id']} in controls, got: {ctrl_ids}"
            )
        finally:
            if memory_id:
                from tests.conftest import cleanup_nodes
                cleanup_nodes(test_driver, memory_id)

    def test_search_memory_hydrates_documents(
        self, client, knowledge_client, test_driver, cl_data
    ):
        """POST /memory/search returns documents[] in MemoryHit for memory linked to a document."""
        memory_id = None
        try:
            resp = client.post("/memory", json={
                "fact": "test-wp076-cl hydrate documents search fact",
                "type": "fact",
                "agent_id": "test-wp076-cl-agent",
                "doc_ids": [cl_data["doc1_id"]],
                "tags": ["test"],
                "ephemeral": True,
            })
            assert resp.status_code == 200, resp.text
            memory_id = resp.json()["memory_id"]

            search_resp = client.post("/memory/search", json={
                "query": "test-wp076-cl hydrate documents search fact",
                "limit": 10,
            })
            assert search_resp.status_code == 200, search_resp.text
            hits = search_resp.json()["memories"]
            hit = next((h for h in hits if h["id"] == memory_id), None)
            assert hit is not None, f"Memory {memory_id} not found in search results"
            doc_ids = [d["id"] for d in hit.get("documents", [])]
            assert cl_data["doc1_id"] in doc_ids, (
                f"Expected {cl_data['doc1_id']} in documents, got: {doc_ids}"
            )
        finally:
            if memory_id:
                from tests.conftest import cleanup_nodes
                cleanup_nodes(test_driver, memory_id)

    def test_merge_memory_rewires_about_control(
        self, client, knowledge_client, test_driver, cl_data
    ):
        """merge_memory transfers ABOUT_CONTROL from source to target."""
        source_id = None
        target_id = None
        try:
            source_resp = client.post("/memory", json={
                "fact": "test-wp076-cl merge source control fact",
                "type": "fact",
                "agent_id": "test-wp076-cl-agent",
                "control_ids": [cl_data["ctrl1_id"]],
                "tags": ["test"],
                "ephemeral": True,
            })
            assert source_resp.status_code == 200, source_resp.text
            source_id = source_resp.json()["memory_id"]

            target_resp = client.post("/memory", json={
                "fact": "test-wp076-cl merge target control fact",
                "type": "fact",
                "agent_id": "test-wp076-cl-agent",
                "tags": ["test"],
                "ephemeral": True,
            })
            assert target_resp.status_code == 200, target_resp.text
            target_id = target_resp.json()["memory_id"]

            merge_resp = client.post(f"/memory/{source_id}/merge", json={
                "target_id": target_id,
            })
            assert merge_resp.status_code == 200, merge_resp.text

            # Source is marked merged (not deleted); target acquires the edge
            assert edge_exists(test_driver, target_id, "ABOUT_CONTROL", cl_data["ctrl1_id"])
            src_node = get_memory_node(test_driver, source_id)
            assert src_node is not None
            assert src_node.get("status") == "merged"
        finally:
            if source_id:
                from tests.conftest import cleanup_nodes
                cleanup_nodes(test_driver, source_id)
            if target_id:
                from tests.conftest import cleanup_nodes
                cleanup_nodes(test_driver, target_id)

    def test_merge_memory_rewires_cites_doc(
        self, client, knowledge_client, test_driver, cl_data
    ):
        """merge_memory transfers CITES_DOC from source to target."""
        source_id = None
        target_id = None
        try:
            source_resp = client.post("/memory", json={
                "fact": "test-wp076-cl merge source doc fact",
                "type": "fact",
                "agent_id": "test-wp076-cl-agent",
                "doc_ids": [cl_data["doc1_id"]],
                "tags": ["test"],
                "ephemeral": True,
            })
            assert source_resp.status_code == 200, source_resp.text
            source_id = source_resp.json()["memory_id"]

            target_resp = client.post("/memory", json={
                "fact": "test-wp076-cl merge target doc fact",
                "type": "fact",
                "agent_id": "test-wp076-cl-agent",
                "tags": ["test"],
                "ephemeral": True,
            })
            assert target_resp.status_code == 200, target_resp.text
            target_id = target_resp.json()["memory_id"]

            merge_resp = client.post(f"/memory/{source_id}/merge", json={
                "target_id": target_id,
            })
            assert merge_resp.status_code == 200, merge_resp.text

            # Source is marked merged (not deleted); target acquires the edge
            assert edge_exists(test_driver, target_id, "CITES_DOC", cl_data["doc1_id"])
            src_node = get_memory_node(test_driver, source_id)
            assert src_node is not None
            assert src_node.get("status") == "merged"
        finally:
            if source_id:
                from tests.conftest import cleanup_nodes
                cleanup_nodes(test_driver, source_id)
            if target_id:
                from tests.conftest import cleanup_nodes
                cleanup_nodes(test_driver, target_id)

    def test_flag_off_knowledge_routes_return_404(self):
        """With ENABLE_KNOWLEDGE_LAYER=false, /knowledge/* returns 404.

        Unit-level test (no live stack needed). Reloads app with flag off.
        """
        import importlib
        import os
        os.environ["ENABLE_KNOWLEDGE_LAYER"] = "false"
        import memory_service.config as cfg_mod
        import memory_service.main as main_mod
        importlib.reload(cfg_mod)
        importlib.reload(main_mod)
        from fastapi.testclient import TestClient
        from unittest.mock import MagicMock
        main_mod.app.state.driver = MagicMock()
        with TestClient(main_mod.app) as c:
            resp = c.get("/knowledge/frameworks/any")
        os.environ["ENABLE_KNOWLEDGE_LAYER"] = "true"  # restore
        assert resp.status_code == 404

    def test_flag_off_add_memory_ignores_control_ids(self):
        """With ENABLE_KNOWLEDGE_LAYER=false, POST /memory with control_ids does not create ABOUT_CONTROL edge.

        Unit-level test (no live stack needed).
        """
        import importlib
        import os
        from unittest.mock import MagicMock, patch
        os.environ["ENABLE_KNOWLEDGE_LAYER"] = "false"
        import memory_service.config as cfg_mod
        import memory_service.main as main_mod
        importlib.reload(cfg_mod)
        importlib.reload(main_mod)
        from fastapi.testclient import TestClient

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = lambda s: mock_session
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        main_mod.app.state.driver = mock_driver

        with TestClient(main_mod.app) as c:
            with patch("memory_service.memory_repo.find_duplicate_memory", return_value=None), \
                 patch("memory_service.memory_repo.add_memory"), \
                 patch("cyber_knowledge.bridge.link_controls") as mock_link:
                resp = c.post("/memory", json={
                    "fact": "test-wp076-cl flag off fact",
                    "type": "fact",
                    "agent_id": "test-wp076-cl-agent",
                    "control_ids": ["some-control-id"],
                })
        os.environ["ENABLE_KNOWLEDGE_LAYER"] = "true"  # restore
        assert resp.status_code == 200, resp.text
        mock_link.assert_not_called()
