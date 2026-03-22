# tests/test_wp040_maintenance.py
"""WP-040: Memory maintenance orchestration tests."""
import uuid
import pytest
from unittest.mock import MagicMock
from memory_service import memory_repo


class TestNewConfigFields:
    def test_new_config_fields_exist_with_correct_defaults(self):
        from memory_service.config import Settings
        s = Settings()
        assert s.short_rest_recency_days == 7
        assert s.long_rest_recency_days == 1
        assert s.rediscovery_strength_threshold == 0.3
        assert s.edge_hard_prune_floor == 0.01
        assert s.edge_hard_prune_min_days == 90
        assert s.edge_modulation_factor == 0.5
        assert s.edge_modulation_cap == 10.0


class TestSystemNodeHelpers:
    def test_upsert_system_node_sets_fields(self):
        """upsert_system_node calls session.run with last_short_rest_at in the query."""
        session = MagicMock()
        session.run.return_value = None
        memory_repo.upsert_system_node(session, last_short_rest_at="2026-01-01T00:00:00+00:00")
        session.run.assert_called_once()
        call_args = session.run.call_args
        assert "last_short_rest_at" in call_args[0][0]

    def test_get_system_timestamps_returns_dict(self):
        """get_system_timestamps returns dict with last_short_rest_at and last_long_rest_at."""
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: {
            "last_short_rest_at": None,
            "last_long_rest_at": None
        }[key]
        session = MagicMock()
        session.run.return_value.single.return_value = mock_record
        result = memory_repo.get_system_timestamps(session)
        assert "last_short_rest_at" in result
        assert "last_long_rest_at" in result


class TestEdgeModulatedDecay:
    def test_apply_decay_no_modulation(self):
        """With factor=0, effective rate == base rate (backward compat)."""
        import math
        from memory_service.memory_repo import _apply_decay_modulated
        result = _apply_decay_modulated(
            current=1.0, base_rate=0.01, days=1.0,
            incoming_weight_sum=5.0,
            factor=0.0, cap=10.0, min_strength=0.0,
        )
        expected = math.exp(-0.01 * 1.0)
        assert abs(result - expected) < 1e-9

    def test_apply_decay_with_modulation_reduces_rate(self):
        """With factor=0.5 and sum_weight=2.0, effective rate is base/2.0."""
        import math
        from memory_service.memory_repo import _apply_decay_modulated
        # effective_rate = 0.01 / min(1 + 0.5*2.0, 10) = 0.01 / 2.0 = 0.005
        result = _apply_decay_modulated(
            current=1.0, base_rate=0.01, days=1.0,
            incoming_weight_sum=2.0,
            factor=0.5, cap=10.0, min_strength=0.0,
        )
        expected = math.exp(-0.005 * 1.0)
        assert abs(result - expected) < 1e-9

    def test_apply_decay_cap_limits_reduction(self):
        """Cap=3.0 means max denominator is 3, even with very high edge weight."""
        import math
        from memory_service.memory_repo import _apply_decay_modulated
        result = _apply_decay_modulated(
            current=1.0, base_rate=0.1, days=1.0,
            incoming_weight_sum=1000.0,
            factor=0.5, cap=3.0, min_strength=0.0,
        )
        # effective_rate = 0.1 / 3.0
        expected = math.exp(-0.1 / 3.0 * 1.0)
        assert abs(result - expected) < 1e-6


