# WP-048: Two-Speed Decay + Importance Floor to Protect Core Memories

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent core memories (people, relationships, long-term history) from being crowded out by high-volume day-to-day activity by: (1) lowering initial strength so new memories must earn retention through recall, (2) switching to a slower decay rate on first reinforcement ("consolidation"), and (3) storing a per-node importance floor so high-importance memories never decay to zero.

**Architecture:** Three coordinated changes, all in `memory_repo.py` and `config.py`. No API shape changes. New memories get low initial strength and a fast `decay_rate`; first reinforcement consolidates to a slow rate and resets the anchor. All decay functions already accept a `min_strength` argument — we add a per-node `min_strength` property so the decay pass reads it from the node instead of using the global config. Existing memories without `min_strength` fall back to the global `min_memory_strength` (0.0) — no migration needed.

**Tech Stack:** Python, Cypher (Memgraph), pytest, FastAPI TestClient

---

## File Map

| File | Change |
|------|--------|
| `memory_service/config.py` | Add 4 new config fields: `initial_strength_factor`, `memory_initial_decay_rate`, `memory_consolidated_decay_rate`, `importance_floor_factor` |
| `memory_service/memory_repo.py` | `add_memory`: lower initial strength + set fast decay rate + store `min_strength`. `reinforce_memory`: on first reinforcement, switch `decay_rate` to consolidated rate. `decay_pass` + `short_rest` + `long_rest`: read per-node `min_strength` instead of passing global as constant. |
| `.env.example` | Document the 4 new config values |
| `tests/test_wp048_two_speed_decay.py` | New: unit + integration tests covering all acceptance criteria |
| `tests/test_wp029_reinforcement.py` | Update 2 tests that hard-code old initial-strength expectations |

---

## Task 1: Add new config fields

**Files:**
- Modify: `memory_service/config.py`

- [ ] **Step 1: Write the failing config test**

```python
# In tests/test_wp048_two_speed_decay.py (create this file)
"""
WP-048: Two-speed decay + importance floor tests.

Unit tests (no live stack):
  U1 — New config fields exist with correct defaults
  U2 — _apply_decay respects per-node min_strength
  U3 — initial strength formula: initial_strength_factor * importance / 5.0

Integration tests (live Memgraph + FastAPI required):
  I1 — New memory has low initial strength and fast decay_rate
  I2 — New memory has min_strength stored = importance_floor_factor * importance / 5.0
  I3 — First reinforcement switches decay_rate to consolidated rate
  I4 — Second reinforcement does NOT change decay_rate again
  I5 — Decay pass uses per-node min_strength as floor
  I6 — High-importance memory never decays below its min_strength floor
"""
import math
import uuid
import pytest
from memory_service.memory_repo import _apply_decay


class TestNewConfigFields:
    def test_new_config_fields_exist_with_correct_defaults(self):
        from memory_service.config import Settings
        s = Settings()
        assert s.initial_strength_factor == pytest.approx(0.4)
        assert s.memory_initial_decay_rate == pytest.approx(0.07)
        assert s.memory_consolidated_decay_rate == pytest.approx(0.01)
        assert s.importance_floor_factor == pytest.approx(0.3)
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd /home/oliver/projects/graph-memory-fabric
pytest tests/test_wp048_two_speed_decay.py::TestNewConfigFields -v 2>&1 | tail -20
```

Expected: FAIL — `Settings` has no `initial_strength_factor`.

- [ ] **Step 3: Add the four new fields to `config.py`**

In `memory_service/config.py`, add after `memory_decay_rate`:

```python
    memory_decay_rate: float = 0.01
    edge_decay_rate: float = 0.005
    initial_strength_factor: float = 0.4
    memory_initial_decay_rate: float = 0.07
    memory_consolidated_decay_rate: float = 0.01
    importance_floor_factor: float = 0.3
    recall_strength_increment: float = 0.05
    # ... rest unchanged
```

- [ ] **Step 4: Run config test to confirm it passes**

```bash
pytest tests/test_wp048_two_speed_decay.py::TestNewConfigFields -v 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add memory_service/config.py tests/test_wp048_two_speed_decay.py
git commit -m "feat: add WP-048 config fields (initial_strength_factor, two decay rates, importance_floor_factor)"
```

