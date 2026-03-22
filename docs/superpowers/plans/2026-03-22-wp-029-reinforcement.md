# WP-029: Memory + Edge Reinforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Ebbinghaus decay + Hebbian activation to the memory graph so frequently-recalled memories surface higher in search and unused edges fade into dormancy.

**Architecture:** Node `strength` (0–1) is seeded from `importance / 5.0` at creation and incremented on each recall/reinforcement (capped at 1.0). A periodic decay pass rewrites stored `strength` using the Ebbinghaus curve. Search automatically increments `recall_count` + `strength` on result nodes in a non-blocking background task. Edges on `RELATED_TO` and `LEADS_TO` gain `activation_count` / `weight` / `decay_rate` / `last_activated_at`. Explicit reinforcement via `POST /memory/{id}/reinforce` bumps strength + co-edge weights (Hebbian step). `POST /memory/maintenance/decay` runs the decay pass.

> **Deferral note (approved):** The spec calls for `effective_strength` (inline Cypher decay formula) as a search sort key. For v1 this is deferred — stored `strength` after a decay pass achieves the same practical effect. A follow-up (track as backlog item) can add inline decay to the search query when search performance tuning is needed. The `min_strength` filter (default 0.0 = off) is implemented in the search template so it is wired but inactive by default.

**Tech Stack:** FastAPI (BackgroundTasks for non-blocking recall), neo4j Bolt driver, pydantic-settings, pytest, respx/httpx for unit mocks, typer, Rich.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `memory_service/config.py` | Modify | Add 8 reinforcement settings |
| `.env.example` | Modify | Document new env vars |
| `memory_service/memory_repo.py` | Modify | `add_memory` seeds strength; new `recall_increment`, `reinforce_memory`, `decay_pass`, `list_weak_edges` functions |
| `memory_service/main.py` | Modify | Maintenance endpoints registered BEFORE `/{memory_id}/reinforce`; new models + endpoints; BackgroundTasks in search |
| `memory_client/client.py` | Modify | `reinforce_memory()`, `run_decay()`, `get_weak_edges()` |
| `memory_client/cli.py` | Modify | `reinforce-memory`, `run-decay` commands |
| `mcp_server/server.py` | Modify | `memory_reinforce`, `memory_run_decay` tools |
| `scripts/migrate_reinforcement_defaults.py` | Create | Backfill reinforcement defaults on existing nodes/edges |
| `tests/test_wp029_reinforcement.py` | Create | All tests for this WP |

---

## Task 1: Config — add reinforcement settings

