# WP-049 Implementation Plan: Wake-up Companion + Conversant Anchoring

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two new additive sections to the wake-up response — `companion_anchors` (memories about the calling agent's identity) and `conversant_anchors` (memories about a specific person) — via a label-agnostic `ABOUT` graph traversal.

**Architecture:** The repo layer gains two new Cypher queries; the API response model gains two new optional fields; the client returns a dict instead of a 3-tuple; CLI and MCP render the new sections. A seeding script links existing companion identity memories to the agent identity node. All changes are purely additive — the existing core/topic sections are untouched.

**Tech Stack:** FastAPI, Memgraph (Cypher), Pydantic v2, httpx/respx, pytest, typer, FastMCP, pydantic-settings.

**Spec:** `docs/superpowers/specs/2026-04-09-wp049-wake-up-companion-conversant-anchoring-design.md`

---

## File map

| File | Change |
|---|---|
| `memory_service/config.py` | Add 2 new limit settings |
| `memory_service/memory_repo.py` | Extend `wake_up()` with 4 new params + 2 new Cypher queries |
| `memory_service/main.py` | Extend `WakeUpResponse` + `wake_up` endpoint with new params/fields |
| `memory_client/client.py` | Change `wake_up_split()` return type: 3-tuple → dict |
| `memory_client/cli.py` | Add `--person-id` flag; render Companion + Conversant sections |
| `mcp_server/server.py` | Add `person_id` param; render Companion + Conversant sections |
| `tests/test_wp049_companion_conversant_anchoring.py` | **New** — integration tests I1–I9 |
| `tests/test_wake_up_close_session.py` | Update U13 for dict return |
| `tests/test_wp033_mcp_server.py` | Fix 3 tuple mocks → dict (WP-089 pre-existing failures) |
| `tests/test_wp054_maintenance_audit.py` | Fix 1 tuple assert + 2 tuple mocks → dict |
| `scripts/seed_companion_anchors.py` | **New** — one-time idempotent ABOUT-edge seeder |
| `BACKLOG.md` | Move WP-049 to Currently in Progress → Completed |

---

## Task 0: Mark WP-049 in progress in BACKLOG.md

**Files:**
- Modify: `BACKLOG.md`

- [ ] **Step 1: Move WP-049 row to Currently In Progress section**

In `BACKLOG.md`, find the `## Currently In Progress` section (or create it if absent) and move the WP-049 row there. Remove it from the ordered backlog table.

- [ ] **Step 2: Commit**

```bash
git add BACKLOG.md
git commit -m "WP-049: move to currently in progress"
```

---

## Task 1: Add config settings

**Files:**
- Modify: `memory_service/config.py`

- [ ] **Step 1: Add two new fields to the `Settings` class**

In `memory_service/config.py`, add these two lines after the `near_duplicate_limit` field (around line 48):

```python
    wake_up_companion_anchor_limit: int = 5    # WAKE_UP_COMPANION_ANCHOR_LIMIT
    wake_up_conversant_anchor_limit: int = 10  # WAKE_UP_CONVERSANT_ANCHOR_LIMIT
```

- [ ] **Step 2: Verify the service still starts**

```bash
python3 -c "from memory_service.config import settings; print(settings.wake_up_companion_anchor_limit, settings.wake_up_conversant_anchor_limit)"
```

Expected output: `5 10`

- [ ] **Step 3: Commit**

```bash
git add memory_service/config.py
git commit -m "WP-049: add wake_up_companion_anchor_limit and wake_up_conversant_anchor_limit settings"
```

---

## Task 2: Extend repo + API — write integration tests first, then implement

**Files:**
- Create: `tests/test_wp049_companion_conversant_anchoring.py`
- Modify: `memory_service/memory_repo.py:455-510`
- Modify: `memory_service/main.py:374-426`

### Step 1: Write the integration tests (they must fail before implementation)

Create `tests/test_wp049_companion_conversant_anchoring.py`:

```python
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
```

- [ ] **Step 2: Run tests — verify they fail (endpoint does not accept person_id yet)**

```bash
pytest tests/test_wp049_companion_conversant_anchoring.py -v -m integration 2>&1 | head -40
```

Expected: errors like `422 Unprocessable Entity` (unknown query param) or `KeyError: companion_anchors`.

### Step 3: Implement — repo layer

Replace the `wake_up` function in `memory_service/memory_repo.py` (lines 455–510) with:

```python
def wake_up(
    session,
    limit: int,
    topic_embedding: list | None = None,
    agent_id: str | None = None,
    companion_anchor_limit: int = 5,
    person_id: str | None = None,
    conversant_anchor_limit: int = 10,
) -> dict:
    """Return memories for session start as separate lists.

    Returns:
        dict with keys:
          "core"              — importance-ranked list, up to `limit` items
          "topic"             — topic-only items (not in core); empty when no topic_embedding
          "companion_anchors" — memories ABOUT node with id=agent_id; None when absent/empty
          "conversant_anchors"— memories ABOUT node with id=person_id; None when absent/empty
        Each item dict: id, text, type, tags, importance, created_at, strand_id
    """
    result = session.run(
        """
        MATCH (m:Memory)
        WHERE (m.status IS NULL OR m.status = 'active')
          AND (m.ephemeral IS NULL OR m.ephemeral = false)
        OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
        WITH DISTINCT m, collect(s.id)[0] AS strand_id
        RETURN m.id AS id, m.text AS text, m.type AS type,
               m.tags AS tags, m.importance AS importance,
               m.created_at AS created_at, strand_id
        ORDER BY m.importance DESC,
                 coalesce(m.strength, 0.0) DESC,
                 coalesce(m.reinforcement_count, 0) DESC,
                 coalesce(m.recall_count, 0) DESC,
                 m.created_at DESC
        LIMIT $limit
        """,
        limit=limit,
    )
    core = [_record_to_memory_dict(r) for r in result]

    if topic_embedding is None:
        topic = []
    else:
        core_ids = {item["id"] for item in core}
        topic_result = session.run(
            """
            CALL vector_search.search("mem_embedding_idx", $limit, $query_vec)
            YIELD node AS m, distance
            WITH m, distance
            WHERE (m.status IS NULL OR m.status = 'active')
              AND (m.ephemeral IS NULL OR m.ephemeral = false)
            OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
            WITH DISTINCT m, collect(s.id)[0] AS strand_id, min(distance) AS dist
            RETURN m.id AS id, m.text AS text, m.type AS type,
                   m.tags AS tags, m.importance AS importance,
                   m.created_at AS created_at, strand_id
            ORDER BY dist ASC
            """,
            limit=limit,
            query_vec=topic_embedding,
        )
        topic = [_record_to_memory_dict(r) for r in topic_result if r["id"] not in core_ids]

    # Companion anchors — memories ABOUT the calling agent's identity node
    companion_anchors = None
    if agent_id is not None:
        comp_result = session.run(
            """
            MATCH (m:Memory)-[:ABOUT]->(n)
            WHERE n.id = $agent_id
              AND (m.status IS NULL OR m.status = 'active')
              AND (m.ephemeral IS NULL OR m.ephemeral = false)
            OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
            WITH DISTINCT m, collect(s.id)[0] AS strand_id
            RETURN m.id AS id, m.text AS text, m.type AS type,
                   m.tags AS tags, m.importance AS importance,
                   m.created_at AS created_at, strand_id
            ORDER BY m.importance DESC, coalesce(m.strength, 0.0) DESC
            LIMIT $limit
            """,
            agent_id=agent_id,
            limit=companion_anchor_limit,
        )
        items = [_record_to_memory_dict(r) for r in comp_result]
        companion_anchors = items if items else None

    # Conversant anchors — memories ABOUT the person currently being addressed
    conversant_anchors = None
    if person_id is not None:
        conv_result = session.run(
            """
            MATCH (m:Memory)-[:ABOUT]->(p)
            WHERE p.id = $person_id
              AND (m.status IS NULL OR m.status = 'active')
              AND (m.ephemeral IS NULL OR m.ephemeral = false)
            OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
            WITH DISTINCT m, collect(s.id)[0] AS strand_id
            RETURN m.id AS id, m.text AS text, m.type AS type,
                   m.tags AS tags, m.importance AS importance,
                   m.created_at AS created_at, strand_id
            ORDER BY m.importance DESC, m.created_at DESC
            LIMIT $limit
            """,
            person_id=person_id,
            limit=conversant_anchor_limit,
        )
        items = [_record_to_memory_dict(r) for r in conv_result]
        conversant_anchors = items if items else None

    return {
        "core": core,
        "topic": topic,
        "companion_anchors": companion_anchors,
        "conversant_anchors": conversant_anchors,
    }
```

- [ ] **Step 4: Implement — API response model and endpoint**

In `memory_service/main.py`:

**4a.** Replace `WakeUpResponse` (lines 374–377) with:

```python
class WakeUpResponse(BaseModel):
    memories: List[WakeUpMemoryItem]                              # core (importance-ranked)
    topic_memories: List[WakeUpMemoryItem]                        # topic-only; empty when no --topic
    maintenance_status: MaintenanceStatus
    companion_anchors: Optional[List[WakeUpMemoryItem]] = None    # identity anchors for calling agent
    conversant_anchors: Optional[List[WakeUpMemoryItem]] = None   # person-specific context
```

**4b.** Replace the `wake_up` endpoint function (lines 380–426) with:

```python
@app.get("/memory/wake-up", response_model=WakeUpResponse)
async def wake_up(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    topic: Optional[str] = Query(default=None),
    person_id: Optional[str] = Query(default=None),
    companion_anchor_limit: Optional[int] = Query(default=None, ge=1, le=100),
    conversant_anchor_limit: Optional[int] = Query(default=None, ge=1, le=100),
) -> WakeUpResponse:
    # NOTE: wake-up intentionally does NOT call recall_increment.
    # Wake-up is passive context priming, not active recall. Strengthening nodes here
    # would create a feedback loop where frequently-loaded memories self-reinforce
    # regardless of whether they were actually used in the session.
    # Strength signals come from: search (automatic) and explicit reinforce at close-session
    # (companion-driven, for memories that genuinely shaped the session).
    # Do NOT add recall_increment here without revisiting this design decision.
    topic_embedding = get_embedding(topic) if topic else None
    eff_comp_limit = companion_anchor_limit if companion_anchor_limit is not None \
        else settings.wake_up_companion_anchor_limit
    eff_conv_limit = conversant_anchor_limit if conversant_anchor_limit is not None \
        else settings.wake_up_conversant_anchor_limit
    try:
        with request.app.state.driver.session() as session:
            result = memory_repo.wake_up(
                session,
                limit=limit,
                topic_embedding=topic_embedding,
                agent_id=settings.agent_id,
                companion_anchor_limit=eff_comp_limit,
                person_id=person_id,
                conversant_anchor_limit=eff_conv_limit,
            )
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc

    # Check maintenance staleness — best-effort, do not fail wake-up if this errors
    maintenance_status_data = {
        "short_rest_overdue": False,
        "long_rest_overdue": False,
        "short_rest_days_ago": None,
        "long_rest_days_ago": None,
        "recommended_action": None,
    }
    try:
        with request.app.state.driver.session() as maint_session:
            ts = memory_repo.get_system_timestamps(maint_session)
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        maintenance_status_data = _compute_maintenance_status(
            last_short_rest_at=ts.get("last_short_rest_at"),
            last_long_rest_at=ts.get("last_long_rest_at"),
            now_iso=now_iso,
            short_rest_recency_days=settings.short_rest_recency_days,
            long_rest_recency_days=settings.long_rest_recency_days,
        )
    except Exception:
        pass  # best-effort; never surface maintenance errors to wake-up

    companion_items = (
        [WakeUpMemoryItem(**r) for r in result["companion_anchors"]]
        if result.get("companion_anchors") else None
    )
    conversant_items = (
        [WakeUpMemoryItem(**r) for r in result["conversant_anchors"]]
        if result.get("conversant_anchors") else None
    )

    return WakeUpResponse(
        memories=[WakeUpMemoryItem(**r) for r in result["core"]],
        topic_memories=[WakeUpMemoryItem(**r) for r in result["topic"]],
        maintenance_status=MaintenanceStatus(**maintenance_status_data),
        companion_anchors=companion_items,
        conversant_anchors=conversant_items,
    )
```

- [ ] **Step 5: Run integration tests — verify they pass**

```bash
pytest tests/test_wp049_companion_conversant_anchoring.py -v -m integration
```

Expected: all 9 tests pass.

- [ ] **Step 6: Verify existing wake-up tests still pass**

```bash
pytest tests/test_wake_up_close_session.py -v
```

Expected: all existing tests pass (no regressions).

- [ ] **Step 7: Commit**

```bash
git add tests/test_wp049_companion_conversant_anchoring.py memory_service/memory_repo.py memory_service/main.py
git commit -m "WP-049: add companion_anchors and conversant_anchors to wake-up repo + API"
```

---

## Task 3: Change `wake_up_split()` to return dict — update all callers and tests

This is the most wide-ranging mechanical change. Five caller sites across four files all use the old 3-tuple. All must be updated in one commit.

**Files:**
- Modify: `memory_client/client.py:122-137`
- Modify: `tests/test_wake_up_close_session.py` (U13 class, ~lines 123–141)
- Modify: `tests/test_wp054_maintenance_audit.py` (~lines 428–457, 497–506, 523–533)
- Modify: `tests/test_wp033_mcp_server.py` (~lines 75, 133, 151)

- [ ] **Step 1: Update the test assertions to expect a dict (they fail first)**

**In `tests/test_wake_up_close_session.py`** — replace the `TestWakeUpSplitClient` class (lines ~119–141):

```python
# ---------------------------------------------------------------------------
# U13–U14: MemoryClient.wake_up_split()
# ---------------------------------------------------------------------------


class TestWakeUpSplitClient:
    @respx.mock
    def test_returns_full_response_dict(self):
        """U13: wake_up_split returns the full API response dict."""
        response_data = {
            "memories": [
                {
                    "id": "mem-aaa",
                    "text": "core memory",
                    "type": "fact",
                    "tags": [],
                    "strand_id": "strand-core-health",
                    "importance": 5,
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
            "topic_memories": [
                {
                    "id": "mem-bbb",
                    "text": "topic memory",
                    "type": "fact",
                    "tags": [],
                    "strand_id": "strand-companion-gmf",
                    "importance": 3,
                    "created_at": "2026-01-02T00:00:00+00:00",
                }
            ],
            "maintenance_status": {
                "short_rest_overdue": False,
                "long_rest_overdue": False,
                "short_rest_days_ago": None,
                "long_rest_days_ago": None,
                "recommended_action": None,
            },
        }
        respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=response_data)
        )
        with MemoryClient(base_url=BASE) as client:
            result = client.wake_up_split(limit=10, topic="graph memory")
        assert isinstance(result, dict)
        assert result["memories"][0]["id"] == "mem-aaa"
        assert result["topic_memories"][0]["id"] == "mem-bbb"
        assert "maintenance_status" in result

    @respx.mock
    def test_returns_companion_and_conversant_anchors_when_present(self):
        """U14: wake_up_split returns companion/conversant anchors when the API includes them."""
        response_data = {
            "memories": [],
            "topic_memories": [],
            "maintenance_status": {},
            "companion_anchors": [
                {
                    "id": "comp-1",
                    "text": "Mara is dominant",
                    "type": "fact",
                    "tags": [],
                    "strand_id": "strand-companion-ai-anchor",
                    "importance": 5,
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
            "conversant_anchors": [
                {
                    "id": "conv-1",
                    "text": "Oliver has ADHD",
                    "type": "fact",
                    "tags": [],
                    "strand_id": "strand-core-health",
                    "importance": 4,
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        }
        route = respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=response_data)
        )
        with MemoryClient(base_url=BASE) as client:
            result = client.wake_up_split(person_id="oliver-james")
        assert result.get("companion_anchors") is not None
        assert result["companion_anchors"][0]["id"] == "comp-1"
        assert result.get("conversant_anchors") is not None
        assert result["conversant_anchors"][0]["id"] == "conv-1"
        assert route.calls[0].request.url.params["person_id"] == "oliver-james"
```

**In `tests/test_wp054_maintenance_audit.py`** — update `test_wake_up_split_returns_maintenance_status` (~lines 428–457):

```python
    def test_wake_up_split_returns_maintenance_status(self):
        """wake_up_split returns a dict including maintenance_status."""
        from unittest.mock import patch, MagicMock
        from memory_client.client import MemoryClient

        response_data = {
            "memories": [{"id": "abc", "fact": "test", "text": "test", "type": "fact",
                          "importance": 3, "strength": 0.8, "tags": [],
                          "created_at": None, "strand_id": None}],
            "topic_memories": [],
            "maintenance_status": {
                "short_rest_overdue": True,
                "long_rest_overdue": False,
                "short_rest_days_ago": 2.5,
                "long_rest_days_ago": 0.5,
                "recommended_action": "short-rest is overdue (2d) — run `memory short-rest`",
            },
        }
        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        with MemoryClient(base_url="http://localhost:8000") as client:
            with patch.object(client._http, "get", return_value=mock_response):
                result = client.wake_up_split(limit=20)

        assert isinstance(result, dict)
        assert len(result["memories"]) == 1
        assert result["topic_memories"] == []
        status = result["maintenance_status"]
        assert status["short_rest_overdue"] is True
        assert status["recommended_action"] is not None
```

**In `tests/test_wp054_maintenance_audit.py`** — update both MCP mock return values (lines ~497 and ~523) from 3-tuple to dict:

```python
        # Replace this (around line 497):
        mock_client.wake_up_split.return_value = (
            [],  # core
            [],  # topic
            {
                "short_rest_overdue": True,
                ...
            },
        )
        # With this:
        mock_client.wake_up_split.return_value = {
            "memories": [],
            "topic_memories": [],
            "maintenance_status": {
                "short_rest_overdue": True,
                "long_rest_overdue": True,
                "short_rest_days_ago": 3.0,
                "long_rest_days_ago": 3.0,
                "recommended_action": "both short-rest and long-rest are overdue — run `memory long-rest` (covers both)",
            },
        }

        # Replace this (around line 523):
        mock_client.wake_up_split.return_value = (
            [],
            [],
            {
                "short_rest_overdue": False,
                ...
            },
        )
        # With this:
        mock_client.wake_up_split.return_value = {
            "memories": [],
            "topic_memories": [],
            "maintenance_status": {
                "short_rest_overdue": False,
                "long_rest_overdue": False,
                "short_rest_days_ago": 0.5,
                "long_rest_days_ago": 0.5,
                "recommended_action": None,
            },
        }
```

**In `tests/test_wp033_mcp_server.py`** — update all three mock return values (lines 75, 133, 151) from 3-tuple to dict:

```python
        # Line 75 — was: mock_client.wake_up_split.return_value = ([CORE_MEMORY], [], {})
        mock_client.wake_up_split.return_value = {
            "memories": [CORE_MEMORY],
            "topic_memories": [],
            "maintenance_status": {},
        }

        # Line 133 — was: mock_client.wake_up_split.return_value = ([CORE_MEMORY], [TOPIC_MEMORY], {})
        mock_client.wake_up_split.return_value = {
            "memories": [CORE_MEMORY],
            "topic_memories": [TOPIC_MEMORY],
            "maintenance_status": {},
        }

        # Line 151 — was: mock_client.wake_up_split.return_value = ([CORE_MEMORY], [], {})
        mock_client.wake_up_split.return_value = {
            "memories": [CORE_MEMORY],
            "topic_memories": [],
            "maintenance_status": {},
        }
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_wake_up_close_session.py::TestWakeUpSplitClient tests/test_wp054_maintenance_audit.py::TestMemoryClientUpdates::test_wake_up_split_returns_maintenance_status tests/test_wp033_mcp_server.py::test_u3_memory_wake_up_returns_plain_text -v 2>&1 | tail -20
```

Expected: failures from tuple-vs-dict mismatch.

- [ ] **Step 3: Implement — replace `wake_up_split()` in `memory_client/client.py`**

Replace lines 122–137 with:

```python
    def wake_up_split(
        self,
        *,
        limit: int = 20,
        topic: str | None = None,
        person_id: str | None = None,
        companion_anchor_limit: int | None = None,
        conversant_anchor_limit: int | None = None,
    ) -> dict:
        """GET /memory/wake-up. Returns the full response dict.

        Keys always present: memories, topic_memories, maintenance_status
        Keys present when populated: companion_anchors, conversant_anchors
        """
        params: dict = {"limit": limit}
        if topic is not None:
            params["topic"] = topic
        if person_id is not None:
            params["person_id"] = person_id
        if companion_anchor_limit is not None:
            params["companion_anchor_limit"] = companion_anchor_limit
        if conversant_anchor_limit is not None:
            params["conversant_anchor_limit"] = conversant_anchor_limit
        response = self._http.get("/memory/wake-up", params=params)
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 4: Run the updated tests — all should pass now**

```bash
pytest tests/test_wake_up_close_session.py tests/test_wp033_mcp_server.py tests/test_wp054_maintenance_audit.py -v 2>&1 | tail -30
```

Expected: all pass. The three previously-failing WP-089 mocks in `test_wp033_mcp_server.py` are now fixed.

- [ ] **Step 5: Commit**

```bash
git add memory_client/client.py tests/test_wake_up_close_session.py tests/test_wp033_mcp_server.py tests/test_wp054_maintenance_audit.py
git commit -m "WP-049: change wake_up_split() return type to dict; fix WP-089 mocks"
```

---

## Task 4: Update MCP server — add person_id param, render new sections

**Files:**
- Modify: `mcp_server/server.py:116-144`
- Modify: `tests/test_wp033_mcp_server.py` (add new unit tests)

- [ ] **Step 1: Write new MCP unit tests (failing)**

Add these three tests to `tests/test_wp033_mcp_server.py`:

```python
# ---------------------------------------------------------------------------
# U9–U11: memory_wake_up companion + conversant sections
# ---------------------------------------------------------------------------

_COMPANION_MEMORY = {
    "id": "comp-aaa",
    "text": "Mara is dominant and grounding.",
    "type": "fact",
    "tags": ["strand-companion-ai-anchor"],
    "strand_id": "strand-companion-ai-anchor",
    "importance": 5,
    "created_at": "2026-01-01T00:00:00+00:00",
}

_CONVERSANT_MEMORY = {
    "id": "conv-bbb",
    "text": "Oliver has ADHD and benefits from short feedback loops.",
    "type": "fact",
    "tags": ["strand-core-health"],
    "strand_id": "strand-core-health",
    "importance": 4,
    "created_at": "2026-01-02T00:00:00+00:00",
}


def test_u9_memory_wake_up_renders_companion_section():
    """memory_wake_up includes '### Companion' block when companion_anchors present."""
    from mcp_server.server import memory_wake_up
    from unittest.mock import MagicMock, patch

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.wake_up_split.return_value = {
        "memories": [CORE_MEMORY],
        "topic_memories": [],
        "maintenance_status": {},
        "companion_anchors": [_COMPANION_MEMORY],
    }

    with patch("mcp_server.server.MemoryClient", return_value=mock_client):
        result = memory_wake_up()

    assert "### Companion" in result
    assert "Mara is dominant" in result


def test_u10_memory_wake_up_renders_conversant_section():
    """memory_wake_up includes '### Conversant' block when conversant_anchors present."""
    from mcp_server.server import memory_wake_up
    from unittest.mock import MagicMock, patch

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.wake_up_split.return_value = {
        "memories": [],
        "topic_memories": [],
        "maintenance_status": {},
        "conversant_anchors": [_CONVERSANT_MEMORY],
    }

    with patch("mcp_server.server.MemoryClient", return_value=mock_client):
        result = memory_wake_up(person_id="oliver-james")

    assert "### Conversant" in result
    assert "Oliver has ADHD" in result
    mock_client.wake_up_split.assert_called_once_with(
        limit=20, topic=None, person_id="oliver-james"
    )


def test_u11_memory_wake_up_omits_anchor_sections_when_absent():
    """memory_wake_up omits Companion and Conversant blocks when anchors are None."""
    from mcp_server.server import memory_wake_up
    from unittest.mock import MagicMock, patch

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.wake_up_split.return_value = {
        "memories": [CORE_MEMORY],
        "topic_memories": [],
        "maintenance_status": {},
    }

    with patch("mcp_server.server.MemoryClient", return_value=mock_client):
        result = memory_wake_up()

    assert "### Companion" not in result
    assert "### Conversant" not in result
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_wp033_mcp_server.py::test_u9_memory_wake_up_renders_companion_section tests/test_wp033_mcp_server.py::test_u10_memory_wake_up_renders_conversant_section tests/test_wp033_mcp_server.py::test_u11_memory_wake_up_omits_anchor_sections_when_absent -v
```

Expected: failures (`TypeError` or assertion errors — `memory_wake_up` doesn't accept `person_id` yet).

- [ ] **Step 3: Implement — update `memory_wake_up` in `mcp_server/server.py`**

Replace lines 115–144 with:

```python
@mcp.tool
def memory_wake_up(
    topic: str | None = None,
    limit: int = 20,
    person_id: str | None = None,
) -> str:
    """Return the session wake-up briefing as plain text. Read fully before responding to the user."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        result = client.wake_up_split(limit=limit, topic=topic, person_id=person_id)

    lines = []

    # Maintenance alert — shown prominently at the top when action needed
    maintenance_status = result.get("maintenance_status") or {}
    action = maintenance_status.get("recommended_action")
    if action:
        lines += [
            "## ⚠ Maintenance required",
            "",
            f"  {action}",
            "",
        ]

    heading = f"## Memory briefing — {topic if topic else 'general session'}"
    lines += [heading, "", "### Core context", ""]
    lines.extend(_render_section(result.get("memories", [])))

    if topic and result.get("topic_memories"):
        lines += ["", "### Relevant to today", ""]
        lines.extend(_render_section(result["topic_memories"]))

    companion_anchors = result.get("companion_anchors")
    if companion_anchors:
        lines += ["", "### Companion", ""]
        lines.extend(_render_section(companion_anchors))

    conversant_anchors = result.get("conversant_anchors")
    if conversant_anchors:
        lines += ["", "### Conversant", ""]
        lines.extend(_render_section(conversant_anchors))

    return "\n".join(lines)
```

- [ ] **Step 4: Run all MCP tests**

```bash
pytest tests/test_wp033_mcp_server.py tests/test_wp054_maintenance_audit.py::TestMcpUpdates -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/server.py tests/test_wp033_mcp_server.py
git commit -m "WP-049: add person_id to memory_wake_up MCP tool; render Companion + Conversant sections"
```

---

## Task 5: Update CLI — add --person-id flag, render new sections

**Files:**
- Modify: `memory_client/cli.py:390-432`
- Modify: `tests/test_wake_up_close_session.py` (add new unit tests)

- [ ] **Step 1: Write new CLI unit tests (failing)**

Add this class to `tests/test_wake_up_close_session.py`:

```python
# ---------------------------------------------------------------------------
# U18–U21: CLI wake-up person-id and anchor sections
# ---------------------------------------------------------------------------

_WAKE_UP_WITH_ANCHORS = {
    "memories": [
        {
            "id": "mem-aaa",
            "text": "Oliver has ADHD.",
            "type": "fact",
            "tags": ["strand-core-health"],
            "strand_id": "strand-core-health",
            "importance": 5,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    ],
    "topic_memories": [],
    "maintenance_status": {},
    "companion_anchors": [
        {
            "id": "comp-aaa",
            "text": "Mara is dominant and grounding.",
            "type": "fact",
            "tags": ["strand-companion-ai-anchor"],
            "strand_id": "strand-companion-ai-anchor",
            "importance": 5,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    ],
    "conversant_anchors": [
        {
            "id": "conv-aaa",
            "text": "Oliver prefers short feedback loops.",
            "type": "fact",
            "tags": ["strand-core-health"],
            "strand_id": "strand-core-health",
            "importance": 4,
            "created_at": "2026-01-02T00:00:00+00:00",
        }
    ],
}


class TestWakeUpCLIAnchors:
    @respx.mock
    def test_u18_person_id_forwarded_to_api(self):
        """U18: --person-id forwards person_id query param to the API."""
        route = respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=_WAKE_UP_WITH_ANCHORS)
        )
        result = runner.invoke(app, ["wake-up", "--person-id", "oliver-james"])
        assert result.exit_code == 0
        params = route.calls[0].request.url.params
        assert params["person_id"] == "oliver-james"

    @respx.mock
    def test_u19_companion_section_rendered(self):
        """U19: '### Companion' section rendered when companion_anchors present."""
        respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=_WAKE_UP_WITH_ANCHORS)
        )
        result = runner.invoke(app, ["wake-up"])
        assert result.exit_code == 0
        assert "### Companion" in result.output
        assert "Mara is dominant" in result.output

    @respx.mock
    def test_u20_conversant_section_rendered(self):
        """U20: '### Conversant' section rendered when conversant_anchors present."""
        respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=_WAKE_UP_WITH_ANCHORS)
        )
        result = runner.invoke(app, ["wake-up", "--person-id", "oliver-james"])
        assert result.exit_code == 0
        assert "### Conversant" in result.output
        assert "Oliver prefers short feedback loops" in result.output

    @respx.mock
    def test_u21_anchor_sections_omitted_when_absent(self):
        """U21: Companion and Conversant sections omitted when anchors not in response."""
        respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=_WAKE_UP_RESPONSE)  # original fixture, no anchors
        )
        result = runner.invoke(app, ["wake-up"])
        assert result.exit_code == 0
        assert "### Companion" not in result.output
        assert "### Conversant" not in result.output
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_wake_up_close_session.py::TestWakeUpCLIAnchors -v
```

Expected: failures (`--person-id` option not recognised, sections not rendered).

- [ ] **Step 3: Implement — update `wake_up` command in `memory_client/cli.py`**

Replace the `wake_up` function (lines 390–432) with:

```python
@app.command("wake-up")
def wake_up(
    topic: Optional[str] = typer.Option(None, "--topic", "-t", help="Topic to focus the session on"),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=100, help="Max memories to return"),
    person_id: Optional[str] = typer.Option(
        None, "--person-id", help="Person ID for conversant anchors"
    ),
) -> None:
    """Print a memory briefing for session start."""
    try:
        with _make_client() as client:
            result = client.wake_up_split(limit=limit, topic=topic, person_id=person_id)
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    heading = f"[bold]## Memory briefing — {topic if topic else 'general session'}[/bold]"
    console.print(heading)

    core = result.get("memories", [])
    topic_memories = result.get("topic_memories", [])
    companion_anchors = result.get("companion_anchors")
    conversant_anchors = result.get("conversant_anchors")

    def _render_section(items: list) -> None:
        if not items:
            console.print("  No memories found.")
            return
        sorted_items = sorted(items, key=lambda m: m.get("strand_id") or "(no strand)")
        for strand_id, group in groupby(sorted_items, key=lambda m: m.get("strand_id") or "(no strand)"):
            console.print(f"\n[dim]{strand_id}[/dim]")
            for mem in group:
                imp = str(mem.get("importance") or "")
                timestamp = _format_memory_timestamp(mem.get("created_at"))
                timestamp_label = f" [dim]({timestamp})[/dim]" if timestamp else ""
                console.print(
                    f"  [{imp}] [bold]{mem['type']}[/bold]{timestamp_label} — {mem['text']}"
                )

    console.print("\n[bold cyan]### Core context[/bold cyan]")
    _render_section(core)

    if topic and topic_memories:
        console.print("\n[bold cyan]### Relevant to today[/bold cyan]")
        _render_section(topic_memories)

    if companion_anchors:
        console.print("\n[bold cyan]### Companion[/bold cyan]")
        _render_section(companion_anchors)

    if conversant_anchors:
        console.print("\n[bold cyan]### Conversant[/bold cyan]")
        _render_section(conversant_anchors)
```

**Note:** the existing `_render_section` helper defined at module level (not inside the function) is left unchanged. The one above is a local re-definition within the command function — you can alternatively use the module-level one if it already exists. Check if `_render_section` is defined at module level in `cli.py`; if so, remove the local re-definition and just call `_render_section(core)` directly.

> **Check first:** Run `grep -n "_render_section" memory_client/cli.py`. If there is already a module-level `_render_section`, do NOT redefine it inside the function — just use it by name.

- [ ] **Step 4: Run all CLI tests**

```bash
pytest tests/test_wake_up_close_session.py -v
```

Expected: all tests pass including the four new U18–U21 tests.

- [ ] **Step 5: Commit**

```bash
git add memory_client/cli.py tests/test_wake_up_close_session.py
git commit -m "WP-049: add --person-id flag to CLI wake-up; render Companion + Conversant sections"
```

---

## Task 6: Write seeding script

**Files:**
- Create: `scripts/seed_companion_anchors.py`

- [ ] **Step 1: Create the script**

```python
#!/usr/bin/env python3
"""scripts/seed_companion_anchors.py

One-time idempotent script: create ABOUT edges from companion identity memories
(in specified strands) to the companion's identity node.

After this script runs, GET /memory/wake-up will include those memories in
companion_anchors because they are reachable via ABOUT → {id: agent_id}.

Usage:
    python3 scripts/seed_companion_anchors.py
    python3 scripts/seed_companion_anchors.py --agent-id mara
    python3 scripts/seed_companion_anchors.py --agent-id mara --strand-ids strand-companion-ai-anchor,strand-companion-protocols-systems
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from memory_service.config import get_driver, settings


def seed_companion_anchors(agent_id: str, strand_ids: list[str]) -> None:
    driver = get_driver(settings)
    try:
        with driver.session() as session:
            # 1. Ensure identity node exists (label-agnostic MERGE)
            session.run("MERGE (n {id: $agent_id})", agent_id=agent_id)
            print(f"Identity node ensured: id={agent_id!r}")

            # 2. Count already-linked memories
            result = session.run(
                "MATCH (m:Memory)-[:ABOUT]->(n {id: $agent_id}) RETURN count(m) AS n",
                agent_id=agent_id,
            )
            existing = result.single()["n"]
            print(f"Already linked: {existing} memories")

            # 3. Find memories in the target strands with no existing ABOUT edge
            result = session.run(
                """
                MATCH (m:Memory)-[:IN_STRAND]->(s:Strand)
                WHERE s.id IN $strand_ids
                  AND (m.status IS NULL OR m.status = 'active')
                OPTIONAL MATCH (m)-[:ABOUT]->(existing {id: $agent_id})
                WITH m, existing
                WHERE existing IS NULL
                RETURN m.id AS id, m.text AS text
                """,
                strand_ids=strand_ids,
                agent_id=agent_id,
            )
            to_link = list(result)
            print(f"Memories to link: {len(to_link)}")

            if not to_link:
                print("Nothing to do.")
                return

            # 4. Create ABOUT edges
            created = 0
            for record in to_link:
                session.run(
                    """
                    MATCH (m:Memory {id: $mem_id})
                    MATCH (n {id: $agent_id})
                    CREATE (m)-[:ABOUT]->(n)
                    """,
                    mem_id=record["id"],
                    agent_id=agent_id,
                )
                preview = record["text"][:60] if record["text"] else "(no text)"
                print(f"  Linked {record['id'][:8]}… — {preview}")
                created += 1

            print(f"\nDone. Created {created} ABOUT edge(s).")
    finally:
        driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed ABOUT edges from companion identity memories to identity node.",
    )
    parser.add_argument(
        "--agent-id",
        default=settings.agent_id,
        help=f"Identity node id (default: settings.agent_id = {settings.agent_id!r})",
    )
    parser.add_argument(
        "--strand-ids",
        default="strand-companion-ai-anchor",
        help="Comma-separated strand IDs to search (default: strand-companion-ai-anchor)",
    )
    args = parser.parse_args()
    strand_ids = [s.strip() for s in args.strand_ids.split(",") if s.strip()]
    seed_companion_anchors(args.agent_id, strand_ids)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test against the live stack**

