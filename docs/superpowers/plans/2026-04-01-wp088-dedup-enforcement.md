# WP-088: Graph Dedup and Agent-ID Enforcement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop duplicate Memory nodes accumulating in the graph, clean up existing duplicates by merging them into their canonical nodes (with reinforcement), and remove the silent `agent_id` fallback that was mis-attributing memories to `claude-code`.

**Architecture:** Three orthogonal changes — (1) a new `find_duplicate_memory()` repo function + pre-write gate in `POST /memory`, (2) a `dedup_cleanup.py` one-time batch script, and (3) `memory_add` MCP tool made to require an explicit `agent_id`. All three share the same `memory_dedup_threshold` setting.

**Tech Stack:** FastAPI, Memgraph (neo4j driver), sentence-transformers, FastMCP, pytest

---

## Context

The graph has accumulated a large number of duplicate Memory nodes. Root causes:
1. `POST /memory` always `CREATE`s a new Memory node unconditionally — there is no pre-write dedup check.
2. The MCP `memory_add` tool has `agent_id: str | None = None` with a fallback `agent_id or settings.agent_id` — subagents that omit `agent_id` silently attribute their memories to `"claude-code"`, making it impossible to determine which agent wrote what.

**Intended outcome:**
- Existing duplicates are merged into their canonical node (oldest/highest-importance wins); the canonical is reinforced once per group because repeated writes signal significance.
- Future writes are checked against existing active memories before `CREATE`; exact or near-identical facts return the existing `memory_id` with `deduplicated: true` and reinforce the canonical.
- The MCP tool `memory_add` now requires `agent_id` — callers must identify themselves explicitly.

---

## Critical files

| File | Change |
|------|--------|
| `memory_service/config.py:44` | Add `memory_dedup_threshold: float = 0.05` |
| `memory_service/memory_repo.py` (end of file) | Add `find_duplicate_memory()` function |
| `memory_service/main.py:88-89` | Extend `AddMemoryResponse` with `deduplicated: bool = False` |
| `memory_service/main.py:92-107` | Update `add_memory` handler with pre-write dedup gate |
| `mcp_server/server.py:32-58` | Make `agent_id` required, remove `or settings.agent_id` fallback |
| `tests/test_wp033_mcp_server.py` | Update existing test that asserts the old fallback behaviour |
| `scripts/dedup_cleanup.py` | New one-time cleanup script (new file) |
| `tests/test_wp088_dedup_enforcement.py` | New test file (new file) |

**Reusable functions:**
- `memory_repo.merge_memory(session, source_id, target_id, strategy, default_edge_decay_rate)` — `memory_service/memory_repo.py:583`
- `memory_repo.reinforce_memory(session, memory_id, strength_increment, edge_increment, co_recalled_ids, now_iso, consolidated_decay_rate)` — `memory_service/memory_repo.py:986`
- `get_driver(settings)` — `memory_service/config.py:49`
- Vector search Cypher: `CALL vector_search.search("mem_embedding_idx", 1, $query_vec) YIELD node, distance`
- Settings fields in `reinforce_memory` calls: `settings.explicit_strength_increment`, `settings.edge_explicit_increment`, `settings.memory_consolidated_decay_rate`

---

## Task 1: Config field `memory_dedup_threshold`

**Files:**
- Modify: `memory_service/config.py` (after `chunk_index_capacity`)
- Test: `tests/test_wp088_dedup_enforcement.py`

- [ ] **Step 1.1 — Write failing test**

```python
# tests/test_wp088_dedup_enforcement.py
"""WP-088: Deduplication and agent-ID enforcement. Requires live stack for integration tests."""
import pytest

class TestSettings:
    def test_memory_dedup_threshold_default(self):
        from memory_service.config import Settings
        assert Settings().memory_dedup_threshold == 0.05
```

- [ ] **Step 1.2 — Run to confirm failure**

```
pytest tests/test_wp088_dedup_enforcement.py::TestSettings -x
```
Expected: `AttributeError: 'Settings' object has no attribute 'memory_dedup_threshold'`

- [ ] **Step 1.3 — Add the field**

In `memory_service/config.py`, after the `chunk_index_capacity` line, add:
```python
memory_dedup_threshold: float = 0.05
```

- [ ] **Step 1.4 — Run to confirm green**

