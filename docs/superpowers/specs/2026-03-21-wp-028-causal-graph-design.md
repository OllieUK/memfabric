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

**`fact` and `so_what` are not returned in `AddMemoryResponse` or `MemoryHit` in v1.** `text` (the derived field) continues to be the search/display field. This is intentional — adding these fields to response models is deferred.

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

Backwards-compat validation is implemented via a Pydantic `model_validator(mode='before')` on `AddMemoryRequest`:
- Both `fact` and `text` absent → raise `ValueError` → 422
- Both present → `fact` wins, `text` ignored
- `text` only → set `fact = text`, `so_what = None`

Example validator:
```python
@model_validator(mode='before')
@classmethod
def resolve_fact(cls, values):
    fact = values.get('fact')
    text = values.get('text')
    if not fact and not text:
        raise ValueError("Either 'fact' or 'text' must be provided")
    if not fact and text:
        values['fact'] = text
    return values
```

### `POST /memory/search` — additions

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `traversal_direction` | `"none" \| "causes" \| "effects" \| "both"` | `"none"` | Controls LEADS_TO traversal in addition to existing RELATED_TO expansion. |

`traversal_direction` operates **independently of `max_hops`**. When `max_hops=0` and `traversal_direction != "none"`, LEADS_TO neighbours are still collected (the zero-hop short-circuit only suppresses RELATED_TO expansion). When `max_hops > 0`, LEADS_TO traversal uses the same hop depth N as RELATED_TO:
- `"causes"` → `OPTIONAL MATCH (m)<-[:LEADS_TO*1..N]-(c:Memory)`
- `"effects"` → `OPTIONAL MATCH (m)-[:LEADS_TO*1..N]->(e:Memory)`
- `"both"` → both clauses

Results from LEADS_TO traversal are merged into the existing `neighbours` list — no new response field.

---

## Repository Layer (`memory_service/memory_repo.py`)

### `add_memory()` — two new steps

After existing steps 1–5:

**Step 6 — cause_ids:** For each UUID `cid` in `cause_ids`, create a `LEADS_TO` edge from that existing Memory to the newly created Memory. The new node's id is `memory_id` (the UUID generated in the handler). `MATCH` is used on the source so missing UUIDs are silently skipped:

```cypher
OPTIONAL MATCH (cause:Memory {id: $cause_id})
WITH cause
WHERE cause IS NOT NULL
MATCH (effect:Memory {id: $new_memory_id})
MERGE (cause)-[:LEADS_TO]->(effect)
```

Parameters: `$cause_id = cid`, `$new_memory_id = memory_id`.

**Step 7 — effect_ids:** For each UUID `eid` in `effect_ids`, create a `LEADS_TO` edge from the newly created Memory to that existing Memory:

```cypher
OPTIONAL MATCH (effect:Memory {id: $effect_id})
WITH effect
WHERE effect IS NOT NULL
MATCH (cause:Memory {id: $new_memory_id})
MERGE (cause)-[:LEADS_TO]->(effect)
```

Parameters: `$effect_id = eid`, `$new_memory_id = memory_id`.

Both steps use `MERGE` on the edge for idempotency. If the UUID from the list doesn't exist the query returns no rows and no edge is created — no exception raised. Log a warning at DEBUG level for each skipped UUID.

### Embedding derivation

Moves to the FastAPI handler before calling `add_memory`:
```python
text = req.fact + (" " + req.so_what if req.so_what else "")
embedding = get_embedding(text)
```
`text` and `embedding` passed into repo as today.

### Search query (`_SEARCH_QUERY_TEMPLATE`)

The `search_memories` function builds the neighbour clause dynamically. The existing logic handles `max_hops=0` (suppresses RELATED_TO) and `max_hops>0` (adds RELATED_TO expansion). This is extended to also handle `traversal_direction`.

For the `"both"` case with `max_hops=2`, the target Cypher shape is:

```cypher
CALL vector_search.search("mem_embedding_idx", $limit, $query_vec)
YIELD node AS m, distance
WITH m, distance
WHERE ($tags IS NULL OR ANY(t IN m.tags WHERE t IN $tags))
OPTIONAL MATCH (m)-[:PRODUCED_BY]->(a:Agent)
WITH m, distance, a
WHERE ($agent_ids IS NULL OR a.id IN $agent_ids)
OPTIONAL MATCH (m)-[:ABOUT]->(p:Project)
WITH m, distance, p
WHERE ($project_ids IS NULL OR p.id IN $project_ids)
OPTIONAL MATCH (m)-[:RELATED_TO*1..2]->(n:Memory)
OPTIONAL MATCH (m)<-[:LEADS_TO*1..2]-(c:Memory)
OPTIONAL MATCH (m)-[:LEADS_TO*1..2]->(e:Memory)
RETURN m.id AS id, m.text AS text, m.type AS type, m.tags AS tags,
       m.importance AS importance, distance,
       collect(DISTINCT n.id) + collect(DISTINCT c.id) + collect(DISTINCT e.id) AS neighbours
ORDER BY distance ASC
```

When `traversal_direction="none"` and `max_hops=0`: all three `OPTIONAL MATCH` blocks are omitted and `[] AS neighbours` is returned (existing behaviour preserved).

When `traversal_direction="none"` and `max_hops>0`: only the `RELATED_TO` block is included (existing behaviour preserved).

When `traversal_direction != "none"` and `max_hops=0`: only the relevant LEADS_TO block(s) are included; RELATED_TO block is omitted.

---

## Migration Script (`scripts/migrate_fact_so_what.py`)