---

## Task 2: Unit tests for decay floor and initial strength formula

**Files:**
- Modify: `tests/test_wp048_two_speed_decay.py`

- [ ] **Step 6: Add unit tests for `_apply_decay` with per-node min_strength and initial strength formula**

Append to `tests/test_wp048_two_speed_decay.py`:

```python
class TestApplyDecayMinStrength:
    def test_decay_floor_respected(self):
        """_apply_decay must not go below min_strength."""
        result = _apply_decay(current=0.5, rate=0.07, days=365.0, min_strength=0.3)
        assert result >= 0.3

    def test_decay_without_floor_reaches_near_zero(self):
        """Without a floor, strength decays to near zero over long period."""
        result = _apply_decay(current=0.4, rate=0.07, days=365.0, min_strength=0.0)
        assert result < 0.01

    def test_fast_rate_half_life_approx_10_days(self):
        """At rate=0.07, half-life should be ~10 days (ln2/0.07 ≈ 9.9)."""
        half_life = math.log(2) / 0.07
        result = _apply_decay(current=1.0, rate=0.07, days=half_life)
        assert abs(result - 0.5) < 0.02

    def test_slow_rate_half_life_approx_69_days(self):
        """At rate=0.01, half-life should be ~69 days (ln2/0.01 ≈ 69.3)."""
        half_life = math.log(2) / 0.01
        result = _apply_decay(current=1.0, rate=0.01, days=half_life)
        assert abs(result - 0.5) < 0.02


class TestInitialStrengthFormula:
    def test_importance_5_initial_strength(self):
        """importance=5, factor=0.4 → strength = 0.4 * 5/5 = 0.4"""
        factor = 0.4
        importance = 5
        expected = factor * (importance / 5.0)
        assert abs(expected - 0.4) < 0.001

    def test_importance_3_initial_strength(self):
        """importance=3, factor=0.4 → strength = 0.4 * 3/5 = 0.24"""
        factor = 0.4
        importance = 3
        expected = factor * (importance / 5.0)
        assert abs(expected - 0.24) < 0.001

    def test_importance_1_initial_strength(self):
        """importance=1, factor=0.4 → strength = 0.4 * 1/5 = 0.08"""
        factor = 0.4
        importance = 1
        expected = factor * (importance / 5.0)
        assert abs(expected - 0.08) < 0.001
```

- [ ] **Step 7: Run unit tests**

```bash
pytest tests/test_wp048_two_speed_decay.py -v -k "not integration" 2>&1 | tail -20
```

Expected: All unit tests PASS.

---

## Task 3: Change `add_memory` — lower initial strength, fast decay rate, store `min_strength`

**Files:**
- Modify: `memory_service/memory_repo.py:12-61`
- Modify: `memory_service/main.py` (pass new params to `add_memory`)

`add_memory` currently takes `decay_rate: float` as a parameter. We need two new params: `initial_strength_factor` and `importance_floor_factor`. The caller (`main.py`) reads these from `settings`.

- [ ] **Step 8: Write the integration test for initial memory state**

Append to `tests/test_wp048_two_speed_decay.py`:

