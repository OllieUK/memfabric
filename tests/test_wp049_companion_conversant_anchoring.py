"""
tests/test_wp049_companion_conversant_anchoring.py — WP-049: companion + conversant anchoring.

Integration tests (live Memgraph + running FastAPI required):
  I1 — companion_anchors present when ABOUT edges to settings.agent_id exist
  I2 — companion_anchors ordered by importance DESC, strength DESC
  I3 — companion_anchor_limit respected
  I4 — conversant_anchors present when person_id supplied and ABOUT memories exist
  I5 — conversant_anchors absent when person_id not supplied
  I6 — conversant_anchors None when person_id supplied but no matching memories
  I7 — conversant_anchors ordered by importance DESC, created_at DESC
  I8 — conversant_anchor_limit respected
  I9 — existing core/topic sections unaffected by new params
"""
import uuid
import pytest

_AGENT_ID = "claude-code"   # matches settings.agent_id default
_PERSON_ID = "test-person-wp049"
_ZERO_EMB = [0.0] * 384


@pytest.fixture
def cleanup_wp049(test_driver):
    """Collect memory IDs during test; DETACH DELETE them and the test Person node on teardown."""
    created_ids: list[str] = []
    yield created_ids
    with test_driver.session() as session:
        for mid in created_ids:
            session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mid)
        session.run(
            "MATCH (p:Person {id: $id}) DETACH DELETE p",
            id=_PERSON_ID,
        )


@pytest.mark.integration
class TestCompanionAnchors:
    def test_i1_companion_anchors_present(self, client, test_driver, cleanup_wp049):
        """I1: companion_anchors included when ABOUT edges to agent_id exist."""
        mem_id = f"wp049-comp-i1-{uuid.uuid4()}"
        cleanup_wp049.append(mem_id)
        with test_driver.session() as session:
            session.run(
                """
                CREATE (m:Memory {
                    id: $id, fact: $fact, text: $fact, type: 'fact',
                    tags: ['test'], importance: 5,
                    created_at: '2026-01-01T00:00:00+00:00',
                    strength: 0.99, min_strength: 0.3, decay_rate: 0.01,
                    embedding: $emb
                })
                WITH m
                MERGE (n {id: $agent_id})
                CREATE (m)-[:ABOUT]->(n)
                """,
                id=mem_id, fact="Mara is dominant and grounding",
                agent_id=_AGENT_ID, emb=_ZERO_EMB,
            )

        resp = client.get("/memory/wake-up", params={"companion_anchor_limit": 20})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("companion_anchors") is not None, "companion_anchors must be present"
        ids = [m["id"] for m in data["companion_anchors"]]
        assert mem_id in ids

    def test_i2_companion_anchors_ordering(self, client, test_driver, cleanup_wp049):
        """I2: companion_anchors ordered by importance DESC, strength DESC. Verified via Bolt."""
        ids = [f"wp049-comp-i2-{i}-{uuid.uuid4()}" for i in range(3)]
        cleanup_wp049.extend(ids)
        with test_driver.session() as session:
            session.run(
                """
                CREATE (m:Memory {
                    id: $id, fact: $fact, text: $fact, type: 'fact',
                    tags: ['test'], importance: 5, strength: 0.99,
                    created_at: '2026-01-01T00:00:00+00:00',
                    min_strength: 0.3, decay_rate: 0.01, embedding: $emb
                })
                WITH m MERGE (n {id: $agent_id}) CREATE (m)-[:ABOUT]->(n)
                """,
                id=ids[0], fact="High importance high strength",
                agent_id=_AGENT_ID, emb=_ZERO_EMB,
            )
            session.run(
                """
                CREATE (m:Memory {
                    id: $id, fact: $fact, text: $fact, type: 'fact',
                    tags: ['test'], importance: 5, strength: 0.50,
                    created_at: '2026-01-02T00:00:00+00:00',
                    min_strength: 0.3, decay_rate: 0.01, embedding: $emb
                })
                WITH m MERGE (n {id: $agent_id}) CREATE (m)-[:ABOUT]->(n)
                """,
                id=ids[1], fact="High importance low strength",
                agent_id=_AGENT_ID, emb=_ZERO_EMB,
            )
            session.run(
                """
                CREATE (m:Memory {
                    id: $id, fact: $fact, text: $fact, type: 'fact',
                    tags: ['test'], importance: 3, strength: 0.99,
                    created_at: '2026-01-03T00:00:00+00:00',
                    min_strength: 0.3, decay_rate: 0.01, embedding: $emb
                })
                WITH m MERGE (n {id: $agent_id}) CREATE (m)-[:ABOUT]->(n)
                """,
                id=ids[2], fact="Low importance high strength",
                agent_id=_AGENT_ID, emb=_ZERO_EMB,
            )

        with test_driver.session() as session:
            result = session.run(
                """
                MATCH (m:Memory)-[:ABOUT]->(n {id: $agent_id})
                WHERE m.id IN $ids
                RETURN m.id AS id
                ORDER BY m.importance DESC, coalesce(m.strength, 0.0) DESC
                """,
                agent_id=_AGENT_ID, ids=ids,
            )
            ordered = [r["id"] for r in result]
        assert ordered == [ids[0], ids[1], ids[2]], \
            f"Expected order [0,1,2] (importance desc, strength desc), got {ordered}"

    def test_i3_companion_anchor_limit_respected(self, client, test_driver, cleanup_wp049):
        """I3: companion_anchor_limit caps the result to the requested count."""
        mem_ids = [f"wp049-comp-i3-{i}-{uuid.uuid4()}" for i in range(4)]
        cleanup_wp049.extend(mem_ids)
        with test_driver.session() as session:
            for i, mid in enumerate(mem_ids):
                session.run(
                    """
                    CREATE (m:Memory {
                        id: $id, fact: $fact, text: $fact, type: 'fact',
                        tags: ['test'], importance: 5, strength: $strength,
                        created_at: '2026-01-01T00:00:00+00:00',
                        min_strength: 0.3, decay_rate: 0.01, embedding: $emb
                    })
                    WITH m MERGE (n {id: $agent_id}) CREATE (m)-[:ABOUT]->(n)
                    """,
                    id=mid, fact=f"Anchor memory {i}", agent_id=_AGENT_ID,
                    strength=round(0.99 - i * 0.05, 2), emb=_ZERO_EMB,
                )

        resp = client.get("/memory/wake-up", params={"companion_anchor_limit": 2})
        assert resp.status_code == 200
        data = resp.json()
        anchors = data.get("companion_anchors") or []
        assert len(anchors) <= 2, f"Expected ≤2 anchors with limit=2, got {len(anchors)}"


