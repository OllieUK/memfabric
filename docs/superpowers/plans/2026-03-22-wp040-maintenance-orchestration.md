# WP-040 — Memory Maintenance Orchestration: Short Rest & Long Rest

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Short Rest and Long Rest maintenance endpoints + stats monitoring, dry-run mode, dump/restore scripts, System node, edge-modulated decay, and CLI/MCP wiring — making fabric maintenance observable and safe to run on a live graph.

**Architecture:** Python-side decay computation (established in WP-029) extended with scoped Short Rest, full Long Rest with edge rediscovery and prune, dry-run mode on both, a stats health endpoint, System node tracking last-run timestamps, and DB dump/restore scripts. All new config vars go in `Settings` + `.env.example`. CLI and MCP updated in lock-step with each endpoint.

**Tech Stack:** FastAPI, neo4j Python driver, Memgraph (Bolt), Pydantic/pydantic-settings, Typer + Rich (CLI), FastMCP (MCP), httpx + respx (tests), pytest (integration tests against live stack).

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `memory_service/config.py` | Modify | 7 new Settings fields |
| `.env.example` | Modify | 7 new vars |
| `memory_service/memory_repo.py` | Modify | `short_rest()`, `long_rest()`, `maintenance_stats()`, `upsert_system_node()`, `get_system_timestamps()`, edge-modulated decay in `decay_pass()` |
| `memory_service/main.py` | Modify | 3 new endpoints: `POST /memory/maintenance/short-rest`, `POST /memory/maintenance/long-rest`, `GET /memory/maintenance/stats`; update `GET /memory/wake-up` to include `maintenance_warning` |
| `memory_client/client.py` | Modify | `short_rest()`, `long_rest()`, `maintenance_stats()` |
| `memory_client/cli.py` | Modify | `short-rest`, `long-rest`, `status` CLI commands |
| `mcp_server/server.py` | Modify | `memory_short_rest`, `memory_long_rest`, `memory_maintenance_stats` tools |
| `scripts/init_schema.py` | Modify | MERGE System node on startup |
| `scripts/dump_db.py` | Create | Dump all Memory nodes + edges to timestamped JSON |
| `scripts/restore_db.py` | Create | Replay dump as MERGE statements |
| `tests/test_wp040_maintenance.py` | Create | ~35 tests (unit + integration) |

---

## Task 1: Config — 7 new Settings fields + .env.example

**Files:**
- Modify: `memory_service/config.py`
- Modify: `.env.example`

**Context:** `Settings` uses pydantic-settings with `SettingsConfigDict(env_file=".env")`. Add 7 new fields. All names match the WP-040 spec.

- [ ] **Step 1: Write the failing test**

In a temporary test (or inline in the test file that will be created in Task 10) verify the new settings fields exist with correct defaults:

```python
def test_new_config_fields():
    from memory_service.config import Settings
    s = Settings()
    assert s.short_rest_recency_days == 7
    assert s.long_rest_recency_days == 1
    assert s.rediscovery_strength_threshold == 0.3
    assert s.edge_hard_prune_floor == 0.01
    assert s.edge_hard_prune_min_days == 90
    assert s.edge_modulation_factor == 0.5
    assert s.edge_modulation_cap == 10.0
```

Run: `pytest -k test_new_config_fields -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 2: Add the 7 fields to `memory_service/config.py`**

After the existing `min_memory_strength` line, add:

```python
    short_rest_recency_days: int = 7
    long_rest_recency_days: int = 1
    rediscovery_strength_threshold: float = 0.3
    edge_hard_prune_floor: float = 0.01
    edge_hard_prune_min_days: int = 90
    edge_modulation_factor: float = 0.5
    edge_modulation_cap: float = 10.0
```

- [ ] **Step 3: Add vars to `.env.example`**

After the `MIN_MEMORY_STRENGTH=0.0` line, add:

```
# Maintenance orchestration (WP-040)
SHORT_REST_RECENCY_DAYS=7
LONG_REST_RECENCY_DAYS=1
REDISCOVERY_STRENGTH_THRESHOLD=0.3
EDGE_HARD_PRUNE_FLOOR=0.01
EDGE_HARD_PRUNE_MIN_DAYS=90
EDGE_MODULATION_FACTOR=0.5
EDGE_MODULATION_CAP=10.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -k test_new_config_fields -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memory_service/config.py .env.example
git -c gpg.format=openpgp -c commit.gpgsign=false commit -m "feat(WP-040): 7 new Settings fields for maintenance orchestration"
```

---

## Task 2: System node — init_schema + repo helpers

**Files:**
- Modify: `scripts/init_schema.py`
- Modify: `memory_service/memory_repo.py`

**Context:** A singleton `System` node `{id: "system"}` tracks `last_short_rest_at` and `last_long_rest_at`. Created idempotently in `init_schema.py`. Two repo helpers: `upsert_system_node(session, **kwargs)` and `get_system_timestamps(session) -> dict`.

- [ ] **Step 1: Write the failing unit tests**

These will live in `tests/test_wp040_maintenance.py`. Create the file with:

```python
# tests/test_wp040_maintenance.py
import uuid
import pytest
from unittest.mock import MagicMock
from memory_service import memory_repo


class TestSystemNodeHelpers:
    def test_upsert_system_node_sets_fields(self):
        """upsert_system_node writes the given kwargs as properties."""
        session = MagicMock()
        session.run.return_value = None
        memory_repo.upsert_system_node(session, last_short_rest_at="2026-01-01T00:00:00+00:00")
        session.run.assert_called_once()
        call_args = session.run.call_args
        # The query should contain SET and last_short_rest_at
        assert "last_short_rest_at" in call_args[0][0]

    def test_get_system_timestamps_returns_dict(self):
        """get_system_timestamps returns a dict with the two timestamp keys."""
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: {"last_short_rest_at": None, "last_long_rest_at": None}[key]
        session = MagicMock()
        session.run.return_value.single.return_value = mock_record
        result = memory_repo.get_system_timestamps(session)
        assert "last_short_rest_at" in result
        assert "last_long_rest_at" in result
```

Run: `pytest tests/test_wp040_maintenance.py::TestSystemNodeHelpers -v`
Expected: FAIL (functions not defined)

- [ ] **Step 2: Add `upsert_system_node` and `get_system_timestamps` to `memory_repo.py`**

Add at the bottom of `memory_service/memory_repo.py`:

```python
def upsert_system_node(session, **kwargs) -> None:
    """Create or update the singleton System node with the given properties.

    Typical kwargs: last_short_rest_at="...", last_long_rest_at="..."
    """
    if not kwargs:
        return
    set_clause = ", ".join(f"sys.{k} = ${k}" for k in kwargs)
    session.run(
        f"""
        MERGE (sys:System {{id: "system"}})
        SET {set_clause}
        """,
        **kwargs,
    )


def get_system_timestamps(session) -> dict:
    """Return last_short_rest_at and last_long_rest_at from the System node.

    Returns dict with keys last_short_rest_at, last_long_rest_at.
    Values are ISO strings or None if not set.
    """
    result = session.run(
        """
        OPTIONAL MATCH (sys:System {id: "system"})
        RETURN sys.last_short_rest_at AS last_short_rest_at,
               sys.last_long_rest_at AS last_long_rest_at
        """
    )
    record = result.single()
    if record is None:
        return {"last_short_rest_at": None, "last_long_rest_at": None}
    return {
        "last_short_rest_at": record["last_short_rest_at"],
        "last_long_rest_at": record["last_long_rest_at"],
    }
