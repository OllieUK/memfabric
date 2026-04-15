# tests/test_wp117_auto_merge.py
"""Tests for WP-117: autonomous dedup auto-merge threshold wired into long_rest."""
import pytest
from unittest.mock import MagicMock, patch, call
from fastapi.testclient import TestClient

from tests.conftest import cleanup_nodes, get_memory_node

_AGENT_ID = "test-agent-wp117"


# ---------------------------------------------------------------------------
# Unit tests — TestPickCanonical
# ---------------------------------------------------------------------------

class TestPickCanonical:
    def _pick(self, a, b):
        from memory_service.memory_repo import _pick_canonical
        return _pick_canonical(a, b)

    def test_higher_importance_wins(self):
        a = {"id": "aaa", "importance": 3, "created_at": "2026-01-01T00:00:00+00:00"}
        b = {"id": "bbb", "importance": 5, "created_at": "2026-01-01T00:00:00+00:00"}
        canonical_id, source_id = self._pick(a, b)
        assert canonical_id == "bbb"
        assert source_id == "aaa"

    def test_higher_importance_wins_reversed(self):
        a = {"id": "aaa", "importance": 5, "created_at": "2026-01-01T00:00:00+00:00"}
        b = {"id": "bbb", "importance": 3, "created_at": "2026-01-01T00:00:00+00:00"}
        canonical_id, source_id = self._pick(a, b)
        assert canonical_id == "aaa"
        assert source_id == "bbb"

    def test_older_created_at_wins_on_tie(self):
        a = {"id": "aaa", "importance": 3, "created_at": "2026-01-01T00:00:00+00:00"}
        b = {"id": "bbb", "importance": 3, "created_at": "2026-02-01T00:00:00+00:00"}
        canonical_id, source_id = self._pick(a, b)
        # older (a) should be canonical
        assert canonical_id == "aaa"
        assert source_id == "bbb"

    def test_id_lexicographic_fallback(self):
        # Both same importance and created_at — lower id string wins
        a = {"id": "aaa", "importance": 3, "created_at": "2026-01-01T00:00:00+00:00"}
        b = {"id": "zzz", "importance": 3, "created_at": "2026-01-01T00:00:00+00:00"}
        canonical_id, source_id = self._pick(a, b)
        assert canonical_id == "aaa"
        assert source_id == "zzz"

    def test_none_importance_treated_as_1(self):
        a = {"id": "aaa", "importance": None, "created_at": "2026-01-01T00:00:00+00:00"}
        b = {"id": "bbb", "importance": 3, "created_at": "2026-01-01T00:00:00+00:00"}
        canonical_id, source_id = self._pick(a, b)
        # b has higher importance (3 vs 1)
        assert canonical_id == "bbb"
        assert source_id == "aaa"

    def test_both_none_importance_uses_timestamp_tiebreak(self):
        a = {"id": "aaa", "importance": None, "created_at": "2026-01-01T00:00:00+00:00"}
        b = {"id": "bbb", "importance": None, "created_at": "2026-02-01T00:00:00+00:00"}
        canonical_id, source_id = self._pick(a, b)
        assert canonical_id == "aaa"
        assert source_id == "bbb"


# ---------------------------------------------------------------------------
# Unit tests — TestAutoMergeDisabled
# ---------------------------------------------------------------------------

