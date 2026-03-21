# WP-028: Causal Graph — `fact`/`so_what` + `LEADS_TO` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split Memory's `text` field into `fact` + `so_what`, derive `text` as their concatenation for embedding, add `LEADS_TO` causal edges between memories, and add `traversal_direction` to search to traverse causal chains.

**Architecture:** Vertical slice through service → repo → client → CLI → MCP server. `AddMemoryRequest` gains `fact`/`so_what`/`cause_ids`/`effect_ids` with a `model_validator` for backwards compat. `memory_repo` gets two new LEADS_TO steps and an extended search query builder. All layers updated atomically; migration script handles existing nodes.

**Tech Stack:** FastAPI + Pydantic v2, Memgraph (Cypher + MAGE vector search), sentence-transformers, httpx, Typer, FastMCP.

---

## File Map

| File | What changes |
|------|-------------|
| `memory_service/main.py` | `AddMemoryRequest`: add `fact`, `so_what`, `cause_ids`, `effect_ids`; deprecate `text` via `model_validator`; derive `text` + embedding in handler |
| `memory_service/memory_repo.py` | `add_memory()`: steps 6–7 for LEADS_TO; `search_memories()`: `traversal_direction` support |
| `memory_client/client.py` | Update `add_memory()` and `search_memory()` signatures |
| `memory_client/cli.py` | `add-memory`: `fact` positional, `--so-what`, `--cause-id`, `--effect-id`; `search-memory`: `--traversal-direction`; `close-session`: update scaffold |
| `mcp_server/server.py` | `memory_add` tool: `fact` param, `so_what`, `cause_ids`, `effect_ids`; `memory_search`: `traversal_direction`; `_CLOSE_SESSION_SCAFFOLD` |
| `scripts/migrate_fact_so_what.py` | New: JSON-line stdin/stdout migration; `--dry-run`; idempotent |
| `tests/test_add_memory.py` | Unit: validator branches + text derivation; Integration: `fact`/`so_what` storage, LEADS_TO edges |
| `tests/test_search_memory.py` | Integration: `traversal_direction` for all four values |

---

## Task 1: Unit tests for `AddMemoryRequest` validator + text derivation

**Context:** Before touching any production code, write the unit tests that define the exact behaviour of the new `AddMemoryRequest`. These tests run without Memgraph (no live stack needed).

**Files:**
- Modify: `tests/test_add_memory.py`

- [ ] **Step 1: Add unit test class for `AddMemoryRequest` validation**

First, add these imports at the **module level** (top of `tests/test_add_memory.py`, after the existing imports):

```python
from pydantic import ValidationError
from memory_service.main import AddMemoryRequest
```

Then add the following class before `class TestPostMemoryMinimal`:

```python
class TestAddMemoryRequestValidator:
    """Unit tests — no live stack required. Mark with pytest.mark.unit."""

    def _base(self, **kwargs):
        defaults = {"type": "fact", "agent_id": "agent-1"}
        return {**defaults, **kwargs}

    def test_fact_only_accepted(self):
        req = AddMemoryRequest(**self._base(fact="Oliver has ADHD."))
        assert req.fact == "Oliver has ADHD."
        assert req.so_what is None
        assert req.text == "Oliver has ADHD."

    def test_text_alias_sets_fact(self):
        req = AddMemoryRequest(**self._base(text="legacy text"))
        assert req.fact == "legacy text"
        assert req.so_what is None
        assert req.text == "legacy text"

    def test_fact_wins_when_both_provided(self):
        req = AddMemoryRequest(**self._base(fact="new fact", text="old text"))
        assert req.fact == "new fact"

    def test_neither_fact_nor_text_raises(self):
        with pytest.raises(ValidationError):
            AddMemoryRequest(**self._base())

    def test_text_derived_from_fact_and_so_what(self):
        req = AddMemoryRequest(**self._base(
            fact="Oliver has ADHD.",
            so_what="Structure and short feedback loops matter more than motivation.",
        ))
        assert req.text == "Oliver has ADHD. Structure and short feedback loops matter more than motivation."

    def test_text_derived_from_fact_alone_when_no_so_what(self):
        req = AddMemoryRequest(**self._base(fact="Oliver has ADHD."))
        assert req.text == "Oliver has ADHD."
```