**Files:**
- Modify: `memory_service/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add 8 new fields to `Settings` in `memory_service/config.py`**

Add these after `agent_id`, before `model_config`:

```python
memory_decay_rate: float = 0.01
edge_decay_rate: float = 0.005
recall_strength_increment: float = 0.05
explicit_strength_increment: float = 0.20
edge_recall_increment: float = 0.02
edge_explicit_increment: float = 0.10
edge_prune_threshold: float = 0.05
min_memory_strength: float = 0.0
```

- [ ] **Step 2: Add env vars to `.env.example`**

```
# Reinforcement / decay (WP-029)
MEMORY_DECAY_RATE=0.01
EDGE_DECAY_RATE=0.005
RECALL_STRENGTH_INCREMENT=0.05
EXPLICIT_STRENGTH_INCREMENT=0.20
EDGE_RECALL_INCREMENT=0.02
EDGE_EXPLICIT_INCREMENT=0.10
EDGE_PRUNE_THRESHOLD=0.05
MIN_MEMORY_STRENGTH=0.0
```

- [ ] **Step 3: Write unit test — settings load with defaults**

Create `tests/test_wp029_reinforcement.py`:

```python
import uuid
import pytest


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
```

- [ ] **Step 4: Run test**

```bash
pytest tests/test_wp029_reinforcement.py::TestReinforcementSettings -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memory_service/config.py .env.example tests/test_wp029_reinforcement.py
git commit -m "feat(WP-029): reinforcement config settings + defaults"
```

---

## Task 2: Memory creation — seed strength from importance

**Files:**
- Modify: `memory_service/memory_repo.py` (CREATE block in `add_memory`)
- Modify: `memory_service/main.py` (pass `decay_rate` to repo)

- [ ] **Step 1: Update `add_memory` signature in `memory_repo.py`**

```python
def add_memory(session, req, memory_id: str, embedding: list, now: str, decay_rate: float) -> None:
```

- [ ] **Step 2: Add new properties to the CREATE block**

In the `CREATE (m:Memory {...})` Cypher, add:
```cypher
strength: $strength,
recall_count: 0,
reinforcement_count: 0,
last_reinforced_at: $now,
decay_rate: $decay_rate
```

Add to the Python parameter dict:
```python
strength=req.importance / 5.0,
decay_rate=decay_rate,
```

(`now` already passes as `created_at` and `last_used_at` — reuse it for `last_reinforced_at`.)

- [ ] **Step 3: Thread `decay_rate` from the endpoint in `main.py`**

In the `add_memory` endpoint:
```python
memory_repo.add_memory(session, req, memory_id, embedding, now, settings.memory_decay_rate)
```

- [ ] **Step 4: Write integration tests — new memory has reinforcement properties**

```python
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
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_wp029_reinforcement.py::TestMemoryCreationSeeding -v
```

Expected: PASS (requires live stack)

- [ ] **Step 6: Commit**

```bash
git add memory_service/memory_repo.py memory_service/main.py tests/test_wp029_reinforcement.py
git commit -m "feat(WP-029): seed strength/recall_count/reinforcement_count on memory creation"
```

---

## Task 3: Search — background recall increment (non-blocking)

**Files:**
- Modify: `memory_service/memory_repo.py` — add `recall_increment()` and `from datetime import datetime, timezone` at top
- Modify: `memory_service/main.py` — import `BackgroundTasks`, add `_do_recall_increment`, update `search_memory` endpoint

**Design notes:**
- `BackgroundTasks` injected into `search_memory` endpoint — FastAPI handles DI automatically; TestClient runs background tasks synchronously before returning.
- Edge activation covers both `RELATED_TO` and `LEADS_TO` (the spec requires both).
- `last_reinforced_at` is NOT updated on recall — only explicit reinforcement updates the decay anchor.

- [ ] **Step 1: Add `from datetime import datetime, timezone` to top of `memory_repo.py`**

(Needed for `recall_increment`'s edge timestamp.)

- [ ] **Step 2: Add `recall_increment` function to `memory_repo.py`**

```python
def recall_increment(
    session,
    memory_ids: list[str],
    strength_increment: float,
    edge_increment: float,
) -> None:
    """Increment recall_count and strength on recalled memories; activate traversed edges.

    Called in a background task after search — does not block the response.
    Strength is capped at 1.0. last_reinforced_at is NOT updated (recall != explicit reinforcement).
    Edge activation covers RELATED_TO and LEADS_TO edges between members of the result set.
    """
    if not memory_ids:
        return

    now = datetime.now(timezone.utc).isoformat()

    # Node increment
    session.run(
        """
        UNWIND $ids AS mid
        MATCH (m:Memory {id: mid})
        SET m.recall_count = coalesce(m.recall_count, 0) + 1,
            m.strength = CASE
                WHEN coalesce(m.strength, m.importance / 5.0) + $increment >= 1.0
                THEN 1.0
                ELSE coalesce(m.strength, m.importance / 5.0) + $increment
            END
        """,
        ids=memory_ids,
        increment=strength_increment,
    )

    # Edge activation — RELATED_TO and LEADS_TO edges within the result set
    if len(memory_ids) > 1:
        session.run(
            """
            UNWIND $ids AS src
            UNWIND $ids AS tgt
            WITH src, tgt
            WHERE src <> tgt
            OPTIONAL MATCH (a:Memory {id: src})-[r:RELATED_TO|LEADS_TO]->(b:Memory {id: tgt})
            WITH r, $edge_increment AS inc, $now AS ts
            WHERE r IS NOT NULL
            SET r.activation_count = coalesce(r.activation_count, 0) + 1,
                r.last_activated_at = ts,
                r.weight = CASE
                    WHEN coalesce(r.weight, 0.5) + inc >= 1.0 THEN 1.0
                    ELSE coalesce(r.weight, 0.5) + inc
                END
            """,
            ids=memory_ids,
            edge_increment=edge_increment,
            now=now,
        )
```

- [ ] **Step 3: Update `search_memory` endpoint in `main.py`**

Add `BackgroundTasks` to import:
```python
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
```

Add helper function (not a route):
```python
def _do_recall_increment(driver, memory_ids: list[str]) -> None:
    """Background task: fire recall increment for searched memories."""
    try:
        with driver.session() as session:
            memory_repo.recall_increment(
                session,
                memory_ids,
                strength_increment=settings.recall_strength_increment,
                edge_increment=settings.edge_recall_increment,
            )
    except Exception:
        pass  # best-effort; do not surface errors to the search response