- Reads all Memory nodes without `fact` set, in batches (default 100)
- For each node: outputs a JSON line to stdout:
  ```json
  {"id": "<uuid>", "text": "<current text>"}
  ```
- Reads responses from stdin as JSON lines:
  ```json
  {"id": "<uuid>", "fact": "<fact text>", "so_what": "<so_what text or null>"}
  ```
- The calling process (e.g. a Claude session) reads the output, produces the split, and writes responses back on stdin — this is the intended "contextual intelligence" interface
- Writes back `fact`, `so_what`, recomputes `text = fact + " " + so_what` (or just `fact`), recomputes and stores embedding
- `--dry-run` flag: emits the JSON lines to stdout but reads no stdin responses and writes nothing
- Idempotent: skips nodes that already have `fact` property set (regardless of value)
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

### `memory_client/client.py` — `search_memory()` updated signature

```python
def search_memory(
    self,
    query: str,
    *,
    tags: list[str] | None = None,
    agent_ids: list[str] | None = None,
    limit: int = 10,
    traversal_direction: str = "none",
) -> list[dict]:
```

`traversal_direction` is keyword-only with default `"none"`. Passed as a field in the POST body.

### `memory_client/cli.py` — `add-memory` command

- `text` positional argument → `fact` positional argument
- New `--so-what` option (optional string)
- New `--cause-id` option (repeatable, like `--strand-id`)
- New `--effect-id` option (repeatable)

### `memory_client/cli.py` — `search-memory` command

- New `--traversal-direction` option (string, default `"none"`, choices: `none|causes|effects|both`)

### `memory_client/cli.py` — `close-session` scaffold

Update the embedded scaffold text to use `--fact` / `--so-what` instead of `--text`.

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
| `memory_service/main.py` | `AddMemoryRequest`: add `fact`, `so_what`, `cause_ids`, `effect_ids`; deprecate `text` via `model_validator`; derive `text` + embedding in handler |
| `memory_service/memory_repo.py` | `add_memory()`: steps 6–7 for LEADS_TO with correct param bindings; search query: `traversal_direction` support with combined collect expression |
| `memory_client/client.py` | Update `add_memory()` signature; update `search_memory()` to accept `traversal_direction` |
| `memory_client/cli.py` | `add-memory`: replace `text` with `fact`, add `--so-what`, `--cause-id`, `--effect-id`; `search-memory`: add `--traversal-direction`; `close-session`: update scaffold text |
| `mcp_server/server.py` | Update `memory_add` tool signature; update `_CLOSE_SESSION_SCAFFOLD`; add `traversal_direction` to `memory_search` |
| `scripts/migrate_fact_so_what.py` | New migration script (JSON line stdin/stdout protocol, --dry-run, idempotent) |
| `tests/test_add_memory.py` | Add `fact`/`so_what` and LEADS_TO tests; keep all existing tests passing |
| `tests/test_search_memory.py` | Add `traversal_direction` tests |

---

## Testing

### Unit tests (no live stack)

- `AddMemoryRequest` validation via `model_validator`:
  - `fact` only → accepted
  - `text` only → `fact = text`, `so_what = None`
  - Both `fact` and `text` → `fact` wins
  - Neither → 422
- `text` derivation: `fact` only → `text == fact`; `fact + so_what` → `text == fact + " " + so_what`

### Integration tests (live Memgraph + FastAPI)

**Add memory:**
- `fact` + `so_what` stored correctly; `text` derived and stored on node
- `cause_ids` → `LEADS_TO` edges created pointing to new node (cause → new)
- `effect_ids` → `LEADS_TO` edges created pointing from new node (new → effect)
- Missing UUID in `cause_ids`/`effect_ids` → silently skipped, rest of write succeeds
- Deprecated `text` alias → node created with `fact=text`, `so_what=None`
- All existing `test_add_memory.py` tests pass unchanged

**Search:**
- `traversal_direction="none"` → same behaviour as today (RELATED_TO only)
- `traversal_direction="causes"`, `max_hops=0` → LEADS_TO upstream nodes in `neighbours`, RELATED_TO not expanded
- `traversal_direction="effects"` → LEADS_TO downstream nodes in `neighbours`
- `traversal_direction="both"` → both directions in `neighbours`
- Round-trip (`max_hops=1`): insert cause → insert effect with `cause_ids=[cause_id]` → search for effect with `traversal_direction="causes", max_hops=1` → cause appears in `neighbours`

**Migration script:**
- Dry-run: JSON lines emitted to stdout, no writes
- Normal run with mocked stdin: nodes updated correctly
- Idempotency: second run skips all nodes (all have `fact` set)

### Acceptance criteria

- [ ] `POST /memory` accepts `fact`, `so_what`, `cause_ids`, `effect_ids`
- [ ] `Memory.text` is computed as `fact + " " + so_what` (or just `fact` if no `so_what`)
- [ ] `LEADS_TO` edges created correctly for `cause_ids` and `effect_ids` paths (correct direction each)
- [ ] Missing UUIDs in `cause_ids`/`effect_ids` are skipped gracefully
- [ ] `POST /memory/search` `traversal_direction` parameter works for all four values
- [ ] `traversal_direction` works independently of `max_hops` (including `max_hops=0`)
- [ ] Deprecated `text` alias accepted and handled correctly via `model_validator`
- [ ] All existing tests pass (backwards compat)
- [ ] `search-memory --traversal-direction causes` works from CLI
- [ ] Migration script: dry-run correct, idempotent on second run
- [ ] Live graph shows `LEADS_TO` edges after round-trip test
