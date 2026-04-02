# tests/test_wp093_agent_search.py
"""Tests for WP-093: agent-optimised search."""
import pytest

from tests.conftest import cleanup_nodes

_AGENT_ID = "test-agent-wp093"


def _cleanup(driver, *memory_ids):
    cleanup_nodes(driver, *memory_ids)
    with driver.session() as session:
        session.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)


def _add_body(fact: str, **kwargs) -> dict:
    body = {
        "fact": fact,
        "type": "fact",
        "agent_id": _AGENT_ID,
        "importance": 3,
    }
    body.update(kwargs)
    return body


# ---------------------------------------------------------------------------
# Task 1 — Integration: score field on MemoryHit
# ---------------------------------------------------------------------------
class TestScoreExposure:
    @pytest.mark.integration
    def test_vector_search_returns_score(self, client, test_driver):
        """Vector search hits include a numeric score field."""
        mid = None
        try:
            r = client.post("/memory", json=_add_body("WP093 score exposure test unique xyz"))
            mid = r.json()["memory_id"]

            r2 = client.post("/memory/search", json={
                "query": "WP093 score exposure test unique xyz", "limit": 5,
            })
            assert r2.status_code == 200
            hits = r2.json()["memories"]
            assert len(hits) >= 1
            hit = next(h for h in hits if h["id"] == mid)
            assert "score" in hit
            assert isinstance(hit["score"], float)
            assert 0.0 <= hit["score"] <= 1.0
        finally:
            if mid:
                _cleanup(test_driver, mid)

    @pytest.mark.integration
    def test_person_anchored_returns_null_score(self, client, test_driver):
        """Person-anchored search hits have score=null."""
        mid = None
        person_id = "person-wp093-score"
        try:
            r = client.post("/memory", json=_add_body(
                "WP093 person score test", person_ids=[person_id],
            ))
            mid = r.json()["memory_id"]

            r2 = client.post("/memory/search", json={
                "query": "anything", "person_ids": [person_id], "limit": 5,
            })
            assert r2.status_code == 200
            hits = r2.json()["memories"]
            assert len(hits) >= 1
            hit = next(h for h in hits if h["id"] == mid)
            assert hit["score"] is None
        finally:
            if mid:
                _cleanup(test_driver, mid)
            with test_driver.session() as session:
                session.run("MATCH (p:Person {id: $id}) DETACH DELETE p", id=person_id)