```
pytest tests/test_wp088_dedup_enforcement.py::TestSettings -x
```
Expected: PASSED

- [ ] **Step 1.5 — Commit**

```bash
git add memory_service/config.py tests/test_wp088_dedup_enforcement.py
git commit -m "WP-088: add memory_dedup_threshold config field (default 0.05)"
```

---

## Task 2: `find_duplicate_memory()` in `memory_repo.py`

**Files:**
- Modify: `memory_service/memory_repo.py` (append at end of file)
- Modify: `tests/test_wp088_dedup_enforcement.py` (add class)

- [ ] **Step 2.1 — Write failing unit tests**

Append to `tests/test_wp088_dedup_enforcement.py`:

```python
from unittest.mock import MagicMock, call as mock_call


class TestFindDuplicateUnit:
    """Unit tests for find_duplicate_memory — mock session, no live stack."""

    def _mock_session(self, exact_hit: str | None, vector_hit: str | None):
        """Return a mock session whose run() returns exact_hit on first call,
        vector_hit on second call. None means empty result."""
        def make_result(id_val):
            if id_val is None:
                m = MagicMock()
                m.single.return_value = None
                return m
            else:
                m = MagicMock()
                m.single.return_value = {"id": id_val}
                return m

        session = MagicMock()
        session.run.side_effect = [make_result(exact_hit), make_result(vector_hit)]
        return session

    def test_exact_match_returns_immediately_without_vector_search(self):
        from memory_service.memory_repo import find_duplicate_memory
        session = self._mock_session(exact_hit="existing-uuid", vector_hit=None)
        result = find_duplicate_memory(session, "some fact", [0.1, 0.2], threshold=0.05)
        assert result == "existing-uuid"
        assert session.run.call_count == 1  # vector search never fired

    def test_exact_match_miss_triggers_vector_search(self):
        from memory_service.memory_repo import find_duplicate_memory
        session = self._mock_session(exact_hit=None, vector_hit="vec-match-uuid")
        result = find_duplicate_memory(session, "some fact", [0.1, 0.2], threshold=0.05)
        assert result == "vec-match-uuid"
        assert session.run.call_count == 2

    def test_no_match_returns_none(self):
        from memory_service.memory_repo import find_duplicate_memory
        session = self._mock_session(exact_hit=None, vector_hit=None)
        result = find_duplicate_memory(session, "unique fact", [0.1, 0.2], threshold=0.05)
        assert result is None

    def test_exact_check_excludes_non_active_statuses(self):
        from memory_service.memory_repo import find_duplicate_memory
        session = MagicMock()
        r = MagicMock(); r.single.return_value = None
        session.run.return_value = r
        find_duplicate_memory(session, "fact", [0.1], threshold=0.05)
        first_query = session.run.call_args_list[0][0][0]
        assert "active" in first_query

    def test_vector_check_excludes_non_active_statuses(self):
        from memory_service.memory_repo import find_duplicate_memory
        session = MagicMock()
        r = MagicMock(); r.single.return_value = None
        session.run.return_value = r
        find_duplicate_memory(session, "fact", [0.1], threshold=0.05)
        second_query = session.run.call_args_list[1][0][0]
        assert "active" in second_query
```

- [ ] **Step 2.2 — Run to confirm failure**

```
pytest tests/test_wp088_dedup_enforcement.py::TestFindDuplicateUnit -x
```
Expected: `ImportError` (function does not exist yet)

- [ ] **Step 2.3 — Implement `find_duplicate_memory` at end of `memory_repo.py`**

```python
def find_duplicate_memory(
    session,
    fact: str,
    embedding: list,
    threshold: float,
) -> str | None:
    """Return the id of an existing active Memory with identical or near-identical fact.

    Checks in order:
    1. Exact case-insensitive match on the 'fact' field.
    2. Vector similarity — nearest neighbour with cosine distance <= threshold.

    Returns None if no duplicate is found.
    Excludes merged and archived nodes from both checks.
    """
    # Step 1: exact match
    result = session.run(
        """
        MATCH (m:Memory)
        WHERE toLower(m.fact) = toLower($fact)
          AND (m.status IS NULL OR m.status = 'active')
        RETURN m.id AS id
        LIMIT 1
        """,
        fact=fact,
    )
    record = result.single()
    if record:
        return record["id"]

    # Step 2: vector similarity (only if exact match missed)
    result = session.run(
        """
        CALL vector_search.search("mem_embedding_idx", 1, $query_vec)
        YIELD node, distance
        WHERE (node.status IS NULL OR node.status = 'active')
          AND distance <= $threshold
        RETURN node.id AS id
        LIMIT 1
        """,
        query_vec=embedding,
        threshold=threshold,
    )
    record = result.single()
    if record:
        return record["id"]

    return None
```

