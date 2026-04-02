"""
tests/test_add_memory.py — Integration tests for POST /memory (WP-004).

Requires Memgraph running with schema initialised (run scripts/init_schema.py first).
All tests clean up their own nodes.
"""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable
from pydantic import ValidationError

from memory_service.main import AddMemoryRequest
from tests.conftest import cleanup_nodes, edge_exists, get_memory_node, node_exists


# Shared test context node ids
_AGENT_ID = "test-agent-001"
_PROJECT_ID = "test-project-001"
_PERSON_ID_1 = "test-person-001"
_PERSON_ID_2 = "test-person-002"
_STRAND_ID = "test-strand-001"

_CONTEXT_IDS = {
    "Agent": _AGENT_ID,
    "Project": _PROJECT_ID,
    "Person": _PERSON_ID_1,
    "Strand": _STRAND_ID,
}


def _cleanup(driver, *memory_ids):
    cleanup_nodes(driver, *memory_ids, extra_ids=_CONTEXT_IDS)
    with driver.session() as session:
        session.run("MATCH (p:Person {id: $id}) DETACH DELETE p", id=_PERSON_ID_2)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAddMemoryRequestValidator:
    """Unit tests — no live stack required."""

    def _base(self, **kwargs):
        defaults = {"type": "fact", "agent_id": "agent-1"}
        return {**defaults, **kwargs}

    def test_fact_only_accepted(self):
        req = AddMemoryRequest(**self._base(fact="Oliver has ADHD."))
        assert req.fact == "Oliver has ADHD."
        assert req.so_what is None

    def test_text_alias_sets_fact(self):
        req = AddMemoryRequest(**self._base(text="legacy text"))
        assert req.fact == "legacy text"
        assert req.so_what is None
        assert req.text == "legacy text"

    def test_fact_wins_when_both_provided(self):
        req = AddMemoryRequest(**self._base(fact="new fact", text="old text"))
        assert req.fact == "new fact"
        assert req.text == "new fact"

    def test_neither_fact_nor_text_raises(self):
        with pytest.raises(ValidationError):
            AddMemoryRequest(**self._base())

    def test_text_derived_from_fact_and_so_what(self):
        req = AddMemoryRequest(**self._base(
            fact="Oliver has ADHD.",
            so_what="Structure and short feedback loops matter more than motivation.",
        ))
        assert req.text == "Oliver has ADHD. Structure and short feedback loops matter more than motivation."

    def test_text_derived_from_fact_alone_when_no_so_what(self):
        req = AddMemoryRequest(**self._base(fact="Oliver has ADHD."))
        assert req.text == "Oliver has ADHD."


@pytest.mark.integration
class TestPostMemoryFactSoWhat:
    """Integration: fact/so_what storage on Memory node."""

    def test_fact_and_so_what_stored_on_node(self, client, test_driver):
        # Use a UUID suffix to avoid dedup collisions with real memory data.
        suffix = uuid.uuid4()
        fact = f"Oliver has ADHD {suffix}."
        so_what = f"Structure and short feedback loops matter more than motivation {suffix}."
        response = client.post("/memory", json={
            "fact": fact,
            "so_what": so_what,
            "type": "fact",
            "agent_id": _AGENT_ID,
        })
        assert response.status_code == 200
        memory_id = response.json()["memory_id"]
        assert response.json()["deduplicated"] is False
        node = get_memory_node(test_driver, memory_id)
        assert node["fact"] == fact
        assert node["so_what"] == so_what
        assert node["text"] == f"{fact} {so_what}"
        assert isinstance(node["embedding"], list)
        _cleanup(test_driver, memory_id)

    def test_fact_only_stores_correctly(self, client, test_driver):
        # Use a UUID suffix to avoid dedup collisions with real memory data.
        suffix = uuid.uuid4()
        fact = f"Oliver prefers async communication {suffix}."
        response = client.post("/memory", json={
            "fact": fact,
            "type": "observation",
            "agent_id": _AGENT_ID,
        })
        assert response.status_code == 200
        memory_id = response.json()["memory_id"]
        assert response.json()["deduplicated"] is False
        node = get_memory_node(test_driver, memory_id)
        assert node["fact"] == fact
        assert node.get("so_what") is None
        assert node["text"] == fact
        _cleanup(test_driver, memory_id)

    def test_deprecated_text_alias_stores_fact(self, client, test_driver):
        # Use a UUID suffix to avoid dedup collisions with real memory data.
        suffix = uuid.uuid4()
        fact = f"legacy text field {suffix}"
        response = client.post("/memory", json={
            "text": fact,
            "type": "fact",
            "agent_id": _AGENT_ID,
        })
        assert response.status_code == 200
        memory_id = response.json()["memory_id"]
        node = get_memory_node(test_driver, memory_id)
        assert node["fact"] == fact
        assert node.get("so_what") is None
        assert node["text"] == fact
        _cleanup(test_driver, memory_id)

    def test_neither_fact_nor_text_returns_422(self, client, test_driver):
        response = client.post("/memory", json={
            "type": "fact",
            "agent_id": _AGENT_ID,
        })
        assert response.status_code == 422


