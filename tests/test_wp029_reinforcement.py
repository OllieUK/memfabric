import uuid
import pytest
from memory_service import memory_repo


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


@pytest.mark.integration
class TestRecallIncrement:
    def test_search_increments_recall_count(self, client, test_driver):
        """Searching twice should give recall_count >= 2 and strength > initial."""
        memory_id = None
        fact = f"wp029-recall-test-{uuid.uuid4()}"
        try:
            resp = client.post("/memory", json={
                "fact": fact, "type": "fact", "agent_id": "test-agent", "importance": 3,
            })
            assert resp.status_code == 200
            memory_id = resp.json()["memory_id"]
            initial_strength = 3 / 5.0  # 0.6

            # Search twice — TestClient runs background tasks synchronously
            for _ in range(2):
                client.post("/memory/search", json={"query": fact, "limit": 5})

            with test_driver.session() as session:
                row = session.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.recall_count AS rc, m.strength AS s",
                    id=memory_id,
                ).single()
                assert row["rc"] >= 2
                assert row["s"] > initial_strength
        finally:
            if memory_id:
                with test_driver.session() as session:
                    session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=memory_id)

    def test_strength_capped_at_1(self, test_driver):
        """Strength must never exceed 1.0 regardless of how many increments."""
        memory_id = None
        try:
            with test_driver.session() as session:
                memory_id = f"wp029-cap-{uuid.uuid4()}"
                session.run(
                    "CREATE (m:Memory {id: $id, importance: 5, strength: 0.95, "
                    "recall_count: 0, type: 'fact', tags: [], text: 'x', fact: 'x', "
                    "embedding: [], created_at: '2026-01-01', last_used_at: '2026-01-01'})",
                    id=memory_id,
                )
                memory_repo.recall_increment(session, [memory_id], 0.5, 0.0)
                row = session.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.strength AS s", id=memory_id
                ).single()
                assert row["s"] <= 1.0
        finally:
            if memory_id:
                with test_driver.session() as session:
                    session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=memory_id)


@pytest.mark.integration
class TestMaintenanceEndpoints:
    def test_decay_pass_returns_counts(self, client, test_driver):
        """Decay pass returns valid node/edge counts."""
        resp = client.post("/memory", json={
            "fact": f"wp029-decay-{uuid.uuid4()}", "type": "fact", "agent_id": "test-agent",
        })
        memory_id = resp.json()["memory_id"]
        try:
            r = client.post("/memory/maintenance/decay")
            assert r.status_code == 200
            data = r.json()
            assert "nodes_updated" in data
            assert "edges_updated" in data
            assert isinstance(data["nodes_updated"], int)
            assert isinstance(data["edges_updated"], int)
            assert data["nodes_updated"] >= 1
        finally:
            with test_driver.session() as session:
                session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=memory_id)

    def test_decay_pass_not_shadowed_by_reinforce_route(self, client):
        """POST /memory/maintenance/decay must NOT return 422 (route ordering check)."""
        r = client.post("/memory/maintenance/decay")
        # 200 = decay ran, 503 = DB issue — anything but 422 (wrong route) or 404
        assert r.status_code not in (404, 422)

    def test_weak_edges_returns_list(self, client):
        r = client.get("/memory/maintenance/weak-edges")
        assert r.status_code == 200
        data = r.json()
        assert "edges" in data
        assert isinstance(data["edges"], list)


@pytest.mark.integration
class TestExplicitReinforcement:
    def test_reinforce_increments_strength(self, client, test_driver):
        memory_id = None
        fact = f"wp029-reinforce-{uuid.uuid4()}"
        try:
            resp = client.post("/memory", json={
                "fact": fact, "type": "fact", "agent_id": "test-agent", "importance": 2,
            })
            memory_id = resp.json()["memory_id"]
            initial_strength = 2 / 5.0  # 0.4

            r = client.post(f"/memory/{memory_id}/reinforce", json={"signal": "explicit"})
            assert r.status_code == 200
            data = r.json()
            assert data["memory_id"] == memory_id
            assert data["new_strength"] > initial_strength

            with test_driver.session() as session:
                row = session.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.reinforcement_count AS rc",
                    id=memory_id,
                ).single()
                assert row["rc"] == 1
        finally:
            if memory_id:
                with test_driver.session() as session:
                    session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=memory_id)

    def test_reinforce_404_on_missing_memory(self, client):
        r = client.post("/memory/nonexistent-id/reinforce", json={"signal": "explicit"})
        assert r.status_code == 404

    def test_reinforce_co_recalled_ids_activates_edges(self, client, test_driver):
        """Two explicitly related memories: reinforce one with the other as co_recalled → edge weight increases."""
        m1 = m2 = None
        try:
            r1 = client.post("/memory", json={
                "fact": f"wp029-hebbian-a-{uuid.uuid4()}", "type": "fact", "agent_id": "test-agent",
            })
            m1 = r1.json()["memory_id"]
            # Use related_ids to guarantee a RELATED_TO edge exists between m2 and m1
            r2 = client.post("/memory", json={
                "fact": f"wp029-hebbian-b-{uuid.uuid4()}", "type": "fact", "agent_id": "test-agent",
                "related_ids": [m1],
            })
            m2 = r2.json()["memory_id"]

            # Confirm edge exists before reinforcement
            with test_driver.session() as session:
                row = session.run(
                    "MATCH (a:Memory {id: $a})-[r:RELATED_TO]->(b:Memory {id: $b}) "
                    "RETURN r.weight AS w, coalesce(r.activation_count, 0) AS ac",
                    a=m2, b=m1,
                ).single()
            assert row is not None, "Expected RELATED_TO edge to exist via related_ids"
            initial_weight = row["w"]
            initial_ac = row["ac"]

            # Reinforce m1 with m2 as co-recalled
            client.post(f"/memory/{m1}/reinforce", json={
                "signal": "explicit", "co_recalled_ids": [m2],
            })

            with test_driver.session() as session:
                row = session.run(
                    "MATCH (a:Memory {id: $a})-[r:RELATED_TO]->(b:Memory {id: $b}) "
                    "RETURN r.weight AS w, r.activation_count AS ac",
                    a=m2, b=m1,
                ).single()
            # Either weight increased or activation_count incremented
            assert row["w"] > initial_weight or row["ac"] > initial_ac
        finally:
            for mid in [m1, m2]:
                if mid:
                    with test_driver.session() as session:
                        session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mid)