```

Update endpoint:
```python
@app.post("/memory/search", response_model=SearchMemoryResponse)
async def search_memory(
    req: SearchMemoryRequest, request: Request, background_tasks: BackgroundTasks
) -> SearchMemoryResponse:
    query_embedding = get_embedding(req.query)
    try:
        with request.app.state.driver.session() as session:
            results = memory_repo.search_memories(session, req, query_embedding)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc

    memory_ids = [r["id"] for r in results]
    if memory_ids:
        background_tasks.add_task(_do_recall_increment, request.app.state.driver, memory_ids)

    return SearchMemoryResponse(
        memories=[
            MemoryHit(
                id=r["id"],
                text=r["text"],
                type=r["type"],
                tags=r["tags"],
                importance=r["importance"],
                neighbours=r["neighbours"],
            )
            for r in results
        ]
    )
```

- [ ] **Step 4: Write integration tests — round-trip recall increment**

```python
from memory_service import memory_repo

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
```

- [ ] **Step 5: Run tests (including existing search tests to verify BackgroundTasks wiring didn't break anything)**

```bash
pytest tests/test_wp029_reinforcement.py::TestRecallIncrement tests/test_search_memory.py -v
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add memory_service/memory_repo.py memory_service/main.py tests/test_wp029_reinforcement.py
git commit -m "feat(WP-029): background recall increment on search results"
```

---

## Task 4: Maintenance endpoints — decay pass + weak edges

**Files:**
- Modify: `memory_service/memory_repo.py` — add `decay_pass()` and `list_weak_edges()`
- Modify: `memory_service/main.py` — add `DecayPassResponse`, `WeakEdgeItem`, `WeakEdgesResponse` models; two maintenance endpoints registered BEFORE `/{memory_id}/reinforce`

**Critical route ordering:** FastAPI matches routes in registration order. `POST /memory/maintenance/decay` MUST be registered before `POST /memory/{memory_id}/reinforce` or the static segment `maintenance` will be captured as the `{memory_id}` path parameter, returning 422 instead of hitting the decay endpoint.

**`localDateTime()` and UTC offsets:** Memgraph's `localDateTime()` does not accept `+00:00` offset strings. All datetime strings passed to `duration.between(localDateTime(...), ...)` must be naive (no timezone suffix). Use:
```python
now_naive = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
```
Use `now_naive` for `duration.between` comparisons. Use the full ISO string for storage fields where no Cypher date arithmetic is applied.

- [ ] **Step 1: Add `decay_pass` and `list_weak_edges` to `memory_repo.py`**

```python
def decay_pass(session, now_naive: str, now_iso: str) -> dict:
    """Recompute and write strength for all Memory nodes and weight for all edges.

    Formula: new_value = current_value * exp(-decay_rate * days_since_anchor)
    Anchors: Memory.last_reinforced_at, edge.last_activated_at.
    After writing, resets anchors to now_iso so future inline calcs stay numerically stable.

    Args:
        now_naive: naive datetime string for localDateTime() comparison, e.g. "2026-03-22T10:30:00"
        now_iso: full ISO string for storage, e.g. "2026-03-22T10:30:00+00:00"

    Returns dict with keys: nodes_updated, edges_updated (int counts).
    """
    node_result = session.run(
        """
        MATCH (m:Memory)
        WHERE m.strength IS NOT NULL AND m.last_reinforced_at IS NOT NULL AND m.decay_rate IS NOT NULL
        WITH m,
             duration.between(localDateTime(m.last_reinforced_at), localDateTime($now_naive)).days AS days
        SET m.strength = CASE
                WHEN m.strength * exp(-m.decay_rate * toFloat(days)) < 0.0 THEN 0.0
                ELSE m.strength * exp(-m.decay_rate * toFloat(days))
            END,
            m.last_reinforced_at = $now_iso
        RETURN count(m) AS n
        """,
        now_naive=now_naive,
        now_iso=now_iso,
    )
    nodes_updated = node_result.single()["n"]

    edge_result = session.run(
        """
        MATCH ()-[r:RELATED_TO|LEADS_TO]->()
        WHERE r.weight IS NOT NULL AND r.last_activated_at IS NOT NULL AND r.decay_rate IS NOT NULL
        WITH r,
             duration.between(localDateTime(r.last_activated_at), localDateTime($now_naive)).days AS days
        SET r.weight = CASE
                WHEN r.weight * exp(-r.decay_rate * toFloat(days)) < 0.0 THEN 0.0
                ELSE r.weight * exp(-r.decay_rate * toFloat(days))
            END,
            r.last_activated_at = $now_iso
        RETURN count(r) AS n
        """,
        now_naive=now_naive,
        now_iso=now_iso,
    )
    edges_updated = edge_result.single()["n"]

    return {"nodes_updated": nodes_updated, "edges_updated": edges_updated}