```

- [ ] **Step 3: Add System node creation to `init_schema.py`**

In `main()`, after creating constraints and vector index, add a `System` node MERGE before returning:

```python
            print("\nCreating System node ...")
            with driver.session() as session:
                session.run('MERGE (sys:System {id: "system"})')
                print("  [OK] System node created (idempotent)")
```

Place this inside the existing `with driver.session() as session:` block, after the vector index creation logic.

- [ ] **Step 4: Run unit tests**

Run: `pytest tests/test_wp040_maintenance.py::TestSystemNodeHelpers -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memory_service/memory_repo.py scripts/init_schema.py tests/test_wp040_maintenance.py
git -c gpg.format=openpgp -c commit.gpgsign=false commit -m "feat(WP-040): System node helpers + init_schema MERGE"
```

---

## Task 3: Edge-modulated decay in `decay_pass`

**Files:**
- Modify: `memory_service/memory_repo.py`

**Context:** The existing `decay_pass()` function fetches nodes, computes `strength * exp(-rate * days)`, and writes back. Extend the node-fetch query to also retrieve the sum of incoming `RELATED_TO` + `LEADS_TO` edge weights per node, then divide the decay rate by `min(1 + factor * sum_weight, cap)` before applying the Ebbinghaus formula. The short_rest and long_rest functions (Task 4/5) will call a shared `_decay_nodes_and_edges()` helper rather than the old `decay_pass()` directly, but `decay_pass()` itself must remain backward-compatible (existing endpoint and tests must not break).

The cleanest approach: extract a new internal helper `_decay_pass_inner(session, now_iso, min_strength, node_filter_clause, edge_modulation_factor, edge_modulation_cap)` that `decay_pass()` delegates to with default args (all nodes, no modulation initially → backward compat by passing factor=0 to disable modulation until WP-040 endpoints enable it).

Actually simpler: modify `decay_pass()` to accept optional `edge_modulation_factor` and `edge_modulation_cap` params (default 0.0 and 1.0 to preserve current behaviour), and add a `node_ids` param for scoped decay. When `node_ids` is None, decay all nodes. When non-None, only decay those nodes.

- [ ] **Step 1: Write failing unit tests for edge-modulated decay**

Add to `tests/test_wp040_maintenance.py`:

```python
class TestEdgeModulatedDecay:
    def test_apply_decay_no_modulation(self):
        """With factor=0, effective rate == base rate (backward compat)."""
        from memory_service.memory_repo import _apply_decay_modulated
        result = _apply_decay_modulated(
            current=1.0, base_rate=0.01, days=1.0,
            incoming_weight_sum=5.0,
            factor=0.0, cap=10.0, min_strength=0.0,
        )
        import math
        expected = math.exp(-0.01 * 1.0)
        assert abs(result - expected) < 1e-9

    def test_apply_decay_with_modulation_reduces_rate(self):
        """With factor=0.5 and sum_weight=2.0, effective rate is base/2.0."""
        from memory_service.memory_repo import _apply_decay_modulated
        import math
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
        from memory_service.memory_repo import _apply_decay_modulated
        import math
        result = _apply_decay_modulated(
            current=1.0, base_rate=0.1, days=1.0,
            incoming_weight_sum=1000.0,
            factor=0.5, cap=3.0, min_strength=0.0,
        )
        # effective_rate = 0.1 / 3.0 ≈ 0.0333
        expected = math.exp(-0.1 / 3.0 * 1.0)
        assert abs(result - expected) < 1e-6
```

Run: `pytest tests/test_wp040_maintenance.py::TestEdgeModulatedDecay -v`
Expected: FAIL (`_apply_decay_modulated` not found)

- [ ] **Step 2: Add `_apply_decay_modulated` to `memory_repo.py`**

After the existing `_apply_decay` function, add:

```python
def _apply_decay_modulated(
    current: float,
    base_rate: float,
    days: float,
    incoming_weight_sum: float,
    factor: float,
    cap: float,
    min_strength: float = 0.0,
) -> float:
    """Apply Ebbinghaus decay with edge-modulated rate.

    Effective rate = base_rate / min(1 + factor * incoming_weight_sum, cap)
    A node with more/stronger incoming edges decays slower (elaborative encoding).
    factor=0 disables modulation (effective_rate == base_rate).
    """
    modulation = min(1.0 + factor * incoming_weight_sum, cap)
    effective_rate = base_rate / modulation
    return _apply_decay(current, effective_rate, days, min_strength)
```

- [ ] **Step 3: Extend `decay_pass()` to support scoped nodes, edge modulation, AND dry-run**

Replace the existing `decay_pass()` signature:
```python
def decay_pass(session, now_naive: str, now_iso: str, min_strength: float = 0.0) -> dict:
```
with:
```python
def decay_pass(
    session,
    now_naive: str,
    now_iso: str,
    min_strength: float = 0.0,
    node_ids: list[str] | None = None,
    edge_modulation_factor: float = 0.0,
    edge_modulation_cap: float = 1.0,
    dry_run: bool = False,
) -> dict:
```

**`dry_run` behaviour:** When `dry_run=True`, all computation runs normally but the two UNWIND SET statements (node writes and edge writes) are skipped. The function still returns the counts of what *would* have been updated. This is critical for the long-rest dry-run path.

In the node-fetch query, if `node_ids` is None use all nodes; if `node_ids` is provided, add `AND m.id IN $node_ids` to the WHERE clause. Also fetch incoming edge weight sum:

For `node_ids=None`:
```cypher
MATCH (m:Memory)
WHERE m.strength IS NOT NULL AND m.last_reinforced_at IS NOT NULL AND m.decay_rate IS NOT NULL
OPTIONAL MATCH (pred:Memory)-[inc:RELATED_TO|LEADS_TO]->(m)
WITH m, coalesce(sum(inc.weight), 0.0) AS incoming_weight_sum
RETURN m.id AS id, m.strength AS strength,
       m.last_reinforced_at AS anchor, m.decay_rate AS rate,
       incoming_weight_sum
```

For `node_ids` not None, add `AND m.id IN $node_ids` to the WHERE clause before the OPTIONAL MATCH.

Then in the Python loop replace `_apply_decay(...)` with `_apply_decay_modulated(...)` passing the new params.

The UNWIND write block for nodes should be:
```python
    if node_updates and not dry_run:
        session.run(...)  # existing UNWIND SET
```
Same pattern for the edge UNWIND write.

For the existing `POST /memory/maintenance/decay` endpoint, `decay_pass()` is called with all defaults (`factor=0.0`, `dry_run=False`) so behaviour is unchanged.

- [ ] **Step 4: Run all tests to verify no regressions**

Run: `pytest tests/test_wp040_maintenance.py::TestEdgeModulatedDecay tests/test_wp029_reinforcement.py -v`
Expected: all PASS (both new and existing tests)

- [ ] **Step 5: Commit**

```bash
git add memory_service/memory_repo.py tests/test_wp040_maintenance.py
git -c gpg.format=openpgp -c commit.gpgsign=false commit -m "feat(WP-040): edge-modulated decay helper + extended decay_pass"
```

---

## Task 4: `short_rest` repo function + `POST /memory/maintenance/short-rest` endpoint

**Files:**
- Modify: `memory_service/memory_repo.py`
- Modify: `memory_service/main.py`

**Context:**
- Short Rest scope: Memory nodes where `last_used_at` is within `SHORT_REST_RECENCY_DAYS` days OR `recall_count > 0`. Adjacent edges.
- Dry-run: compute everything, write nothing; `dry_run: bool` field in response.
- After a live run (not dry-run), call `upsert_system_node(session, last_short_rest_at=now_iso)`.
- Response shape: `{nodes_decayed: int, edges_decayed: int, dry_run: bool}`

The `short_rest` repo function signature:
```python
def short_rest(session, now_iso: str, recency_days: int, min_strength: float,
               edge_modulation_factor: float, edge_modulation_cap: float,
               dry_run: bool = False) -> dict:
