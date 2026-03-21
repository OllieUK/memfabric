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
        response = client.post("/memory", json={
            "text": "memory in a strand",
            "type": "fact",
            "agent_id": _AGENT_ID,
            "strand_ids": [_STRAND_ID],
        })
        memory_id = response.json()["memory_id"]
        assert node_exists(test_driver, "Strand", _STRAND_ID)
        assert edge_exists(test_driver, memory_id, "IN_STRAND", _STRAND_ID)
        with test_driver.session() as session:
            result = session.run(
                "MATCH (m:Memory {id: $mid})-[r:IN_STRAND]->(s:Strand {id: $sid}) RETURN r.weight AS w",
                mid=memory_id,
                sid=_STRAND_ID,
            )
            weight = result.single()["w"]
        assert weight == 1.0
        _cleanup(test_driver, memory_id)


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


class TestPostMemoryDbUnavailable:
    def test_returns_503_when_db_down(self, test_driver):
        """Inject a driver that raises ServiceUnavailable; expect 503."""
        from memory_service.main import app

        mock_driver = MagicMock()
        mock_driver.session.side_effect = ServiceUnavailable("connection refused")

        original_driver = getattr(app.state, "driver", None)
        app.state.driver = mock_driver
        try:
            with TestClient(app) as c:
                response = c.post("/memory", json={
                    "text": "db down test",
                    "type": "fact",
                    "agent_id": _AGENT_ID,
                })
            assert response.status_code == 503
        finally:
            app.state.driver = original_driver