def list_weak_edges(session, threshold: float) -> list[dict]:
    """Return edges whose stored weight is below threshold (up to 200 results).

    Run a decay pass first for accurate results.
    """
    result = session.run(
        """
        MATCH (src:Memory)-[r:RELATED_TO|LEADS_TO]->(tgt:Memory)
        WHERE r.weight IS NOT NULL AND r.weight < $threshold
        RETURN src.id AS source_id, tgt.id AS target_id,
               type(r) AS relation, r.weight AS weight,
               r.activation_count AS activation_count
        ORDER BY r.weight ASC
        LIMIT 200
        """,
        threshold=threshold,
    )
    return [
        {
            "source_id": row["source_id"],
            "target_id": row["target_id"],
            "relation": row["relation"],
            "weight": row["weight"],
            "activation_count": row["activation_count"],
        }
        for row in result
    ]
```

- [ ] **Step 2: Add models and maintenance endpoints in `main.py` — BEFORE `/{memory_id}/reinforce`**

Add models:
```python
class DecayPassResponse(BaseModel):
    nodes_updated: int
    edges_updated: int


class WeakEdgeItem(BaseModel):
    source_id: str
    target_id: str
    relation: str
    weight: float
    activation_count: Optional[int] = None


class WeakEdgesResponse(BaseModel):
    edges: List[WeakEdgeItem]
```

Add endpoints — place these in the file **before** the `POST /memory/{memory_id}/reinforce` endpoint:
```python
@app.post("/memory/maintenance/decay", response_model=DecayPassResponse)
async def run_decay_pass(request: Request) -> DecayPassResponse:
    now_naive = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            result = memory_repo.decay_pass(session, now_naive, now_iso)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return DecayPassResponse(**result)


@app.get("/memory/maintenance/weak-edges", response_model=WeakEdgesResponse)
async def get_weak_edges(request: Request) -> WeakEdgesResponse:
    try:
        with request.app.state.driver.session() as session:
            edges = memory_repo.list_weak_edges(session, settings.edge_prune_threshold)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return WeakEdgesResponse(edges=[WeakEdgeItem(**e) for e in edges])
```

- [ ] **Step 3: Write integration tests**

```python
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_wp029_reinforcement.py::TestMaintenanceEndpoints -v
```

Expected: PASS. If `decay_pass` raises a Memgraph error about `localDateTime()`, the naive string format `"%Y-%m-%dT%H:%M:%S"` needs to match exactly what Memgraph accepts — try `"%Y-%m-%dT%H:%M:%S"` first; if that fails, try `"%Y-%m-%d %H:%M:%S"`.

- [ ] **Step 5: Commit**

```bash
git add memory_service/memory_repo.py memory_service/main.py tests/test_wp029_reinforcement.py
git commit -m "feat(WP-029): decay pass + weak-edges maintenance endpoints"
```

---

## Task 5: Explicit reinforcement endpoint

**Files:**
- Modify: `memory_service/memory_repo.py` — add `reinforce_memory()`
- Modify: `memory_service/main.py` — add `ReinforceRequest`, `ReinforceResponse`, `POST /memory/{memory_id}/reinforce` endpoint (AFTER the maintenance endpoints)

- [ ] **Step 1: Add `reinforce_memory` to `memory_repo.py`**

```python
def reinforce_memory(
    session,
    memory_id: str,
    strength_increment: float,
    edge_increment: float,
    co_recalled_ids: list[str],
    now_iso: str,
) -> float:
    """Explicitly reinforce a memory node and its co-recalled edges.

    Updates last_reinforced_at (unlike recall_increment, which does not).
    Returns the new stored strength value (float).
    """
    result = session.run(
        """
        MATCH (m:Memory {id: $id})
        SET m.reinforcement_count = coalesce(m.reinforcement_count, 0) + 1,
            m.last_reinforced_at = $now,
            m.strength = CASE
                WHEN coalesce(m.strength, m.importance / 5.0) + $increment >= 1.0
                THEN 1.0
                ELSE coalesce(m.strength, m.importance / 5.0) + $increment
            END
        RETURN m.strength AS strength
        """,
        id=memory_id,
        increment=strength_increment,
        now=now_iso,
    )
    row = result.single()
    if row is None:
        raise ValueError(f"Memory not found: {memory_id}")
    new_strength = row["strength"]

    # Hebbian step — bump edges between this memory and co-recalled memories
    if co_recalled_ids:
        all_ids = [memory_id] + co_recalled_ids
        session.run(
            """
            UNWIND $all_ids AS src
            UNWIND $all_ids AS tgt
            WITH src, tgt
            WHERE src <> tgt
            OPTIONAL MATCH (a:Memory {id: src})-[r:RELATED_TO|LEADS_TO]->(b:Memory {id: tgt})
            WITH r, $edge_increment AS inc, $now AS ts
            WHERE r IS NOT NULL
            SET r.activation_count = coalesce(r.activation_count, 0) + 1,
                r.last_activated_at = ts,
                r.weight = CASE
                    WHEN coalesce(r.weight, 0.5) + inc >= 1.0 THEN 1.0
                    ELSE coalesce(r.weight, 0.5) + inc
                END
            """,
            all_ids=all_ids,
            edge_increment=edge_increment,
            now=now_iso,
        )

    return new_strength