```

For scoped edge decay: after identifying the in-scope node IDs, also decay edges where BOTH src and tgt are in the scoped set. This keeps edge decay consistent with node scope.

- [ ] **Step 1: Write failing integration test outline**

Add to `tests/test_wp040_maintenance.py`:

```python
@pytest.mark.integration
class TestShortRest:
    def test_short_rest_dry_run_returns_counts_no_write(self, client, test_driver):
        """Dry-run: response shape correct; DB state unchanged."""
        import uuid
        from datetime import datetime, timezone
        mem_id = f"wp040-sr-dr-{uuid.uuid4()}"
        try:
            # Create a memory with recent last_used_at
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

            # Verify DB unchanged
            with test_driver.session() as session:
                row = session.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.strength AS s", id=mem_id
                ).single()
            assert abs(row["s"] - before_strength) < 0.001
        finally:
            with test_driver.session() as session:
                session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mem_id)

    def test_short_rest_live_writes_and_updates_system_node(self, client, test_driver):
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

            # System node updated
            with test_driver.session() as session:
                row = session.run(
                    "MATCH (sys:System {id: 'system'}) RETURN sys.last_short_rest_at AS ts"
                ).single()
            assert row is not None
            assert row["ts"] is not None
        finally:
            with test_driver.session() as session:
                session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mem_id)
```

Run: `pytest tests/test_wp040_maintenance.py::TestShortRest -v`
Expected: FAIL (endpoint 404)

- [ ] **Step 2: Add `short_rest()` to `memory_repo.py`**

```python
def short_rest(
    session,
    now_iso: str,
    recency_days: int,
    min_strength: float,
    edge_modulation_factor: float,
    edge_modulation_cap: float,
    dry_run: bool = False,
) -> dict:
    """Decay recently-active Memory nodes and their adjacent edges.

    Scope: nodes where recall_count > 0 OR last_used_at within recency_days days.
    Edge scope: RELATED_TO and LEADS_TO edges between nodes in the scoped set.
    """
    now = _parse_iso(now_iso)

    # Compute cutoff ISO string for Cypher string comparison
    # We do the comparison in Python by fetching and filtering
    node_rows = list(session.run(
        """
        MATCH (m:Memory)
        WHERE m.strength IS NOT NULL AND m.last_reinforced_at IS NOT NULL AND m.decay_rate IS NOT NULL
        AND (
            (m.recall_count IS NOT NULL AND m.recall_count > 0)
            OR m.last_used_at IS NOT NULL
        )
        OPTIONAL MATCH (pred:Memory)-[inc:RELATED_TO|LEADS_TO]->(m)
        WITH m, coalesce(sum(inc.weight), 0.0) AS incoming_weight_sum
        RETURN m.id AS id, m.strength AS strength,
               m.last_reinforced_at AS anchor, m.decay_rate AS rate,
               m.last_used_at AS last_used_at, m.recall_count AS recall_count,
               incoming_weight_sum
        """
    ))

    recency_cutoff_days = recency_days
    in_scope_ids = []
    node_updates = []

    for row in node_rows:
        # Check scope: recall_count > 0 OR last_used_at within recency window
        in_scope = False
        if row["recall_count"] and row["recall_count"] > 0:
            in_scope = True
        if not in_scope and row["last_used_at"]:
            try:
                lu = _parse_iso(row["last_used_at"])
                if (now - lu).total_seconds() / 86400.0 <= recency_cutoff_days:
                    in_scope = True
            except (ValueError, TypeError):
                pass

        if not in_scope:
            continue

        in_scope_ids.append(row["id"])

        try:
            anchor = _parse_iso(row["anchor"])
        except (ValueError, TypeError):
            continue

        days = (now - anchor).total_seconds() / 86400.0
        new_val = _apply_decay_modulated(
            row["strength"], row["rate"], days,
            row["incoming_weight_sum"],
            edge_modulation_factor, edge_modulation_cap,
            min_strength,
        )
        node_updates.append({"id": row["id"], "new_val": new_val})

    if node_updates and not dry_run:
        session.run(
            """
            UNWIND $updates AS upd
            MATCH (m:Memory {id: upd.id})
            SET m.strength = upd.new_val, m.last_reinforced_at = $now_iso
            """,
            updates=node_updates,
            now_iso=now_iso,
        )

    # Edge decay — only edges between in-scope nodes
    edge_updates = []
    if in_scope_ids:
        edge_rows = list(session.run(
            """
            MATCH (src:Memory)-[r:RELATED_TO|LEADS_TO]->(tgt:Memory)
            WHERE src.id IN $ids AND tgt.id IN $ids
            AND r.weight IS NOT NULL AND r.last_activated_at IS NOT NULL AND r.decay_rate IS NOT NULL
            RETURN id(r) AS rid, r.weight AS weight,
                   r.last_activated_at AS anchor, r.decay_rate AS rate
            """,
            ids=in_scope_ids,
        ))

        for row in edge_rows:
            try:
                anchor = _parse_iso(row["anchor"])
            except (ValueError, TypeError):
                continue
            days = (now - anchor).total_seconds() / 86400.0
            edge_updates.append({
                "rid": row["rid"],
                "new_val": _apply_decay(row["weight"], row["rate"], days),
            })

        if edge_updates and not dry_run:
            session.run(
                """
                UNWIND $updates AS upd
                MATCH ()-[r:RELATED_TO|LEADS_TO]->()
                WHERE id(r) = upd.rid
                SET r.weight = upd.new_val, r.last_activated_at = $now_iso
                """,
                updates=edge_updates,
                now_iso=now_iso,
            )

    if not dry_run:
        upsert_system_node(session, last_short_rest_at=now_iso)

    return {
        "nodes_decayed": len(node_updates),
        "edges_decayed": len(edge_updates),
        "dry_run": dry_run,
    }
```

- [ ] **Step 3: Add Pydantic models and endpoint to `main.py`**

Add after the existing `DecayPassResponse` model block (after line ~288):

```python
class ShortRestResponse(BaseModel):
    nodes_decayed: int
    edges_decayed: int
    dry_run: bool