- [ ] **Step 2.4 — Run to confirm green**

```
pytest tests/test_wp088_dedup_enforcement.py::TestFindDuplicateUnit -x
```
Expected: 5 PASSED

- [ ] **Step 2.5 — Commit**

```bash
git add memory_service/memory_repo.py tests/test_wp088_dedup_enforcement.py
git commit -m "WP-088: add find_duplicate_memory() to memory_repo"
```

---

## Task 3: Extend `AddMemoryResponse` + pre-write dedup gate

**Files:**
- Modify: `memory_service/main.py:88-89` and `memory_service/main.py:92-107`
- Modify: `tests/test_wp088_dedup_enforcement.py` (add classes)

- [ ] **Step 3.1 — Write unit tests for the response model**

Append to `tests/test_wp088_dedup_enforcement.py`:

```python
class TestAddMemoryResponseModel:
    def test_deduplicated_defaults_false(self):
        from memory_service.main import AddMemoryResponse
        r = AddMemoryResponse(memory_id="abc-123")
        assert r.deduplicated is False

    def test_deduplicated_can_be_true(self):
        from memory_service.main import AddMemoryResponse
        r = AddMemoryResponse(memory_id="abc-123", deduplicated=True)
        assert r.deduplicated is True
```

- [ ] **Step 3.2 — Run to confirm failure**

```
pytest tests/test_wp088_dedup_enforcement.py::TestAddMemoryResponseModel -x
```
Expected: `ValidationError` or `AttributeError` — field doesn't exist yet

- [ ] **Step 3.3 — Add `deduplicated` to `AddMemoryResponse` in `main.py`**

In `memory_service/main.py`, change (lines 88-89):
```python
class AddMemoryResponse(BaseModel):
    memory_id: str
```
to:
```python
class AddMemoryResponse(BaseModel):
    memory_id: str
    deduplicated: bool = False
```

- [ ] **Step 3.4 — Run to confirm green**

```
pytest tests/test_wp088_dedup_enforcement.py::TestAddMemoryResponseModel -x
```
Expected: 2 PASSED

- [ ] **Step 3.5 — Write integration tests for the dedup gate**

Append to `tests/test_wp088_dedup_enforcement.py`:

```python
import uuid as _uuid
from tests.conftest import cleanup_nodes, get_memory_node

_DEDUP_AGENT = "test-wp088-agent"
_DEDUP_CONTEXT = {"Agent": _DEDUP_AGENT}


def _cleanup_dedup(driver, *memory_ids):
    cleanup_nodes(driver, *memory_ids, extra_ids=_DEDUP_CONTEXT)


@pytest.mark.integration
class TestPreWriteDedup:
    def test_exact_duplicate_returns_same_id_deduplicated_true(self, client, test_driver):
        fact = f"WP-088 exact dedup test {_uuid.uuid4()}"
        body = {"fact": fact, "type": "fact", "agent_id": _DEDUP_AGENT}
        r1 = client.post("/memory", json=body)
        assert r1.status_code == 200
        mid1 = r1.json()["memory_id"]
        assert r1.json()["deduplicated"] is False

        r2 = client.post("/memory", json=body)
        assert r2.status_code == 200
        assert r2.json()["memory_id"] == mid1
        assert r2.json()["deduplicated"] is True

        _cleanup_dedup(test_driver, mid1)

    def test_reinforcement_count_incremented_on_dedup(self, client, test_driver):
        fact = f"WP-088 reinforce test {_uuid.uuid4()}"
        body = {"fact": fact, "type": "fact", "agent_id": _DEDUP_AGENT}
        r1 = client.post("/memory", json=body)
        mid = r1.json()["memory_id"]

        client.post("/memory", json=body)  # duplicate write

        node = get_memory_node(test_driver, mid)
        assert node["reinforcement_count"] >= 1

        _cleanup_dedup(test_driver, mid)

    def test_different_fact_creates_new_memory(self, client, test_driver):
        suffix = _uuid.uuid4()
        r1 = client.post("/memory", json={"fact": f"first fact {suffix}", "type": "fact", "agent_id": _DEDUP_AGENT})
        r2 = client.post("/memory", json={"fact": f"second fact {suffix}", "type": "fact", "agent_id": _DEDUP_AGENT})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["memory_id"] != r2.json()["memory_id"]
        assert r2.json()["deduplicated"] is False
        _cleanup_dedup(test_driver, r1.json()["memory_id"], r2.json()["memory_id"])


@pytest.mark.integration
class TestPreWriteSemanticDedup:
    def test_near_identical_fact_deduplicates(self, client, test_driver):
        # These two are semantically near-identical with all-MiniLM-L6-v2.
        # Expected cosine distance < 0.05.
        suffix = _uuid.uuid4()
        fact1 = f"Oliver prefers short feedback loops {suffix}"
        fact2 = f"Oliver likes short feedback cycles {suffix}"
        r1 = client.post("/memory", json={"fact": fact1, "type": "fact", "agent_id": _DEDUP_AGENT})
        assert r1.status_code == 200
        mid1 = r1.json()["memory_id"]

        r2 = client.post("/memory", json={"fact": fact2, "type": "fact", "agent_id": _DEDUP_AGENT})
        assert r2.status_code == 200
        assert r2.json()["memory_id"] == mid1, (
            "Near-identical facts should resolve to the same memory_id. "
            "If this fails, the model may place these further apart than 0.05 — "
            "consider adjusting the test phrases."
        )
        assert r2.json()["deduplicated"] is True
        _cleanup_dedup(test_driver, mid1)
```

- [ ] **Step 3.6 — Run to confirm failure**

```
pytest tests/test_wp088_dedup_enforcement.py::TestPreWriteDedup tests/test_wp088_dedup_enforcement.py::TestPreWriteSemanticDedup -x -m integration
```
Expected: assertion errors — second POST creates a new ID instead of returning the existing one

- [ ] **Step 3.7 — Update `add_memory` handler in `main.py`**

Replace the handler body (lines 93–107) with:

```python
@app.post("/memory", response_model=AddMemoryResponse)
async def add_memory(req: AddMemoryRequest, request: Request) -> AddMemoryResponse:
    embedding = get_embedding(req.text)
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            existing_id = memory_repo.find_duplicate_memory(
                session,
                req.fact,
                embedding,
                settings.memory_dedup_threshold,
            )
            if existing_id is not None:
                memory_repo.reinforce_memory(
                    session,
                    existing_id,
                    strength_increment=settings.explicit_strength_increment,
                    edge_increment=settings.edge_explicit_increment,
                    co_recalled_ids=[],
                    now_iso=now,
                    consolidated_decay_rate=settings.memory_consolidated_decay_rate,
                )
                return AddMemoryResponse(memory_id=existing_id, deduplicated=True)
            memory_id = str(uuid.uuid4())
            memory_repo.add_memory(
                session, req, memory_id, embedding, now,
                decay_rate=settings.memory_initial_decay_rate,
                initial_strength_factor=settings.initial_strength_factor,
                importance_floor_factor=settings.importance_floor_factor,
            )
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return AddMemoryResponse(memory_id=memory_id)
```

- [ ] **Step 3.8 — Run integration tests**

```
pytest tests/test_wp088_dedup_enforcement.py::TestPreWriteDedup tests/test_wp088_dedup_enforcement.py::TestPreWriteSemanticDedup -x -m integration
```
Expected: all PASSED

- [ ] **Step 3.9 — Regression check on existing add_memory tests**

```
pytest tests/test_add_memory.py -x -m integration
```
Expected: all PASSED (the `deduplicated=False` default means all non-duplicate writes are unchanged)

- [ ] **Step 3.10 — Commit**

```bash
git add memory_service/main.py tests/test_wp088_dedup_enforcement.py
git commit -m "WP-088: pre-write dedup gate on POST /memory with reinforcement on hit"
```

---

## Task 4: MCP `agent_id` enforcement