class TestPostMemoryMinimal:
    def test_returns_200_with_memory_id(self, client, test_driver):
        response = client.post("/memory", json={
            "text": "test minimal memory",
            "type": "fact",
            "agent_id": _AGENT_ID,
        })
        assert response.status_code == 200
        data = response.json()
        assert "memory_id" in data
        uuid.UUID(data["memory_id"])  # raises ValueError if not valid UUID
        _cleanup(test_driver, data["memory_id"])

    def test_memory_node_properties(self, client, test_driver):
        response = client.post("/memory", json={
            "text": "test properties memory",
            "type": "insight",
            "agent_id": _AGENT_ID,
        })
        memory_id = response.json()["memory_id"]
        node = get_memory_node(test_driver, memory_id)
        assert node is not None
        assert node["text"] == "test properties memory"
        assert node["type"] == "insight"
        assert isinstance(node["embedding"], list)
        assert len(node["embedding"]) > 0
        assert node["importance"] == 3  # model default
        assert "created_at" in node
        assert "last_used_at" in node
        _cleanup(test_driver, memory_id)


class TestPostMemoryAgentUpsert:
    def test_agent_node_created(self, client, test_driver):
        response = client.post("/memory", json={
            "text": "agent upsert test",
            "type": "fact",
            "agent_id": _AGENT_ID,
        })
        memory_id = response.json()["memory_id"]
        assert node_exists(test_driver, "Agent", _AGENT_ID)
        _cleanup(test_driver, memory_id)

    def test_agent_not_duplicated(self, client, test_driver):
        r1 = client.post("/memory", json={
            "text": "first memory for agent",
            "type": "fact",
            "agent_id": _AGENT_ID,
        })
        r2 = client.post("/memory", json={
            "text": "second memory for agent",
            "type": "fact",
            "agent_id": _AGENT_ID,
        })
        m1 = r1.json()["memory_id"]
        m2 = r2.json()["memory_id"]
        with test_driver.session() as session:
            result = session.run(
                "MATCH (a:Agent {id: $id}) RETURN count(a) AS cnt",
                id=_AGENT_ID,
            )
            count = result.single()["cnt"]
        assert count == 1
        _cleanup(test_driver, m1, m2)


class TestPostMemoryWithProject:
    def test_project_node_and_about_edge(self, client, test_driver):
        response = client.post("/memory", json={
            "text": "memory about a project",
            "type": "decision",
            "agent_id": _AGENT_ID,
            "project_id": _PROJECT_ID,
        })
        memory_id = response.json()["memory_id"]
        assert node_exists(test_driver, "Project", _PROJECT_ID)
        assert edge_exists(test_driver, memory_id, "ABOUT", _PROJECT_ID)
        _cleanup(test_driver, memory_id)


class TestPostMemoryWithPersons:
    def test_person_nodes_and_about_edges(self, client, test_driver):
        response = client.post("/memory", json={
            "text": "memory about people",
            "type": "observation",
            "agent_id": _AGENT_ID,
            "person_ids": [_PERSON_ID_1, _PERSON_ID_2],
        })
        memory_id = response.json()["memory_id"]
        assert node_exists(test_driver, "Person", _PERSON_ID_1)
        assert node_exists(test_driver, "Person", _PERSON_ID_2)
        assert edge_exists(test_driver, memory_id, "ABOUT", _PERSON_ID_1)
        assert edge_exists(test_driver, memory_id, "ABOUT", _PERSON_ID_2)
        _cleanup(test_driver, memory_id)