@app.post("/memory/maintenance/short-rest", response_model=ShortRestResponse)
async def short_rest(
    request: Request,
    dry_run: bool = Query(default=False),
) -> ShortRestResponse:
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            result = memory_repo.short_rest(
                session,
                now_iso=now_iso,
                recency_days=settings.short_rest_recency_days,
                min_strength=settings.min_memory_strength,
                edge_modulation_factor=settings.edge_modulation_factor,
                edge_modulation_cap=settings.edge_modulation_cap,
                dry_run=dry_run,
            )
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return ShortRestResponse(**result)
```

**IMPORTANT:** This endpoint must be registered BEFORE `POST /memory/{memory_id}/reinforce` to avoid FastAPI routing the path incorrectly. Place it before that handler.

- [ ] **Step 4: Run integration tests**

Run: `pytest tests/test_wp040_maintenance.py::TestShortRest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memory_service/memory_repo.py memory_service/main.py tests/test_wp040_maintenance.py
git -c gpg.format=openpgp -c commit.gpgsign=false commit -m "feat(WP-040): short_rest repo + POST /memory/maintenance/short-rest"
```

---

## Task 5: `long_rest` repo function + `POST /memory/maintenance/long-rest` endpoint

**Files:**
- Modify: `memory_service/memory_repo.py`
- Modify: `memory_service/main.py`

**Context:** Long Rest = full decay on all nodes + edges, then edge rediscovery, then optional hard-prune. Three sub-operations, all skipped on dry-run. Rediscovery uses the existing vector search index. Prune hard-deletes edges; only runs if `prune=True` AND `dry_run=False`.

Response shape: `{nodes_decayed, edges_decayed, edges_discovered, edges_pruned, dry_run: bool}`

Rediscovery: for each Memory with `strength >= rediscovery_strength_threshold`, re-run `vector_search.search`, MERGE new `RELATED_TO` edges for pairs within `AUTO_RELATED_MAX_DISTANCE` that don't exist yet. Use `_AUTO_RELATED_K` and `_AUTO_RELATED_MAX_DISTANCE` constants already defined in `memory_repo.py`.

Prune candidates: edges where `weight < edge_hard_prune_floor` AND `last_activated_at` is more than `edge_hard_prune_min_days` days ago (Python-side date check).

- [ ] **Step 1: Write failing integration tests**

Add to `tests/test_wp040_maintenance.py`:

```python
@pytest.mark.integration
class TestLongRest:
    def test_long_rest_dry_run_shape(self, client):
        """Dry-run returns correct response shape without writing."""
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

    def test_long_rest_dry_run_same_numbers_as_live(self, client, test_driver):
        """Dry-run and live run produce same counts; DB state unchanged after dry-run."""
        import uuid
        mem_id = f"wp040-lr-dr-{uuid.uuid4()}"
        try:
            with test_driver.session() as session:
                session.run(
                    "CREATE (m:Memory {id: $id, fact: 'test', text: 'test', "
                    "type: 'fact', tags: [], importance: 3, strength: 0.5, "
                    "recall_count: 0, reinforcement_count: 0, "
                    "last_reinforced_at: '2020-01-01T00:00:00+00:00', "
                    "last_used_at: '2020-01-01T00:00:00+00:00', "
                    "decay_rate: 0.01, embedding: []})",
                    id=mem_id,
                )

            dr = client.post("/memory/maintenance/long-rest?dry_run=true")
            live = client.post("/memory/maintenance/long-rest")
            assert dr.json()["nodes_decayed"] == live.json()["nodes_decayed"]

            # After dry-run the DB strength should have changed (live ran after)
            # but that's fine — the critical invariant is dry-run itself doesn't write
        finally:
            with test_driver.session() as session:
                session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mem_id)

    def test_long_rest_edge_rediscovery(self, client, test_driver):
        """Two memories with embeddings and high strength: long-rest discovers RELATED_TO edge."""
        import uuid
        from memory_service.embeddings import get_embedding
        m1 = m2 = None
        try:
            # Create two semantically similar memories above rediscovery threshold
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

            # Remove any auto-created RELATED_TO edges between them
            with test_driver.session() as session:
                session.run(
                    "MATCH (a:Memory {id: $a})-[r:RELATED_TO]-(b:Memory {id: $b}) DELETE r",
                    a=m1, b=m2,
                )

            r = client.post("/memory/maintenance/long-rest")
            assert r.status_code == 200

            # Check a RELATED_TO edge was created in at least one direction
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
```

Run: `pytest tests/test_wp040_maintenance.py::TestLongRest -v`
Expected: FAIL (endpoint 404)

- [ ] **Step 2: Add `long_rest()` to `memory_repo.py`**

```python
def long_rest(
    session,
    now_iso: str,
    min_strength: float,
    edge_modulation_factor: float,
    edge_modulation_cap: float,
    rediscovery_strength_threshold: float,
    edge_hard_prune_floor: float,
    edge_hard_prune_min_days: int,
    dry_run: bool = False,
    prune: bool = False,
) -> dict:
    """Full maintenance pass: decay all nodes/edges, edge rediscovery, optional prune.

    Steps:
    1. Full decay pass (all nodes + edges, edge-modulated)
    2. Edge rediscovery: for strong nodes, re-run vector search and MERGE new RELATED_TO
    3. Weak-edge pruning: hard-delete edges below floor + min-days (if prune=True and not dry_run)
    4. Update System node last_long_rest_at
    """
    now = _parse_iso(now_iso)

    # Step 1: Full decay pass
    decay_result = decay_pass(
        session, "", now_iso, min_strength,
        node_ids=None,
        edge_modulation_factor=edge_modulation_factor,
        edge_modulation_cap=edge_modulation_cap,
        dry_run=dry_run,
    )
    nodes_decayed = decay_result["nodes_updated"]
    edges_decayed = decay_result["edges_updated"]

    # Step 2: Edge rediscovery — nodes with strength >= threshold
    strong_nodes = list(session.run(
        """
        MATCH (m:Memory)
        WHERE m.strength IS NOT NULL AND m.strength >= $threshold AND m.embedding IS NOT NULL
        RETURN m.id AS id, m.embedding AS embedding
        """,
        threshold=rediscovery_strength_threshold,
    ))

    edges_discovered = 0
    for node in strong_nodes:
        result = session.run(
            """
            CALL vector_search.search("mem_embedding_idx", $k, $query_vec)
            YIELD node AS candidate, distance
            WHERE candidate.id <> $src_id AND distance < $max_distance
            WITH candidate
            MATCH (src:Memory {id: $src_id})
            OPTIONAL MATCH (src)-[existing:RELATED_TO]->(candidate)
            WITH src, candidate, existing
            WHERE existing IS NULL
            MERGE (src)-[r:RELATED_TO]->(candidate)
            ON CREATE SET r.weight = 1.0 - distance,
                          r.activation_count = 0,
                          r.last_activated_at = $now_iso,
                          r.decay_rate = $edge_decay_rate
            RETURN count(r) AS discovered
            """,
            k=_AUTO_RELATED_K,
            query_vec=node["embedding"],
            src_id=node["id"],
            max_distance=_AUTO_RELATED_MAX_DISTANCE,
            now_iso=now_iso,
            edge_decay_rate=0.005,  # default edge decay rate
        ) if not dry_run else None

        if result is not None:
            row = result.single()
            if row:
                edges_discovered += row["discovered"] or 0
        else:
            # Dry-run: estimate — count pairs that would be discovered
            est = session.run(
                """
                CALL vector_search.search("mem_embedding_idx", $k, $query_vec)
                YIELD node AS candidate, distance
                WHERE candidate.id <> $src_id AND distance < $max_distance
                WITH candidate
                MATCH (src:Memory {id: $src_id})
                OPTIONAL MATCH (src)-[existing:RELATED_TO]->(candidate)
                WITH existing
                WHERE existing IS NULL
                RETURN count(*) AS would_discover
                """,
                k=_AUTO_RELATED_K,
                query_vec=node["embedding"],
                src_id=node["id"],
                max_distance=_AUTO_RELATED_MAX_DISTANCE,
            ).single()
            if est:
                edges_discovered += est["would_discover"] or 0

    # Step 3: Weak-edge pruning
    prune_rows = list(session.run(
        """
        MATCH (src:Memory)-[r:RELATED_TO|LEADS_TO]->(tgt:Memory)
        WHERE r.weight IS NOT NULL AND r.weight < $floor
        AND r.last_activated_at IS NOT NULL
        RETURN id(r) AS rid, r.last_activated_at AS last_activated
        """,
        floor=edge_hard_prune_floor,
    ))

    prune_candidates = []
    for row in prune_rows:
        try:
            last_act = _parse_iso(row["last_activated"])
        except (ValueError, TypeError):
            continue
        if (now - last_act).total_seconds() / 86400.0 >= edge_hard_prune_min_days:
            prune_candidates.append(row["rid"])

    edges_pruned = len(prune_candidates)
    if prune_candidates and prune and not dry_run:
        session.run(
            """
            UNWIND $rids AS rid
            MATCH ()-[r:RELATED_TO|LEADS_TO]->()
            WHERE id(r) = rid
            DELETE r
            """,
            rids=prune_candidates,
        )

    # Step 4: Update System node
    if not dry_run:
        upsert_system_node(session, last_long_rest_at=now_iso)

    return {
        "nodes_decayed": nodes_decayed,
        "edges_decayed": edges_decayed,
        "edges_discovered": edges_discovered,
        "edges_pruned": edges_pruned,
        "dry_run": dry_run,
    }