```python
_AGENT_ID = "test-wp048-agent"


def _cleanup(test_driver, *ids):
    with test_driver.session() as s:
        for mid in ids:
            s.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mid)
        s.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)


@pytest.mark.integration
class TestInitialMemoryState:
    def test_new_memory_has_low_initial_strength(self, client, test_driver):
        """New memory importance=5 → strength = 0.4 * 1.0 = 0.4 (not 1.0)."""
        fact = f"wp048-initial-strength-{uuid.uuid4()}"
        resp = client.post("/memory", json={
            "fact": fact, "type": "fact", "agent_id": _AGENT_ID, "importance": 5,
        })
        assert resp.status_code == 200
        mid = resp.json()["memory_id"]
        try:
            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.strength AS strength, "
                    "m.decay_rate AS decay_rate, m.min_strength AS min_strength",
                    id=mid,
                ).single()
            assert row["strength"] == pytest.approx(0.4, abs=0.001)
            assert row["decay_rate"] == pytest.approx(0.07, abs=0.001)
        finally:
            _cleanup(test_driver, mid)

    def test_new_memory_importance_3_initial_strength(self, client, test_driver):
        """importance=3, factor=0.4 → strength = 0.24."""
        fact = f"wp048-imp3-{uuid.uuid4()}"
        resp = client.post("/memory", json={
            "fact": fact, "type": "fact", "agent_id": _AGENT_ID, "importance": 3,
        })
        assert resp.status_code == 200
        mid = resp.json()["memory_id"]
        try:
            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.strength AS strength",
                    id=mid,
                ).single()
            assert row["strength"] == pytest.approx(0.24, abs=0.001)
        finally:
            _cleanup(test_driver, mid)

    def test_new_memory_has_min_strength_stored(self, client, test_driver):
        """importance=5, floor_factor=0.3 → min_strength = 0.3."""
        fact = f"wp048-min-strength-{uuid.uuid4()}"
        resp = client.post("/memory", json={
            "fact": fact, "type": "fact", "agent_id": _AGENT_ID, "importance": 5,
        })
        assert resp.status_code == 200
        mid = resp.json()["memory_id"]
        try:
            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.min_strength AS min_strength",
                    id=mid,
                ).single()
            assert row["min_strength"] == pytest.approx(0.3, abs=0.001)
        finally:
            _cleanup(test_driver, mid)

    def test_new_memory_importance_1_min_strength(self, client, test_driver):
        """importance=1, floor_factor=0.3 → min_strength = 0.06."""
        fact = f"wp048-min-str-imp1-{uuid.uuid4()}"
        resp = client.post("/memory", json={
            "fact": fact, "type": "fact", "agent_id": _AGENT_ID, "importance": 1,
        })
        assert resp.status_code == 200
        mid = resp.json()["memory_id"]
        try:
            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.min_strength AS min_strength",
                    id=mid,
                ).single()
            assert row["min_strength"] == pytest.approx(0.06, abs=0.001)
        finally:
            _cleanup(test_driver, mid)
```

- [ ] **Step 9: Run to confirm tests fail**

```bash
pytest tests/test_wp048_two_speed_decay.py::TestInitialMemoryState -v -m integration 2>&1 | tail -20
```

Expected: Tests fail (strength is still old value of `importance/5.0`).

- [ ] **Step 10: Update `add_memory` signature and Cypher**

In `memory_service/memory_repo.py`, change the `add_memory` function signature from:

```python
def add_memory(session, req, memory_id: str, embedding: list, now: str, decay_rate: float) -> None:
```

to:

```python
def add_memory(
    session,
    req,
    memory_id: str,
    embedding: list,
    now: str,
    decay_rate: float,
    initial_strength_factor: float = 0.4,
    importance_floor_factor: float = 0.3,
) -> None:
```

Then change the two computed values passed to the Cypher (lines 58-59 currently):

```python
        strength=req.importance / 5.0,
        last_reinforced_at=now,
        decay_rate=decay_rate,
```

to:

```python
        strength=initial_strength_factor * (req.importance / 5.0),
        min_strength=importance_floor_factor * (req.importance / 5.0),
        last_reinforced_at=now,
        decay_rate=decay_rate,
```

And add `min_strength: $min_strength,` to the `CREATE (m:Memory {...})` Cypher block (after `decay_rate`):

```cypher
        CREATE (m:Memory {
            id: $id,
            fact: $fact,
            so_what: $so_what,
            text: $text,
            type: $type,
            tags: $tags,
            importance: $importance,
            created_at: $created_at,
            last_used_at: $last_used_at,
            embedding: $embedding,
            strength: $strength,
            min_strength: $min_strength,
            recall_count: 0,
            reinforcement_count: 0,
            last_reinforced_at: $last_reinforced_at,
            decay_rate: $decay_rate
        })
```

- [ ] **Step 11: Update `main.py` to pass new params to `add_memory`**

Find the call to `memory_repo.add_memory` in `memory_service/main.py` (around line 99):

```python
            memory_repo.add_memory(session, req, memory_id, embedding, now, settings.memory_decay_rate)
```

Replace with:

```python
            memory_repo.add_memory(
                session, req, memory_id, embedding, now,
                decay_rate=settings.memory_initial_decay_rate,
                initial_strength_factor=settings.initial_strength_factor,
                importance_floor_factor=settings.importance_floor_factor,
            )
```

- [ ] **Step 12: Run integration tests**

```bash
pytest tests/test_wp048_two_speed_decay.py::TestInitialMemoryState -v -m integration 2>&1 | tail -20
```

Expected: All 4 tests PASS.

- [ ] **Step 13: Update existing tests that hard-code old initial-strength expectations**

In `tests/test_wp029_reinforcement.py`, two tests assert the old `importance/5.0` formula:

**Test 1** (`test_new_memory_has_strength_seeded_from_importance`, line ~37):
```python
                assert abs(row["strength"] - 0.8) < 0.001
                assert row["decay_rate"] == pytest.approx(0.01, abs=0.0001)
```
Change to:
```python
                # WP-048: initial_strength_factor=0.4, so importance=4 → 0.4 * 4/5 = 0.32
                assert abs(row["strength"] - 0.32) < 0.001
                # WP-048: new memories start with fast decay rate
                assert row["decay_rate"] == pytest.approx(0.07, abs=0.0001)
```

**Test 2** (`test_importance_1_gives_strength_0_2`, line ~60):
```python
                assert abs(row["strength"] - 0.2) < 0.001
```
Change to:
```python
                # WP-048: initial_strength_factor=0.4, importance=1 → 0.4 * 1/5 = 0.08
                assert abs(row["strength"] - 0.08) < 0.001
```

**Test 3** (`test_search_increments_recall_count`, line ~94):
```python
            initial_strength = 3 / 5.0  # 0.6
```
Change to:
```python
            initial_strength = 0.4 * (3 / 5.0)  # 0.24 — WP-048 initial_strength_factor=0.4
```

- [ ] **Step 14: Run all reinforcement tests**

```bash
pytest tests/test_wp029_reinforcement.py -v 2>&1 | tail -20
```

Expected: All tests PASS.

- [ ] **Step 15: Commit**

```bash
git add memory_service/memory_repo.py memory_service/main.py tests/test_wp029_reinforcement.py tests/test_wp048_two_speed_decay.py
git commit -m "feat: lower initial strength + store min_strength + use fast decay rate on creation"
```

---

## Task 4: Consolidation — switch to slow decay rate on first reinforcement

**Files:**
- Modify: `memory_service/memory_repo.py:588-646` (`reinforce_memory`)
- Modify: `memory_service/main.py` (pass `consolidated_decay_rate` to `reinforce_memory`)

- [ ] **Step 16: Write the consolidation tests**

Append to `tests/test_wp048_two_speed_decay.py`:

```python
@pytest.mark.integration
class TestConsolidationOnFirstReinforcement:
    def test_first_reinforcement_switches_to_slow_decay_rate(self, client, test_driver):
        """After first reinforcement, decay_rate must switch to consolidated rate (0.01)."""
        fact = f"wp048-consolidate-{uuid.uuid4()}"
        resp = client.post("/memory", json={
            "fact": fact, "type": "fact", "agent_id": _AGENT_ID, "importance": 3,
        })
        assert resp.status_code == 200
        mid = resp.json()["memory_id"]
        try:
            # Confirm fast rate before reinforcement
            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.decay_rate AS rate, "
                    "m.reinforcement_count AS rc",
                    id=mid,
                ).single()
            assert row["rate"] == pytest.approx(0.07, abs=0.001)
            assert row["rc"] == 0

            # Reinforce once
            r = client.post(f"/memory/{mid}/reinforce", json={
                "strength_increment": 0.2,
                "co_recalled_ids": [],
            })
            assert r.status_code == 200

            # Confirm decay_rate has switched to slow rate
            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.decay_rate AS rate, "
                    "m.reinforcement_count AS rc",
                    id=mid,
                ).single()
            assert row["rate"] == pytest.approx(0.01, abs=0.001), (
                "After first reinforcement, decay_rate must switch to consolidated rate 0.01"
            )
            assert row["rc"] == 1
        finally:
            _cleanup(test_driver, mid)

    def test_second_reinforcement_does_not_change_decay_rate(self, client, test_driver):
        """Subsequent reinforcements must not change decay_rate again."""
        fact = f"wp048-second-reinforce-{uuid.uuid4()}"
        resp = client.post("/memory", json={
            "fact": fact, "type": "fact", "agent_id": _AGENT_ID, "importance": 3,
        })
        assert resp.status_code == 200
        mid = resp.json()["memory_id"]
        try:
            # Two reinforcements
            for _ in range(2):
                client.post(f"/memory/{mid}/reinforce", json={
                    "strength_increment": 0.2,
                    "co_recalled_ids": [],
                })

            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.decay_rate AS rate, "
                    "m.reinforcement_count AS rc",
                    id=mid,
                ).single()
            assert row["rate"] == pytest.approx(0.01, abs=0.001)
            assert row["rc"] == 2
        finally:
            _cleanup(test_driver, mid)
```

