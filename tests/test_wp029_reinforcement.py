import uuid
import pytest


@pytest.mark.integration
class TestMemoryCreationSeeding:
    def test_new_memory_has_strength_seeded_from_importance(self, client, test_driver):
        """Memory created with importance=4 should have strength=0.8."""
        memory_id = None
        fact = f"wp029-seed-test-{uuid.uuid4()}"
        try:
            resp = client.post("/memory", json={
                "fact": fact,
                "type": "fact",
                "agent_id": "test-agent",
                "importance": 4,
            })
            assert resp.status_code == 200
            memory_id = resp.json()["memory_id"]

            with test_driver.session() as session:
                result = session.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.strength AS strength, "
                    "m.recall_count AS recall_count, m.reinforcement_count AS reinforcement_count, "
                    "m.last_reinforced_at AS last_reinforced_at, m.decay_rate AS decay_rate",
                    id=memory_id,
                )
                row = result.single()
                assert row is not None
                assert abs(row["strength"] - 0.8) < 0.001
                assert row["recall_count"] == 0
                assert row["reinforcement_count"] == 0
                assert row["last_reinforced_at"] is not None
                assert row["decay_rate"] == pytest.approx(0.01, abs=0.0001)
        finally:
            if memory_id:
                with test_driver.session() as session:
                    session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=memory_id)

    def test_importance_1_gives_strength_0_2(self, client, test_driver):
        memory_id = None
        fact = f"wp029-seed-imp1-{uuid.uuid4()}"
        try:
            resp = client.post("/memory", json={
                "fact": fact, "type": "fact", "agent_id": "test-agent", "importance": 1,
            })
            assert resp.status_code == 200
            memory_id = resp.json()["memory_id"]
            with test_driver.session() as session:
                row = session.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.strength AS strength", id=memory_id
                ).single()
                assert abs(row["strength"] - 0.2) < 0.001
        finally:
            if memory_id:
                with test_driver.session() as session:
                    session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=memory_id)


class TestReinforcementSettings:
    def test_default_values(self):
        from memory_service.config import Settings
        s = Settings()
        assert s.memory_decay_rate == 0.01
        assert s.edge_decay_rate == 0.005
        assert s.recall_strength_increment == 0.05
        assert s.explicit_strength_increment == 0.20
        assert s.edge_recall_increment == 0.02
        assert s.edge_explicit_increment == 0.10
        assert s.edge_prune_threshold == 0.05
        assert s.min_memory_strength == 0.0