**Files:**
- Modify: `mcp_server/server.py:32-58`
- Modify: `tests/test_wp033_mcp_server.py` (update existing test that tests the old fallback)
- Modify: `tests/test_wp088_dedup_enforcement.py` (add class)

- [ ] **Step 4.1 — Write failing MCP unit tests**

Append to `tests/test_wp088_dedup_enforcement.py`:

```python
class TestMcpAgentIdRequired:
    def test_memory_add_without_agent_id_raises(self):
        """Calling memory_add without agent_id must raise TypeError — no fallback."""
        from mcp_server.server import memory_add
        import pytest
        with pytest.raises(TypeError, match="agent_id"):
            memory_add(fact="some fact", type="fact")  # agent_id omitted

    def test_memory_add_passes_explicit_agent_id_to_client(self):
        """The explicit agent_id must be forwarded verbatim — settings.agent_id not used."""
        from unittest.mock import patch, MagicMock
        from mcp_server.server import memory_add
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.add_memory.return_value = "new-memory-id"
        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            result = memory_add(fact="some fact", type="fact", agent_id="my-custom-agent")
        assert result == "new-memory-id"
        call_kwargs = mock_client.add_memory.call_args
        # agent_id is the 3rd positional arg (fact, type, agent_id) to client.add_memory
        passed_agent_id = call_kwargs[0][2]
        assert passed_agent_id == "my-custom-agent"

    def test_settings_agent_id_not_used_as_fallback(self):
        """Even if settings.agent_id is set, it must NOT appear when agent_id is not passed."""
        from mcp_server.server import memory_add
        import pytest
        # The function must raise before any client call — settings.agent_id fallback is gone
        with pytest.raises(TypeError):
            memory_add(fact="fact")  # no agent_id
```

- [ ] **Step 4.2 — Run to confirm failure**

```
pytest tests/test_wp088_dedup_enforcement.py::TestMcpAgentIdRequired -x
```
Expected: `test_memory_add_without_agent_id_raises` fails because the call currently succeeds (uses settings fallback)

- [ ] **Step 4.3 — Update `memory_add` in `mcp_server/server.py`**

Replace lines 32–58 with:

```python
@mcp.tool
def memory_add(
    fact: str,
    agent_id: str,
    type: str = "fact",
    strand_ids: list[str] | None = None,
    tags: list[str] | None = None,
    importance: int = 3,
    so_what: str | None = None,
    cause_ids: list[str] | None = None,
    effect_ids: list[str] | None = None,
) -> str:
    """Add a memory to the fabric.

    agent_id is required — pass your own agent identifier (e.g. "claude-code",
    "engineering-implementer"). Do NOT omit it or pass "claude-code" unless you
    ARE the main Claude Code session. Returns the memory_id (existing if a
    duplicate was detected).
    """
    with MemoryClient(base_url=settings.api_base_url) as client:
        mid = client.add_memory(
            fact,
            type,
            agent_id,
            so_what=so_what,
            cause_ids=cause_ids,
            effect_ids=effect_ids,
            tags=tags,
            importance=importance,
            strand_ids=strand_ids,
        )
    return mid
```

- [ ] **Step 4.4 — Run new MCP tests**

```
pytest tests/test_wp088_dedup_enforcement.py::TestMcpAgentIdRequired -x
```
Expected: 3 PASSED

- [ ] **Step 4.5 — Update existing MCP server test that tested the old fallback**

In `tests/test_wp033_mcp_server.py`, find `test_u1_memory_add_resolves_agent_id` (near line 29).

Replace the test name and body:
- Old: calls `memory_add(fact="hello", type="fact")` (no agent_id), asserts `call_args.args[2] == settings.agent_id`
- New: rename to `test_u1_memory_add_passes_explicit_agent_id`, call `memory_add(fact="hello", type="fact", agent_id="test-agent-wp033")`, assert `call_args.args[2] == "test-agent-wp033"`

Also find any other calls to `memory_add` in `tests/test_wp033_mcp_server.py` that omit `agent_id` and add `agent_id="test-agent-wp033"` to each.

- [ ] **Step 4.6 — Run WP-033 tests**

```
pytest tests/test_wp033_mcp_server.py -x
```
Expected: all PASSED

- [ ] **Step 4.7 — Commit**