- [ ] **Step 17: Run to confirm tests fail**

```bash
pytest tests/test_wp048_two_speed_decay.py::TestConsolidationOnFirstReinforcement -v -m integration 2>&1 | tail -20
```

Expected: FAIL — decay_rate does not change on first reinforcement yet.

- [ ] **Step 18: Update `reinforce_memory` signature**

Change the signature from:

```python
def reinforce_memory(
    session,
    memory_id: str,
    strength_increment: float,
    edge_increment: float,
    co_recalled_ids: list[str],
    now_iso: str,
) -> float:
```

to:

```python
def reinforce_memory(
    session,
    memory_id: str,
    strength_increment: float,
    edge_increment: float,
    co_recalled_ids: list[str],
    now_iso: str,
    consolidated_decay_rate: float | None = None,
) -> float:
```

- [ ] **Step 19: Update the Cypher in `reinforce_memory` to conditionally switch decay rate**

Replace the `SET` block in `reinforce_memory` (the first `session.run` call, currently around line 601):

```python
    result = session.run(
        """
        MATCH (m:Memory {id: $id})
        SET m.reinforcement_count = coalesce(m.reinforcement_count, 0) + 1,
            m.last_reinforced_at = $now,
            m.strength = CASE
                WHEN coalesce(m.strength, m.importance / 5.0) + $increment >= 1.0
                THEN 1.0
                ELSE coalesce(m.strength, m.importance / 5.0) + $increment
            END,
            m.decay_rate = CASE
                WHEN $consolidated_rate IS NOT NULL AND coalesce(m.reinforcement_count, 0) = 0
                THEN $consolidated_rate
                ELSE m.decay_rate
            END
        RETURN m.strength AS strength
        """,
        id=memory_id,
        increment=strength_increment,
        now=now_iso,
        consolidated_rate=consolidated_decay_rate,
    )
```

Note: `coalesce(m.reinforcement_count, 0) = 0` checks the count *before* the increment, which is the correct consolidation trigger — this is the first reinforcement.

- [ ] **Step 20: Update `main.py` to pass `consolidated_decay_rate` to `reinforce_memory`**

Find the call to `memory_repo.reinforce_memory` in `memory_service/main.py`. It looks like:

```python
    new_strength = memory_repo.reinforce_memory(
        session,
        memory_id,
        strength_increment=settings.explicit_strength_increment,
        edge_increment=settings.edge_explicit_increment,
        co_recalled_ids=req.co_recalled_ids,
        now_iso=now_iso,
    )
```

Add the new parameter:

```python
    new_strength = memory_repo.reinforce_memory(
        session,
        memory_id,
        strength_increment=settings.explicit_strength_increment,
        edge_increment=settings.edge_explicit_increment,
        co_recalled_ids=req.co_recalled_ids,
        now_iso=now_iso,
        consolidated_decay_rate=settings.memory_consolidated_decay_rate,
    )
```

- [ ] **Step 21: Run consolidation tests**

```bash
pytest tests/test_wp048_two_speed_decay.py::TestConsolidationOnFirstReinforcement -v -m integration 2>&1 | tail -20
```

Expected: Both tests PASS.

- [ ] **Step 22: Commit**

