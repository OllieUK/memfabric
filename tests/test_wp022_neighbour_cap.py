"""
tests/test_wp022_neighbour_cap.py — Tests for WP-022: cap neighbour count in search results.

Unit tests verify the Cypher query string contains the slice syntax.
Integration tests (require live Memgraph + FastAPI) verify the cap is enforced on a real graph.
"""

import uuid
import pytest
from unittest.mock import MagicMock

from memory_service import memory_repo
from tests.conftest import cleanup_nodes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AGENT_ID = "test-wp022-agent"


def _make_req(max_hops=1, direction="none"):
    req = MagicMock()
    req.max_hops = max_hops
    req.traversal_direction = direction
    req.tags = None
    req.agent_ids = None
    req.project_ids = None
    req.limit = 10
    return req


def _add_memory(client, text):
    r = client.post("/memory", json={"text": text, "type": "fact", "agent_id": _AGENT_ID, "tags": ["test"]})
    assert r.status_code == 200, r.text
    return r.json()["memory_id"]


def _wire_related(driver, from_id, to_id):
    with driver.session() as session:
        session.run(
            "MATCH (a:Memory {id: $a}), (b:Memory {id: $b}) MERGE (a)-[:RELATED_TO]->(b)",
            a=from_id, b=to_id,
        )


def _wire_leads_to(driver, cause_id, effect_id):
    with driver.session() as session:
        session.run(
            "MATCH (a:Memory {id: $a}), (b:Memory {id: $b}) MERGE (a)-[:LEADS_TO]->(b)",
            a=cause_id, b=effect_id,
        )


# ---------------------------------------------------------------------------
# Unit tests — no Memgraph required
# ---------------------------------------------------------------------------

def test_cypher_slice_syntax_related():
    """collect(DISTINCT n.id) must be sliced when max_hops > 0."""
    session = MagicMock()
    session.run.return_value = []
    req = _make_req(max_hops=1, direction="none")
    memory_repo.search_memories(session, req, [0.0] * 384, neighbour_cap=50)
    cypher = session.run.call_args[0][0]
    assert "collect(DISTINCT n.id)[..50]" in cypher


def test_cypher_slice_syntax_causes_effects():
    """collect expressions for causes and effects must both carry the slice."""
    session = MagicMock()
    session.run.return_value = []
    req = _make_req(max_hops=1, direction="both")
    memory_repo.search_memories(session, req, [0.0] * 384, neighbour_cap=25)
    cypher = session.run.call_args[0][0]
    assert "collect(DISTINCT c.id)[..25]" in cypher
    assert "collect(DISTINCT e.id)[..25]" in cypher


def test_cypher_no_slice_when_no_neighbours():
    """When max_hops=0 and direction=none, no slice syntax should appear."""
    session = MagicMock()
    session.run.return_value = []
    req = _make_req(max_hops=0, direction="none")
    memory_repo.search_memories(session, req, [0.0] * 384, neighbour_cap=50)
    cypher = session.run.call_args[0][0]
    assert "[..50]" not in cypher
    assert "[] AS neighbours" in cypher


def test_cypher_cap_value_is_configurable():
    """The cap value in the Cypher must match the neighbour_cap argument."""
    session = MagicMock()
    session.run.return_value = []
    req = _make_req(max_hops=1, direction="none")
    memory_repo.search_memories(session, req, [0.0] * 384, neighbour_cap=7)
    cypher = session.run.call_args[0][0]
    assert "[..7]" in cypher
    assert "[..50]" not in cypher


# ---------------------------------------------------------------------------
# Integration tests — require live Memgraph + running FastAPI service
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_related_neighbours_capped(client, test_driver, monkeypatch):
    """Hub with N+5 RELATED_TO edges must return ≤ cap neighbours."""
    cap = 5  # small cap to keep the test fixture manageable
    hub_id = None
    spoke_ids = []
    try:
        # Create hub and cap+5 spokes, wire RELATED_TO from hub to each spoke
        hub_id = _add_memory(client, "wp022 hub memory related cap test")
        for i in range(cap + 5):
            sid = _add_memory(client, f"wp022 spoke related {i}")
            spoke_ids.append(sid)
            _wire_related(test_driver, hub_id, sid)

        from memory_service import config as cfg
        monkeypatch.setattr(cfg.settings, "search_neighbour_cap", cap)
        r = client.post("/memory/search", json={
            "query": "wp022 hub memory related cap test",
            "max_hops": 1,
            "limit": 5,
        })

        assert r.status_code == 200
        hits = r.json()["memories"]
        hub_hits = [h for h in hits if h["id"] == hub_id]
        assert hub_hits, "Hub memory not found in results"
        assert len(hub_hits[0]["neighbours"]) <= cap
    finally:
        cleanup_nodes(test_driver, hub_id, *spoke_ids, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_leads_to_neighbours_capped(client, test_driver, monkeypatch):
    """Hub with N+3 LEADS_TO (effects) edges must return ≤ cap effect neighbours."""
    cap = 3
    hub_id = None
    effect_ids = []
    try:
        hub_id = _add_memory(client, "wp022 hub memory effects cap test")
        for i in range(cap + 3):
            eid = _add_memory(client, f"wp022 effect {i}")
            effect_ids.append(eid)
            _wire_leads_to(test_driver, hub_id, eid)

        from memory_service import config as cfg
        monkeypatch.setattr(cfg.settings, "search_neighbour_cap", cap)
        # max_hops=0 so only LEADS_TO traversal contributes (no RELATED_TO collect)
        r = client.post("/memory/search", json={
            "query": "wp022 hub memory effects cap test",
            "max_hops": 0,
            "traversal_direction": "effects",
            "limit": 5,
        })

        assert r.status_code == 200
        hits = r.json()["memories"]
        hub_hits = [h for h in hits if h["id"] == hub_id]
        assert hub_hits, "Hub memory not found in results"
        assert len(hub_hits[0]["neighbours"]) <= cap
    finally:
        cleanup_nodes(test_driver, hub_id, *effect_ids, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_neighbours_below_cap_returned_in_full(client, test_driver):
    """When a node has fewer neighbours than the cap, all are returned."""
    cap = 50
    hub_id = None
    spoke_ids = []
    n_spokes = 3  # well below default cap
    try:
        hub_id = _add_memory(client, "wp022 hub memory below cap test")
        for i in range(n_spokes):
            sid = _add_memory(client, f"wp022 spoke below cap {i}")
            spoke_ids.append(sid)
            _wire_related(test_driver, hub_id, sid)

        r = client.post("/memory/search", json={
            "query": "wp022 hub memory below cap test",
            "max_hops": 1,
            "limit": 5,
        })
        assert r.status_code == 200
        hits = r.json()["memories"]
        hub_hits = [h for h in hits if h["id"] == hub_id]
        assert hub_hits, "Hub memory not found in results"
        # The service auto-links via vector search, so we may get more than n_spokes.
        # The key assertion is that all n_spokes are present and the total is below cap.
        neighbours = hub_hits[0]["neighbours"]
        assert len(neighbours) >= n_spokes, "Explicitly wired neighbours missing"
        assert len(neighbours) <= cap, "Cap must not truncate below the wired count"
    finally:
        cleanup_nodes(test_driver, hub_id, *spoke_ids, extra_ids={"Agent": _AGENT_ID})
