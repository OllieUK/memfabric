# WP-028: Causal Graph — `fact`/`so_what` Fields + `LEADS_TO` Edge

## Goal

Split the current single `text` field on Memory nodes into `fact` (observable statement) and `so_what` (impact/meaning), derive `text` as their concatenation for embedding, and introduce a directed `LEADS_TO` edge for explicit causal relationships between memories. Include `traversal_direction` on search to traverse causal chains.

## Architecture

The change touches the full stack vertically: service schema → repo → API → client → CLI → MCP server. No new services or infrastructure required. Migration script handles existing memories. All changes are backwards-compatible for one release via a `text` alias on `AddMemoryRequest`.

## Tech Stack

FastAPI, Memgraph (Cypher + MAGE vector search), sentence-transformers (local embeddings), httpx client, Typer CLI, FastMCP.

---

## Data Model

### Memory node — new properties

| Property | Type | Description |
|----------|------|-------------|
| `fact` | `str` | The raw, observable fact. e.g. *"Oliver has ADHD."* Required on new writes. |
| `so_what` | `str \| None` | The impact or meaning. e.g. *"Structure and short feedback loops matter more than motivation."* Optional. |
| `text` | `str` | Derived at write time: `fact + " " + so_what` (or just `fact` if `so_what` is absent). Still the embedding target and primary search field. Unchanged as a stored property. |

Existing Memory nodes without `fact`/`so_what` are left as-is. Cypher queries use `coalesce(m.fact, m.text, "")` where needed.

### New edge type: `LEADS_TO`

| Edge | Direction | Meaning |
|------|-----------|---------|
| `LEADS_TO` | Memory → Memory | Explicit causal link: this fact produces or enables this consequence. Directional, not symmetric. |

Properties: none in v1 (weight/reinforcement deferred to WP-029).

Multiple causes can converge on one effect node. One cause can have multiple effects. The graph is a DAG in practice; cycles are possible but rare.

No `init_schema.py` changes — Memgraph handles new edge types dynamically.

**`create_effect_node` is explicitly out of scope.** Callers always create both Memory nodes explicitly and wire them via `cause_ids`/`effect_ids`.

---

## API

### `POST /memory` — request body additions

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `fact` | `str` | required | Replaces `text` as primary input. |
| `so_what` | `str \| None` | `None` | Optional consequence statement. |
| `cause_ids` | `list[str]` | `[]` | Existing Memory UUIDs that cause *this* memory. Creates `LEADS_TO` edges pointing *to* this node. |
| `effect_ids` | `list[str]` | `[]` | Existing Memory UUIDs that *this* memory causes. Creates `LEADS_TO` edges pointing *from* this node. |
| `text` | `str \| None` | `None` | **Deprecated alias.** If `fact` absent and `text` present, `fact = text`, `so_what = None`. |

Backwards-compat validation rule (enforced in `AddMemoryRequest`):
- Both `fact` and `text` absent → 422
- Both present → `fact` wins, `text` ignored
- `text` only → `fact = text`, `so_what = None`

### `POST /memory/search` — additions

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `traversal_direction` | `"none" \| "causes" \| "effects" \| "both"` | `"none"` | Controls LEADS_TO traversal in addition to existing RELATED_TO expansion. |

When `traversal_direction != "none"`, additional `OPTIONAL MATCH` clauses on `LEADS_TO` are appended to the search query. Results are merged into the existing `neighbours` list — no new response field.

- `"causes"` → `OPTIONAL MATCH (m)<-[:LEADS_TO*1..{max_hops}]-(c:Memory)`
- `"effects"` → `OPTIONAL MATCH (m)-[:LEADS_TO*1..{max_hops}]->(e:Memory)`
- `"both"` → both clauses

---

## Repository Layer (`memory_service/memory_repo.py`)

### `add_memory()` — two new steps

After existing steps 1–5:

**Step 6 — cause_ids:** For each UUID in `cause_ids`:
```cypher
MATCH (cause:Memory {id: $cause_id})
MATCH (effect:Memory {id: $effect_id})
MERGE (cause)-[:LEADS_TO]->(effect)
```
If source UUID doesn't exist → skip silently, log warning. `MERGE` ensures idempotency.

**Step 7 — effect_ids:** Same pattern, direction reversed.

### Embedding derivation

Moves to the FastAPI handler before calling `add_memory`:
```python
text = req.fact + (" " + req.so_what if req.so_what else "")
embedding = get_embedding(text)
```
`text` and `embedding` passed into repo as today.

### Search query (`_SEARCH_QUERY_TEMPLATE`)