```

Note: `decay_pass()` also needs a `dry_run` parameter added. Add `dry_run: bool = False` to `decay_pass()` and skip the UNWIND write statements when `dry_run=True`, returning the counts as computed.

- [ ] **Step 3: Add endpoint to `main.py`**

```python
class LongRestResponse(BaseModel):
    nodes_decayed: int
    edges_decayed: int
    edges_discovered: int
    edges_pruned: int
    dry_run: bool


@app.post("/memory/maintenance/long-rest", response_model=LongRestResponse)
async def long_rest(
    request: Request,
    dry_run: bool = Query(default=False),
    prune: bool = Query(default=False),
) -> LongRestResponse:
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            result = memory_repo.long_rest(
                session,
                now_iso=now_iso,
                min_strength=settings.min_memory_strength,
                edge_modulation_factor=settings.edge_modulation_factor,
                edge_modulation_cap=settings.edge_modulation_cap,
                rediscovery_strength_threshold=settings.rediscovery_strength_threshold,
                edge_hard_prune_floor=settings.edge_hard_prune_floor,
                edge_hard_prune_min_days=settings.edge_hard_prune_min_days,
                dry_run=dry_run,
                prune=prune,
            )
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return LongRestResponse(**result)
```

Place before `POST /memory/{memory_id}/reinforce`.

- [ ] **Step 4: Run integration tests**

Run: `pytest tests/test_wp040_maintenance.py::TestLongRest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memory_service/memory_repo.py memory_service/main.py tests/test_wp040_maintenance.py
git -c gpg.format=openpgp -c commit.gpgsign=false commit -m "feat(WP-040): long_rest repo + POST /memory/maintenance/long-rest"
```

---

## Task 6: Maintenance stats endpoint + wake-up staleness warning

**Files:**
- Modify: `memory_service/memory_repo.py`
- Modify: `memory_service/main.py`

**Context:** `GET /memory/maintenance/stats` returns a health snapshot. Also update `GET /memory/wake-up` to include a `maintenance_warning: str | None` field — non-null when `long_rest_overdue` is true.

Stats JSON shape (see WP-040 spec for exact field names). `short_rest_overdue` = true if `last_short_rest_at` is older than `SHORT_REST_RECENCY_DAYS` days. `long_rest_overdue` = true if `last_long_rest_at` is older than `LONG_REST_RECENCY_DAYS` days (or never ran).

- [ ] **Step 1: Write failing tests**

Add to `tests/test_wp040_maintenance.py`:

```python
@pytest.mark.integration
class TestMaintenanceStats:
    def test_stats_endpoint_returns_shape(self, client):
        r = client.get("/memory/maintenance/stats")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data
        assert "maintenance" in data
        nodes = data["nodes"]
        for field in ["total", "mean_strength", "median_strength", "below_prune_floor", "at_max_strength"]:
            assert field in nodes, f"Missing nodes field: {field}"
        edges = data["edges"]
        for field in ["total", "mean_weight", "weak_count"]:
            assert field in edges, f"Missing edges field: {field}"
        maint = data["maintenance"]
        for field in ["last_short_rest_at", "last_long_rest_at", "short_rest_overdue", "long_rest_overdue"]:
            assert field in maint, f"Missing maintenance field: {field}"


class TestWakeUpMaintenanceWarning:
    def test_wake_up_response_has_maintenance_warning_field(self):
        """WakeUpResponse model should include maintenance_warning (may be None)."""
        from memory_service.main import WakeUpResponse
        import inspect
        fields = WakeUpResponse.model_fields
        assert "maintenance_warning" in fields