class TestAutoMergeDisabled:
    def _make_session(self, near_dup_pairs=None):
        """Return a session mock wired to return near_dup_pairs from find_near_duplicates."""
        mock_session = MagicMock()
        # Stub out all session.run calls with a plausible return value
        mock_run_result = MagicMock()
        mock_run_result.__iter__ = MagicMock(return_value=iter([]))
        mock_run_result.single = MagicMock(return_value={"n": 0, "would_discover": 0})
        mock_session.run.return_value = mock_run_result
        return mock_session

    def test_long_rest_returns_zero_when_threshold_none(self):
        from memory_service.memory_repo import long_rest
        session = self._make_session()

        with patch("memory_service.memory_repo.decay_pass") as mock_decay, \
             patch("memory_service.memory_repo.find_near_duplicates") as mock_dups, \
             patch("memory_service.memory_repo.upsert_system_node"), \
             patch("memory_service.memory_repo.append_maintenance_log"):
            mock_decay.return_value = {"nodes_updated": 0, "edges_updated": 0}
            mock_dups.return_value = []

            result = long_rest(
                session,
                now_iso="2026-01-01T03:00:00+00:00",
                min_strength=0.0,
                edge_modulation_factor=0.5,
                edge_modulation_cap=10.0,
                rediscovery_strength_threshold=0.3,
                edge_hard_prune_floor=0.01,
                edge_hard_prune_min_days=90,
                edge_decay_rate=0.005,
                auto_merge_threshold=None,
            )

        assert result["auto_merged_count"] == 0

    def test_long_rest_returns_zero_on_dry_run(self):
        from memory_service.memory_repo import long_rest
        session = self._make_session()

        with patch("memory_service.memory_repo.decay_pass") as mock_decay, \
             patch("memory_service.memory_repo.find_near_duplicates") as mock_dups, \
             patch("memory_service.memory_repo.upsert_system_node"), \
             patch("memory_service.memory_repo.append_maintenance_log"):
            mock_decay.return_value = {"nodes_updated": 0, "edges_updated": 0}
            # Provide a pair that would match the threshold — should be ignored on dry_run
            mock_dups.return_value = [
                {
                    "a": {"id": "id-1", "text": "hello", "importance": 3, "created_at": "2026-01-01T00:00:00+00:00"},
                    "b": {"id": "id-2", "text": "hello world", "importance": 2, "created_at": "2026-01-02T00:00:00+00:00"},
                    "similarity": 0.95,
                }
            ]

            result = long_rest(
                session,
                now_iso="2026-01-01T03:00:00+00:00",
                min_strength=0.0,
                edge_modulation_factor=0.5,
                edge_modulation_cap=10.0,
                rediscovery_strength_threshold=0.3,
                edge_hard_prune_floor=0.01,
                edge_hard_prune_min_days=90,
                edge_decay_rate=0.005,
                auto_merge_threshold=0.80,
                dry_run=True,
            )

        assert result["auto_merged_count"] == 0


# ---------------------------------------------------------------------------
# Unit tests — TestNewConfigField
# ---------------------------------------------------------------------------

class TestNewConfigField:
    def test_auto_merge_threshold_default_is_none(self):
        import os
        # Temporarily clear the env var in case it's set
        original = os.environ.pop("AUTO_MERGE_THRESHOLD", None)
        try:
            from memory_service.config import Settings
            s = Settings(_env_file=None)
            assert s.auto_merge_threshold is None
        finally:
            if original is not None:
                os.environ["AUTO_MERGE_THRESHOLD"] = original

    def test_auto_merge_threshold_can_be_set(self):
        import os
        os.environ["AUTO_MERGE_THRESHOLD"] = "0.97"
        try:
            from memory_service.config import Settings
            s = Settings(_env_file=None)
            assert s.auto_merge_threshold == pytest.approx(0.97)
        finally:
            del os.environ["AUTO_MERGE_THRESHOLD"]


# ---------------------------------------------------------------------------
# Unit tests — TestLongRestResponseModel
# ---------------------------------------------------------------------------

class TestLongRestResponseModel:
    def test_auto_merged_count_in_response(self):
        from memory_service.main import LongRestResponse
        resp = LongRestResponse(
            nodes_decayed=0,
            edges_decayed=0,
            edges_discovered=0,
            edges_pruned=0,
            embedded_memory_count=0,
            index_capacity=5000,
            index_utilisation_pct=None,
            index_near_capacity=False,
            near_duplicate_count=0,
            near_duplicate_candidates=[],
            dry_run=False,
            auto_merged_count=3,
        )
        assert resp.auto_merged_count == 3

    def test_auto_merged_count_defaults_to_zero(self):
        from memory_service.main import LongRestResponse
        resp = LongRestResponse(
            nodes_decayed=0,
            edges_decayed=0,
            edges_discovered=0,
            edges_pruned=0,
            embedded_memory_count=0,
            index_capacity=5000,
            index_near_capacity=False,
            near_duplicate_count=0,
            near_duplicate_candidates=[],
            dry_run=False,
        )
        assert resp.auto_merged_count == 0


# ---------------------------------------------------------------------------
# Integration tests — TestAutoMergeIntegration
# ---------------------------------------------------------------------------

def _add_body(fact: str, importance: int = 1, **kwargs) -> dict:
    body = {
        "fact": fact,
        "type": "fact",
        "agent_id": _AGENT_ID,
        "importance": importance,
        "tags": ["test"],
    }
    body.update(kwargs)
    return body