@pytest.mark.integration
class TestShortRest:
    def test_short_rest_dry_run_returns_correct_shape(self, client, test_driver):
        """Dry-run: response has correct shape and dry_run=True."""
        import uuid
        mem_id = f"wp040-sr-dr-{uuid.uuid4()}"
        try:
            with test_driver.session() as session:
                session.run(
                    "CREATE (m:Memory {id: $id, fact: 'test', text: 'test', "
                    "type: 'fact', tags: [], importance: 3, strength: 0.6, "
                    "recall_count: 1, reinforcement_count: 0, "
                    "last_reinforced_at: '2026-01-01T00:00:00+00:00', "
                    "last_used_at: '2026-01-01T00:00:00+00:00', "
                    "decay_rate: 0.01, embedding: []})",
                    id=mem_id,
                )
            before_strength = 0.6

            r = client.post("/memory/maintenance/short-rest?dry_run=true")
            assert r.status_code == 200
            data = r.json()
            assert data["dry_run"] is True
            assert "nodes_decayed" in data
            assert "edges_decayed" in data
            assert isinstance(data["nodes_decayed"], int)

            # DB state unchanged after dry-run
            with test_driver.session() as session:
                row = session.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.strength AS s", id=mem_id
                ).single()
            assert abs(row["s"] - before_strength) < 0.001
        finally:
            with test_driver.session() as session:
                session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mem_id)

    def test_short_rest_live_decays_and_updates_system_node(self, client, test_driver):
        """Live run decays in-scope nodes and sets last_short_rest_at on System node."""
        import uuid
        mem_id = f"wp040-sr-live-{uuid.uuid4()}"
        try:
            with test_driver.session() as session:
                session.run(
                    "CREATE (m:Memory {id: $id, fact: 'test', text: 'test', "
                    "type: 'fact', tags: [], importance: 3, strength: 0.6, "
                    "recall_count: 1, reinforcement_count: 0, "
                    "last_reinforced_at: '2020-01-01T00:00:00+00:00', "
                    "last_used_at: '2020-01-01T00:00:00+00:00', "
                    "decay_rate: 0.01, embedding: []})",
                    id=mem_id,
                )

            r = client.post("/memory/maintenance/short-rest")
            assert r.status_code == 200
            data = r.json()
            assert data["dry_run"] is False
            assert data["nodes_decayed"] >= 1

            # System node must be updated
            with test_driver.session() as session:
                row = session.run(
                    "MATCH (sys:System {id: 'system'}) RETURN sys.last_short_rest_at AS ts"
                ).single()
            assert row is not None
            assert row["ts"] is not None
        finally:
            with test_driver.session() as session:
                session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mem_id)


@pytest.mark.integration
class TestLongRest:
    def test_long_rest_dry_run_returns_correct_shape(self, client):
        """Dry-run: response has correct shape with dry_run=True."""
        r = client.post("/memory/maintenance/long-rest?dry_run=true")
        assert r.status_code == 200
        data = r.json()
        assert data["dry_run"] is True
        for field in ["nodes_decayed", "edges_decayed", "edges_discovered", "edges_pruned"]:
            assert field in data
            assert isinstance(data[field], int)

    def test_long_rest_live_updates_system_node(self, client, test_driver):
        """Live long-rest sets last_long_rest_at on System node."""
        r = client.post("/memory/maintenance/long-rest")
        assert r.status_code == 200
        data = r.json()
        assert data["dry_run"] is False

        with test_driver.session() as session:
            row = session.run(
                "MATCH (sys:System {id: 'system'}) RETURN sys.last_long_rest_at AS ts"
            ).single()
        assert row is not None
        assert row["ts"] is not None

    def test_long_rest_edge_rediscovery(self, client, test_driver):
        """Two semantically similar memories: long-rest discovers a RELATED_TO edge."""
        import uuid
        from memory_service.embeddings import get_embedding
        m1 = m2 = None
        try:
            emb1 = get_embedding("The user drinks coffee every morning")
            emb2 = get_embedding("The user starts each day with a hot beverage")
            m1 = f"wp040-rd-a-{uuid.uuid4()}"
            m2 = f"wp040-rd-b-{uuid.uuid4()}"

            with test_driver.session() as session:
                for mid, emb, fact in [
                    (m1, emb1, "The user drinks coffee every morning"),
                    (m2, emb2, "The user starts each day with a hot beverage"),
                ]:
                    session.run(
                        "CREATE (m:Memory {id: $id, fact: $fact, text: $fact, "
                        "type: 'fact', tags: [], importance: 3, strength: 0.8, "
                        "recall_count: 0, reinforcement_count: 0, "
                        "last_reinforced_at: '2026-01-01T00:00:00+00:00', "
                        "last_used_at: '2026-01-01T00:00:00+00:00', "
                        "decay_rate: 0.01, embedding: $emb})",
                        id=mid, fact=fact, emb=emb,
                    )

            # Remove any auto-created RELATED_TO edges
            with test_driver.session() as session:
                session.run(
                    "MATCH (a:Memory {id: $a})-[r:RELATED_TO]-(b:Memory {id: $b}) DELETE r",
                    a=m1, b=m2,
                )

            r = client.post("/memory/maintenance/long-rest")
            assert r.status_code == 200

            with test_driver.session() as session:
                row = session.run(
                    "MATCH (a:Memory {id: $a})-[r:RELATED_TO]-(b:Memory {id: $b}) RETURN r",
                    a=m1, b=m2,
                ).single()
            assert row is not None, "Expected RELATED_TO edge to be discovered between similar memories"
        finally:
            for mid in [m1, m2]:
                if mid:
                    with test_driver.session() as session:
                        session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mid)