```bash
git add mcp_server/server.py tests/test_wp033_mcp_server.py tests/test_wp088_dedup_enforcement.py
git commit -m "WP-088: make agent_id required in MCP memory_add, remove settings fallback"
```

---

## Task 5: One-time cleanup script

**Files:**
- Create: `scripts/dedup_cleanup.py`
- Modify: `tests/test_wp088_dedup_enforcement.py` (add class)

- [ ] **Step 5.1 — Write failing cleanup script tests**

Append to `tests/test_wp088_dedup_enforcement.py`:

```python
import subprocess
import sys

_CLEANUP_AGENT = "test-wp088-cleanup-agent"
_CLEANUP_CONTEXT = {"Agent": _CLEANUP_AGENT}


def _insert_raw_memories(driver, facts: list[str], agent_id: str = _CLEANUP_AGENT) -> list[str]:
    """Insert Memory nodes directly via Cypher (bypassing pre-write dedup for test setup)."""
    from datetime import datetime, timezone
    ids = []
    with driver.session() as session:
        for fact in facts:
            mid = str(_uuid.uuid4())
            session.run(
                """
                MERGE (a:Agent {id: $agent_id})
                CREATE (m:Memory {
                    id: $id, fact: $fact, text: $fact, type: 'fact',
                    tags: [], importance: 3,
                    created_at: $now, last_used_at: $now,
                    embedding: [],
                    strength: 0.4, min_strength: 0.12,
                    recall_count: 0, reinforcement_count: 0,
                    last_reinforced_at: $now, decay_rate: 0.07,
                    status: 'active'
                })
                CREATE (m)-[:PRODUCED_BY]->(a)
                """,
                agent_id=agent_id,
                id=mid,
                fact=fact,
                now=datetime.now(timezone.utc).isoformat(),
            )
            ids.append(mid)
    return ids


@pytest.mark.integration
class TestCleanupScript:
    def test_dry_run_prints_count_makes_no_changes(self, test_driver):
        shared_fact = f"WP-088 cleanup dry-run {_uuid.uuid4()}"
        ids = _insert_raw_memories(test_driver, [shared_fact, shared_fact, shared_fact])
        try:
            result = subprocess.run(
                [sys.executable, "scripts/dedup_cleanup.py", "--dry-run"],
                capture_output=True, text=True,
                cwd="/home/oliver/projects/graph-memory-fabric",
            )
            assert result.returncode == 0, result.stderr
            assert "dry-run" in result.stdout.lower()
            # All 3 nodes must still exist
            with test_driver.session() as session:
                count = session.run(
                    "MATCH (m:Memory) WHERE m.id IN $ids RETURN count(m) AS cnt",
                    ids=ids,
                ).single()["cnt"]
            assert count == 3
        finally:
            cleanup_nodes(test_driver, *ids, extra_ids=_CLEANUP_CONTEXT)

    def test_merge_run_leaves_one_node_with_reinforcement(self, test_driver):
        shared_fact = f"WP-088 cleanup merge {_uuid.uuid4()}"
        ids = _insert_raw_memories(test_driver, [shared_fact, shared_fact, shared_fact])
        try:
            result = subprocess.run(
                [sys.executable, "scripts/dedup_cleanup.py"],
                capture_output=True, text=True,
                cwd="/home/oliver/projects/graph-memory-fabric",
            )
            assert result.returncode == 0, result.stderr
            with test_driver.session() as session:
                active = session.run(
                    "MATCH (m:Memory) WHERE m.id IN $ids AND (m.status IS NULL OR m.status='active') RETURN count(m) AS cnt",
                    ids=ids,
                ).single()["cnt"]
                canonical_id = session.run(
                    "MATCH (m:Memory) WHERE m.id IN $ids AND (m.status IS NULL OR m.status='active') RETURN m.id AS id LIMIT 1",
                    ids=ids,
                ).single()["id"]
                node = get_memory_node(test_driver, canonical_id)
            assert active == 1
            assert node["reinforcement_count"] >= 1
        finally:
            # Clean up all ids (some may now be status='merged', DETACH DELETE handles them)
            cleanup_nodes(test_driver, *ids, extra_ids=_CLEANUP_CONTEXT)
```

- [ ] **Step 5.2 — Run to confirm failure**