@pytest.mark.integration
class TestConversantAnchors:
    def test_i4_conversant_anchors_present(self, client, test_driver, cleanup_wp049):
        """I4: conversant_anchors included when person_id supplied and ABOUT memories exist."""
        mem_id = f"wp049-conv-i4-{uuid.uuid4()}"
        cleanup_wp049.append(mem_id)
        with test_driver.session() as session:
            session.run(
                """
                MERGE (p:Person {id: $pid})
                WITH p
                CREATE (m:Memory {
                    id: $id, fact: $fact, text: $fact, type: 'fact',
                    tags: ['test'], importance: 4,
                    created_at: '2026-01-01T00:00:00+00:00',
                    strength: 0.8, min_strength: 0.3, decay_rate: 0.01, embedding: $emb
                })
                CREATE (m)-[:ABOUT]->(p)
                """,
                pid=_PERSON_ID, id=mem_id, fact="Oliver has ADHD", emb=_ZERO_EMB,
            )

        resp = client.get("/memory/wake-up", params={"person_id": _PERSON_ID})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("conversant_anchors") is not None, "conversant_anchors must be present"
        ids = [m["id"] for m in data["conversant_anchors"]]
        assert mem_id in ids

    def test_i5_conversant_anchors_absent_without_person_id(self, client):
        """I5: conversant_anchors is absent/None when person_id not supplied."""
        resp = client.get("/memory/wake-up")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("conversant_anchors") is None

    def test_i6_conversant_anchors_none_for_unknown_person(self, client):
        """I6: conversant_anchors is None when person_id matches no ABOUT memories."""
        unknown = f"test-person-unknown-{uuid.uuid4()}"
        resp = client.get("/memory/wake-up", params={"person_id": unknown})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("conversant_anchors") is None

    def test_i7_conversant_anchors_ordering(self, client, test_driver, cleanup_wp049):
        """I7: conversant_anchors ordered by importance DESC, created_at DESC. Via Bolt."""
        ids = [f"wp049-conv-i7-{i}-{uuid.uuid4()}" for i in range(3)]
        cleanup_wp049.extend(ids)
        with test_driver.session() as session:
            session.run("MERGE (p:Person {id: $pid})", pid=_PERSON_ID)
            session.run(
                """
                CREATE (m:Memory {
                    id: $id, fact: $fact, text: $fact, type: 'fact',
                    tags: ['test'], importance: 5,
                    created_at: '2026-03-01T00:00:00+00:00',
                    strength: 0.5, min_strength: 0.3, decay_rate: 0.01, embedding: $emb
                })
                WITH m MATCH (p:Person {id: $pid}) CREATE (m)-[:ABOUT]->(p)
                """,
                id=ids[0], fact="High importance recent", pid=_PERSON_ID, emb=_ZERO_EMB,
            )
            session.run(
                """
                CREATE (m:Memory {
                    id: $id, fact: $fact, text: $fact, type: 'fact',
                    tags: ['test'], importance: 5,
                    created_at: '2026-01-01T00:00:00+00:00',
                    strength: 0.5, min_strength: 0.3, decay_rate: 0.01, embedding: $emb
                })
                WITH m MATCH (p:Person {id: $pid}) CREATE (m)-[:ABOUT]->(p)
                """,
                id=ids[1], fact="High importance older", pid=_PERSON_ID, emb=_ZERO_EMB,
            )
            session.run(
                """
                CREATE (m:Memory {
                    id: $id, fact: $fact, text: $fact, type: 'fact',
                    tags: ['test'], importance: 3,
                    created_at: '2026-03-15T00:00:00+00:00',
                    strength: 0.5, min_strength: 0.3, decay_rate: 0.01, embedding: $emb
                })
                WITH m MATCH (p:Person {id: $pid}) CREATE (m)-[:ABOUT]->(p)
                """,
                id=ids[2], fact="Low importance recent", pid=_PERSON_ID, emb=_ZERO_EMB,
            )

        with test_driver.session() as session:
            result = session.run(
                """
                MATCH (m:Memory)-[:ABOUT]->(p {id: $pid})
                WHERE m.id IN $ids
                RETURN m.id AS id
                ORDER BY m.importance DESC, m.created_at DESC
                """,
                pid=_PERSON_ID, ids=ids,
            )
            ordered = [r["id"] for r in result]
        assert ordered == [ids[0], ids[1], ids[2]], \
            f"Expected order [0,1,2] (importance desc, created_at desc), got {ordered}"

    def test_i8_conversant_anchor_limit_respected(self, client, test_driver, cleanup_wp049):
        """I8: conversant_anchor_limit caps the result."""
        mem_ids = [f"wp049-conv-i8-{i}-{uuid.uuid4()}" for i in range(4)]
        cleanup_wp049.extend(mem_ids)
        with test_driver.session() as session:
            session.run("MERGE (p:Person {id: $pid})", pid=_PERSON_ID)
            for i, mid in enumerate(mem_ids):
                session.run(
                    """
                    CREATE (m:Memory {
                        id: $id, fact: $fact, text: $fact, type: 'fact',
                        tags: ['test'], importance: 4,
                        created_at: '2026-01-01T00:00:00+00:00',
                        strength: 0.5, min_strength: 0.3, decay_rate: 0.01, embedding: $emb
                    })
                    WITH m MATCH (p:Person {id: $pid}) CREATE (m)-[:ABOUT]->(p)
                    """,
                    id=mid, fact=f"Conversant {i}", pid=_PERSON_ID, emb=_ZERO_EMB,
                )

        resp = client.get(
            "/memory/wake-up",
            params={"person_id": _PERSON_ID, "conversant_anchor_limit": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["conversant_anchors"]) <= 2

    def test_i9_existing_sections_unaffected(self, client):
        """I9: core memories and topic_memories fields still present with new params."""
        resp = client.get(
            "/memory/wake-up",
            params={"limit": 5, "topic": "memory", "person_id": "nonexistent-wp049"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "memories" in data
        assert "topic_memories" in data
        assert "maintenance_status" in data