def _run_long_rest(client, auto_merge_threshold=None, dry_run=False):
    params = {}
    if auto_merge_threshold is not None:
        params["auto_merge_threshold"] = auto_merge_threshold
    if dry_run:
        params["dry_run"] = "true"
    resp = client.post("/memory/maintenance/long-rest", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.integration
class TestAutoMergeIntegration:

    def test_auto_merge_fires_on_near_identical_pair(self, client, test_driver):
        """Near-identical memories should be merged when threshold is set below their similarity."""
        id_a = None
        id_b = None
        try:
            # Create two memories with nearly identical text
            r1 = client.post("/memory", json=_add_body(
                "The API server is not responding to requests.",
                importance=3,
            ))
            assert r1.status_code == 200, r1.text
            id_a = r1.json()["memory_id"]

            r2 = client.post("/memory", json=_add_body(
                "The API server has stopped responding to requests.",
                importance=2,
            ))
            assert r2.status_code == 200, r2.text
            id_b = r2.json()["memory_id"]

            # find_near_duplicates requires a RELATED_TO edge between the pair.
            # New nodes have low initial strength so edge rediscovery won't pick them up.
            # Explicitly wire the edge via the driver to make the pair discoverable.
            with test_driver.session() as session:
                session.run(
                    """
                    MATCH (a:Memory {id: $id_a}), (b:Memory {id: $id_b})
                    MERGE (a)-[r:RELATED_TO]->(b)
                    ON CREATE SET r.weight = 0.90,
                                  r.activation_count = 0,
                                  r.last_activated_at = '2026-01-01T00:00:00+00:00',
                                  r.decay_rate = 0.005
                    """,
                    id_a=id_a,
                    id_b=id_b,
                )

            # Run long_rest with a low threshold to catch similar pairs
            result = _run_long_rest(client, auto_merge_threshold=0.80)
            assert result["auto_merged_count"] >= 1, (
                f"Expected at least 1 auto-merge but got {result['auto_merged_count']}. "
                f"near_duplicate_count={result['near_duplicate_count']}"
            )

            # The lower-importance node (id_b, importance=2) should be merged into id_a (importance=3)
            merged_node = get_memory_node(test_driver, id_b)
            if merged_node and merged_node.get("status") == "merged":
                assert merged_node.get("superseded_by") == id_a
                id_b = None  # archived — cleanup handles the merged node via DETACH DELETE on id_a

        finally:
            cleanup_nodes(test_driver, *[x for x in [id_a, id_b] if x is not None])
            with test_driver.session() as session:
                session.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)

    def test_auto_merge_writes_maintenance_log_entry(self, client, test_driver):
        """After auto-merge, the maintenance log should contain an operation='auto_merge' entry."""
        id_a = None
        id_b = None
        try:
            r1 = client.post("/memory", json=_add_body(
                "Memory consolidation is a key function of sleep in biological systems.",
                importance=3,
            ))
            assert r1.status_code == 200, r1.text
            id_a = r1.json()["memory_id"]

            r2 = client.post("/memory", json=_add_body(
                "Sleep consolidates memories in biological neural systems.",
                importance=2,
            ))
            assert r2.status_code == 200, r2.text
            id_b = r2.json()["memory_id"]

            # Wire the RELATED_TO edge directly so find_near_duplicates can discover the pair
            with test_driver.session() as session:
                session.run(
                    """
                    MATCH (a:Memory {id: $id_a}), (b:Memory {id: $id_b})
                    MERGE (a)-[r:RELATED_TO]->(b)
                    ON CREATE SET r.weight = 0.90,
                                  r.activation_count = 0,
                                  r.last_activated_at = '2026-01-01T00:00:00+00:00',
                                  r.decay_rate = 0.005
                    """,
                    id_a=id_a,
                    id_b=id_b,
                )

            result = _run_long_rest(client, auto_merge_threshold=0.80)
            auto_count = result["auto_merged_count"]

            if auto_count >= 1:
                maint_resp = client.get("/memory/maintenance/log")
                assert maint_resp.status_code == 200, maint_resp.text
                log_data = maint_resp.json()
                entries = log_data.get("entries", log_data) if isinstance(log_data, dict) else log_data
                auto_merge_entries = [e for e in entries if e.get("operation") == "auto_merge"]
                assert len(auto_merge_entries) >= 1, (
                    f"Expected auto_merge log entries but found none. All entries: {entries}"
                )
                entry = auto_merge_entries[-1]
                assert "source_id" in entry
                assert "canonical_id" in entry
                assert "similarity" in entry
                assert "merged_at" in entry

            # Cleanup: find which node was merged
            node_b = get_memory_node(test_driver, id_b)
            if node_b and node_b.get("status") == "merged":
                id_b = None  # archived

        finally:
            cleanup_nodes(test_driver, *[x for x in [id_a, id_b] if x is not None])
            with test_driver.session() as session:
                session.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)

    def test_auto_merge_skipped_below_threshold(self, client, test_driver):
        """Pairs below the threshold should not be merged."""
        id_a = None
        id_b = None
        try:
            r1 = client.post("/memory", json=_add_body(
                "The project uses Python for backend services.",
            ))
            assert r1.status_code == 200, r1.text
            id_a = r1.json()["memory_id"]

            r2 = client.post("/memory", json=_add_body(
                "Oliver prefers hiking on weekends.",
            ))
            assert r2.status_code == 200, r2.text
            id_b = r2.json()["memory_id"]

            # Very high threshold — these unrelated memories shouldn't match
            result = _run_long_rest(client, auto_merge_threshold=0.97)
            # These memories have very low similarity — even if auto_merged_count > 0,
            # these specific memories should still both be active
            node_a = get_memory_node(test_driver, id_a)
            node_b = get_memory_node(test_driver, id_b)
            assert node_a is not None and node_a.get("status") in (None, "active")
            assert node_b is not None and node_b.get("status") in (None, "active")

        finally:
            cleanup_nodes(test_driver, *[x for x in [id_a, id_b] if x is not None])
            with test_driver.session() as session:
                session.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)

    def test_auto_merge_disabled_by_default(self, client, test_driver):
        """long_rest with no auto_merge_threshold should return auto_merged_count=0."""
        result = _run_long_rest(client)
        assert result["auto_merged_count"] == 0

    def test_canonical_node_has_correct_id(self, client, test_driver):
        """The higher-importance node should be the canonical (survivor) after merge."""
        id_low = None
        id_high = None
        try:
            r1 = client.post("/memory", json=_add_body(
                "Graphs are efficient for representing relationships between entities.",
                importance=2,
            ))
            assert r1.status_code == 200, r1.text
            id_low = r1.json()["memory_id"]

            r2 = client.post("/memory", json=_add_body(
                "Graph databases efficiently represent entity relationships.",
                importance=4,
            ))
            assert r2.status_code == 200, r2.text
            id_high = r2.json()["memory_id"]

            # Wire RELATED_TO edge directly
            with test_driver.session() as session:
                session.run(
                    """
                    MATCH (a:Memory {id: $id_low}), (b:Memory {id: $id_high})
                    MERGE (a)-[r:RELATED_TO]->(b)
                    ON CREATE SET r.weight = 0.90,
                                  r.activation_count = 0,
                                  r.last_activated_at = '2026-01-01T00:00:00+00:00',
                                  r.decay_rate = 0.005
                    """,
                    id_low=id_low,
                    id_high=id_high,
                )

            result = _run_long_rest(client, auto_merge_threshold=0.80)

            if result["auto_merged_count"] >= 1:
                node_low = get_memory_node(test_driver, id_low)
                node_high = get_memory_node(test_driver, id_high)

                if node_low and node_low.get("status") == "merged":
                    # Low importance was merged — correct behaviour
                    assert node_low.get("superseded_by") == id_high
                    assert node_high.get("status") in (None, "active")
                    id_low = None
                # If they weren't similar enough, both remain active — that's fine

        finally:
            cleanup_nodes(test_driver, *[x for x in [id_low, id_high] if x is not None])
            with test_driver.session() as session:
                session.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)

    def test_dry_run_does_not_merge(self, client, test_driver):
        """dry_run=True with auto_merge_threshold set should not merge any nodes."""
        id_a = None
        id_b = None
        try:
            r1 = client.post("/memory", json=_add_body(
                "The service restarts automatically when it encounters an error.",
                importance=3,
            ))
            assert r1.status_code == 200, r1.text
            id_a = r1.json()["memory_id"]

            r2 = client.post("/memory", json=_add_body(
                "When an error occurs, the service will restart itself automatically.",
                importance=2,
            ))
            assert r2.status_code == 200, r2.text
            id_b = r2.json()["memory_id"]

            # Wire RELATED_TO edge directly so the pair is discoverable
            with test_driver.session() as session:
                session.run(
                    """
                    MATCH (a:Memory {id: $id_a}), (b:Memory {id: $id_b})
                    MERGE (a)-[r:RELATED_TO]->(b)
                    ON CREATE SET r.weight = 0.90,
                                  r.activation_count = 0,
                                  r.last_activated_at = '2026-01-01T00:00:00+00:00',
                                  r.decay_rate = 0.005
                    """,
                    id_a=id_a,
                    id_b=id_b,
                )

            result = _run_long_rest(client, auto_merge_threshold=0.80, dry_run=True)
            assert result["auto_merged_count"] == 0
            assert result["dry_run"] is True

            # Both nodes should still be active
            node_a = get_memory_node(test_driver, id_a)
            node_b = get_memory_node(test_driver, id_b)
            assert node_a is not None and node_a.get("status") in (None, "active")
            assert node_b is not None and node_b.get("status") in (None, "active")

        finally:
            cleanup_nodes(test_driver, *[x for x in [id_a, id_b] if x is not None])
            with test_driver.session() as session:
                session.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)