- [ ] **Step 2: Run tests — expect FAIL (AddMemoryRequest doesn't have `fact` yet)**

```bash
cd /home/oliver/projects/graph-memory-fabric
pytest tests/test_add_memory.py::TestAddMemoryRequestValidator -v
```

Expected: `FAILED` — `AddMemoryRequest` does not accept `fact` field.

---

## Task 2: Update `AddMemoryRequest` in `memory_service/main.py`

**Context:** `main.py` line 51–60 has `AddMemoryRequest`. We add `fact`, `so_what`, `cause_ids`, `effect_ids`, deprecate `text`, and add the `model_validator`. We also update the handler at line 69 to derive `text` from `fact`/`so_what`.

**Files:**
- Modify: `memory_service/main.py:L1-77`

- [ ] **Step 3: Update imports at top of `main.py`**

Replace line 11:
```python
from pydantic import BaseModel, Field
```
with:
```python
from pydantic import BaseModel, Field, model_validator
```

- [ ] **Step 4: Replace `AddMemoryRequest` (lines 51–60)**

Replace:
```python
class AddMemoryRequest(BaseModel):
    text: str
    type: MemoryType
    tags: List[str] = []
    agent_id: str
    project_id: Optional[str] = None
    person_ids: List[str] = []
    strand_ids: List[str] = []
    importance: int = Field(default=3, ge=1, le=5)
    related_ids: Optional[List[str]] = None
```

with:
```python
class AddMemoryRequest(BaseModel):
    fact: Optional[str] = None   # populated by validator; None means "not yet provided"
    so_what: Optional[str] = None
    text: Optional[str] = None   # deprecated alias for fact
    type: MemoryType
    tags: List[str] = []
    agent_id: str
    project_id: Optional[str] = None
    person_ids: List[str] = []
    strand_ids: List[str] = []
    importance: int = Field(default=3, ge=1, le=5)
    related_ids: Optional[List[str]] = None
    cause_ids: List[str] = []
    effect_ids: List[str] = []

    @model_validator(mode="before")
    @classmethod
    def resolve_fact_and_text(cls, values: dict) -> dict:
        fact = values.get("fact")
        text = values.get("text")
        if not fact and not text:
            raise ValueError("Either 'fact' or 'text' must be provided")
        if not fact and text:
            values["fact"] = text
        # Derive text from fact + so_what
        resolved_fact = values.get("fact") or ""
        so_what = values.get("so_what")
        values["text"] = resolved_fact + (" " + so_what if so_what else "")
        return values
```

- [ ] **Step 5: Update the POST /memory handler (line 69) to use derived text**

Replace:
```python
    embedding = get_embedding(req.text)
```
with:
```python
    embedding = get_embedding(req.text)  # req.text is already derived (fact + so_what)
```

*(No code change needed — `req.text` is already the derived value after the validator runs. Just verify the handler passes `req` to `add_memory` unchanged.)*

- [ ] **Step 6: Run unit tests — expect PASS**

```bash
pytest tests/test_add_memory.py::TestAddMemoryRequestValidator -v
```

Expected: all 6 tests `PASS`.

- [ ] **Step 7: Run full existing test suite to check backwards compat**

```bash
pytest tests/test_add_memory.py -v -k "not TestAddMemoryRequestValidator"
```

Expected: all existing tests pass. The `text` alias means old tests using `"text": "..."` in JSON bodies still work.

- [ ] **Step 8: Commit**

```bash
git add memory_service/main.py tests/test_add_memory.py
git commit -m "feat(WP-028): AddMemoryRequest — fact/so_what fields + model_validator + text derivation"
```

---

## Task 3: Integration tests for `fact`/`so_what` storage

**Context:** These tests verify that `fact`, `so_what`, and derived `text` are stored correctly on the Memory node in Memgraph. Requires live stack.

**Files:**
- Modify: `tests/test_add_memory.py`

- [ ] **Step 9: Add integration test class for fact/so_what storage**

Add after `TestAddMemoryRequestValidator`:

```python
import pytest

@pytest.mark.integration
class TestPostMemoryFactSoWhat:
    """Integration: fact/so_what storage on Memory node."""

    def test_fact_and_so_what_stored_on_node(self, client, test_driver):
        response = client.post("/memory", json={
            "fact": "Oliver has ADHD.",
            "so_what": "Structure and short feedback loops matter more than motivation.",
            "type": "fact",
            "agent_id": _AGENT_ID,
        })
        assert response.status_code == 200
        memory_id = response.json()["memory_id"]
        node = get_memory_node(test_driver, memory_id)
        assert node["fact"] == "Oliver has ADHD."
        assert node["so_what"] == "Structure and short feedback loops matter more than motivation."
        assert node["text"] == "Oliver has ADHD. Structure and short feedback loops matter more than motivation."
        assert isinstance(node["embedding"], list)
        _cleanup(test_driver, memory_id)

    def test_fact_only_stores_correctly(self, client, test_driver):
        response = client.post("/memory", json={
            "fact": "Oliver prefers async communication.",
            "type": "observation",
            "agent_id": _AGENT_ID,
        })
        assert response.status_code == 200
        memory_id = response.json()["memory_id"]
        node = get_memory_node(test_driver, memory_id)
        assert node["fact"] == "Oliver prefers async communication."
        assert node.get("so_what") is None
        assert node["text"] == "Oliver prefers async communication."
        _cleanup(test_driver, memory_id)

    def test_deprecated_text_alias_stores_fact(self, client, test_driver):
        response = client.post("/memory", json={
            "text": "legacy text field",
            "type": "fact",
            "agent_id": _AGENT_ID,
        })
        assert response.status_code == 200
        memory_id = response.json()["memory_id"]
        node = get_memory_node(test_driver, memory_id)
        assert node["fact"] == "legacy text field"
        assert node.get("so_what") is None
        assert node["text"] == "legacy text field"
        _cleanup(test_driver, memory_id)

    def test_neither_fact_nor_text_returns_422(self, client, test_driver):
        response = client.post("/memory", json={
            "type": "fact",
            "agent_id": _AGENT_ID,
        })
        assert response.status_code == 422
```

- [ ] **Step 10: Update `memory_repo.add_memory` Step 1 to store `fact` and `so_what`**

In `memory_service/memory_repo.py`, the `CREATE (m:Memory {...})` block (lines 25–34) stores `text` but not `fact`/`so_what`. Update it:

```python
    session.run(
        """
        MERGE (a:Agent {id: $agent_id})
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
            embedding: $embedding
        })
        CREATE (m)-[:PRODUCED_BY]->(a)
        """,
        agent_id=req.agent_id,
        id=memory_id,
        fact=req.fact,
        so_what=req.so_what,
        text=req.text,
        type=req.type.value,
        tags=req.tags,
        importance=req.importance,
        created_at=now,
        last_used_at=now,
        embedding=embedding,
    )
```

- [ ] **Step 11: Run integration tests (requires live stack)**

```bash
pytest tests/test_add_memory.py::TestPostMemoryFactSoWhat -v -m integration
```

Expected: all 4 tests `PASS`.

- [ ] **Step 12: Run full test suite**

```bash
pytest tests/test_add_memory.py -v
```

Expected: all tests pass (existing + new).

- [ ] **Step 13: Commit**

```bash
git add memory_service/memory_repo.py tests/test_add_memory.py
git commit -m "feat(WP-028): store fact/so_what on Memory node; integration tests"
```

---

## Task 4: LEADS_TO edge creation (steps 6 & 7 in `add_memory`)

**Context:** Add two new steps to `memory_repo.add_memory()` after the existing step 5. Step 6 creates LEADS_TO edges from each `cause_id` → new memory. Step 7 creates LEADS_TO edges from new memory → each `effect_id`. Missing UUIDs are silently skipped.

**Files:**
- Modify: `memory_service/memory_repo.py:L87-116`
- Modify: `tests/test_add_memory.py`

- [ ] **Step 14: Write failing integration tests for LEADS_TO edges**

Add to `tests/test_add_memory.py`:

```python
@pytest.mark.integration
class TestPostMemoryLeadsTo:
    """Integration: LEADS_TO edge creation via cause_ids and effect_ids."""

    def test_cause_ids_creates_leads_to_edge(self, client, test_driver):
        # Create cause memory first
        r1 = client.post("/memory", json={"fact": "Cause memory", "type": "fact", "agent_id": _AGENT_ID})
        cause_id = r1.json()["memory_id"]

        # Create effect memory referencing cause
        r2 = client.post("/memory", json={
            "fact": "Effect memory",
            "type": "fact",
            "agent_id": _AGENT_ID,
            "cause_ids": [cause_id],
        })
        effect_id = r2.json()["memory_id"]

        # LEADS_TO should go cause → effect
        assert edge_exists(test_driver, cause_id, "LEADS_TO", effect_id)
        _cleanup(test_driver, cause_id, effect_id)

    def test_effect_ids_creates_leads_to_edge(self, client, test_driver):
        # Create effect memory first
        r1 = client.post("/memory", json={"fact": "Effect memory", "type": "fact", "agent_id": _AGENT_ID})
        effect_id = r1.json()["memory_id"]

        # Create cause memory referencing effect
        r2 = client.post("/memory", json={
            "fact": "Cause memory",
            "type": "fact",
            "agent_id": _AGENT_ID,
            "effect_ids": [effect_id],
        })
        cause_id = r2.json()["memory_id"]

        # LEADS_TO should go cause → effect
        assert edge_exists(test_driver, cause_id, "LEADS_TO", effect_id)
        _cleanup(test_driver, cause_id, effect_id)

    def test_missing_uuid_in_cause_ids_skipped_silently(self, client, test_driver):
        r = client.post("/memory", json={
            "fact": "New memory with missing cause",
            "type": "fact",
            "agent_id": _AGENT_ID,
            "cause_ids": ["00000000-0000-0000-0000-000000000000"],
        })
        assert r.status_code == 200
        memory_id = r.json()["memory_id"]
        # No LEADS_TO edge created, but write succeeded
        node = get_memory_node(test_driver, memory_id)
        assert node is not None
        _cleanup(test_driver, memory_id)

    def test_missing_uuid_in_effect_ids_skipped_silently(self, client, test_driver):
        r = client.post("/memory", json={
            "fact": "New memory with missing effect",
            "type": "fact",
            "agent_id": _AGENT_ID,
            "effect_ids": ["00000000-0000-0000-0000-000000000000"],
        })
        assert r.status_code == 200
        memory_id = r.json()["memory_id"]
        node = get_memory_node(test_driver, memory_id)
        assert node is not None
        _cleanup(test_driver, memory_id)

    def test_leads_to_edge_is_idempotent(self, client, test_driver):
        """MERGE ensures the same directed edge is not duplicated."""
        r1 = client.post("/memory", json={"fact": "Cause", "type": "fact", "agent_id": _AGENT_ID})
        cause_id = r1.json()["memory_id"]
        r2 = client.post("/memory", json={
            "fact": "Effect",
            "type": "fact",
            "agent_id": _AGENT_ID,
            "cause_ids": [cause_id],
        })
        effect_id = r2.json()["memory_id"]

        # Manually create the same LEADS_TO edge a second time (simulating a re-run)
        with test_driver.session() as s:
            s.run(
                "MATCH (c:Memory {id: $c}), (e:Memory {id: $e}) MERGE (c)-[:LEADS_TO]->(e)",
                c=cause_id, e=effect_id,
            )

        # Verify exactly one LEADS_TO edge exists between the pair
        with test_driver.session() as s:
            result = s.run(
                "MATCH (c:Memory {id: $c})-[r:LEADS_TO]->(e:Memory {id: $e}) RETURN count(r) AS cnt",
                c=cause_id, e=effect_id,
            )
            count = result.single()["cnt"]
        assert count == 1, f"Expected exactly 1 LEADS_TO edge, got {count}"
        _cleanup(test_driver, cause_id, effect_id)
```

- [ ] **Step 15: Run tests — expect FAIL**

```bash
pytest tests/test_add_memory.py::TestPostMemoryLeadsTo -v -m integration
```

Expected: `FAILED` — `cause_ids`/`effect_ids` fields not yet on model / no LEADS_TO step.

- [ ] **Step 16: Add steps 6 and 7 to `memory_repo.add_memory()`**

In `memory_service/memory_repo.py`, after the existing step 5 block (after line 116), add:

```python
    # Step 6 — LEADS_TO edges: cause_ids → this memory (this memory is the effect)
    for cause_id in req.cause_ids:
        session.run(
            """
            OPTIONAL MATCH (cause:Memory {id: $cause_id})
            WITH cause
            WHERE cause IS NOT NULL
            MATCH (effect:Memory {id: $new_memory_id})
            MERGE (cause)-[:LEADS_TO]->(effect)
            """,
            cause_id=cause_id,
            new_memory_id=memory_id,
        )

    # Step 7 — LEADS_TO edges: this memory → effect_ids (this memory is the cause)
    for effect_id in req.effect_ids:
        session.run(
            """
            OPTIONAL MATCH (effect:Memory {id: $effect_id})
            WITH effect
            WHERE effect IS NOT NULL
            MATCH (cause:Memory {id: $new_memory_id})
            MERGE (cause)-[:LEADS_TO]->(effect)
            """,
            effect_id=effect_id,
            new_memory_id=memory_id,
        )
```

- [ ] **Step 17: Run LEADS_TO tests — expect PASS**

```bash
pytest tests/test_add_memory.py::TestPostMemoryLeadsTo -v -m integration
```

Expected: all 5 tests `PASS`.

- [ ] **Step 18: Run full test suite**

```bash
pytest tests/test_add_memory.py -v
```

Expected: all tests pass.

- [ ] **Step 19: Commit**

```bash
git add memory_service/memory_repo.py tests/test_add_memory.py
git commit -m "feat(WP-028): LEADS_TO edge creation — cause_ids and effect_ids steps"
```

---

## Task 5: `traversal_direction` on search

**Context:** Extend `SearchMemoryRequest` with `traversal_direction` and update `search_memories()` to build the appropriate Cypher. The existing `_SEARCH_QUERY_TEMPLATE` uses `{neighbour_clause}` and `{neighbour_return}` substitution; we extend the logic that fills those slots.

**Files:**
- Modify: `memory_service/main.py:L80-86`
- Modify: `memory_service/memory_repo.py:L145-187`
- Modify: `tests/test_search_memory.py`

- [ ] **Step 20: Write failing tests for `traversal_direction`**

Read `tests/test_search_memory.py` lines 28–60 to see the `_add()` and `_search()` helpers, then add a new test class at the end of the file:

```python
@pytest.mark.integration
class TestSearchTraversalDirection:
    """Integration: LEADS_TO traversal via traversal_direction parameter."""

    def test_traversal_direction_none_is_default_behaviour(self, client, test_driver):
        r = client.post("/memory/search", json={
            "query": "test query",
            "traversal_direction": "none",
            "max_hops": 0,
        })
        assert r.status_code == 200
        # Just verify the field is accepted and response is valid
        data = r.json()
        assert "memories" in data

    def test_traversal_direction_causes_returns_upstream(self, client, test_driver):
        # Create cause → effect chain and verify cause appears in neighbours when
        # searching for the effect with traversal_direction="causes"
        r_cause = client.post("/memory", json={
            "fact": "ADHD affects focus.",
            "type": "fact",
            "agent_id": "test-agent-traversal",
        })
        cause_id = r_cause.json()["memory_id"]

        r_effect = client.post("/memory", json={
            "fact": "Oliver needs structure to stay productive.",
            "type": "insight",
            "agent_id": "test-agent-traversal",
            "cause_ids": [cause_id],
        })
        effect_id = r_effect.json()["memory_id"]

        # Search for the effect; with direction=causes, the cause should appear in neighbours
        r_search = client.post("/memory/search", json={
            "query": "Oliver needs structure",
            "traversal_direction": "causes",
            "max_hops": 1,
            "limit": 5,
        })
        assert r_search.status_code == 200
        hits = r_search.json()["memories"]
        # Find the effect hit and check cause is in its neighbours
        effect_hit = next((h for h in hits if h["id"] == effect_id), None)
        assert effect_hit is not None, "Effect memory should appear in search results"
        assert cause_id in effect_hit["neighbours"]

        # Cleanup
        with test_driver.session() as s:
            s.run("MATCH (a:Agent {id: 'test-agent-traversal'}) DETACH DELETE a")
        with test_driver.session() as s:
            s.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=cause_id)
            s.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=effect_id)

    def test_traversal_direction_effects_returns_downstream(self, client, test_driver):
        """Search for the cause with direction=effects; the effect must appear in its neighbours."""
        r_cause = client.post("/memory", json={
            "fact": "Oliver trained as an engineer.",
            "type": "fact",
            "agent_id": "test-agent-traversal",
        })
        cause_id = r_cause.json()["memory_id"]

        r_effect = client.post("/memory", json={
            "fact": "Oliver enjoys systematic problem-solving.",
            "type": "insight",
            "agent_id": "test-agent-traversal",
            "cause_ids": [cause_id],
        })
        effect_id = r_effect.json()["memory_id"]

        # Filter by agent_id so only our test nodes can appear; retrieve both
        r_search = client.post("/memory/search", json={
            "query": "Oliver engineer training",
            "agent_ids": ["test-agent-traversal"],
            "traversal_direction": "effects",
            "max_hops": 1,
            "limit": 10,
        })
        assert r_search.status_code == 200
        hits = r_search.json()["memories"]
        cause_hit = next((h for h in hits if h["id"] == cause_id), None)
        assert cause_hit is not None, "Cause memory must appear in results (agent_ids filter used)"
        assert effect_id in cause_hit["neighbours"], \
            "Effect memory must appear in cause's neighbours when traversal_direction='effects'"

        with test_driver.session() as s:
            s.run("MATCH (a:Agent {id: 'test-agent-traversal'}) DETACH DELETE a")
        with test_driver.session() as s:
            s.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=cause_id)
            s.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=effect_id)

    def test_causes_with_max_hops_zero_still_returns_upstream(self, client, test_driver):
        """traversal_direction works independently of max_hops — even max_hops=0 traverses LEADS_TO."""
        r_cause = client.post("/memory", json={
            "fact": "ADHD impairs working memory.",
            "type": "fact",
            "agent_id": "test-agent-traversal",
        })
        cause_id = r_cause.json()["memory_id"]

        r_effect = client.post("/memory", json={
            "fact": "Oliver forgets tasks unless written down.",
            "type": "insight",
            "agent_id": "test-agent-traversal",
            "cause_ids": [cause_id],
        })
        effect_id = r_effect.json()["memory_id"]

        r_search = client.post("/memory/search", json={
            "query": "Oliver forgets tasks",
            "agent_ids": ["test-agent-traversal"],
            "traversal_direction": "causes",
            "max_hops": 0,   # RELATED_TO suppressed; LEADS_TO must still work
            "limit": 10,
        })
        assert r_search.status_code == 200
        hits = r_search.json()["memories"]
        effect_hit = next((h for h in hits if h["id"] == effect_id), None)
        assert effect_hit is not None, "Effect memory must appear in results"
        assert cause_id in effect_hit["neighbours"], \
            "Cause must appear in neighbours even when max_hops=0"

        with test_driver.session() as s:
            s.run("MATCH (a:Agent {id: 'test-agent-traversal'}) DETACH DELETE a")
        with test_driver.session() as s:
            s.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=cause_id)
            s.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=effect_id)

    def test_unknown_traversal_direction_returns_422(self, client, test_driver):
        r = client.post("/memory/search", json={
            "query": "test",
            "traversal_direction": "invalid_value",
        })
        assert r.status_code == 422
```

- [ ] **Step 21: Run tests — expect FAIL**

```bash
pytest tests/test_search_memory.py::TestSearchTraversalDirection -v -m integration
```

Expected: `FAILED` — `traversal_direction` not yet on `SearchMemoryRequest`.

- [ ] **Step 22: Add `traversal_direction` to `SearchMemoryRequest` in `main.py`**

Replace `SearchMemoryRequest` (lines 80–86):

```python
from typing import Literal

class SearchMemoryRequest(BaseModel):
    query: str
    tags: Optional[List[str]] = None
    agent_ids: Optional[List[str]] = None
    project_ids: Optional[List[str]] = None
    limit: int = Field(default=10, ge=1, le=100)
    max_hops: int = Field(default=1, ge=0, le=3)
    traversal_direction: Literal["none", "causes", "effects", "both"] = "none"
```

Add `Literal` to the imports from `typing` at line 7.

- [ ] **Step 23: Update `search_memories()` in `memory_repo.py` to build LEADS_TO clauses**

First, read `memory_service/memory_repo.py` lines 127–142 (`_SEARCH_QUERY_TEMPLATE`) and lines 145–187 (`search_memories`). Confirm that the template does **not** already use `c` or `e` as Cypher aliases — the new LEADS_TO clauses introduce `c` (cause nodes) and `e` (effect nodes) and these must not collide with existing aliases in the template. The current template uses `m`, `a`, `p`, `n` — so `c` and `e` are safe.

Replace the `search_memories` function body (lines 145–187) with:

```python
def search_memories(session, req, query_embedding: list) -> list:
    """Run vector search with optional filters and graph expansion.

    Args:
        session: open neo4j Session
        req: SearchMemoryRequest (query, tags, agent_ids, project_ids, limit, max_hops,
             traversal_direction)
        query_embedding: pre-computed embedding for req.query

    Returns:
        List of dicts with keys: id, text, type, tags, importance, neighbours
    """
    direction = getattr(req, "traversal_direction", "none")
    hops = req.max_hops

    # Build RELATED_TO clause (existing logic)
    related_clause = f"OPTIONAL MATCH (m)-[:RELATED_TO*1..{hops}]->(n:Memory)" if hops > 0 else ""

    # Build LEADS_TO clause(s) based on traversal_direction
    causes_clause = ""
    effects_clause = ""
    hop_depth = max(hops, 1)  # when max_hops=0, LEADS_TO still traverses 1 hop
    if direction in ("causes", "both"):
        causes_clause = f"OPTIONAL MATCH (m)<-[:LEADS_TO*1..{hop_depth}]-(c:Memory)"
    if direction in ("effects", "both"):
        effects_clause = f"OPTIONAL MATCH (m)-[:LEADS_TO*1..{hop_depth}]->(e:Memory)"

    # Combine neighbour clauses and collect expressions
    neighbour_clauses = "\n".join(
        c for c in [related_clause, causes_clause, effects_clause] if c
    )

    collect_parts = []
    if hops > 0:
        collect_parts.append("collect(DISTINCT n.id)")
    if direction in ("causes", "both"):
        collect_parts.append("collect(DISTINCT c.id)")
    if direction in ("effects", "both"):
        collect_parts.append("collect(DISTINCT e.id)")

    if collect_parts:
        neighbour_return = " + ".join(collect_parts) + " AS neighbours"
    else:
        neighbour_return = "[] AS neighbours"

    query = _SEARCH_QUERY_TEMPLATE.format(
        neighbour_clause=neighbour_clauses,
        neighbour_return=neighbour_return,
    )

    result = session.run(
        query,
        query_vec=query_embedding,
        limit=req.limit,
        tags=req.tags,
        agent_ids=req.agent_ids,
        project_ids=req.project_ids,
    )

    return [
        {
            "id": record["id"],
            "text": record["text"],
            "type": record["type"],
            "tags": record["tags"],
            "importance": record["importance"],
            "neighbours": record["neighbours"],
        }
        for record in result
    ]
```

- [ ] **Step 24: Run traversal_direction tests — expect PASS**

```bash
pytest tests/test_search_memory.py::TestSearchTraversalDirection -v -m integration
```

Expected: all tests `PASS`.

- [ ] **Step 25: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass (existing + new).

- [ ] **Step 26: Commit**

```bash
git add memory_service/main.py memory_service/memory_repo.py tests/test_search_memory.py
git commit -m "feat(WP-028): traversal_direction on search — LEADS_TO causes/effects/both"
```

---

## Task 6: Update `memory_client/client.py`

**Context:** `client.py` `add_memory()` currently takes `text` as first positional arg. Replace with `fact` + `so_what`. Add `cause_ids`/`effect_ids`. Update `search_memory()` to accept `traversal_direction`.

**Files:**
- Modify: `memory_client/client.py:L19-74`

- [ ] **Step 27: Replace `add_memory()` method (lines 19–48)**

```python
    def add_memory(
        self,
        fact: str,
        type: str,
        agent_id: str,
        *,
        so_what: str | None = None,
        cause_ids: list[str] | None = None,
        effect_ids: list[str] | None = None,
        tags: list[str] | None = None,
        importance: int = 3,
        project_id: str | None = None,
        person_ids: list[str] | None = None,
        strand_ids: list[str] | None = None,
        related_ids: list[str] | None = None,
    ) -> str:
        """POST /memory. Returns memory_id string."""
        body: dict = {
            "fact": fact,
            "type": type,
            "agent_id": agent_id,
            "tags": tags or [],
            "importance": importance,
            "person_ids": person_ids or [],
            "strand_ids": strand_ids or [],
        }
        if so_what is not None:
            body["so_what"] = so_what
        if cause_ids is not None:
            body["cause_ids"] = cause_ids
        if effect_ids is not None:
            body["effect_ids"] = effect_ids
        if project_id is not None:
            body["project_id"] = project_id
        if related_ids is not None:
            body["related_ids"] = related_ids
        response = self._http.post("/memory", json=body)
        response.raise_for_status()
        return response.json()["memory_id"]
```

- [ ] **Step 28: Update `search_memory()` method (lines 50–74)**

Add `traversal_direction` parameter:

```python
    def search_memory(
        self,
        query: str,
        *,
        tags: list[str] | None = None,
        agent_ids: list[str] | None = None,
        project_ids: list[str] | None = None,
        limit: int = 10,
        max_hops: int = 1,
        traversal_direction: str = "none",
    ) -> list[dict]:
        """POST /memory/search. Returns list of MemoryHit dicts."""
        body: dict = {
            "query": query,
            "limit": limit,
            "max_hops": max_hops,
            "traversal_direction": traversal_direction,
        }
        if tags is not None:
            body["tags"] = tags
        if agent_ids is not None:
            body["agent_ids"] = agent_ids
        if project_ids is not None:
            body["project_ids"] = project_ids
        response = self._http.post("/memory/search", json=body)
        response.raise_for_status()
        return response.json()["memories"]
```

- [ ] **Step 29: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 30: Commit**

```bash
git add memory_client/client.py
git commit -m "feat(WP-028): update MemoryClient — fact/so_what/cause_ids/effect_ids + traversal_direction"
```

---

## Task 7: Update `memory_client/cli.py`

**Context:** Three changes: (1) `add-memory` command: `text` → `fact` positional arg, add `--so-what`, `--cause-id`, `--effect-id`. (2) `search-memory` command: add `--traversal-direction`. (3) `close-session` scaffold text: update `--text` references to `--fact`/`--so-what`.

**Files:**
- Modify: `memory_client/cli.py:L24-56, L59-84, L172-193`

- [ ] **Step 31: Replace `add-memory` command (lines 24–56)**

```python
@app.command("add-memory")
def add_memory(
    fact: str = typer.Argument(..., help="The raw, observable fact"),
    type: str = typer.Option(..., "--type", "-t", help="fact|decision|insight|todo|event|observation"),
    agent_id: str = typer.Option(settings.agent_id, "--agent-id", "-a", help="Agent ID producing this memory"),
    so_what: Optional[str] = typer.Option(None, "--so-what", help="Impact or meaning of this fact (optional)"),
    cause_ids: Optional[list[str]] = typer.Option(None, "--cause-id", help="Memory UUID that caused this (repeatable)"),
    effect_ids: Optional[list[str]] = typer.Option(None, "--effect-id", help="Memory UUID this causes (repeatable)"),
    tags: Optional[list[str]] = typer.Option(None, "--tag", help="Tag (repeatable: --tag a --tag b)"),
    importance: int = typer.Option(3, "--importance", "-i", min=1, max=5, help="Importance 1-5"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Project node ID"),
    person_ids: Optional[list[str]] = typer.Option(None, "--person-id", help="Person ID (repeatable)"),
    strand_ids: Optional[list[str]] = typer.Option(None, "--strand-id", help="Strand ID (repeatable)"),
    related_ids: Optional[list[str]] = typer.Option(None, "--related-id", help="Explicit related memory ID (repeatable)"),
) -> None:
    """Add a new memory to the graph."""
    try:
        with _make_client() as client:
            memory_id = client.add_memory(
                fact=fact,
                type=type,
                agent_id=agent_id,
                so_what=so_what,
                cause_ids=cause_ids,
                effect_ids=effect_ids,
                tags=tags,
                importance=importance,
                project_id=project_id,
                person_ids=person_ids,
                strand_ids=strand_ids,
                related_ids=related_ids,
            )
        console.print(memory_id)
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)
```

- [ ] **Step 32: Add `--traversal-direction` to `search-memory` command (lines 59–84)**

Add one option to the function signature after `max_hops`:

```python
    traversal_direction: str = typer.Option(
        "none", "--traversal-direction",
        help="LEADS_TO traversal: none|causes|effects|both",
    ),
```

And pass it through to the client call:

```python
            results = client.search_memory(
                query=query,
                tags=tags,
                agent_ids=agent_ids,
                project_ids=project_ids,
                limit=limit,
                max_hops=max_hops,
                traversal_direction=traversal_direction,
            )
```

- [ ] **Step 33: Update `close-session` scaffold text (lines 177–193)**

Replace the scaffold `console.print(...)` content to use `--fact`/`--so-what`:

```python
    console.print("""
Review this session and answer the following before ending:

1. What decisions were made? (store as type: decision)
   → memory add-memory "..." --type decision --strand-id <strand-id>

2. What was learned or observed about the user? (store as type: insight or observation)
   → memory add-memory "..." --type insight --strand-id <strand-id>
   → Use --so-what "..." to capture the impact or meaning

3. What actions were committed to? (store as type: todo)
   → memory add-memory "..." --type todo --strand-id <strand-id>

4. What context should a future session know that isn't already in the fabric?
   → memory add-memory "..." --type fact --strand-id <strand-id>

5. Are there causal links between memories? (use --cause-id / --effect-id)
   → memory add-memory "..." --type fact --cause-id <uuid> --effect-id <uuid>

Run `memory list-strands` if strand IDs are uncertain.
Do not end the session without running at least one `memory add-memory` if any of the above apply.""")
```

- [ ] **Step 34: Smoke test the CLI**

```bash
memory add-memory "CLI smoke test fact" --type fact
memory search-memory "CLI smoke test" --traversal-direction none
```

Expected: memory ID printed; search returns the test memory.

- [ ] **Step 35: Commit**

```bash
git add memory_client/cli.py
git commit -m "feat(WP-028): update CLI — fact positional arg, --so-what, --cause-id, --effect-id, --traversal-direction"
```

---

## Task 8: Update `mcp_server/server.py`

**Context:** Update the `memory_add` tool to use `fact` instead of `text`, add `so_what`/`cause_ids`/`effect_ids`. Add `traversal_direction` to `memory_search`. Update `_CLOSE_SESSION_SCAFFOLD`.

**Files:**
- Modify: `mcp_server/server.py:L17-54, L109-128`

- [ ] **Step 36: Replace `memory_add` tool (lines 17–37)**

```python
@mcp.tool
def memory_add(
    fact: str,
    type: str = "fact",
    so_what: str | None = None,
    cause_ids: list[str] | None = None,
    effect_ids: list[str] | None = None,
    strand_ids: list[str] | None = None,
    tags: list[str] | None = None,
    importance: int = 3,
    agent_id: str | None = None,
) -> str:
    """Add a memory to the fabric. Returns the created memory ID."""
    resolved_agent_id = agent_id or settings.agent_id
    with MemoryClient(base_url=settings.api_base_url) as client:
        mid = client.add_memory(
            fact,
            type,
            resolved_agent_id,
            so_what=so_what,
            cause_ids=cause_ids,
            effect_ids=effect_ids,
            tags=tags,
            importance=importance,
            strand_ids=strand_ids,
        )
    return mid
```

- [ ] **Step 37: Add `traversal_direction` to `memory_search` tool (lines 40–54)**

```python
@mcp.tool
def memory_search(
    query: str,
    tags: list[str] | None = None,
    agent_ids: list[str] | None = None,
    limit: int = 10,
    traversal_direction: str = "none",
) -> list[dict]:
    """Search the memory fabric by semantic similarity."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.search_memory(
            query,
            tags=tags,
            agent_ids=agent_ids,
            limit=limit,
            traversal_direction=traversal_direction,
        )
```

- [ ] **Step 38: Update `_CLOSE_SESSION_SCAFFOLD` (lines 109–128)**

```python
_CLOSE_SESSION_SCAFFOLD = """\
## Session close-out

Review this session and answer the following before ending:

1. What decisions were made? (store as type: decision)
   → memory_add(fact="...", type="decision", strand_ids=["<strand-id>"])

2. What was learned or observed about the user? (store as type: insight or observation)
   → memory_add(fact="...", so_what="...", type="insight", strand_ids=["<strand-id>"])

3. What actions were committed to? (store as type: todo)
   → memory_add(fact="...", type="todo", strand_ids=["<strand-id>"])

4. What context should a future session know that isn't already in the fabric?
   → memory_add(fact="...", so_what="...", type="fact", strand_ids=["<strand-id>"])

5. Are there causal links between memories? Link them explicitly.
   → memory_add(fact="...", type="fact", cause_ids=["<uuid>"], effect_ids=["<uuid>"])

Run memory_list_strands() if strand IDs are uncertain.
Do not end the session without calling memory_add at least once if any of the above apply.\
"""
```

- [ ] **Step 39: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 40: Commit**

```bash
git add mcp_server/server.py
git commit -m "feat(WP-028): update MCP server — memory_add fact/so_what/cause_ids, memory_search traversal_direction"
```

---

## Task 9: Migration script (`scripts/migrate_fact_so_what.py`)

**Context:** New script. Reads Memory nodes without `fact` set, outputs JSON lines on stdout for each, reads `fact`/`so_what` answers from stdin, writes them back. Idempotent; `--dry-run` flag.

**Files:**
- Create: `scripts/migrate_fact_so_what.py`

- [ ] **Step 41: Create the migration script**

```python
#!/usr/bin/env python3
"""
scripts/migrate_fact_so_what.py

Migrate existing Memory nodes from the legacy single `text` field to the
new `fact` / `so_what` split.

Protocol (JSON lines):
  stdout: {"id": "<uuid>", "text": "<current text>"}   — one per node without `fact`
  stdin:  {"id": "<uuid>", "fact": "<fact>", "so_what": "<so_what or null>"}

The calling process reads stdout lines and responds on stdin. This script then
writes the fact/so_what split back to Memgraph and recomputes the embedding.

Usage:
    python scripts/migrate_fact_so_what.py [--dry-run] [--batch-size N]

Flags:
    --dry-run       Print JSON lines to stdout but do not read stdin or write.
    --batch-size N  Number of nodes to fetch per Memgraph query (default 100).
"""

import json
import sys
import argparse
from datetime import datetime, timezone

from memory_service.config import get_driver, settings
from memory_service.embeddings import get_embedding


def fetch_batch(session, batch_size: int) -> list[dict]:
    # Always fetch from SKIP 0: as nodes are migrated (m.fact set), they leave
    # the WHERE m.fact IS NULL result set, so offset-based pagination is incorrect.
    result = session.run(
        """
        MATCH (m:Memory)
        WHERE m.fact IS NULL
        RETURN m.id AS id, m.text AS text
        ORDER BY m.created_at
        LIMIT $limit
        """,
        limit=batch_size,
    )
    return [{"id": r["id"], "text": r["text"]} for r in result]


def write_node(session, node_id: str, fact: str, so_what: str | None) -> None:
    text = fact + (" " + so_what if so_what else "")
    embedding = get_embedding(text)
    session.run(
        """
        MATCH (m:Memory {id: $id})
        SET m.fact = $fact,
            m.so_what = $so_what,
            m.text = $text,
            m.embedding = $embedding
        """,
        id=node_id,
        fact=fact,
        so_what=so_what,
        text=text,
        embedding=embedding,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Memory nodes to fact/so_what split")
    parser.add_argument("--dry-run", action="store_true", help="Print only, do not write")
    parser.add_argument("--batch-size", type=int, default=100, help="Nodes per batch")
    args = parser.parse_args()

    driver = get_driver(settings)
    total = 0

    while True:
        with driver.session() as session:
            # Always fetch from SKIP 0: migrated nodes leave the WHERE m.fact IS NULL
            # result set, so offset-based pagination would skip unmigrated nodes.
            batch = fetch_batch(session, args.batch_size)
        if not batch:
            break

        for node in batch:
            print(json.dumps({"id": node["id"], "text": node["text"]}), flush=True)
            total += 1

            if not args.dry_run:
                line = sys.stdin.readline()
                if not line:
                    print("[migrate] stdin closed — stopping", file=sys.stderr)
                    driver.close()
                    sys.exit(1)
                answer = json.loads(line.strip())
                fact = answer["fact"]
                so_what = answer.get("so_what") or None
                with driver.session() as session:
                    write_node(session, node["id"], fact, so_what)

    driver.close()
    print(f"[migrate] done — processed {total} nodes", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 42: Test dry-run (no live stack changes)**

```bash
python scripts/migrate_fact_so_what.py --dry-run
```

Expected: JSON lines printed for each Memory node without `fact`, no writes to Memgraph.

- [ ] **Step 43: Test idempotency — run twice after a node has been migrated**

If any nodes were migrated in step 42 (or manually):
```bash
python scripts/migrate_fact_so_what.py --dry-run
```

Expected: Only nodes still missing `fact` appear. Migrated nodes are skipped.

- [ ] **Step 44: Commit**

```bash
git add scripts/migrate_fact_so_what.py
git commit -m "feat(WP-028): migration script — fact/so_what split, JSON-line protocol, --dry-run"
```

---

## Task 10: Final verification

- [ ] **Step 45: Run complete test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass — unit, integration (against live stack).

- [ ] **Step 46: Live round-trip smoke test**

```bash
# Add cause memory
CAUSE_ID=$(memory add-memory "Oliver has ADHD." --type fact --strand-id strand-core-health)
echo "Cause: $CAUSE_ID"

# Add effect memory, linking to cause
EFFECT_ID=$(memory add-memory "Oliver needs structure and short feedback loops." \
  --type insight --strand-id strand-core-health --cause-id "$CAUSE_ID")
echo "Effect: $EFFECT_ID"

# Search for effect with causes traversal — cause should appear in neighbours
memory search-memory "structure feedback loops" --traversal-direction causes --max-hops 1
```

Expected: search result for the effect memory shows `cause_id` in neighbours.

- [ ] **Step 47: Verify LEADS_TO edge in Memgraph Lab**

Open http://localhost:3000 and run:
```cypher
MATCH (a:Memory)-[r:LEADS_TO]->(b:Memory) RETURN a, r, b LIMIT 10
```

Expected: edge(s) visible in graph view.

- [ ] **Step 48: Update BACKLOG.md — mark WP-028 complete**

In `BACKLOG.md`:
- Remove WP-028 row from `## Currently In Progress`
- Add to `## Completed` section:
  ```
  | WP-028 | Causal graph: `fact`/`so_what` fields + `LEADS_TO` edge | Done | 2026-03-21 |
  ```
- Add retrospective note

- [ ] **Step 49: Final commit**

```bash
git add BACKLOG.md
git commit -m "WP-028: causal graph complete — fact/so_what + LEADS_TO + traversal_direction"
```