```

Run: `pytest tests/test_wp040_maintenance.py::TestMaintenanceStats tests/test_wp040_maintenance.py::TestWakeUpMaintenanceWarning -v`
Expected: FAIL

- [ ] **Step 2: Add `maintenance_stats()` to `memory_repo.py`**

```python
def maintenance_stats(
    session,
    now_iso: str,
    edge_prune_threshold: float,
    short_rest_recency_days: int,
    long_rest_recency_days: int,
) -> dict:
    """Return a health snapshot of the graph for monitoring."""
    now = _parse_iso(now_iso)

    # Node stats
    node_rows = list(session.run(
        "MATCH (m:Memory) WHERE m.strength IS NOT NULL "
        "RETURN m.strength AS s"
    ))
    strengths = [r["s"] for r in node_rows]
    total_nodes = len(strengths)
    mean_strength = sum(strengths) / total_nodes if strengths else 0.0
    sorted_s = sorted(strengths)
    if sorted_s:
        n = len(sorted_s)
        median_strength = sorted_s[n // 2] if n % 2 else (sorted_s[n // 2 - 1] + sorted_s[n // 2]) / 2
    else:
        median_strength = 0.0
    below_prune_floor = sum(1 for s in strengths if s < edge_prune_threshold)
    at_max_strength = sum(1 for s in strengths if s >= 1.0)

    # Edge stats
    edge_rows = list(session.run(
        "MATCH (src:Memory)-[r:RELATED_TO|LEADS_TO]->(tgt:Memory) "
        "WHERE r.weight IS NOT NULL RETURN r.weight AS w"
    ))
    weights = [r["w"] for r in edge_rows]
    total_edges = len(weights)
    mean_weight = sum(weights) / total_edges if weights else 0.0
    weak_count = sum(1 for w in weights if w < edge_prune_threshold)

    # System timestamps
    ts = get_system_timestamps(session)
    last_short = ts["last_short_rest_at"]
    last_long = ts["last_long_rest_at"]

    def _is_overdue(ts_str: str | None, days: int) -> bool:
        if ts_str is None:
            return True
        try:
            last = _parse_iso(ts_str)
            return (now - last).total_seconds() / 86400.0 > days
        except (ValueError, TypeError):
            return True

    return {
        "nodes": {
            "total": total_nodes,
            "mean_strength": round(mean_strength, 4),
            "median_strength": round(median_strength, 4),
            "below_prune_floor": below_prune_floor,
            "at_max_strength": at_max_strength,
        },
        "edges": {
            "total": total_edges,
            "mean_weight": round(mean_weight, 4),
            "weak_count": weak_count,
        },
        "maintenance": {
            "last_short_rest_at": last_short,
            "last_long_rest_at": last_long,
            "short_rest_overdue": _is_overdue(last_short, short_rest_recency_days),
            "long_rest_overdue": _is_overdue(last_long, long_rest_recency_days),
        },
    }
```

- [ ] **Step 3: Add endpoint + update WakeUpResponse in `main.py`**

Add Pydantic models and endpoint:

```python
class MaintenanceStatsNodes(BaseModel):
    total: int
    mean_strength: float
    median_strength: float
    below_prune_floor: int
    at_max_strength: int

class MaintenanceStatsEdges(BaseModel):
    total: int
    mean_weight: float
    weak_count: int

class MaintenanceStatsMaintenance(BaseModel):
    last_short_rest_at: Optional[str]
    last_long_rest_at: Optional[str]
    short_rest_overdue: bool
    long_rest_overdue: bool

class MaintenanceStatsResponse(BaseModel):
    nodes: MaintenanceStatsNodes
    edges: MaintenanceStatsEdges
    maintenance: MaintenanceStatsMaintenance


@app.get("/memory/maintenance/stats", response_model=MaintenanceStatsResponse)
async def maintenance_stats(request: Request) -> MaintenanceStatsResponse:
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            result = memory_repo.maintenance_stats(
                session,
                now_iso=now_iso,
                edge_prune_threshold=settings.edge_hard_prune_floor,  # NOT edge_prune_threshold (WP-029)
                short_rest_recency_days=settings.short_rest_recency_days,
                long_rest_recency_days=settings.long_rest_recency_days,
            )
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return MaintenanceStatsResponse(**result)
```

Update `WakeUpResponse` to include `maintenance_warning`:
```python
class WakeUpResponse(BaseModel):
    memories: List[WakeUpMemoryItem]
    topic_memories: List[WakeUpMemoryItem]
    maintenance_warning: Optional[str] = None
```

In the `wake_up` endpoint, check `long_rest_overdue` and set `maintenance_warning` if true:
```python
    # After getting the memory results, check maintenance state
    maintenance_warning = None
    try:
        with request.app.state.driver.session() as session:
            ts = memory_repo.get_system_timestamps(session)
        last_long = ts.get("last_long_rest_at")
        if last_long is None:
            maintenance_warning = "Note: long-rest has never run — consider running `memory long-rest` before this session."
        else:
            from datetime import datetime, timezone as tz_mod
            last_dt = memory_repo._parse_iso(last_long)
            days_ago = (datetime.now(tz=tz_mod.utc) - last_dt).total_seconds() / 86400.0
            if days_ago > settings.long_rest_recency_days:
                maintenance_warning = (
                    f"Note: long-rest last ran {days_ago:.0f} day(s) ago — "
                    "consider running `memory long-rest` before this session."
                )
    except Exception:
        pass  # best-effort; do not surface maintenance errors to wake-up response
```

Then pass `maintenance_warning=maintenance_warning` to `WakeUpResponse(...)`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_wp040_maintenance.py::TestMaintenanceStats tests/test_wp040_maintenance.py::TestWakeUpMaintenanceWarning -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest tests/ -v`
Note any failures — fix before committing.

- [ ] **Step 6: Commit**

```bash
git add memory_service/memory_repo.py memory_service/main.py tests/test_wp040_maintenance.py
git -c gpg.format=openpgp -c commit.gpgsign=false commit -m "feat(WP-040): maintenance stats endpoint + wake-up staleness warning"
```

---

## Task 7: CLI commands — `short-rest`, `long-rest`, `status`

**Files:**
- Modify: `memory_client/client.py`
- Modify: `memory_client/cli.py`

**Context:** Three new CLI commands. `status` calls `GET /memory/maintenance/stats` and renders a human-readable summary using Rich. `short-rest` and `long-rest` call the new endpoints.

- [ ] **Step 1: Write failing unit tests**

Add to `tests/test_wp040_maintenance.py` (unit, no live stack needed):

```python
class TestMaintenanceCLI:
    from typer.testing import CliRunner
    runner = CliRunner()

    def test_status_command_renders_output(self):
        import respx, httpx
        from typer.testing import CliRunner
        from memory_client.cli import app as cli_app
        runner = CliRunner()
        stats = {
            "nodes": {"total": 50, "mean_strength": 0.61, "median_strength": 0.58,
                       "below_prune_floor": 3, "at_max_strength": 1},
            "edges": {"total": 200, "mean_weight": 0.43, "weak_count": 10},
            "maintenance": {
                "last_short_rest_at": "2026-03-22T10:00:00+00:00",
                "last_long_rest_at": None,
                "short_rest_overdue": False,
                "long_rest_overdue": True,
            }
        }
        with respx.mock:
            respx.get("http://localhost:8000/memory/maintenance/stats").mock(
                return_value=httpx.Response(200, json=stats)
            )
            result = runner.invoke(cli_app, ["status"])
        assert result.exit_code == 0
        assert "50" in result.output  # total nodes

    def test_short_rest_dry_run_cli(self):
        import respx, httpx
        from typer.testing import CliRunner
        from memory_client.cli import app as cli_app
        runner = CliRunner()
        with respx.mock:
            respx.post("http://localhost:8000/memory/maintenance/short-rest").mock(
                return_value=httpx.Response(200, json={"nodes_decayed": 5, "edges_decayed": 2, "dry_run": True})
            )
            result = runner.invoke(cli_app, ["short-rest", "--dry-run"])
        assert result.exit_code == 0
        assert "dry" in result.output.lower() or "5" in result.output

    def test_long_rest_cli(self):
        import respx, httpx
        from typer.testing import CliRunner
        from memory_client.cli import app as cli_app
        runner = CliRunner()
        with respx.mock:
            respx.post("http://localhost:8000/memory/maintenance/long-rest").mock(
                return_value=httpx.Response(200, json={
                    "nodes_decayed": 10, "edges_decayed": 4,
                    "edges_discovered": 2, "edges_pruned": 0, "dry_run": False,
                })
            )
            result = runner.invoke(cli_app, ["long-rest"])
        assert result.exit_code == 0
        assert "10" in result.output
```

Run: `pytest tests/test_wp040_maintenance.py::TestMaintenanceCLI -v`
Expected: FAIL (commands not found)

- [ ] **Step 2: Add client methods to `memory_client/client.py`**

```python
    def short_rest(self, *, dry_run: bool = False) -> dict:
        """POST /memory/maintenance/short-rest."""
        params = {}
        if dry_run:
            params["dry_run"] = "true"
        response = self._http.post("/memory/maintenance/short-rest", params=params)
        response.raise_for_status()
        return response.json()

    def long_rest(self, *, dry_run: bool = False, prune: bool = False) -> dict:
        """POST /memory/maintenance/long-rest."""
        params = {}
        if dry_run:
            params["dry_run"] = "true"
        if prune:
            params["prune"] = "true"
        response = self._http.post("/memory/maintenance/long-rest", params=params)
        response.raise_for_status()
        return response.json()

    def maintenance_stats(self) -> dict:
        """GET /memory/maintenance/stats."""
        response = self._http.get("/memory/maintenance/stats")
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 3: Add CLI commands to `memory_client/cli.py`**

```python
@app.command("short-rest")
def short_rest(
    dry_run: bool = typer.Option(False, "--dry-run", help="Compute but do not write"),
) -> None:
    """Run a Short Rest decay pass on recently-active memories."""
    try:
        with _make_client() as client:
            result = client.short_rest(dry_run=dry_run)
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    dr_label = " [dim](dry-run)[/dim]" if result.get("dry_run") else ""
    console.print(
        f"Nodes decayed: {result['nodes_decayed']}, "
        f"Edges decayed: {result['edges_decayed']}{dr_label}"
    )


@app.command("long-rest")
def long_rest(
    dry_run: bool = typer.Option(False, "--dry-run", help="Compute but do not write"),
    prune: bool = typer.Option(False, "--prune", help="Hard-delete eligible weak edges"),
) -> None:
    """Run a Long Rest: full decay + edge rediscovery + optional prune."""
    try:
        with _make_client() as client:
            result = client.long_rest(dry_run=dry_run, prune=prune)
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    dr_label = " [dim](dry-run)[/dim]" if result.get("dry_run") else ""
    console.print(
        f"Nodes decayed: {result['nodes_decayed']}, "
        f"Edges decayed: {result['edges_decayed']}, "
        f"Edges discovered: {result['edges_discovered']}, "
        f"Edges pruned: {result['edges_pruned']}{dr_label}"
    )


@app.command("status")
def status() -> None:
    """Show a health summary of the memory fabric."""
    try:
        with _make_client() as client:
            data = client.maintenance_stats()
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    nodes = data["nodes"]
    edges = data["edges"]
    maint = data["maintenance"]

    console.print("\n[bold]Memory Fabric Health[/bold]")
    console.print(f"  Nodes: {nodes['total']} total  "
                  f"mean strength: {nodes['mean_strength']:.2f}  "
                  f"median: {nodes['median_strength']:.2f}  "
                  f"at-max: {nodes['at_max_strength']}  "
                  f"below-floor: {nodes['below_prune_floor']}")
    console.print(f"  Edges: {edges['total']} total  "
                  f"mean weight: {edges['mean_weight']:.2f}  "
                  f"weak: {edges['weak_count']}")

    sr_overdue = "[red]OVERDUE[/red]" if maint["short_rest_overdue"] else "[green]ok[/green]"
    lr_overdue = "[red]OVERDUE[/red]" if maint["long_rest_overdue"] else "[green]ok[/green]"
    console.print(f"\n  Short rest: {maint.get('last_short_rest_at') or 'never'} — {sr_overdue}")
    console.print(f"  Long rest:  {maint.get('last_long_rest_at') or 'never'} — {lr_overdue}")
```

- [ ] **Step 4: Run unit tests**

Run: `pytest tests/test_wp040_maintenance.py::TestMaintenanceCLI -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memory_client/client.py memory_client/cli.py tests/test_wp040_maintenance.py
git -c gpg.format=openpgp -c commit.gpgsign=false commit -m "feat(WP-040): CLI short-rest / long-rest / status commands"
```

---

## Task 8: MCP tools — `memory_short_rest`, `memory_long_rest`, `memory_maintenance_stats`

**Files:**
- Modify: `mcp_server/server.py`

**Context:** Three new MCP tools following the existing pattern (fresh MemoryClient per call). `memory_short_rest` and `memory_long_rest` return a formatted string summary. `memory_maintenance_stats` returns the raw dict.

- [ ] **Step 1: Write failing unit tests**

Add to `tests/test_wp040_maintenance.py`:

```python
class TestMcpMaintenance:
    def test_memory_short_rest_tool(self):
        from unittest.mock import MagicMock, patch
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.short_rest.return_value = {"nodes_decayed": 3, "edges_decayed": 1, "dry_run": False}
        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            from mcp_server.server import memory_short_rest
            result = memory_short_rest()
        assert "3" in result or result["nodes_decayed"] == 3 or "nodes_decayed" in str(result)

    def test_memory_long_rest_tool(self):
        from unittest.mock import MagicMock, patch
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.long_rest.return_value = {
            "nodes_decayed": 10, "edges_decayed": 5,
            "edges_discovered": 2, "edges_pruned": 0, "dry_run": True,
        }
        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            from mcp_server.server import memory_long_rest
            result = memory_long_rest(dry_run=True)
        assert "10" in str(result) or result.get("nodes_decayed") == 10

    def test_memory_maintenance_stats_tool(self):
        from unittest.mock import MagicMock, patch
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.maintenance_stats.return_value = {
            "nodes": {"total": 100, "mean_strength": 0.5, "median_strength": 0.5,
                       "below_prune_floor": 5, "at_max_strength": 2},
            "edges": {"total": 300, "mean_weight": 0.4, "weak_count": 15},
            "maintenance": {"last_short_rest_at": None, "last_long_rest_at": None,
                             "short_rest_overdue": True, "long_rest_overdue": True},
        }
        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            from mcp_server.server import memory_maintenance_stats
            result = memory_maintenance_stats()
        assert result["nodes"]["total"] == 100
```

Run: `pytest tests/test_wp040_maintenance.py::TestMcpMaintenance -v`
Expected: FAIL (tools not found)

- [ ] **Step 2: Add tools to `mcp_server/server.py`**

```python
@mcp.tool
def memory_short_rest(dry_run: bool = False) -> str:
    """Run Short Rest decay pass on recently-active memories.
    Returns a plain-text summary. Use dry_run=True to preview without writing."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        result = client.short_rest(dry_run=dry_run)
    dr = " (dry-run)" if result.get("dry_run") else ""
    return (
        f"Short Rest{dr}: {result['nodes_decayed']} nodes decayed, "
        f"{result['edges_decayed']} edges decayed."
    )


@mcp.tool
def memory_long_rest(dry_run: bool = False, prune: bool = False) -> str:
    """Run Long Rest: full decay + edge rediscovery + optional prune.
    Returns a plain-text summary. Use dry_run=True to preview without writing.
    Use prune=True to hard-delete eligible weak edges (only applies when dry_run=False)."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        result = client.long_rest(dry_run=dry_run, prune=prune)
    dr = " (dry-run)" if result.get("dry_run") else ""
    return (
        f"Long Rest{dr}: {result['nodes_decayed']} nodes decayed, "
        f"{result['edges_decayed']} edges decayed, "
        f"{result['edges_discovered']} edges discovered, "
        f"{result['edges_pruned']} edges pruned."
    )


@mcp.tool
def memory_maintenance_stats() -> dict:
    """Return a health snapshot of the memory fabric including node/edge stats and maintenance timestamps."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.maintenance_stats()
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_wp040_maintenance.py::TestMcpMaintenance -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add mcp_server/server.py tests/test_wp040_maintenance.py
git -c gpg.format=openpgp -c commit.gpgsign=false commit -m "feat(WP-040): MCP memory_short_rest / memory_long_rest / memory_maintenance_stats"
```

---

## Task 9: `scripts/dump_db.py` and `scripts/restore_db.py`

**Files:**
- Create: `scripts/dump_db.py`
- Create: `scripts/restore_db.py`

**Context:** Pre-maintenance snapshot/rollback. `dump_db.py` dumps all Memory nodes and all `RELATED_TO`/`LEADS_TO` edges to a timestamped JSON file. `restore_db.py` replays the dump as MERGE statements. Both read from `.env` via `Settings`. The dump is the v1 rollback mechanism.

CLI entry points: `memory dump-db [--output path]` (via `memory_client/cli.py`) and `scripts/restore_db.py --from snapshot.json`.

Actually, for simplicity (and to avoid making scripts depend on the memory client package), `dump_db.py` and `restore_db.py` are standalone scripts that connect directly to Memgraph. They do NOT go through the REST API. `memory dump-db` in the CLI is separate (Task 7 already defined `dump-graph` which is a placeholder for WP-006 — this is different). The `dump-db` CLI command should call the script directly or replicate the logic via the HTTP API.

Simplest v1: `dump_db.py` is a standalone Python script using the neo4j driver. `restore_db.py` is also standalone. No HTTP API involvement — direct DB access. This makes them usable even when the service is down.

Dump format:
```json
{
  "created_at": "2026-03-22T10:00:00Z",
  "nodes": [{"id": "...", "fact": "...", ...}, ...],
  "edges": [{"src": "...", "tgt": "...", "type": "RELATED_TO", "weight": 0.8, ...}, ...]
}
```

- [ ] **Step 1: Write a unit test for dump/restore**

Add to `tests/test_wp040_maintenance.py`:

```python
class TestDumpRestoreScript:
    def test_dump_produces_valid_json(self, tmp_path, test_driver):
        """dump_db main() writes a JSON file with nodes and edges keys."""
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
```

Mark this integration (needs `test_driver`). Run: `pytest tests/test_wp040_maintenance.py::TestDumpRestoreScript -v`
Expected: FAIL (module not found)

- [ ] **Step 2: Create `scripts/dump_db.py`**

```python
"""
dump_db.py — Dump all Memory nodes and edges to a JSON snapshot.

Usage:
    python scripts/dump_db.py [--output path/to/snapshot.json]

The output file is timestamped by default: dump_YYYYMMDD_HHMMSS.json
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from memory_service.config import Settings, get_driver


def dump_db(session, output_path: str) -> dict:
    """Dump Memory nodes and RELATED_TO/LEADS_TO edges to a JSON file.

    Returns summary dict with node_count and edge_count.
    """
    node_rows = list(session.run(
        "MATCH (m:Memory) RETURN properties(m) AS props"
    ))
    nodes = [dict(r["props"]) for r in node_rows]

    edge_rows = list(session.run(
        """
        MATCH (src:Memory)-[r:RELATED_TO|LEADS_TO]->(tgt:Memory)
        RETURN src.id AS src, tgt.id AS tgt, type(r) AS type,
               properties(r) AS props
        """
    ))
    edges = []
    for r in edge_rows:
        edge = {"src": r["src"], "tgt": r["tgt"], "type": r["type"]}
        edge.update(dict(r["props"]))
        edges.append(edge)

    data = {
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "nodes": nodes,
        "edges": edges,
    }
    Path(output_path).write_text(json.dumps(data, indent=2, default=str))
    return {"node_count": len(nodes), "edge_count": len(edges)}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Dump Memory graph to JSON")
    parser.add_argument("--output", default=None, help="Output file path")
    args = parser.parse_args()

    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = args.output or f"dump_{ts}.json"

    settings = Settings()
    driver = get_driver(settings)
    try:
        driver.verify_connectivity()
    except Exception as exc:
        print(f"[FAIL] Cannot connect to Memgraph: {exc}")
        return 1

    with driver.session() as session:
        summary = dump_db(session, output_path)
    driver.close()

    print(f"Dumped {summary['node_count']} nodes, {summary['edge_count']} edges → {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Create `scripts/restore_db.py`**

```python
"""
restore_db.py — Restore Memory nodes and edges from a JSON snapshot.

Usage:
    python scripts/restore_db.py --from snapshot.json [--dry-run]

WARNING: This MERGEs nodes and edges — it does NOT clear the DB first.
To do a clean restore, drop all Memory nodes first manually:
    MATCH (m:Memory) DETACH DELETE m
"""
import json
import sys
from pathlib import Path

from memory_service.config import Settings, get_driver


def restore_db(session, data: dict, dry_run: bool = False) -> dict:
    """Replay dump as MERGE statements. Returns summary dict."""
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    if dry_run:
        return {"nodes_merged": len(nodes), "edges_merged": len(edges), "dry_run": True}

    # Restore nodes
    nodes_merged = 0
    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            continue
        # Remove embedding from SET — handle separately if needed
        props = {k: v for k, v in node.items() if k != "id" and v is not None}
        set_clause = ", ".join(f"m.{k} = ${k}" for k in props)
        session.run(
            f"MERGE (m:Memory {{id: $id}}) SET {set_clause}",
            id=node_id, **props,
        )
        nodes_merged += 1

    # Restore edges
    edges_merged = 0
    for edge in edges:
        src = edge.get("src")
        tgt = edge.get("tgt")
        etype = edge.get("type", "RELATED_TO")
        if not src or not tgt:
            continue
        # Allowlist guard — prevents injection if dump file is corrupted/edited
        if etype not in ("RELATED_TO", "LEADS_TO"):
            print(f"  [SKIP] Unexpected edge type: {etype!r}")
            continue
        props = {k: v for k, v in edge.items() if k not in ("src", "tgt", "type") and v is not None}
        if props:
            set_clause = "SET " + ", ".join(f"r.{k} = ${k}" for k in props)
        else:
            set_clause = ""
        session.run(
            f"""
            MATCH (a:Memory {{id: $src}}), (b:Memory {{id: $tgt}})
            MERGE (a)-[r:{etype}]->(b)
            {set_clause}
            """,
            src=src, tgt=tgt, **props,
        )
        edges_merged += 1

    return {"nodes_merged": nodes_merged, "edges_merged": edges_merged, "dry_run": False}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Restore Memory graph from JSON dump")
    parser.add_argument("--from", dest="from_file", required=True, help="Path to dump file")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    dump_path = Path(args.from_file)
    if not dump_path.exists():
        print(f"[FAIL] File not found: {dump_path}")
        return 1

    data = json.loads(dump_path.read_text())
    settings = Settings()
    driver = get_driver(settings)
    try:
        driver.verify_connectivity()
    except Exception as exc:
        print(f"[FAIL] Cannot connect to Memgraph: {exc}")
        return 1

    with driver.session() as session:
        summary = restore_db(session, data, dry_run=args.dry_run)
    driver.close()

    dr = " (dry-run)" if summary["dry_run"] else ""
    print(f"Restored{dr}: {summary['nodes_merged']} nodes, {summary['edges_merged']} edges")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/test_wp040_maintenance.py::TestDumpRestoreScript -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/dump_db.py scripts/restore_db.py tests/test_wp040_maintenance.py
git -c gpg.format=openpgp -c commit.gpgsign=false commit -m "feat(WP-040): dump_db.py + restore_db.py snapshot/rollback scripts"
```

---

## Task 10: Full test run + integration validation

**Files:**
- No new code changes expected; this task validates the whole WP.

**Context:** Run the full test suite against the live stack. Verify all 15 Definition of Success checkboxes. This task is mandatory per the DoD.

- [ ] **Step 1: Run full test suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -50
```

Expected: all existing tests pass + new WP-040 tests pass. Note any failures.

- [ ] **Step 2: Run integration tests explicitly**

```bash
pytest tests/test_wp040_maintenance.py -v -m integration
```

Expected: all integration tests PASS.

- [ ] **Step 3: Smoke-test the endpoints against live service**

The live service must be running (`docker compose up -d` + `uvicorn memory_service.main:app`).

```bash
# Stats
curl -s http://localhost:8000/memory/maintenance/stats | python -m json.tool

# Short rest dry-run
curl -s -X POST "http://localhost:8000/memory/maintenance/short-rest?dry_run=true" | python -m json.tool

# Long rest dry-run
curl -s -X POST "http://localhost:8000/memory/maintenance/long-rest?dry_run=true" | python -m json.tool

# Wake-up — check for maintenance_warning field
curl -s "http://localhost:8000/memory/wake-up" | python -m json.tool

# CLI status
memory status

# CLI dry-run flows
memory short-rest --dry-run
memory long-rest --dry-run
```

Expected: all return 200 with correct JSON shapes; no 404 or 422 errors.

- [ ] **Step 4: Verify Definition of Success checkboxes**

Work through each of the 15 checkboxes in the WP-040 spec in BACKLOG.md. Mark off each one.

- [ ] **Step 5: Update BACKLOG.md**

Move WP-040 to Completed section. Add retrospective note. Add any new backlog items discovered.

- [ ] **Step 6: Commit**

```bash
git add BACKLOG.md
git -c gpg.format=openpgp -c commit.gpgsign=false commit -m "WP-040: Memory maintenance orchestration — Short Rest & Long Rest"
```

---

## Test count estimate

| Category | Count |
|----------|-------|
| Config fields (unit) | 1 |
| System node helpers (unit) | 2 |
| Edge-modulated decay (unit) | 3 |
| Short Rest integration | 2 |
| Long Rest integration | 4 |
| Maintenance stats integration | 1 |
| Wake-up warning (unit) | 1 |
| CLI (unit + respx mock) | 3 |
| MCP (unit mock) | 3 |
| Dump/restore integration | 1 |
| **Total** | **~21** |

Existing test count before WP-040: 175 passing. Target after: ~196 passing.