```
pytest tests/test_wp088_dedup_enforcement.py::TestCleanupScript -x -m integration
```
Expected: `FileNotFoundError` or `subprocess` non-zero exit (script doesn't exist)

- [ ] **Step 5.3 — Implement `scripts/dedup_cleanup.py`**

```python
#!/usr/bin/env python3
"""
scripts/dedup_cleanup.py — One-time cleanup: merge duplicate Memory nodes.

Finds Memory nodes that share an identical fact (case-insensitive) or are
semantically near-identical (cosine distance <= threshold), merges each
group into the canonical node (oldest created_at; tie-break: highest
importance), and reinforces the canonical once to record the significance
of repeated writes.

Usage:
    python scripts/dedup_cleanup.py [--dry-run] [--similarity-threshold FLOAT]

Flags:
    --dry-run                  Print duplicate groups but make no changes.
    --similarity-threshold F   Cosine distance threshold (default 0.05).
"""

import argparse
import math
from datetime import datetime, timezone

from memory_service.config import Settings, get_driver
from memory_service import memory_repo


def _cosine_distance(a: list, b: list) -> float:
    """Compute cosine distance between two embedding vectors using stdlib math."""
    if not a or not b:
        return 1.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 1.0
    return 1.0 - dot / (norm_a * norm_b)


def _fetch_active_memories(session) -> list[dict]:
    """Return all active Memory nodes with id, fact, created_at, importance, embedding."""
    result = session.run(
        """
        MATCH (m:Memory)
        WHERE (m.status IS NULL OR m.status = 'active')
        RETURN m.id AS id, m.fact AS fact,
               m.created_at AS created_at,
               coalesce(m.importance, 3) AS importance,
               m.embedding AS embedding
        """
    )
    return [dict(r) for r in result]


def _find_exact_groups(memories: list[dict]) -> tuple[list[list[dict]], set[str]]:
    """Group memories by normalised fact text. Returns groups (>1 member) and the set of IDs already grouped."""
    from collections import defaultdict
    buckets: dict[str, list[dict]] = defaultdict(list)
    for m in memories:
        if m["fact"]:
            buckets[m["fact"].lower()].append(m)
    groups = [v for v in buckets.values() if len(v) > 1]
    grouped_ids = {m["id"] for g in groups for m in g}
    return groups, grouped_ids


def _find_semantic_groups(memories: list[dict], threshold: float, already_grouped: set[str]) -> list[list[dict]]:
    """Union-find over remaining memories: group pairs with cosine distance <= threshold."""
    remaining = [m for m in memories if m["id"] not in already_grouped and m["embedding"]]
    if len(remaining) < 2:
        return []

    parent = {m["id"]: m["id"] for m in remaining}
    by_id = {m["id"]: m for m in remaining}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    ids = [m["id"] for m in remaining]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            dist = _cosine_distance(by_id[a]["embedding"], by_id[b]["embedding"])
            if dist <= threshold:
                union(a, b)

    from collections import defaultdict
    clusters: dict[str, list[dict]] = defaultdict(list)
    for mid in ids:
        clusters[find(mid)].append(by_id[mid])

    return [v for v in clusters.values() if len(v) > 1]


def pick_canonical(group: list[dict]) -> dict:
    """Oldest created_at wins; on tie, highest importance wins."""
    return sorted(group, key=lambda m: (m["created_at"] or "", -(m["importance"] or 3)))[0]


def merge_group(session, canonical_id: str, duplicate_ids: list[str], settings) -> None:
    """Merge each duplicate into canonical, then reinforce canonical once."""
    now_iso = datetime.now(timezone.utc).isoformat()
    for dup_id in duplicate_ids:
        memory_repo.merge_memory(
            session,
            source_id=dup_id,
            target_id=canonical_id,
            strategy="replace",
            default_edge_decay_rate=settings.edge_decay_rate,
        )
    memory_repo.reinforce_memory(
        session,
        canonical_id,
        strength_increment=settings.explicit_strength_increment,
        edge_increment=settings.edge_explicit_increment,
        co_recalled_ids=[],
        now_iso=now_iso,
        consolidated_decay_rate=settings.memory_consolidated_decay_rate,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge duplicate Memory nodes in Memgraph")
    parser.add_argument("--dry-run", action="store_true", help="Print groups but make no changes")
    parser.add_argument("--similarity-threshold", type=float, default=0.05,
                        help="Cosine distance threshold for semantic dedup (default 0.05)")
    args = parser.parse_args()

    settings = Settings()
    driver = get_driver(settings)

    with driver.session() as session:
        memories = _fetch_active_memories(session)

    if not memories:
        print("[dedup] No active Memory nodes found.")
        driver.close()
        return

    exact_groups, grouped_ids = _find_exact_groups(memories)
    semantic_groups = _find_semantic_groups(memories, args.similarity_threshold, grouped_ids)
    all_groups = exact_groups + semantic_groups

    if not all_groups:
        print("[dedup] No duplicate groups found.")
        driver.close()
        return

    total_merges = sum(len(g) - 1 for g in all_groups)
    print(f"[dedup] Found {len(all_groups)} duplicate group(s) ({len(exact_groups)} exact, "
          f"{len(semantic_groups)} semantic), {total_merges} merge(s) to perform.")

    if args.dry_run:
        for i, group in enumerate(all_groups, 1):
            canonical = pick_canonical(group)
            dups = [m["id"] for m in group if m["id"] != canonical["id"]]
            kind = "exact" if i <= len(exact_groups) else "semantic"
            print(f"  Group {i} [{kind}]: canonical={canonical['id']!r} fact={canonical['fact']!r:.60}, "
                  f"duplicates={dups}")
        print("[dedup] Dry-run: no changes made.")
        driver.close()
        return

    performed = 0
    for group in all_groups:
        canonical = pick_canonical(group)
        dup_ids = [m["id"] for m in group if m["id"] != canonical["id"]]
        with driver.session() as session:
            merge_group(session, canonical["id"], dup_ids, settings)
        performed += len(dup_ids)

    print(f"[dedup] Done. {len(all_groups)} groups processed, {performed} merge(s) performed.")
    driver.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5.4 — Run cleanup script tests**

```
pytest tests/test_wp088_dedup_enforcement.py::TestCleanupScript -x -m integration
```
Expected: 2 PASSED

- [ ] **Step 5.5 — Commit**

```bash
git add scripts/dedup_cleanup.py tests/test_wp088_dedup_enforcement.py
git commit -m "WP-088: add dedup_cleanup.py one-time batch merge script"
```

---

## Task 6: Full regression sweep

- [ ] **Step 6.1 — Run all WP-088 unit tests**

```
pytest tests/test_wp088_dedup_enforcement.py -v -k "not integration"
```
Expected: all PASSED

- [ ] **Step 6.2 — Run all WP-088 integration tests**

```
pytest tests/test_wp088_dedup_enforcement.py -v -m integration
```
Expected: all PASSED (live stack must be running)

- [ ] **Step 6.3 — Run full integration suite (regression)**

```
pytest tests/ -x -m integration
```
Expected: all PASSED

- [ ] **Step 6.4 — Run complete test suite**

```
pytest tests/ -x
```
Expected: all PASSED

- [ ] **Step 6.5 — Run the cleanup script against live data (dry-run first)**

```bash
python scripts/dedup_cleanup.py --dry-run
python scripts/dedup_cleanup.py  # only if dry-run output looks correct
```
Expected: duplicate groups printed in dry-run; clean output on actual run.

---

## Verification

**End-to-end smoke test (against live service):**

1. Confirm service is healthy: `curl -s http://localhost:8000/health`
2. Add a memory: `POST /memory {"fact": "Oliver uses graph memory", "type": "fact", "agent_id": "claude-code"}`
3. Add same memory again: same POST. Assert `deduplicated: true` in response and same `memory_id`.
4. Confirm MCP enforcement: call `memory_add(fact="test", type="fact")` from Python — assert TypeError raised.
5. Confirm cleanup script: `python scripts/dedup_cleanup.py --dry-run` — zero duplicate groups expected after step 3 merged them.

---

## Notes on semantic dedup test

`TestPreWriteSemanticDedup.test_near_identical_fact_deduplicates` relies on the specific embedding distance of two rephrased sentences with `all-MiniLM-L6-v2`. If the test is flaky with those phrases, swap for phrases with a larger vocabulary overlap (e.g. "Oliver prefers concise feedback" vs "Oliver likes concise feedback"). The test includes an assertion message that explains this.
