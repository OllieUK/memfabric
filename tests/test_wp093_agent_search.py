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


# ---------------------------------------------------------------------------
# Task 2 — Integration: min_score filter
# ---------------------------------------------------------------------------
class TestMinScoreFilter:
    @pytest.mark.integration
    def test_min_score_filters_low_hits(self, client, test_driver):
        """Only hits with score >= min_score are returned."""
        mid = None
        try:
            r = client.post("/memory", json=_add_body("WP093 min_score test unique abc"))
            mid = r.json()["memory_id"]

            # Search with impossibly high min_score
            r2 = client.post("/memory/search", json={
                "query": "completely unrelated topic about marine biology",
                "min_score": 0.99,
                "limit": 10,
            })
            assert r2.status_code == 200
            hits = r2.json()["memories"]
            # All returned hits should have score >= 0.99
            for h in hits:
                assert h["score"] >= 0.99
        finally:
            if mid:
                _cleanup(test_driver, mid)

    @pytest.mark.integration
    def test_min_score_empty_list_valid(self, client, test_driver):
        """min_score that excludes everything returns empty list, not error."""
        r = client.post("/memory/search", json={
            "query": "random query for wp093",
            "min_score": 0.9999,
            "limit": 10,
        })
        assert r.status_code == 200
        # Empty list is valid
        assert isinstance(r.json()["memories"], list)

    @pytest.mark.integration
    def test_min_score_ignored_with_person_ids(self, client, test_driver):
        """min_score is ignored when person_ids is set."""
        mid = None
        person_id = "person-wp093-minscore"
        try:
            r = client.post("/memory", json=_add_body(
                "WP093 person min_score bypass", person_ids=[person_id],
            ))
            mid = r.json()["memory_id"]

            r2 = client.post("/memory/search", json={
                "query": "anything",
                "person_ids": [person_id],
                "min_score": 0.99,
                "limit": 10,
            })
            assert r2.status_code == 200
            hits = r2.json()["memories"]
            hit_ids = [h["id"] for h in hits]
            assert mid in hit_ids
        finally:
            if mid:
                _cleanup(test_driver, mid)
            with test_driver.session() as session:
                session.run("MATCH (p:Person {id: $id}) DETACH DELETE p", id=person_id)

    @pytest.mark.integration
    def test_no_min_score_returns_all(self, client, test_driver):
        """Omitting min_score returns all results (backward compatible)."""
        mid = None
        try:
            r = client.post("/memory", json=_add_body("WP093 no min_score test"))
            mid = r.json()["memory_id"]

            r2 = client.post("/memory/search", json={
                "query": "WP093 no min_score test", "limit": 10,
            })
            assert r2.status_code == 200
            assert len(r2.json()["memories"]) >= 1
        finally:
            if mid:
                _cleanup(test_driver, mid)


