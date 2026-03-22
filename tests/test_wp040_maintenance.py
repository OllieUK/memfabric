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


@pytest.mark.integration
class TestDumpRestoreScript:
    def test_dump_produces_valid_json(self, tmp_path, test_driver):
        """dump_db() writes a JSON file with nodes, edges, and created_at keys."""
        import json
        from scripts.dump_db import dump_db
        out_path = tmp_path / "test_dump.json"
        with test_driver.session() as session:
            dump_db(session, str(out_path))
        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert "nodes" in data
        assert "edges" in data
        assert "created_at" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    def test_restore_dry_run_returns_counts_without_writing(self, test_driver):
        """restore_db dry_run=True returns expected counts but does not write."""
        from scripts.restore_db import restore_db
        data = {
            "created_at": "2026-01-01T00:00:00+00:00",
            "nodes": [{"id": "restore-dry-run-test", "fact": "test", "text": "test",
                        "type": "fact", "tags": [], "importance": 3}],
            "edges": [],
        }
        with test_driver.session() as session:
            result = restore_db(session, data, dry_run=True)
        assert result["dry_run"] is True
        assert result["nodes_merged"] == 1
        # Node must NOT have been written
        with test_driver.session() as session:
            row = session.run(
                "MATCH (m:Memory {id: 'restore-dry-run-test'}) RETURN m"
            ).single()
        assert row is None

    def test_restore_allowlist_guard_skips_unknown_edge_type(self, test_driver, capsys):
        """restore_db skips edges with unknown types and prints a warning."""
        import uuid
        from scripts.restore_db import restore_db
        m1 = f"restore-guard-a-{uuid.uuid4()}"
        m2 = f"restore-guard-b-{uuid.uuid4()}"
        try:
            with test_driver.session() as session:
                for mid in [m1, m2]:
                    session.run(
                        "CREATE (m:Memory {id: $id, fact: 'test', text: 'test', "
                        "type: 'fact', tags: [], importance: 3, strength: 0.6, embedding: []})",
                        id=mid,
                    )
            data = {
                "created_at": "2026-01-01T00:00:00+00:00",
                "nodes": [],
                "edges": [
                    {"src": m1, "tgt": m2, "type": "PRODUCED_BY", "weight": 0.5}
                ],
            }
            with test_driver.session() as session:
                result = restore_db(session, data, dry_run=False)
            # Edge should have been skipped
            assert result["edges_merged"] == 0
            # Verify no PRODUCED_BY edge was created
            with test_driver.session() as session:
                row = session.run(
                    "MATCH (a:Memory {id: $a})-[r:PRODUCED_BY]->(b:Memory {id: $b}) RETURN r",
                    a=m1, b=m2,
                ).single()
            assert row is None
        finally:
            for mid in [m1, m2]:
                with test_driver.session() as session:
                    session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mid)


@pytest.mark.integration
class TestMaintenanceStats:
    def test_stats_endpoint_returns_correct_shape(self, client):
        """GET /memory/maintenance/stats returns correct nested shape."""
        r = client.get("/memory/maintenance/stats")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data
        assert "maintenance" in data
        for field in ["total", "mean_strength", "median_strength", "below_prune_floor", "at_max_strength"]:
            assert field in data["nodes"], f"Missing nodes.{field}"
        for field in ["total", "mean_weight", "weak_count"]:
            assert field in data["edges"], f"Missing edges.{field}"
        for field in ["last_short_rest_at", "last_long_rest_at", "short_rest_overdue", "long_rest_overdue"]:
            assert field in data["maintenance"], f"Missing maintenance.{field}"
        assert isinstance(data["maintenance"]["short_rest_overdue"], bool)
        assert isinstance(data["maintenance"]["long_rest_overdue"], bool)


class TestWakeUpMaintenanceWarning:
    def test_wake_up_response_model_has_maintenance_warning(self):
        """WakeUpResponse model should include maintenance_warning field."""
        from memory_service.main import WakeUpResponse
        fields = WakeUpResponse.model_fields
        assert "maintenance_warning" in fields

    def test_wake_up_response_maintenance_warning_is_optional(self):
        """maintenance_warning can be None."""
        from memory_service.main import WakeUpResponse
        r = WakeUpResponse(memories=[], topic_memories=[], maintenance_warning=None)
        assert r.maintenance_warning is None