```bash
git add memory_service/memory_repo.py memory_service/main.py tests/test_wp048_two_speed_decay.py
git commit -m "feat: consolidate decay rate to slow on first reinforcement (WP-048)"
```

---

## Task 5: Per-node `min_strength` floor in decay passes

**Files:**
- Modify: `memory_service/memory_repo.py` — `decay_pass`, `short_rest`, `long_rest`

Currently all three decay functions call `_apply_decay_modulated` or `_apply_decay` with the global `min_strength` parameter. We change them to read `m.min_strength` from each node row and use that as the per-node floor, falling back to the global `min_strength` for nodes that don't have the property (older memories).

- [ ] **Step 23: Write the importance floor integration test**

Append to `tests/test_wp048_two_speed_decay.py`:

```python
@pytest.mark.integration
class TestImportanceFloor:
    def test_high_importance_memory_never_decays_below_floor(self, client, test_driver):
        """importance=5 memory must never drop below min_strength=0.3 after decay."""
        fact = f"wp048-floor-{uuid.uuid4()}"
        resp = client.post("/memory", json={
            "fact": fact, "type": "fact", "agent_id": _AGENT_ID, "importance": 5,
        })
        assert resp.status_code == 200
        mid = resp.json()["memory_id"]
        try:
            # Simulate extreme decay by directly setting last_reinforced_at far in the past
            past = "2020-01-01T00:00:00+00:00"
            with test_driver.session() as s:
                s.run(
                    "MATCH (m:Memory {id: $id}) SET m.last_reinforced_at = $past",
                    id=mid, past=past,
                )

            # Run a decay pass
            r = client.post("/memory/maintenance/decay")
            assert r.status_code == 200

            # Verify strength didn't go below min_strength
            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.strength AS strength, "
                    "m.min_strength AS min_strength",
                    id=mid,
                ).single()
            assert row["min_strength"] == pytest.approx(0.3, abs=0.001)
            assert row["strength"] >= row["min_strength"] - 0.001, (
                f"Strength {row['strength']} dropped below floor {row['min_strength']}"
            )
        finally:
            _cleanup(test_driver, mid)

    def test_low_importance_memory_can_decay_near_zero(self, client, test_driver):
        """importance=1 memory (floor=0.06) can decay close to zero."""
        fact = f"wp048-low-floor-{uuid.uuid4()}"
        resp = client.post("/memory", json={
            "fact": fact, "type": "fact", "agent_id": _AGENT_ID, "importance": 1,
        })
        assert resp.status_code == 200
        mid = resp.json()["memory_id"]
        try:
            past = "2020-01-01T00:00:00+00:00"
            with test_driver.session() as s:
                s.run(
                    "MATCH (m:Memory {id: $id}) SET m.last_reinforced_at = $past",
                    id=mid, past=past,
                )

            r = client.post("/memory/maintenance/decay")
            assert r.status_code == 200

            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.strength AS strength, "
                    "m.min_strength AS min_strength",
                    id=mid,
                ).single()
            # min_strength = 0.3 * 1/5 = 0.06; strength should be at/near floor
            assert row["min_strength"] == pytest.approx(0.06, abs=0.001)
            assert row["strength"] >= row["min_strength"] - 0.001
        finally:
            _cleanup(test_driver, mid)
```

- [ ] **Step 24: Run floor tests to confirm they fail**

```bash
pytest tests/test_wp048_two_speed_decay.py::TestImportanceFloor -v -m integration 2>&1 | tail -20
```

Expected: FAIL — decay pass still uses global `min_strength=0.0` and will decay below the node's floor.

- [ ] **Step 25: Update `decay_pass` to read per-node `min_strength`**

In `memory_service/memory_repo.py`, in `decay_pass`, the node query currently returns `m.id, m.strength, m.last_reinforced_at, m.decay_rate, incoming_weight_sum`. Add `m.min_strength`:

```python
    node_rows = list(session.run(
        f"""
        MATCH (m:Memory)
        WHERE m.strength IS NOT NULL AND m.last_reinforced_at IS NOT NULL AND m.decay_rate IS NOT NULL
        {node_filter}
        OPTIONAL MATCH (pred:Memory)-[inc:RELATED_TO|LEADS_TO]->(m)
        WITH m, coalesce(sum(inc.weight), 0.0) AS incoming_weight_sum
        RETURN m.id AS id, m.strength AS strength,
               m.last_reinforced_at AS anchor, m.decay_rate AS rate,
               m.min_strength AS min_strength,
               incoming_weight_sum
        """,
        node_ids=node_ids if node_ids is not None else [],
    ))
```