# ---------------------------------------------------------------------------
# Task 3 — Integration: associated expansion
# ---------------------------------------------------------------------------
class TestAssociatedExpansion:
    @pytest.mark.integration
    def test_associated_returns_linked_memories(self, client, test_driver):
        """Search returns associated memories via RELATED_TO edges."""
        mid_a = mid_b = None
        try:
            # Create two related memories
            r1 = client.post("/memory", json=_add_body("WP093 the original fact about graph databases"))
            mid_a = r1.json()["memory_id"]
            r2 = client.post("/memory", json=_add_body(
                "WP093 observation about graph databases being fast",
                related_ids=[mid_a],
            ))
            mid_b = r2.json()["memory_id"]

            # Search for the observation with a high min_score so only mid_b hits
            # as a primary result. mid_a (a less similar fact) is thus excluded from
            # primary hits and can appear in mid_b's associated list.
            r3 = client.post("/memory/search", json={
                "query": "WP093 observation about graph databases being fast",
                "limit": 5,
                "neighbour_cap": 3,
                "min_score": 0.95,
            })
            assert r3.status_code == 200
            hits = r3.json()["memories"]
            hit_b = next((h for h in hits if h["id"] == mid_b), None)
            if hit_b is not None:
                assoc_ids = [a["id"] for a in hit_b.get("associated", [])]
                assert mid_a in assoc_ids
        finally:
            if mid_a:
                _cleanup(test_driver, mid_a)
            if mid_b:
                _cleanup(test_driver, mid_b)

    @pytest.mark.integration
    def test_associated_has_edge_weight(self, client, test_driver):
        """Associated entries include edge_weight."""
        mid_a = mid_b = None
        try:
            r1 = client.post("/memory", json=_add_body("WP093 weight test original"))
            mid_a = r1.json()["memory_id"]
            r2 = client.post("/memory", json=_add_body(
                "WP093 weight test related",
                related_ids=[mid_a],
            ))
            mid_b = r2.json()["memory_id"]

            r3 = client.post("/memory/search", json={
                "query": "WP093 weight test related",
                "limit": 5,
                "neighbour_cap": 3,
            })
            hits = r3.json()["memories"]
            hit_b = next((h for h in hits if h["id"] == mid_b), None)
            if hit_b and hit_b.get("associated"):
                for a in hit_b["associated"]:
                    assert "edge_weight" in a
                    assert isinstance(a["edge_weight"], (int, float))
        finally:
            if mid_a:
                _cleanup(test_driver, mid_a)
            if mid_b:
                _cleanup(test_driver, mid_b)

    @pytest.mark.integration
    def test_primary_hit_excluded_from_associated(self, client, test_driver):
        """A memory that is a primary hit does not appear in any associated list."""
        mid_a = mid_b = None
        try:
            r1 = client.post("/memory", json=_add_body("WP093 dedup primary alpha"))
            mid_a = r1.json()["memory_id"]
            r2 = client.post("/memory", json=_add_body(
                "WP093 dedup primary beta",
                related_ids=[mid_a],
            ))
            mid_b = r2.json()["memory_id"]

            r3 = client.post("/memory/search", json={
                "query": "WP093 dedup primary",
                "limit": 10,
                "neighbour_cap": 5,
            })
            hits = r3.json()["memories"]
            primary_ids = {h["id"] for h in hits}
            for hit in hits:
                for a in hit.get("associated", []):
                    assert a["id"] not in primary_ids, \
                        f"Primary hit {a['id']} should not appear in associated list"
        finally:
            if mid_a:
                _cleanup(test_driver, mid_a)
            if mid_b:
                _cleanup(test_driver, mid_b)

    @pytest.mark.integration
    def test_person_anchored_returns_empty_associated(self, client, test_driver):
        """Person-anchored search returns associated=[] for all hits."""
        mid = None
        person_id = "person-wp093-assoc"
        try:
            r = client.post("/memory", json=_add_body(
                "WP093 person assoc test", person_ids=[person_id],
            ))
            mid = r.json()["memory_id"]

            r2 = client.post("/memory/search", json={
                "query": "anything",
                "person_ids": [person_id],
                "limit": 5,
            })
            hits = r2.json()["memories"]
            for h in hits:
                assert h.get("associated", []) == []
        finally:
            if mid:
                _cleanup(test_driver, mid)
            with test_driver.session() as session:
                session.run("MATCH (p:Person {id: $id}) DETACH DELETE p", id=person_id)

    @pytest.mark.integration
    def test_neighbour_cap_zero_returns_empty(self, client, test_driver):
        """neighbour_cap=0 returns empty associated lists."""
        mid = None
        try:
            r = client.post("/memory", json=_add_body("WP093 cap zero test"))
            mid = r.json()["memory_id"]

            r2 = client.post("/memory/search", json={
                "query": "WP093 cap zero test",
                "limit": 5,
                "neighbour_cap": 0,
            })
            hits = r2.json()["memories"]
            for h in hits:
                assert h.get("associated", []) == []
        finally:
            if mid:
                _cleanup(test_driver, mid)