```

- [ ] **Step 2: Add models and endpoint to `main.py` — AFTER the maintenance endpoints**

```python
class ReinforceRequest(BaseModel):
    signal: Literal["explicit"] = "explicit"
    co_recalled_ids: List[str] = []


class ReinforceResponse(BaseModel):
    memory_id: str
    new_strength: float


@app.post("/memory/{memory_id}/reinforce", response_model=ReinforceResponse)
async def reinforce_memory(
    memory_id: str, req: ReinforceRequest, request: Request
) -> ReinforceResponse:
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            new_strength = memory_repo.reinforce_memory(
                session,
                memory_id,
                strength_increment=settings.explicit_strength_increment,
                edge_increment=settings.edge_explicit_increment,
                co_recalled_ids=req.co_recalled_ids,
                now_iso=now_iso,
            )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return ReinforceResponse(memory_id=memory_id, new_strength=new_strength)
```

- [ ] **Step 3: Write integration tests**

```python
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_wp029_reinforcement.py::TestExplicitReinforcement -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memory_service/memory_repo.py memory_service/main.py tests/test_wp029_reinforcement.py
git commit -m "feat(WP-029): POST /memory/{id}/reinforce endpoint + Hebbian edge activation"
```

---

## Task 6: Client, CLI, MCP

**Files:**
- Modify: `memory_client/client.py`
- Modify: `memory_client/cli.py`
- Modify: `mcp_server/server.py`

- [ ] **Step 1: Add 3 methods to `MemoryClient` in `memory_client/client.py`**

```python
def reinforce_memory(
    self,
    memory_id: str,
    co_recalled_ids: list[str] | None = None,
) -> dict:
    """POST /memory/{id}/reinforce. Returns {memory_id, new_strength}."""
    body: dict = {"signal": "explicit"}
    if co_recalled_ids:
        body["co_recalled_ids"] = co_recalled_ids
    response = self._http.post(f"/memory/{memory_id}/reinforce", json=body)
    response.raise_for_status()
    return response.json()

def run_decay(self) -> dict:
    """POST /memory/maintenance/decay. Returns {nodes_updated, edges_updated}."""
    response = self._http.post("/memory/maintenance/decay")
    response.raise_for_status()
    return response.json()

def get_weak_edges(self) -> list[dict]:
    """GET /memory/maintenance/weak-edges. Returns list of weak edge dicts."""
    response = self._http.get("/memory/maintenance/weak-edges")
    response.raise_for_status()
    return response.json()["edges"]
```

- [ ] **Step 2: Add 2 CLI commands to `memory_client/cli.py`**

```python
@app.command("reinforce-memory")
def reinforce_memory(
    memory_id: str = typer.Argument(..., help="Memory UUID to reinforce"),
    co_recalled_id: Optional[list[str]] = typer.Option(
        None, "--co-recalled-id", help="Co-recalled memory ID (repeatable)"
    ),
) -> None:
    """Explicitly reinforce a memory (Hebbian signal)."""
    try:
        with _make_client() as client:
            result = client.reinforce_memory(memory_id, co_recalled_ids=co_recalled_id)
        console.print(f"Strength: {result['new_strength']:.3f}")
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)


@app.command("run-decay")
def run_decay() -> None:
    """Trigger a full-graph decay pass (maintenance operation)."""
    try:
        with _make_client() as client:
            result = client.run_decay()
        console.print(f"Nodes updated: {result['nodes_updated']}, Edges updated: {result['edges_updated']}")
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)
```

- [ ] **Step 3: Add 2 MCP tools to `mcp_server/server.py`**

```python
@mcp.tool
def memory_reinforce(memory_id: str, co_recalled_ids: list[str] | None = None) -> dict:
    """Explicitly reinforce a memory. Pass co_recalled_ids for Hebbian edge strengthening."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.reinforce_memory(memory_id, co_recalled_ids=co_recalled_ids)


@mcp.tool
def memory_run_decay() -> dict:
    """Trigger a full-graph decay pass. Returns nodes_updated and edges_updated counts."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.run_decay()