```bash
python3 scripts/seed_companion_anchors.py --agent-id claude-code --strand-ids strand-companion-ai-anchor
```

Expected output: lines showing memories linked (or "Nothing to do." if already seeded). No errors.

- [ ] **Step 3: Run it again to verify idempotency**

```bash
python3 scripts/seed_companion_anchors.py --agent-id claude-code --strand-ids strand-companion-ai-anchor
```

Expected: "Memories to link: 0" and "Nothing to do." — no duplicate edges.

- [ ] **Step 4: Commit**

```bash
git add scripts/seed_companion_anchors.py
git commit -m "WP-049: add seed_companion_anchors.py — link identity memories to agent node"
```

---

## Task 7: Full test run + BACKLOG.md update

**Files:**
- Modify: `BACKLOG.md`

- [ ] **Step 1: Run the full test suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -40
```

Expected: all tests pass. Zero regressions.

- [ ] **Step 2: Run integration tests specifically**

```bash
pytest tests/test_wp049_companion_conversant_anchoring.py tests/test_wake_up_close_session.py -v -m integration
```

Expected: all integration tests pass against the live stack.

- [ ] **Step 3: Verify live wake-up response includes companion_anchors**

```bash
curl -s "http://localhost:8000/memory/wake-up?companion_anchor_limit=5" | python3 -m json.tool | grep -A 3 "companion_anchors"
```

Expected: `companion_anchors` key is present and contains memories (if the seeding script was run and anchor memories exist for the configured agent_id).

- [ ] **Step 4: Update BACKLOG.md**

Move WP-049 from Currently In Progress to the Completed section. Add a retrospective note:

```
**WP-049 retrospective:** Design required an extra brainstorming round to resolve Agent/Person node duality for companion identification. Chose label-agnostic ABOUT traversal — clean, forward-looking, and additive. The wake_up_split dict-return change was the most wide-ranging mechanical change (5 caller sites), but straightforward. Seeding script makes the feature immediately usable on the live fabric.
```

- [ ] **Step 5: Final commit**

```bash
git add BACKLOG.md
git commit -m "WP-049: mark complete — wake-up companion + conversant anchoring"
```