Then in the loop, use the per-node floor (falling back to the global `min_strength` param for nodes that predate WP-048):

```python
    for row in node_rows:
        try:
            anchor = _parse_iso(row["anchor"])
        except (ValueError, TypeError):
            continue
        days = (now - anchor).total_seconds() / 86400.0
        node_floor = row["min_strength"] if row["min_strength"] is not None else min_strength
        node_updates.append({
            "id": row["id"],
            "new_val": _apply_decay_modulated(
                row["strength"], row["rate"], days,
                row["incoming_weight_sum"],
                edge_modulation_factor, edge_modulation_cap,
                node_floor,
            ),
        })
```

- [ ] **Step 26: Apply the same per-node floor change to `short_rest`**

In `short_rest` (around line 712), the node query also needs `m.min_strength`:

```python
        RETURN m.id AS id, m.strength AS strength,
               m.last_reinforced_at AS anchor, m.decay_rate AS rate,
               m.last_used_at AS last_used_at, m.recall_count AS recall_count,
               m.min_strength AS min_strength,
               incoming_weight_sum
```

And in the loop (around line 756):

```python
        node_floor = row["min_strength"] if row["min_strength"] is not None else min_strength
        new_val = _apply_decay_modulated(
            row["strength"], row["rate"], days,
            row["incoming_weight_sum"],
            edge_modulation_factor, edge_modulation_cap,
            node_floor,
        )
```

Note: `short_rest` receives `min_strength` as the parameter named in its signature but the parameter is called `min_strength` — it's used as the fallback for nodes without the property.

- [ ] **Step 27: Run floor tests**

```bash
pytest tests/test_wp048_two_speed_decay.py::TestImportanceFloor -v -m integration 2>&1 | tail -20
```

Expected: Both tests PASS.

- [ ] **Step 28: Commit**

```bash
git add memory_service/memory_repo.py tests/test_wp048_two_speed_decay.py
git commit -m "feat: use per-node min_strength as decay floor in decay_pass and short_rest"
```

---

## Task 6: Document new config values in `.env.example`

**Files:**
- Modify: `.env.example`

- [ ] **Step 29: Add new config values to `.env.example`**

Find the decay-related section in `.env.example` and add after `MEMORY_DECAY_RATE`:

```bash
# WP-048: Two-speed decay + importance floor
# Multiplier on (importance/5) for initial memory strength (default: 0.4)
# INITIAL_STRENGTH_FACTOR=0.4

# Fast decay rate applied to new memories before first reinforcement (default: 0.07, ~10-day half-life)
# MEMORY_INITIAL_DECAY_RATE=0.07

# Slow decay rate after first reinforcement / consolidation (default: 0.01, ~69-day half-life)
# MEMORY_CONSOLIDATED_DECAY_RATE=0.01

# Multiplier on (importance/5) for per-node min_strength floor (default: 0.3)
# importance=5 → floor=0.3; importance=1 → floor=0.06
# IMPORTANCE_FLOOR_FACTOR=0.3
```

- [ ] **Step 30: Commit**

```bash
git add .env.example
git commit -m "docs: document WP-048 config values in .env.example"
```

---

## Task 7: Full test suite and backlog update

- [ ] **Step 31: Run full test suite**

```bash
pytest tests/ -v 2>&1 | tail -40
```

Expected: All tests pass (integration tests may skip if Memgraph not running, but no failures).

- [ ] **Step 32: Move WP-048 to Completed in BACKLOG.md and update CHANGELOG.md**

Delete the WP-048 row from `BACKLOG.md` Prioritised Backlog. Add entry to `docs/CHANGELOG.md`.

- [ ] **Step 33: Final commit**

```bash
git add BACKLOG.md docs/CHANGELOG.md
git commit -m "WP-048: Two-speed decay + importance floor to protect core memories"
```
