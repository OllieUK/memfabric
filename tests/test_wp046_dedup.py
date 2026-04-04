# tests/test_wp046_dedup.py
"""
WP-046: Regression tests for duplicate Memory nodes in search and wake-up results.

Integration tests (live Memgraph + running FastAPI required).

Test topology used: diamond
    A (root) -RELATED_TO-> B
    A (root) -RELATED_TO-> C
    B        -RELATED_TO-> D
    C        -RELATED_TO-> D

When searching for A with max_hops=2, D is reachable via A->B->D and A->C->D.
Before the fix, D appears twice in neighbour lists (or as a duplicate primary hit).
After the fix, D appears exactly once.
"""
import uuid
import pytest

_AGENT_ID = "test-wp046-agent"


def _add(client, text, *, related_ids=None):
    body = {"fact": text, "type": "fact", "agent_id": _AGENT_ID, "tags": ["test"]}
    if related_ids:
        body["related_ids"] = related_ids
    r = client.post("/memory", json=body)
    assert r.status_code == 200, r.text
    return r.json()["memory_id"]


def _cleanup(test_driver, *ids):
    with test_driver.session() as s:
        for mid in ids:
            s.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mid)
        s.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)


@pytest.mark.integration
class TestSearchDedup:
    def test_primary_results_have_no_duplicate_ids(self, client, test_driver):
        """Each memory id appears at most once in the search results list."""
        tag = f"wp046-{uuid.uuid4().hex[:8]}"
        ids = [_add(client, f"dedup primary test memory {i} {tag}") for i in range(4)]
        try:
            r = client.post("/memory/search", json={
                "query": f"dedup primary test memory {tag}",
                "limit": 20,
                "max_hops": 0,
            })
            assert r.status_code == 200
            result_ids = [m["id"] for m in r.json()["memories"]]
            assert len(result_ids) == len(set(result_ids)), (
                f"Duplicate ids in search results: {result_ids}"
            )
        finally:
            _cleanup(test_driver, *ids)

    def test_diamond_topology_no_duplicate_neighbours(self, client, test_driver):
        """With diamond A->B->D and A->C->D, D must appear at most once in A's neighbours."""
        suffix = uuid.uuid4().hex[:8]
        a_id = _add(client, f"diamond root {suffix}")
        b_id = _add(client, f"diamond left {suffix}", related_ids=[a_id])
        c_id = _add(client, f"diamond right {suffix}", related_ids=[a_id])
        d_id = _add(client, f"diamond bottom {suffix}", related_ids=[b_id, c_id])
        try:
            r = client.post("/memory/search", json={
                "query": f"diamond root {suffix}",
                "agent_ids": [_AGENT_ID],
                "max_hops": 2,
                "limit": 10,
            })
            assert r.status_code == 200
            hits = r.json()["memories"]
            a_hit = next((h for h in hits if h["id"] == a_id), None)
            assert a_hit is not None, "Root memory A must be in results"
            neighbours = a_hit["neighbours"]
            assert neighbours.count(d_id) <= 1, (
                f"D appears {neighbours.count(d_id)} times in neighbours — expected ≤1"
            )
        finally:
            _cleanup(test_driver, a_id, b_id, c_id, d_id)

    def test_wake_up_topic_has_no_duplicate_ids(self, client, test_driver):
        """Wake-up topic list must not contain duplicate memory ids."""
        tag = f"wp046-wakeup-{uuid.uuid4().hex[:8]}"
        ids = [_add(client, f"wake up dedup test {i} {tag}") for i in range(3)]
        try:
            r = client.get("/memory/wake-up", params={"topic": f"wake up dedup test {tag}", "limit": 20})
            assert r.status_code == 200
            data = r.json()
            topic_ids = [m["id"] for m in data.get("topic_memories", [])]
            assert len(topic_ids) == len(set(topic_ids)), (
                f"Duplicate ids in wake-up topic: {topic_ids}"
            )
        finally:
            _cleanup(test_driver, *ids)