The neighbour clause is extended based on `traversal_direction`. The `LEADS_TO` neighbours are collected and merged with `RELATED_TO` neighbours into the same `neighbours` list returned to the caller.

---

## Migration Script (`scripts/migrate_fact_so_what.py`)

- Reads all Memory nodes in batches (default 100)
- For each node without `fact` set: prints `id` + current `text`, accepts `fact` / `so_what` as structured input (suitable for a calling process with contextual intelligence)
- Writes back `fact`, `so_what`, recomputes `text = fact + " " + so_what`, recomputes and stores embedding
- `--dry-run` flag: prints proposed writes without executing
- Idempotent: skips nodes that already have `fact` set
- Runs in same maintenance window as WP-037 migration

---

## Client Layer

### `memory_client/client.py` — `add_memory()` new signature

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
```

`text` parameter removed. Body sends `fact` + `so_what`; no `text` key sent.

### `memory_client/cli.py` — `add-memory` command

- `text` positional argument → `fact` positional argument
- New `--so-what` option (optional string)
- New `--cause-id` option (repeatable)
- New `--effect-id` option (repeatable)

### `mcp_server/server.py` — `memory_add` tool

```python
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
```

`text` parameter removed. `_CLOSE_SESSION_SCAFFOLD` updated to use `fact=` and `so_what=` in example calls.

### `mcp_server/server.py` — `memory_search` tool

Gains `traversal_direction: str = "none"` parameter, passed through to the API.

---

## Files Changed

| File | Change |
|------|--------|
| `memory_service/main.py` | `AddMemoryRequest`: add `fact`, `so_what`, `cause_ids`, `effect_ids`; deprecate `text`; derive `text` + embedding in handler |
| `memory_service/memory_repo.py` | `add_memory()`: steps 6–7 for LEADS_TO; search query: `traversal_direction` support |
| `memory_service/search_models.py` | Add `traversal_direction` to `SearchRequest` (if in separate file; else `main.py`) |
| `memory_client/client.py` | Update `add_memory()` signature; update `search_memory()` to accept `traversal_direction` |
| `memory_client/cli.py` | `add-memory`: replace `text` with `fact`, add `--so-what`, `--cause-id`, `--effect-id` |
| `mcp_server/server.py` | Update `memory_add` tool signature; update `_CLOSE_SESSION_SCAFFOLD`; add `traversal_direction` to `memory_search` |
| `scripts/migrate_fact_so_what.py` | New migration script |
| `tests/test_add_memory.py` | Add `fact`/`so_what` and LEADS_TO tests; keep all existing tests passing |
| `tests/test_search_memory.py` | Add `traversal_direction` tests |

---

## Testing

### Unit tests (no live stack)

- `AddMemoryRequest` validation: `fact` required, `text` alias works, both present → `fact` wins, neither → 422
- `text` derivation: `fact` only → `text == fact`; `fact + so_what` → `text == fact + " " + so_what`

### Integration tests (live Memgraph + FastAPI)

**Add memory:**
- `fact` + `so_what` stored correctly; `text` derived and stored on node
- `cause_ids` → `LEADS_TO` edges created pointing to new node
- `effect_ids` → `LEADS_TO` edges created pointing from new node
- Missing UUID in `cause_ids`/`effect_ids` → silently skipped, rest of write succeeds
- Deprecated `text` alias → node created with `fact=text`, `so_what=None`
- All existing `test_add_memory.py` tests pass unchanged

**Search:**
- `traversal_direction="none"` → same behaviour as today (RELATED_TO only)
- `traversal_direction="causes"` → LEADS_TO upstream nodes appear in `neighbours`
- `traversal_direction="effects"` → LEADS_TO downstream nodes appear in `neighbours`
- `traversal_direction="both"` → both directions in `neighbours`

**Migration script:**
- Dry-run: no writes, correct output printed
- Idempotency: running twice on same node produces no duplicate writes

### Acceptance criteria

- [ ] `POST /memory` accepts `fact`, `so_what`, `cause_ids`, `effect_ids`
- [ ] `Memory.text` is computed as `fact + " " + so_what` (or just `fact` if no `so_what`)
- [ ] `LEADS_TO` edges created correctly for `cause_ids` and `effect_ids` paths
- [ ] Missing UUIDs in `cause_ids`/`effect_ids` are skipped gracefully
- [ ] `POST /memory/search` `traversal_direction` parameter works for all four values
- [ ] Deprecated `text` alias accepted and handled correctly
- [ ] All existing tests pass (backwards compat)
- [ ] Migration script runs dry-run correctly and is idempotent
- [ ] Live graph shows `LEADS_TO` edges after a round-trip test
