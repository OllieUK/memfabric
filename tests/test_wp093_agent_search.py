# tests/test_wp093_agent_search.py
"""Tests for WP-093: agent-optimised search."""
import json

import httpx
import pytest
import respx

from memory_client.client import MemoryClient
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
        "tags": ["test"],
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
    def test_person_anchored_returns_float_score(self, client, test_driver):
        """Person-anchored search hits carry a numeric score (WP-149: vector path for all searches)."""
        mid = None
        person_id = "person-wp093-score"
        try:
            r = client.post("/memory", json=_add_body(
                "WP093 person score test unique fact", person_ids=[person_id],
            ))
            mid = r.json()["memory_id"]

            r2 = client.post("/memory/search", json={
                "query": "WP093 person score test unique fact",
                "person_ids": [person_id],
                "limit": 5,
            })
            assert r2.status_code == 200
            hits = r2.json()["memories"]
            assert len(hits) >= 1
            hit = next(h for h in hits if h["id"] == mid)
            assert isinstance(hit["score"], float), f"expected float score, got {hit['score']!r}"
            assert 0.0 <= hit["score"] <= 1.0
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
    def test_min_score_applied_with_person_ids(self, client, test_driver):
        """min_score is now applied even when person_ids is set (WP-149)."""
        mid = None
        person_id = "person-wp093-minscore"
        try:
            r = client.post("/memory", json=_add_body(
                "WP093 person min_score applied unique", person_ids=[person_id],
            ))
            mid = r.json()["memory_id"]

            # Impossibly high min_score — the low-relevance hit above should be excluded.
            r2 = client.post("/memory/search", json={
                "query": "completely unrelated marine biology topic",
                "person_ids": [person_id],
                "min_score": 0.99,
                "limit": 10,
            })
            assert r2.status_code == 200
            hits = r2.json()["memories"]
            hit_ids = [h["id"] for h in hits]
            # The memory is linked to this person but semantically unrelated to the query;
            # with min_score=0.99 it should not appear.
            assert mid not in hit_ids, (
                "expected low-relevance person-linked memory to be filtered by min_score=0.99"
            )
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
# Task 2b — Integration: person_ids vector semantics (WP-149)
# ---------------------------------------------------------------------------
class TestPersonIdsVectorSemantics:
    @pytest.mark.integration
    def test_person_filter_ranks_by_topic_relevance(self, client, test_driver):
        """Person-filtered results are ranked by semantic relevance, not importance."""
        mid_relevant = mid_noise = None
        person_id = "person-wp093-relevance"
        try:
            # A highly-relevant memory linked to the person
            r1 = client.post("/memory", json=_add_body(
                "kubernetes deployment yaml pods replica scaling",
                person_ids=[person_id], importance=3,
            ))
            mid_relevant = r1.json()["memory_id"]

            # A low-relevance memory linked to the same person with higher importance
            r2 = client.post("/memory", json=_add_body(
                "favourite coffee shop afternoon espresso",
                person_ids=[person_id], importance=4,
            ))
            mid_noise = r2.json()["memory_id"]

            r3 = client.post("/memory/search", json={
                "query": "kubernetes pods deployment",
                "person_ids": [person_id],
                "limit": 5,
            })
            assert r3.status_code == 200
            hits = r3.json()["memories"]
            ids = [h["id"] for h in hits]
            assert mid_relevant in ids, "relevant memory should appear in results"

            if mid_noise in ids:
                idx_relevant = ids.index(mid_relevant)
                idx_noise = ids.index(mid_noise)
                assert idx_relevant < idx_noise, (
                    "semantically relevant memory should rank above the noise memory "
                    f"(relevant at {idx_relevant}, noise at {idx_noise})"
                )
        finally:
            if mid_relevant:
                _cleanup(test_driver, mid_relevant)
            if mid_noise:
                _cleanup(test_driver, mid_noise)
            with test_driver.session() as session:
                session.run("MATCH (p:Person {id: $id}) DETACH DELETE p", id=person_id)

    @pytest.mark.integration
    def test_person_filter_overfetch_recovers_lower_ranked_match(self, client, test_driver):
        """Over-fetch recovers a person-linked memory that would otherwise fall outside top-K."""
        person_id = "person-wp093-overfetch"
        noise_ids = []
        target_id = None
        try:
            # Create 4 generic memories without person association — these will rank
            # above the person-linked memory in raw vector distance for our query.
            for i in range(4):
                r = client.post("/memory", json=_add_body(
                    f"WP093 overfetch noise memory index {i} unique abc xyz",
                ))
                noise_ids.append(r.json()["memory_id"])

            # Create the person-linked memory with the target text
            r = client.post("/memory", json=_add_body(
                "WP093 overfetch target person linked fact unique abc xyz",
                person_ids=[person_id],
            ))
            target_id = r.json()["memory_id"]

            # Fetch with limit=3; without over-fetch the target could be buried past top-3.
            # With _PERSON_OVERFETCH_MULTIPLIER=5, effective fetch is 15, which surfaces
            # the person-linked memory before the ABOUT-edge filter truncates.
            r2 = client.post("/memory/search", json={
                "query": "WP093 overfetch target person linked fact unique abc xyz",
                "person_ids": [person_id],
                "limit": 3,
            })
            assert r2.status_code == 200
            hits = r2.json()["memories"]
            hit_ids = [h["id"] for h in hits]
            assert target_id in hit_ids, (
                "person-linked memory should be recovered via over-fetch even if outside natural top-K"
            )
        finally:
            cleanup_nodes(test_driver, *noise_ids)
            if target_id:
                cleanup_nodes(test_driver, target_id)
            with test_driver.session() as session:
                session.run("MATCH (p:Person {id: $id}) DETACH DELETE p", id=person_id)


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
            assert hit_b is not None, f"mid_b {mid_b} not in primary hits {[h['id'] for h in hits]}"
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

            # Use min_score=0.95 so only mid_b (exact match) hits as primary;
            # mid_a stays out of primary hits and can appear in associated.
            r3 = client.post("/memory/search", json={
                "query": "WP093 weight test related",
                "limit": 5,
                "neighbour_cap": 3,
                "min_score": 0.95,
            })
            hits = r3.json()["memories"]
            hit_b = next((h for h in hits if h["id"] == mid_b), None)
            assert hit_b is not None, f"mid_b {mid_b} not in primary hits"
            assert len(hit_b.get("associated", [])) >= 1, "expected at least one associated entry"
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


# ---------------------------------------------------------------------------
# Task 4 — Unit: MemoryClient passes new params
# ---------------------------------------------------------------------------
_BASE_URL = "http://localhost:8000"


class TestClientSearchParams:
    @respx.mock
    def test_passes_min_score(self):
        respx.post(f"{_BASE_URL}/memory/search").mock(
            return_value=httpx.Response(200, json={"memories": []})
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            client.search_memory("test", min_score=0.8)
        body = json.loads(respx.calls.last.request.content)
        assert body["min_score"] == 0.8

    @respx.mock
    def test_passes_neighbour_cap(self):
        respx.post(f"{_BASE_URL}/memory/search").mock(
            return_value=httpx.Response(200, json={"memories": []})
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            client.search_memory("test", neighbour_cap=5)
        body = json.loads(respx.calls.last.request.content)
        assert body["neighbour_cap"] == 5

    @respx.mock
    def test_omitting_new_params_backward_compatible(self):
        respx.post(f"{_BASE_URL}/memory/search").mock(
            return_value=httpx.Response(200, json={"memories": []})
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            client.search_memory("test")
        body = json.loads(respx.calls.last.request.content)
        assert "min_score" not in body
        assert "neighbour_cap" not in body