class TestPostMemoryWithStrands:
    def test_strand_node_and_in_strand_edge(self, client, test_driver):
        # Use a seeded strand — MATCH (not MERGE) requires the node to pre-exist
        seeded_strand_id = "strand-core-health"
        response = client.post("/memory", json={
            "text": "memory in a strand",
            "type": "fact",
            "agent_id": _AGENT_ID,
            "strand_ids": [seeded_strand_id],
        })
        memory_id = response.json()["memory_id"]
        assert node_exists(test_driver, "Strand", seeded_strand_id)
        assert edge_exists(test_driver, memory_id, "IN_STRAND", seeded_strand_id)
        with test_driver.session() as session:
            result = session.run(
                "MATCH (m:Memory {id: $mid})-[r:IN_STRAND]->(s:Strand {id: $sid}) RETURN r.weight AS w",
                mid=memory_id,
                sid=seeded_strand_id,
            )
            weight = result.single()["w"]
        assert weight == 1.0
        cleanup_nodes(test_driver, memory_id)


@pytest.mark.integration
class TestPostMemoryStrandIdsInResponse:
    """Integration: strand_ids returned in POST /memory response."""

    def test_strand_ids_in_response_when_linked(self, client, test_driver):
        suffix = uuid.uuid4()
        seeded_strand_id = "strand-core-health"
        resp = client.post("/memory", json={
            "fact": f"memory for strand_ids response test {suffix}",
            "type": "fact",
            "agent_id": _AGENT_ID,
            "strand_ids": [seeded_strand_id],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "strand_ids" in data
        assert seeded_strand_id in data["strand_ids"]
        cleanup_nodes(test_driver, data["memory_id"])

    def test_strand_ids_empty_when_none_requested(self, client, test_driver):
        suffix = uuid.uuid4()
        resp = client.post("/memory", json={
            "fact": f"memory with no strands {suffix}",
            "type": "fact",
            "agent_id": _AGENT_ID,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["strand_ids"] == []
        cleanup_nodes(test_driver, data["memory_id"])


class TestPostMemoryExplicitRelatedIds:
    def test_related_to_edge_created(self, client, test_driver):
        r1 = client.post("/memory", json={
            "text": "seed memory for relation",
            "type": "fact",
            "agent_id": _AGENT_ID,
        })
        seed_id = r1.json()["memory_id"]

        r2 = client.post("/memory", json={
            "text": "related memory",
            "type": "fact",
            "agent_id": _AGENT_ID,
            "related_ids": [seed_id],
        })
        new_id = r2.json()["memory_id"]

        assert edge_exists(test_driver, new_id, "RELATED_TO", seed_id)
        with test_driver.session() as session:
            result = session.run(
                "MATCH (m:Memory {id: $mid})-[r:RELATED_TO]->(s:Memory {id: $sid}) RETURN r.weight AS w",
                mid=new_id,
                sid=seed_id,
            )
            weight = result.single()["w"]
        assert weight == 1.0
        _cleanup(test_driver, seed_id, new_id)


class TestPostMemoryAutoRelatedTo:
    def test_auto_related_to_no_self_loop(self, client, test_driver):
        """After inserting, the memory should not have a RELATED_TO edge to itself."""
        response = client.post("/memory", json={
            "text": "auto related test — unique phrase xyzzy42",
            "type": "fact",
            "agent_id": _AGENT_ID,
        })
        memory_id = response.json()["memory_id"]
        assert not edge_exists(test_driver, memory_id, "RELATED_TO", memory_id)
        _cleanup(test_driver, memory_id)

    def test_auto_related_weights_in_range(self, client, test_driver):
        """Auto RELATED_TO weights should be in (0.0, 1.0] when edges exist."""
        r1 = client.post("/memory", json={
            "text": "the quick brown fox jumps over the lazy dog",
            "type": "fact",
            "agent_id": _AGENT_ID,
        })
        seed_id = r1.json()["memory_id"]

        r2 = client.post("/memory", json={
            "text": "a fast brown fox leaps over a sleepy dog",
            "type": "fact",
            "agent_id": _AGENT_ID,
        })
        new_id = r2.json()["memory_id"]

        with test_driver.session() as session:
            result = session.run(
                "MATCH (m:Memory {id: $mid})-[r:RELATED_TO]->(n) RETURN r.weight AS w",
                mid=new_id,
            )
            weights = [record["w"] for record in result]

        for w in weights:
            assert 0.0 < w <= 1.0, f"weight {w} out of range"

        _cleanup(test_driver, seed_id, new_id)


class TestPostMemoryValidation:
    def test_importance_out_of_range_returns_422(self, client, test_driver):
        response = client.post("/memory", json={
            "text": "validation test",
            "type": "fact",
            "agent_id": _AGENT_ID,
            "importance": 6,
        })
        assert response.status_code == 422

    def test_missing_required_fields_returns_422(self, client, test_driver):
        response = client.post("/memory", json={"text": "no type or agent"})
        assert response.status_code == 422


@pytest.mark.integration
class TestPostMemoryLeadsTo:
    """Integration: LEADS_TO edge creation via cause_ids and effect_ids."""

    def test_cause_ids_creates_leads_to_edge(self, client, test_driver):
        # Create cause memory first
        r1 = client.post("/memory", json={"fact": "Cause memory", "type": "fact", "agent_id": _AGENT_ID})
        cause_id = r1.json()["memory_id"]

        # Create effect memory referencing cause
        r2 = client.post("/memory", json={
            "fact": "Effect memory",
            "type": "fact",
            "agent_id": _AGENT_ID,
            "cause_ids": [cause_id],
        })
        effect_id = r2.json()["memory_id"]

        # LEADS_TO should go cause → effect
        assert edge_exists(test_driver, cause_id, "LEADS_TO", effect_id)
        _cleanup(test_driver, cause_id, effect_id)

    def test_effect_ids_creates_leads_to_edge(self, client, test_driver):
        # Create effect memory first
        r1 = client.post("/memory", json={"fact": "Effect memory", "type": "fact", "agent_id": _AGENT_ID})
        effect_id = r1.json()["memory_id"]

        # Create cause memory referencing effect
        r2 = client.post("/memory", json={
            "fact": "Cause memory",
            "type": "fact",
            "agent_id": _AGENT_ID,
            "effect_ids": [effect_id],
        })
        cause_id = r2.json()["memory_id"]

        # LEADS_TO should go cause → effect
        assert edge_exists(test_driver, cause_id, "LEADS_TO", effect_id)
        _cleanup(test_driver, cause_id, effect_id)

    def test_missing_uuid_in_cause_ids_skipped_silently(self, client, test_driver):
        r = client.post("/memory", json={
            "fact": "New memory with missing cause",
            "type": "fact",
            "agent_id": _AGENT_ID,
            "cause_ids": ["00000000-0000-0000-0000-000000000000"],
        })
        assert r.status_code == 200
        memory_id = r.json()["memory_id"]
        # No LEADS_TO edge created, but write succeeded
        node = get_memory_node(test_driver, memory_id)
        assert node is not None
        _cleanup(test_driver, memory_id)

    def test_missing_uuid_in_effect_ids_skipped_silently(self, client, test_driver):
        r = client.post("/memory", json={
            "fact": "New memory with missing effect",
            "type": "fact",
            "agent_id": _AGENT_ID,
            "effect_ids": ["00000000-0000-0000-0000-000000000000"],
        })
        assert r.status_code == 200
        memory_id = r.json()["memory_id"]
        node = get_memory_node(test_driver, memory_id)
        assert node is not None
        _cleanup(test_driver, memory_id)

    def test_leads_to_edge_is_idempotent(self, client, test_driver):
        """MERGE ensures the same directed edge is not duplicated."""
        r1 = client.post("/memory", json={"fact": "Cause", "type": "fact", "agent_id": _AGENT_ID})
        cause_id = r1.json()["memory_id"]
        r2 = client.post("/memory", json={
            "fact": "Effect",
            "type": "fact",
            "agent_id": _AGENT_ID,
            "cause_ids": [cause_id],
        })
        effect_id = r2.json()["memory_id"]

        # Manually create the same LEADS_TO edge a second time (simulating a re-run)
        with test_driver.session() as s:
            s.run(
                "MATCH (c:Memory {id: $c}), (e:Memory {id: $e}) MERGE (c)-[:LEADS_TO]->(e)",
                c=cause_id, e=effect_id,
            )

        # Verify exactly one LEADS_TO edge exists between the pair
        with test_driver.session() as s:
            result = s.run(
                "MATCH (c:Memory {id: $c})-[r:LEADS_TO]->(e:Memory {id: $e}) RETURN count(r) AS cnt",
                c=cause_id, e=effect_id,
            )
            count = result.single()["cnt"]
        assert count == 1, f"Expected exactly 1 LEADS_TO edge, got {count}"
        _cleanup(test_driver, cause_id, effect_id)


class TestPostMemoryDbUnavailable:
    def test_returns_503_when_db_down(self):
        """Inject a driver that raises ServiceUnavailable; expect 503."""
        from memory_service.main import app

        mock_driver = MagicMock()
        mock_driver.session.side_effect = ServiceUnavailable("connection refused")

        with TestClient(app) as c:
            original_driver = app.state.driver
            app.state.driver = mock_driver
            try:
                response = c.post("/memory", json={
                    "text": "db down test",
                    "type": "fact",
                    "agent_id": _AGENT_ID,
                })
            finally:
                app.state.driver = original_driver
        assert response.status_code == 503