```

- [ ] **Step 4: Write unit tests**

```python
import respx
import httpx
from memory_client.client import MemoryClient
from typer.testing import CliRunner
from memory_client.cli import app as cli_app


class TestMemoryClientReinforce:
    def test_reinforce_memory_returns_dict(self):
        with respx.mock:
            respx.post("http://test/memory/abc123/reinforce").mock(
                return_value=httpx.Response(200, json={"memory_id": "abc123", "new_strength": 0.85})
            )
            with MemoryClient(base_url="http://test") as client:
                result = client.reinforce_memory("abc123")
            assert result["new_strength"] == 0.85

    def test_reinforce_memory_sends_co_recalled_ids(self):
        import json
        with respx.mock:
            route = respx.post("http://test/memory/abc/reinforce").mock(
                return_value=httpx.Response(200, json={"memory_id": "abc", "new_strength": 0.9})
            )
            with MemoryClient(base_url="http://test") as client:
                client.reinforce_memory("abc", co_recalled_ids=["x", "y"])
            body = json.loads(route.calls[0].request.content)
            assert body["co_recalled_ids"] == ["x", "y"]

    def test_run_decay_returns_counts(self):
        with respx.mock:
            respx.post("http://test/memory/maintenance/decay").mock(
                return_value=httpx.Response(200, json={"nodes_updated": 42, "edges_updated": 7})
            )
            with MemoryClient(base_url="http://test") as client:
                result = client.run_decay()
            assert result["nodes_updated"] == 42

    def test_get_weak_edges_returns_list(self):
        with respx.mock:
            respx.get("http://test/memory/maintenance/weak-edges").mock(
                return_value=httpx.Response(200, json={"edges": [{"source_id": "a", "target_id": "b", "relation": "RELATED_TO", "weight": 0.02, "activation_count": 0}]})
            )
            with MemoryClient(base_url="http://test") as client:
                edges = client.get_weak_edges()
            assert len(edges) == 1
            assert edges[0]["weight"] == 0.02


class TestMcpReinforcement:
    def test_memory_reinforce_tool(self):
        from unittest.mock import MagicMock, patch
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.reinforce_memory.return_value = {"memory_id": "abc", "new_strength": 0.75}
        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            from mcp_server.server import memory_reinforce
            result = memory_reinforce("abc")
        assert result["new_strength"] == 0.75

    def test_memory_run_decay_tool(self):
        from unittest.mock import MagicMock, patch
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.run_decay.return_value = {"nodes_updated": 10, "edges_updated": 3}
        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            from mcp_server.server import memory_run_decay
            result = memory_run_decay()
        assert result["nodes_updated"] == 10


class TestReinforceMemoryCLI:
    runner = CliRunner()

    def test_reinforce_memory_prints_strength(self):
        with respx.mock:
            respx.post("http://localhost:8000/memory/abc123/reinforce").mock(
                return_value=httpx.Response(200, json={"memory_id": "abc123", "new_strength": 0.75})
            )
            result = self.runner.invoke(cli_app, ["reinforce-memory", "abc123"])
        assert "0.750" in result.output

    def test_run_decay_prints_counts(self):
        with respx.mock:
            respx.post("http://localhost:8000/memory/maintenance/decay").mock(
                return_value=httpx.Response(200, json={"nodes_updated": 5, "edges_updated": 2})
            )
            result = self.runner.invoke(cli_app, ["run-decay"])
        assert "5" in result.output
        assert "2" in result.output
```

- [ ] **Step 5: Run unit tests**

```bash
pytest tests/test_wp029_reinforcement.py::TestMemoryClientReinforce tests/test_wp029_reinforcement.py::TestMcpReinforcement tests/test_wp029_reinforcement.py::TestReinforceMemoryCLI -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add memory_client/client.py memory_client/cli.py mcp_server/server.py tests/test_wp029_reinforcement.py
git commit -m "feat(WP-029): client/CLI/MCP reinforce-memory + run-decay"
```

---

## Task 7: Migration script — backfill existing nodes

**Files:**
- Create: `scripts/migrate_reinforcement_defaults.py`

Idempotent: uses `WHERE m.strength IS NULL` to skip already-migrated nodes.

- [ ] **Step 1: Create the migration script**

```python
#!/usr/bin/env python3
"""
scripts/migrate_reinforcement_defaults.py

Backfill reinforcement properties on existing Memory nodes and RELATED_TO/LEADS_TO edges.

Idempotent: skips nodes/edges that already have the properties set.

Usage:
    python scripts/migrate_reinforcement_defaults.py [--dry-run]
"""
import argparse
from datetime import datetime, timezone

from memory_service.config import Settings, get_driver


def backfill_nodes(session, now_iso: str, decay_rate: float, dry_run: bool) -> int:
    if dry_run:
        result = session.run(
            "MATCH (m:Memory) WHERE m.strength IS NULL RETURN count(m) AS n"
        )
        return result.single()["n"]

    result = session.run(
        """
        MATCH (m:Memory)
        WHERE m.strength IS NULL
        SET m.strength = m.importance / 5.0,
            m.recall_count = 0,
            m.reinforcement_count = 0,
            m.last_reinforced_at = $now,
            m.decay_rate = $decay_rate
        RETURN count(m) AS n
        """,
        now=now_iso,
        decay_rate=decay_rate,
    )
    return result.single()["n"]


def backfill_edges(session, now_iso: str, edge_decay_rate: float, dry_run: bool) -> int:
    if dry_run:
        result = session.run(
            """
            MATCH ()-[r:RELATED_TO|LEADS_TO]->()
            WHERE r.activation_count IS NULL
            RETURN count(r) AS n
            """
        )
        return result.single()["n"]

    result = session.run(
        """
        MATCH ()-[r:RELATED_TO|LEADS_TO]->()
        WHERE r.activation_count IS NULL
        SET r.activation_count = 0,
            r.last_activated_at = $now,
            r.decay_rate = $edge_decay_rate
        RETURN count(r) AS n
        """,
        now=now_iso,
        edge_decay_rate=edge_decay_rate,
    )
    return result.single()["n"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill reinforcement defaults on Memory nodes and edges")
    parser.add_argument("--dry-run", action="store_true", help="Count only, do not write")
    args = parser.parse_args()

    settings = Settings()
    driver = get_driver(settings)
    now_iso = datetime.now(timezone.utc).isoformat()

    with driver.session() as session:
        nodes = backfill_nodes(session, now_iso, settings.memory_decay_rate, args.dry_run)
        edges = backfill_edges(session, now_iso, settings.edge_decay_rate, args.dry_run)

    driver.close()
    verb = "Would update" if args.dry_run else "Updated"
    print(f"[migrate] {verb} {nodes} Memory nodes, {edges} edges")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write integration tests for the migration script**

```python
@pytest.mark.integration
class TestMigrateReinforcementScript:
    def test_backfill_nodes_sets_defaults(self, test_driver):
        """Insert a node without strength, run backfill, verify properties set."""
        from datetime import datetime, timezone
        from memory_service.config import Settings, get_driver as gd
        from scripts.migrate_reinforcement_defaults import backfill_nodes

        mem_id = f"wp029-migrate-{uuid.uuid4()}"
        try:
            with test_driver.session() as session:
                session.run(
                    "CREATE (m:Memory {id: $id, fact: 'test', text: 'test', "
                    "type: 'fact', tags: [], importance: 3, "
                    "created_at: '2026-01-01T00:00:00+00:00', "
                    "last_used_at: '2026-01-01T00:00:00+00:00', embedding: []})",
                    id=mem_id,
                )

            now_iso = datetime.now(timezone.utc).isoformat()
            s = Settings()
            driver = gd(s)
            with driver.session() as session:
                count = backfill_nodes(session, now_iso, 0.01, dry_run=False)
            driver.close()
            assert count >= 1

            with test_driver.session() as session:
                row = session.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.strength AS s, m.recall_count AS rc",
                    id=mem_id,
                ).single()
                assert abs(row["s"] - 0.6) < 0.001
                assert row["rc"] == 0
        finally:
            with test_driver.session() as session:
                session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mem_id)

    def test_backfill_is_idempotent(self, test_driver):
        """Second backfill run updates 0 nodes (all already migrated by Task 2)."""
        from datetime import datetime, timezone
        from memory_service.config import Settings, get_driver as gd
        from scripts.migrate_reinforcement_defaults import backfill_nodes

        now_iso = datetime.now(timezone.utc).isoformat()
        s = Settings()
        driver = gd(s)
        with driver.session() as session:
            count = backfill_nodes(session, now_iso, 0.01, dry_run=False)
        driver.close()
        # All memories created in WP-029 already have strength set → 0 updated
        assert count == 0

    def test_dry_run_does_not_write(self, test_driver):
        from datetime import datetime, timezone
        from memory_service.config import Settings, get_driver as gd
        from scripts.migrate_reinforcement_defaults import backfill_nodes

        mem_id = f"wp029-dryrun-{uuid.uuid4()}"
        try:
            with test_driver.session() as session:
                session.run(
                    "CREATE (m:Memory {id: $id, fact: 'dry', text: 'dry', "
                    "type: 'fact', tags: [], importance: 2, "
                    "created_at: '2026-01-01T00:00:00+00:00', "
                    "last_used_at: '2026-01-01T00:00:00+00:00', embedding: []})",
                    id=mem_id,
                )

            now_iso = datetime.now(timezone.utc).isoformat()
            s = Settings()
            driver = gd(s)
            with driver.session() as session:
                count = backfill_nodes(session, now_iso, 0.01, dry_run=True)
            driver.close()
            assert count >= 1

            with test_driver.session() as session:
                row = session.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.strength AS s", id=mem_id
                ).single()
                assert row["s"] is None  # not written in dry-run
        finally:
            with test_driver.session() as session:
                session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mem_id)
```

- [ ] **Step 3: Run migration tests**

```bash
pytest tests/test_wp029_reinforcement.py::TestMigrateReinforcementScript -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/migrate_reinforcement_defaults.py tests/test_wp029_reinforcement.py
git commit -m "feat(WP-029): migration script — backfill reinforcement defaults on existing nodes/edges"
```

---

## Task 8: Full suite + live smoke tests + BACKLOG + final commit

- [ ] **Step 1: Run full test suite**

```bash
pytest -v 2>&1 | tail -30
```

Expected: All WP-029 tests pass. Pre-existing 4 failures unchanged. New failures = 0.

- [ ] **Step 2: Restart uvicorn and run manual smoke tests**

```bash
# Verify service is running and has picked up code changes
curl -s http://localhost:8000/health

# Add a memory and capture the memory_id
curl -s -X POST http://localhost:8000/memory \
  -H 'Content-Type: application/json' \
  -d '{"fact":"Smoke test WP-029","type":"fact","agent_id":"claude-code","importance":4}' \
  | python3 -m json.tool

# Search for it (should trigger background recall increment)
curl -s -X POST http://localhost:8000/memory/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"smoke test WP-029","limit":3}' | python3 -m json.tool

# Reinforce it (replace MEMORY_ID with actual id from above)
curl -s -X POST http://localhost:8000/memory/MEMORY_ID/reinforce \
  -H 'Content-Type: application/json' \
  -d '{"signal":"explicit"}' | python3 -m json.tool

# Route ordering check: maintenance endpoints must not return 422
curl -s -X POST http://localhost:8000/memory/maintenance/decay | python3 -m json.tool
curl -s http://localhost:8000/memory/maintenance/weak-edges | python3 -m json.tool
```

- [ ] **Step 3: Run migration script against live DB**

```bash
python scripts/migrate_reinforcement_defaults.py --dry-run
python scripts/migrate_reinforcement_defaults.py
```

Expected: `Updated N Memory nodes, M edges` with both ≥ 0. Pre-WP-029 nodes should have N > 0 on first run; second run returns 0 (idempotent).

- [ ] **Step 4: Update BACKLOG.md**

- Move WP-029 row from Prioritised Backlog to Completed section
- Update WP-006 "Depends on" to show WP-029 ✅
- Add backlog item for inline `effective_strength` sort in search (deferred from this WP)
- Add retrospective note

- [ ] **Step 5: Final commit**

```bash
git add BACKLOG.md
git commit -m "WP-029: Memory + edge reinforcement — strength, decay, Hebbian activation"
```

---

## Acceptance Criteria Checklist

- [ ] Memory nodes created with `strength` seeded from `importance / 5.0`
- [ ] `recall_count=0`, `reinforcement_count=0`, `last_reinforced_at`, `decay_rate` on new nodes
- [ ] `RELATED_TO` and `LEADS_TO` edges gain `activation_count`, `last_activated_at`, `decay_rate` (via migration script for existing edges; new edges get them on first activation)
- [ ] `POST /memory/search` fires background recall increments (non-blocking; TestClient verifies synchronously)
- [ ] `POST /memory/{id}/reinforce` updates node strength + co-edge weights; returns `new_strength`
- [ ] `POST /memory/maintenance/decay` not shadowed by `/{memory_id}/reinforce` — returns 200, not 422
- [ ] `POST /memory/maintenance/decay` returns `{nodes_updated, edges_updated}`
- [ ] `GET /memory/maintenance/weak-edges` returns list of edges below threshold
- [ ] `memory reinforce-memory <id>` CLI command prints new strength
- [ ] `memory run-decay` CLI command prints node/edge counts
- [ ] `memory_reinforce`, `memory_run_decay` MCP tools functional
- [ ] All 8 config vars in `Settings` + `.env.example`
- [ ] Migration script run against live DB; pre-WP-029 nodes updated
- [ ] Round-trip: insert → search × 2 → `recall_count >= 2` and `strength > initial`
- [ ] Existing 175 passing tests still pass; 4 pre-existing failures unchanged
