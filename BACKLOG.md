# Graph-Memory Fabric – Feature Backlog

> **Value:** H = High / M = Medium / L = Low
> **Effort:** S = Small (hrs) / M = Medium (day) / L = Large (days) / XL = Extra-large (week+)

---

## Currently In Progress

| ID | Title | Phase | Value | Effort | Depends on | Notes |
|----|-------|-------|-------|--------|------------|-------|

---

## Prioritised Backlog

> **MVP** = minimum to store and retrieve memories via CLI day-to-day.
> Complete MVP work packages in order before moving to post-MVP items.

### 🎯 MVP — Store + retrieve memories via CLI

*(MVP complete — all items delivered)*

### Post-MVP — Companion integration (expanded MVP)

> Companion access is the priority gate. Nothing in "Complete v1 feature set" below starts until WP-032 (end-to-end validation) is done.

| ID | Title | Phase | Value | Effort | Depends on | Notes |
|----|-------|-------|-------|--------|------------|-------|

### Post-MVP — Complete v1 feature set

| ID | Title | Phase | Value | Effort | Depends on | Notes |
|----|-------|-------|-------|--------|------------|-------|
| WP-037 | Person nodes + `ABOUT` edges — schema, API, migration | 4 | H | M | WP-028 | Wire `Person` nodes and `ABOUT (Memory→Person)` edges. Add `person_ids: list[str]` to `POST /memory` request body and `memory_repo.add_memory`. Add `GET /person` list endpoint. Write migration script to scan existing memories and create ABOUT edges for named individuals (~15–20 memories). Do immediately after WP-028 (shares the migration pass). See detailed description below. |
| WP-029 | Memory + edge reinforcement (strength, decay, Hebbian activation) | 4 | H | L | WP-028 | **Do before WP-006** — adds reinforcement properties to nodes and edges; WP-006 graph export should reflect the final schema. See detailed description below. |
| WP-006 | Wire GET /memory/graph | 4 | M | M | WP-028, WP-029 | Filtered subgraph export: project/agent/tag/since/until params; returns `{nodes, edges}`. Do after WP-028/029 so exported schema is complete. |
| WP-012 | Pin dependency versions in requirements.txt | 1 | M | S | — | Use `>=x,<y` bounds for reproducibility; research compatible version matrix. Do before stack is considered stable. |
| WP-013 | Pin Docker image tags (no `latest`) | 1 | M | S | WP-012 | Replace `memgraph/memgraph-mage:latest` + `memgraph/lab:latest` with specific versions. Do after stack stabilises (after WP-012). |
| WP-014 | Docker resource limits | 1 | L | S | — | Add `mem_limit`/`cpus` to docker-compose to prevent runaway resource use. |
| WP-017 | Embedding cache eviction / size cap | 3 | L | S | WP-003 | `EMBEDDING_CACHE_DIR` grows without bound. Add LRU eviction or max-entry cap before long-running deployments. `/simplify` finding from WP-003. |
| WP-019 | Expose vector index `capacity` as config | 3 | L | S | WP-016 | `capacity: 1000` is hardcoded in `init_schema.py`'s index query. Add `vector_index_capacity: int = 1000` to `Settings` and use it in `create_vector_index`. `/simplify` finding from WP-018. |
| WP-022 | Cap neighbour count in search results | 4 | M | S | WP-005 | `collect(DISTINCT n.id)` in search query is unbounded; with `max_hops=3` on a dense graph this can return thousands of UUIDs per result row. Add a slice cap (e.g. `[..50]`) in `_SEARCH_QUERY_TEMPLATE`. `/simplify` finding from WP-005. |
| WP-023 | Extract `get_session` context manager for 503 handling | 4 | L | S | WP-006 | The `try/with driver.session()/except ServiceUnavailable→503` block is copy-pasted across all endpoints. Extract to a context manager or dependency helper. WP-006 creates the 3rd copy; WP-029 adds further endpoints — do after either. `/simplify` finding from WP-005. |
| WP-020 | UNWIND for person/strand/related_ids writes | 4 | L | S | WP-004 | Steps 3/4/5a in `memory_repo.add_memory` loop with one `session.run()` per item. Replace with UNWIND queries for bulk-friendly writes. Negligible at v1 cardinality; add `related_ids` max-length cap (e.g. 20) at same time. `/simplify` finding from WP-004. |
| WP-021 | Non-blocking embedding in async endpoints | 4 | L | S | WP-004, WP-005 | `get_embedding()` is synchronous and blocks the event loop in both `/memory` and `/memory/search`. Wrap with `run_in_executor` when concurrent usage makes this a real problem. `/simplify` finding from WP-004. |
| WP-025 | Extract shared CLI error handler in `cli.py` | 5 | L | S | — | `add-memory`, `search-memory`, `dump-graph`, `list-strands` all repeat identical `except httpx.HTTPStatusError / ConnectError` blocks — **4 copies, trigger condition met.** Extract a shared error handler. `/simplify` finding from WP-007 and WP-027. |
| WP-026 | `MemoryType` mirror in `memory_client` | 5 | L | S | WP-007 | `add_memory(type: str)` accepts any string; mirror `MemoryType` enum from `memory_service/main.py` into `memory_client/` so callers get IDE completion without cross-package import. `/simplify` finding from WP-007. |
| WP-024 | `cleanup_nodes` support multiple ids per label | 5 | L | S | — | `extra_ids: dict[str, str]` only supports one node per label; test modules that need to clean two Agent or Project nodes must open a second session. Change to `dict[str, str \| list[str]]`. `/simplify` finding from WP-005. |
| WP-034 | Add version/build hash to `/health` response | 5 | L | S | — | Detect stale service during companion session startup. Gap found in WP-032 validation: service ran stale code silently. |
| WP-035 | Return strand_ids in `add-memory` API response | 5 | L | S | — | Reduce friction when adding chains of related memories. Gap found in WP-032 validation. |
| WP-036 | Document `### Relevant to today` suppression behaviour in COMPANION.md | 5 | L | S | — | Avoid companion confusion when topic section is absent on small DBs. Gap found in WP-032 validation. |

---

### WP-028 Detail — Causal graph: `fact`/`so_what` fields + `LEADS_TO` edge

#### Motivation

Every memory in the Memory Web has two conceptual parts: the **fact** (what is true) and the **so what** (why it matters / what it causes or constrains). The current data model stores a single `text` field that conflates both. This makes it impossible to:

- Traverse *backwards* from a consequence to its causes ("why does Oliver respond well to structure?")
- Traverse *forwards* from a root fact to everything it shapes downstream
- Distinguish raw factual retrieval from impact/meaning retrieval in search

#### Data model changes

**New Memory node properties:**

| Property | Type | Description |
|----------|------|-------------|
| `fact` | `str` | The raw, observable fact. e.g. *"Oliver has ADHD."* |
| `so_what` | `str \| None` | The impact or meaning. e.g. *"Structure and short feedback loops matter more than motivation."* |
| `text` | `str` | Embedding target: `fact + " " + so_what` (computed at write time). Unchanged as the search field. |

`so_what` is optional — not every memory type (e.g. `event`, `todo`) has a meaningful consequence statement.

**New edge type:**

| Edge | Direction | Meaning |
|------|-----------|---------|
| `LEADS_TO` | Memory → Memory | Causal: this fact produces or enables this consequence. Directional, not symmetric. |

`LEADS_TO` complements `RELATED_TO` (semantic/associative, auto-linked by vector search). The difference:
- `RELATED_TO`: *these memories are conceptually close*
- `LEADS_TO`: *this memory is a cause or precondition of that memory*

**Example graph fragment:**

```
(Oliver has ADHD) ──LEADS_TO──► (Oliver responds well to structure and short feedback loops)
(Oliver trained as engineer) ──LEADS_TO──► (Oliver responds well to structure and short feedback loops)
(Oliver responds well to structure) ──LEADS_TO──► (Oliver enjoys D&D — clear rules, structured world)
(Oliver responds well to structure) ──LEADS_TO──► (Oliver uses Notion + checklists for everything)
```

Multiple causes can converge on a single consequence node. A consequence can itself be a cause further downstream. The graph is a DAG (in practice; cycles are possible but should be rare and meaningful).

#### API changes

`POST /memory` request body gains:

```json
{
  "fact": "Oliver has ADHD.",
  "so_what": "Structure and short feedback loops matter more than motivation.",
  "cause_ids": ["<memory-uuid>"],
  "effect_ids": ["<memory-uuid>"],
  "create_effect_node": true
}
```

- `fact` replaces `text` as the primary input field. `text` is derived internally.
- `so_what` is optional. If provided and `create_effect_node=true`, the service auto-creates a new Memory node for the consequence and links it with `LEADS_TO`.
- `cause_ids`: explicit list of existing Memory UUIDs that cause *this* memory → creates `LEADS_TO` edges pointing *to* this node.
- `effect_ids`: explicit list of existing Memory UUIDs that *this* memory causes → creates `LEADS_TO` edges pointing *from* this node.

#### Search changes

`POST /memory/search` gains a `traversal_direction` parameter:

| Value | Behaviour |
|-------|-----------|
| `"none"` (default) | Current behaviour: `RELATED_TO` expansion only |
| `"causes"` | Also traverse `LEADS_TO` edges *backwards* (find contributing causes) |
| `"effects"` | Also traverse `LEADS_TO` edges *forwards* (find downstream consequences) |
| `"both"` | Both directions |

#### Backwards compatibility

- `text` field on `AddMemoryRequest` is kept as a deprecated alias for `fact` (for one release). If `text` is provided and `fact` is not, `fact = text` and `so_what = None`.
- Existing Memory nodes without `fact`/`so_what` properties are unaffected. The properties are simply absent; Cypher queries handle missing properties gracefully with `coalesce()`.

#### Definition of Success

- [ ] `POST /memory` accepts `fact`, `so_what`, `cause_ids`, `effect_ids`, `create_effect_node`
- [ ] `Memory.text` is computed as `fact + " " + so_what` (or just `fact` if no `so_what`)
- [ ] `LEADS_TO` edges created correctly for all four ingestion paths (cause_ids, effect_ids, create_effect_node, none)
- [ ] `POST /memory/search` supports `traversal_direction` parameter
- [ ] At least one round-trip test: insert cause + effect, search for effect, traverse back to cause
- [ ] Existing tests pass (backwards compat via `text`→`fact` alias)
- [ ] `scripts/seed_strands.py` unchanged — no Strand schema impact

---

### WP-037 Detail — Person nodes + `ABOUT` edges

#### Motivation

As the memory fabric fills up, many memories refer to named individuals (Oliver, colleagues, family, etc.). Without Person nodes, these memories are isolated text blobs — there is no way to:

- Ask "what do I know about person X?"
- Traverse from a person to all related memories
- Search within a person context (e.g. `agent_ids` equivalent for people)

The Person node makes named individuals first-class citizens in the graph, mirroring how Strand nodes organise memories by topic.

#### Data model

**New node:**

| Label | Properties |
|-------|-----------|
| `Person` | `id` (kebab-case string, e.g. `oliver-james`), `name` (display name), `description` (optional, free-text bio) |

**New edge:**

| Edge | Direction | Meaning |
|------|-----------|---------|
| `ABOUT` | Memory → Person | This memory is about (or directly involves) this person |

`ABOUT` is similar in role to `IN_STRAND` — a memory can be ABOUT multiple people.

#### API changes

`POST /memory` request body gains:

```json
{
  "person_ids": ["oliver-james", "sarah-chen"]
}
```

`GET /person` — new list endpoint, returns all Person nodes (id, name, description).

`POST /person` — create or merge a Person node by id.

#### Migration

After WP-028 runs its migration pass, run a second pass for Person nodes:

1. Script scans all existing Memory nodes
2. For each memory whose `text` (or `fact`) mentions a named individual, create the Person node (MERGE on id) and wire an `ABOUT` edge
3. Estimated scope: ~15–20 memories out of current ~82 require wiring
4. Script is idempotent (MERGE semantics) — safe to re-run

This migration runs immediately after the WP-028 migration pass, in the same maintenance window (avoid running the service twice across users during a single batch).

#### Definition of Success

- [ ] `Person` nodes exist in the schema (init_schema updated)
- [ ] `POST /memory` accepts `person_ids` and creates `ABOUT` edges
- [ ] `POST /person` creates/merges a Person node
- [ ] `GET /person` returns all Person nodes
- [ ] `memory_client` CLI: `memory list-persons` subcommand
- [ ] Migration script: `scripts/migrate_person_nodes.py` — idempotent, MERGE-based, scans all memories, logs each ABOUT edge created
- [ ] Integration test: add memory with `person_ids`, verify ABOUT edge exists in graph
- [ ] Migration script run against live graph; ABOUT edges verified in Memgraph Lab

---

### WP-029 Detail — Memory + edge reinforcement (strength, decay, Hebbian activation)

#### Motivation

A flat memory store treats a note written yesterday the same as a pattern confirmed over years. The reinforcement system fixes this by making the graph *self-organise around relevance over time*:

- Memories that are repeatedly recalled and confirmed as useful become **stronger** and surface higher in search results.
- Memories that are never recalled **decay** and fade into the background — still retrievable, but de-prioritised.
- Edges between memories that are frequently co-retrieved become **stronger**, making graph expansion along those paths more likely.
- Edges that were auto-created by vector similarity but never confirmed as useful weaken and are eventually excluded from traversal.

This combines two well-established mechanisms:
- **Ebbinghaus forgetting curve** (spaced repetition): strength decays exponentially with time since last reinforcement.
- **Hebbian learning**: "neurons that fire together, wire together" — co-activation of connected memories strengthens the edge between them.

---

#### Node reinforcement

**New Memory node properties:**

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `strength` | `float` (0–1) | derived from `importance` | Current reinforcement level. Decays over time; incremented on recall and explicit reinforcement. |
| `recall_count` | `int` | 0 | Total number of times this memory has appeared in a search result. Monotonically increasing — never decays. |
| `reinforcement_count` | `int` | 0 | Total number of explicit reinforcement signals received. Monotonically increasing. |
| `last_reinforced_at` | `datetime` | `created_at` | Timestamp of last explicit reinforcement. Used as the anchor for decay calculation. |
| `decay_rate` | `float` | `MEMORY_DECAY_RATE` env var (default 0.01) | Per-memory decay rate. Allows pinned/important memories to decay more slowly. |

**Initial strength** is seeded from `importance`: `strength = importance / 5.0` (so importance=5 starts at 1.0, importance=1 starts at 0.2).

**Effective strength** (computed at query time via Cypher):
```
effective_strength = strength × exp(-decay_rate × days_since_last_reinforced)
```

This is the Ebbinghaus forgetting curve. It is **not stored** — it is computed inline during search queries so it always reflects the current moment.

**Two reinforcement signals:**

| Signal | Trigger | `strength` increment | Who sends it |
|--------|---------|---------------------|--------------|
| `recall` | Memory appears in search results | +0.05 (configurable) | Server-side, automatic on every search response |
| `explicit` | Caller confirms memory was actually used | +0.20 (configurable) | Caller via `POST /memory/{id}/reinforce` |

The `recall` increment is applied automatically by the search endpoint — the caller does not need to do anything. The `explicit` increment requires the caller to actively confirm relevance, which provides a stronger signal.

**Strength ceiling:** `min(strength + increment, 1.0)` — strength is capped at 1.0.

**Search integration:** `effective_strength` is used as a secondary sort key after vector distance. Two candidates at similar distances will be ranked by their effective strength. A configurable `min_strength` filter (default 0.0, i.e. off) can exclude fully-decayed memories from results.

---

#### Edge reinforcement (Hebbian activation)

**New edge properties** (added to `RELATED_TO` and `LEADS_TO`):

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `weight` | `float` (0–1) | set at creation | Already exists on `RELATED_TO`. Now also the reinforceable activation strength, not just the initial similarity score. |
| `activation_count` | `int` | 0 | Number of times this edge has been traversed in a retrieval session. Monotonically increasing. |
| `last_activated_at` | `datetime` | `created_at` | Timestamp of last traversal. Used for decay. |
| `decay_rate` | `float` | `EDGE_DECAY_RATE` env var (default 0.005) | Edge decay rate (slower than node decay by default — connections persist longer than individual memories). |

**Effective weight** (computed at query time):
```
effective_weight = weight × exp(-decay_rate × days_since_last_activated)
```

**Activation trigger:** when a graph expansion traverses an edge (i.e. the `max_hops > 0` path in search), that edge receives a small activation increment (+0.02 by default). When an explicit reinforcement signal is sent for a memory, all edges connecting it to other memories that appeared in the *same search result set* also receive a larger increment (+0.10).

**Weak edge handling:**
- Edges with `effective_weight < EDGE_PRUNE_THRESHOLD` (default 0.05) are excluded from graph expansion queries — they remain in the DB but are dormant.
- A background maintenance operation (manual in v1, scheduled in v2) can hard-delete edges below a minimum floor (e.g. `effective_weight < 0.01` after 90 days of no activation).

---

#### New API surface

**Automatic (no caller action required):**
- `POST /memory/search` — after building the result set, the server fires a lightweight Cypher update in a background task (non-blocking): increments `recall_count` and `strength` on all returned Memory nodes; increments `activation_count` and `weight` on all edges traversed during graph expansion.

**Explicit reinforcement:**
- `POST /memory/{id}/reinforce`
  - Body: `{ "signal": "explicit", "co_recalled_ids": ["<uuid>", ...] }`
  - `signal`: always `"explicit"` for caller-initiated reinforcement (server handles `"recall"` automatically).
  - `co_recalled_ids`: optional list of other memory IDs that were recalled in the same session — used to reinforce the edges between them (Hebbian step).
  - Response: `{ "memory_id": "...", "new_strength": 0.85 }`

**Maintenance:**
- `POST /memory/maintenance/decay` — triggers a full-graph decay pass: recomputes and writes `strength` for all Memory nodes and `weight` for all edges based on their `last_reinforced_at`/`last_activated_at`. Intended for scheduled execution (e.g. nightly cron in v2). In v1, run manually via CLI (`memory run-decay`).
- `GET /memory/maintenance/weak-edges` — returns edges below the prune threshold, for review before hard deletion.

---

#### Configuration (new `.env` variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORY_DECAY_RATE` | `0.01` | Default per-node decay rate (per day) |
| `EDGE_DECAY_RATE` | `0.005` | Default per-edge decay rate (per day) |
| `RECALL_STRENGTH_INCREMENT` | `0.05` | Strength bump on automatic recall |
| `EXPLICIT_STRENGTH_INCREMENT` | `0.20` | Strength bump on explicit reinforcement |
| `EDGE_RECALL_INCREMENT` | `0.02` | Edge weight bump on traversal |
| `EDGE_EXPLICIT_INCREMENT` | `0.10` | Edge weight bump on explicit co-reinforcement |
| `EDGE_PRUNE_THRESHOLD` | `0.05` | Effective weight below which edges are excluded from traversal |
| `MIN_MEMORY_STRENGTH` | `0.0` | Minimum effective strength to appear in search results (0 = off) |

---

#### Definition of Success

- [ ] `Memory` nodes created with `strength`, `recall_count`, `reinforcement_count`, `last_reinforced_at`, `decay_rate` properties
- [ ] `strength` seeded from `importance` at creation time
- [ ] `RELATED_TO` and `LEADS_TO` edges gain `activation_count`, `last_activated_at`; `decay_rate` added to edges
- [ ] `POST /memory/search` automatically fires background recall increments (non-blocking — does not add latency to the response)
- [ ] `effective_strength` computed inline in search Cypher and used as secondary sort key
- [ ] `POST /memory/{id}/reinforce` accepts `explicit` signal + `co_recalled_ids`; updates node strength and co-edge weights
- [ ] `POST /memory/maintenance/decay` runs full decay pass; returns count of nodes + edges updated
- [ ] `GET /memory/maintenance/weak-edges` returns edges below prune threshold
- [ ] `memory run-decay` CLI command triggers maintenance decay pass
- [ ] All new config variables read from `.env` via `Settings`
- [ ] At least one round-trip test: insert memory, search for it twice, confirm `recall_count == 2` and `strength > initial_strength`
- [ ] At least one edge activation test: insert two linked memories, search with `max_hops=1`, confirm edge `activation_count` incremented
- [ ] Existing tests pass (backwards compat — new properties have defaults, old queries unaffected)

### v2+ — Future phases (not in scope for v1)

| ID | Title | Phase | Value | Effort | Depends on | Notes |
|----|-------|-------|-------|--------|------------|-------|
| WP-034 | Subject/object schema on Memory nodes | 6 | H | L | WP-028 | v2+: Add explicit `subject` and `object` fields to Memory nodes. Currently "the user" is the implied subject of all memories. This makes the schema portable across multiple users and enables memories about third parties (e.g. "the user's manager said X"). Required before any multi-user or shared-memory scenario. Keep this in mind when designing ingestion APIs — avoid hard-coded subject assumptions. |
| WP-035 | Self-contained `memory_client` packaging | 6 | M | S | WP-031 | v2+: Move `pyproject.toml` / `setup.cfg` into `memory_client/` so the package can be installed independently of the full repo. Currently the editable install targets the repo root. Needed for true portability when dropping the client into companion environments that don't have access to the full repo. |
| WP-008 | LLMClient abstraction | 7 | M | M | WP-007 | v2+: `LLMClient.ask(system, prompt, model)` wrappers for Claude/OpenAI/Ollama |
| WP-009 | Headless agent framework | 7 | M | L | WP-008 | v2+: `BaseAgent` using `memory_client` + `LLMClient`; scheduled/event-driven tasks |
| WP-010 | Remote/mobile access | 8 | L | XL | WP-009 | v2+: Tailscale/VPS hosting + TLS + API key auth |
| WP-011 | Custom graph-cloud UI | 9 | L | XL | WP-006 | v2+: React + D3.js/vis-network consuming `GET /memory/graph` |

---

## Completed

### WP-028 — Causal graph: `fact`/`so_what` fields + `LEADS_TO` edge

**Date:** 2026-03-21

- `AddMemoryRequest` split into `fact` + `so_what`; `text` deprecated as alias via `model_validator(mode="before")`; `text` derived as `fact + " " + so_what` and used for embeddings
- `cause_ids`/`effect_ids` on `AddMemoryRequest`; steps 6 & 7 in `memory_repo.add_memory()` create `LEADS_TO` edges using `OPTIONAL MATCH + WHERE IS NOT NULL + MERGE` (missing UUIDs silently skipped)
- `traversal_direction` on `SearchMemoryRequest` (`none|causes|effects|both`); `search_memories()` builds LEADS_TO clauses independently of `max_hops`; `hop_depth = max(hops, 1)` ensures traversal even when `max_hops=0`
- `memory_client/client.py`, `cli.py`, `mcp_server/server.py` all updated; `close-session` scaffolds updated to use `fact=`/`so_what=` and include causal link step
- `scripts/migrate_fact_so_what.py`: JSON-line stdin/stdout protocol, `--dry-run`, idempotent (WHERE m.fact IS NULL, always fetches from SKIP 0)
- 6 unit tests + 9 integration tests; 117 passing, 3 pre-existing mock failures

**Retrospective:** Three rounds of plan review were needed — each caught real bugs: Pydantic v2 `Optional[str] = None` vs `str = ""` sentinel, migration pagination bug (SKIP 0 not offset), vacuous test assertions. The subagent for Tasks 6–8 went beyond scope and did all three in one pass, requiring a separate fix pass for cli.py and server.py gaps. Spec reviewer caught this cleanly. Two-stage review (spec then quality) paid off — quality review caught the `not fact` vs `is None` issue which was a genuine correctness hazard.

---

### WP-033 — MCP server + Claude Code/Desktop wiring

**Date:** 2026-03-21

- FastMCP-based server in `mcp_server/` exposing 5 tools via STDIO: `memory_add`, `memory_search`, `memory_wake_up`, `memory_list_strands`, `memory_close_session`
- `pyproject.toml` consolidated (removed `setup.cfg`), `memory-mcp` entry point registered
- `.mcp.json` created at repo root for Claude Code auto-discovery
- `WIRING.md` fully updated: Claude Code MCP + CLI wiring, Claude Desktop entry-point + fallback configs
- `COMPANION.md` updated: MCP tools as preferred path, CLI as fallback
- 7 unit tests + 5 integration tests all passing

**Retrospective:** FastMCP decorator syntax is clean; fresh-client-per-call pattern safe for concurrent requests; plain-text briefing assembly avoids Rich dependency in server; `.mcp.json` auto-discovery in Claude Code works out of the box. Setup.cfg/pyproject.toml conflict required removing setup.cfg and using `--no-build-isolation` for editable installs in this environment.

---

### WP-032 — End-to-end companion validation
**Completed:** 2026-03-21

**Delivered:** Ran full companion validation session against live stack; all five criteria passed. Identified and resolved a pre-existing service-restart issue (stale uvicorn process) that caused strand_id to be absent from wake-up API responses. Created `docs/wp-032-validation-evidence.md` with PASS/FAIL evidence, gap analysis, and three new backlog items (WP-034, WP-035, WP-036).

**Retrospective:** The audit against the spec (Section 4.2) before starting WP-032 caught two deviations from WP-030 that were not caught at the time: grouping by tag instead of strand_id, and missing the topic section. Including a compliance check against the spec as part of every WP's handoff would catch these earlier. The from_topic approach (initially planned) was correctly replaced with a two-list backend design during plan review, which was a better architectural decision. The stale-service bug (no `--reload` on uvicorn start) was invisible from the CLI — no error, just wrong grouping — which argues for a version hash in `/health` (WP-034).

---

### WP-031 — `memory_client` companion package: COMPANION.md + WIRING.md + docs
**Completed:** 2026-03-21

**What was done:**
- Created `memory_client/COMPANION.md` — full session protocol: wake-up, add-memory, close-session; type/importance reference; minimal session pattern
- Created `memory_client/WIRING.md` — Claude Code wiring (active), Claude Desktop + MCP placeholder (WP-033), generic HTTP/Python fallback
- Created `docs/companion-integration.md` — high-level overview, current capability status table, quick-start snippet
- Updated BACKLOG.md: WP-031 deleted from backlog, moved to Completed

**Retrospective:** Pure docs WP — fast to execute. Placeholder MCP section in WIRING.md will need updating when WP-033 lands. COMPANION.md will also need updating when WP-028 lands (--text → --fact / --so-what).

---

### WP-030 — `memory wake-up` + `memory close-session` CLI commands
**Completed:** 2026-03-21

**What was done:**
- Added `wake_up(session, limit, topic_embedding)` to `memory_service/memory_repo.py`: importance-ranked query merged with optional vector search, deduplicated, capped at limit. Extracted `_record_to_memory_dict()` helper to avoid duplicate comprehensions.
- Added `WakeUpMemoryItem`, `WakeUpResponse` Pydantic models and `GET /memory/wake-up` endpoint to `memory_service/main.py` with `Query()` params.
- Added `MemoryClient.wake_up()` to `memory_client/client.py`: single `GET /memory/wake-up` call; server handles merge.
- Added `memory wake-up` and `memory close-session` CLI commands to `memory_client/cli.py`. `wake-up` renders grouped by first tag; `close-session` is fully local (no API call).
- Created `tests/test_wake_up_close_session.py`: 15 tests (U1–U11 unit, I1–I3 integration against live stack).
- Seeded 12 active memories from Notion Memory Vault into live Memgraph.

**DoS result:** 15/15 WP-030 tests passing (12 unit, 3 integration against live stack). All 5 smoke tests green: `GET /memory/wake-up` (with and without topic), `memory wake-up` (with and without topic), `memory close-session`.

**Retrospective:** `/simplify` caught a two-HTTP-call design flaw in the CLI (server already handles merge server-side — one call is correct). Also caught duplicate record-to-dict comprehensions, extracted to `_record_to_memory_dict()`. `Field()` vs `Query()` for FastAPI query params is a subtle footgun — always use `Query()` in endpoint function signatures.

---

### WP-027 — `memory list-strands` CLI command
**Completed:** 2026-03-21

**What was done:**
- Fixed all 20 strand descriptions in `scripts/seed_strands.py` to use "the user" as subject (not "you") and "the Companion" instead of "your AI" — language convention now enforced end-to-end.
- Re-seeded live Memgraph DB via `seed_strands.py`.
- Added `list_strands(session)` to `memory_service/memory_repo.py`: single `MATCH (s:Strand)` query ordered by category then name.
- Added `StrandItem`, `StrandsResponse` Pydantic models and `GET /strands` endpoint to `memory_service/main.py`.
- Added `MemoryClient.list_strands()` to `memory_client/client.py`.
- Added `memory list-strands` CLI command to `memory_client/cli.py` using `itertools.groupby` for category grouping.
- Created `tests/test_list_strands.py`: 15 tests (U1–U3 unit/static, I1–I3 integration against live stack, plus CLI tests).

**DoS result:** 15/15 tests passing including 3 integration tests against live Memgraph + FastAPI. `GET /strands` smoke-tested via curl (200, 20 strands). `memory list-strands` smoke-tested against live service — all 20 strands displayed, grouped by category, with correct language throughout.

**Retrospective:** Editable install (`pip install -e .`) not available without a venv; ran all commands with `PYTHONPATH=.`. This is the current workaround until WP-035 resolves packaging. `/simplify` identified CLI error handler duplication now at 4 copies — WP-025 trigger condition met (updated WP-025 note, dependency removed).

---

### WP-015 — In-session LLM workflow patterns
**Completed:** 2026-03-20

**What was done:**
- Created `docs/workflows/` directory with five workflow files and an index README.
- `README.md`: index table, prerequisites, trigger prompt pattern, MemoryType reference table, CLI quick reference.
- `contextual-recall.md`: retrieve relevant memories before starting a task; parallelised searches, zero-result early-exit, stale-todo flagging (corrected to not reference `created_at` which is not in the API response).
- `summarise-session.md`: convert session notes to structured Memory records; draft-then-approve gate before any CLI writes.
- `propose-todos.md`: surface action items from past memories; parallel search, early-exit on empty results, internal deduplication.
- `refine-edges.md`: identify and add missing RELATED_TO links via bridging observation workaround; pair-selection criterion added (weight ≥ 0.6, max 10 pairs).
- `strand-maintenance.md`: audit and assign memories to Strands; v1 limitation noted (no PATCH endpoint, no list-strands command).

**DoS result:** Six markdown files created and reviewed. No runtime changes. `/simplify` run; four issues fixed (parallelised searches, early-exit conditions, `created_at` unexecutable step, refine-edges pair-selection ambiguity). One BACKLOG item added (WP-027).

---

### WP-007 — memory_client.py + Typer CLI
**Completed:** 2026-03-20

**What was done:**
- Created `memory_client/` package: `__init__.py`, `config.py` (`ClientSettings` with `api_base_url` + `agent_id`), `client.py` (`MemoryClient` synchronous httpx client wrapping all three API endpoints), `cli.py` (Typer app with `add-memory`, `search-memory`, `dump-graph` commands).
- Created `memory_client/requirements.txt` (httpx, typer, rich, pydantic-settings, respx).
- Created `pyproject.toml` + `setup.cfg` for editable install and `memory` console-script entry point.
- Updated `.env.example` with `API_BASE_URL=http://localhost:8000`.
- Created `tests/test_cli.py`: 17 unit tests across 3 classes using `typer.testing.CliRunner` + `respx` HTTP mocks; no running service required.

**DoS result:** `PYTHONPATH=. python3 -m pytest tests/test_cli.py -v` → 17 passed. `PYTHONPATH=. python3 -m memory_client.cli --help` lists all three commands.

---

### WP-005 — Wire POST /memory/search
**Completed:** 2026-03-20

**What was done:**
- Added `_SEARCH_QUERY_TEMPLATE` and `search_memories(session, req, query_embedding)` to `memory_service/memory_repo.py`: single Cypher query combining vector search, tag/agent/project filters via `EXISTS{}` subqueries, and optional neighbour expansion via `OPTIONAL MATCH (m)-[:RELATED_TO*1..N]->(n:Memory)` (N f-stringed, Pydantic-validated).
- Implemented `search_memory` endpoint in `memory_service/main.py`: same driver/503 pattern as `add_memory`; maps repo `list[dict]` to `SearchMemoryResponse`.
- Created `tests/test_search_memory.py`: 18 tests across 8 classes covering basic search, ordering, limit/validation, tag/agent/project filters, graph expansion (max_hops=0 and 1), and 503 path.

**DoS result:** All DoS checklist items verified against implementation. `pytest tests/test_search_memory.py` requires Memgraph running with schema initialised.

---

### WP-004 — Wire POST /memory
**Completed:** 2026-03-20

**What was done:**
- Created `memory_service/memory_repo.py`: `add_memory(session, req, memory_id, embedding, now)` — all Cypher operations in one place; upserts Agent+Memory+PRODUCED_BY in a single round-trip; upserts Project/Person/Strand with ABOUT/IN_STRAND edges; auto RELATED_TO via vector search (k=5, distance < 0.5) when `related_ids` not provided; explicit RELATED_TO when provided.
- Updated `memory_service/main.py`: driver lifecycle in lifespan (`app.state.driver`); added `strand_ids` to `AddMemoryRequest`; moved `importance` default from repo to Pydantic model (`Field(default=3, ge=1, le=5)`); implemented endpoint with 503 handling for `ServiceUnavailable`.
- Updated `tests/conftest.py`: added `test_driver` (session-scoped) and `client` fixtures; moved graph inspection helpers (`node_exists`, `edge_exists`, `get_memory_node`, `cleanup_nodes`) to conftest for reuse across future test modules; replaced `Settings()` re-instantiation with module-level `settings` singleton.
- Created `tests/test_add_memory.py`: 14 integration tests covering minimal write, node properties, agent upsert idempotency, project/person/strand edges, explicit and auto RELATED_TO, validation, and 503 error path.

**DoS result:** All DoS checklist items verified manually against implementation. `pytest tests/test_add_memory.py` requires Memgraph running with schema initialised.

---

### WP-016 — Shared config module
**Completed:** 2026-03-20

**What was done:**
- Created `memory_service/config.py`: canonical `Settings` class, `get_driver()`, and module-level `settings` singleton
- Updated `memory_service/main.py`: removed duplicate `Settings` class; imports from `config`
- Updated `scripts/init_schema.py`: removed duplicate `Settings` + `get_driver()`; imports from `config`
- Updated `scripts/smoke_test.py`: removed duplicate `Settings` + `get_driver()` + unused `ClientError` import; imports from `config`

**DoS result:** `python -c "from memory_service.config import Settings, get_driver, settings; print(settings.embedding_model)"` prints `all-MiniLM-L6-v2`.

---

### WP-018 — Vector index dimension from model at runtime
**Completed:** 2026-03-20

**What was done:**
- Added `get_embedding_dimension(model_name)` to `init_schema.py`: loads ST model, returns `.get_sentence_embedding_dimension()`
- Added `get_existing_index_dimension(session)`: queries `SHOW INDEX INFO`, finds Memory/embedding vector index, returns its dimension (or None); defers `dict()` conversion to matching row only; warns on unexpected errors
- Updated `create_vector_index(session, dim, model_name)`: builds query dynamically; logs dim + model name
- Updated `main()`: loads dim before opening DB session (fast-fail on bad model name); detects dimension mismatch before create with actionable error message
- Updated `tests/test_embeddings.py`: replaced hardcoded `len == 384` assertion with model-reported dimension
- Updated `memory_service/embeddings.py` docstring: removed hardcoded `→ 384-dim` example

**DoS result:** Schema init now prints `Embedding dimension: 384` (or correct dim for any configured model). Mismatch detection will print actionable DROP INDEX instructions rather than silently creating a broken index.

---

### WP-002 — Memgraph schema + vector index
**Completed:** 2026-03-20

**What was done:**
- Created `scripts/init_schema.py`: creates uniqueness constraints on Memory/Strand/Agent/Person/Project nodes and vector index on `Memory(embedding)` (dim=384, cosine). Idempotent.
- Created `scripts/smoke_test.py`: inserts a test Memory node, runs `vector_search.search`, asserts id and distance, then cleans up.
- Added `AGENT_ID=claude-code` to `.env` and `.env.example`
- Updated `CLAUDE.md` data model quick-reference: added `Strand` node, `IN_STRAND` edge, edge weight properties

**DoS result:** Scripts created and reviewed. Smoke test requires Memgraph running + WP-003 complete to execute.

---

### WP-003 — Local embeddings module
**Completed:** 2026-03-20

**What was done:**
- Created `memory_service/embeddings.py`: `get_embedding(text) -> list[float]`; model loaded once at import; optional on-disk cache via `EMBEDDING_CACHE_DIR`
- Updated `memory_service/main.py` lifespan to import `embeddings` at startup (triggers model load before first request)
- Added `agent_id` field to `Settings` in `main.py`; added `Strand` to `NodeLabel` enum
- Created `tests/test_embeddings.py` with 4 tests (list shape, determinism, distinct texts, cache)

**DoS result:** Tests written; require `sentence-transformers` installed to run (`python -m pytest tests/test_embeddings.py -v`).

---

### WP-001 — Project framework + Phase 1 scaffold
**Completed:** 2026-03-20

**What was done:**
- Created `.gitignore`, `.env`, `.env.example`
- Updated `docker-compose.yml` with env var passthrough for Memgraph credentials
- Created `memory_service/requirements.txt` (fastapi, uvicorn, neo4j, sentence-transformers, pydantic-settings)
- Updated `memory_service/main.py` with `Settings` class via `pydantic-settings`
- Created `CLAUDE.md` (operating instructions, working norms, DoD)
- Created `BACKLOG.md` (this file)
- Created `README.md` (setup guide)
- Initialised git repo with initial commit

**DoS result:** All 11 checklist items passed.

---

## Retrospective Log

### WP-001 (2026-03-20)
- **What went well:** Existing partial scaffold (docker-compose.yml, main.py) was correct and required only additive changes. Parallel file creation was efficient.
- **What to improve:** Future WPs should include a `scripts/` or `tests/` structure from the start so smoke tests have a natural home. Added as note on WP-002.
- **Simplify findings acted on:** Added `MemoryType` enum (fixes stringly-typed `type` field); added `importance` bounds validation (ge=1, le=5); added `limit`/`max_hops` bounds (prevents unbounded graph expansion); added `lifespan` stub to main.py (correct hook for model/connection init in WP-002/003); added Memgraph healthcheck to docker-compose; Lab now waits for `service_healthy` before starting.
- **Deferred to backlog:** WP-012 (pin dep versions), WP-013 (pin Docker image tags), WP-014 (Docker resource limits).

### WP-002 + WP-003 (2026-03-20)
- **What went well:** Parallel agent dispatch worked cleanly — no file conflicts, both agents completed independently. Schema design review (Strands as graph nodes, weighted `IN_STRAND` edges) correctly preceded implementation.
- **What to improve:** `Settings` and `get_driver()` ended up triplicated across main.py + 2 scripts. Future WPs that add scripts should import from a shared module from the start.
- **Simplify findings acted on:** Tightened idempotency catch in `init_schema.py` (was swallowing real errors via broad substring match); fixed double `_cache_key`/`cache_path` construction in `embeddings.py`; removed redundant `get_embedding("warmup")` call from lifespan (import alone is sufficient); swapped smoke test order to fast-fail on Memgraph connectivity before slow model load.
- **Deferred to backlog:** WP-016 (shared config module), WP-017 (cache eviction), WP-018 (vector dimension from model at runtime).

### WP-016 + WP-018 (2026-03-20)
- **What went well:** Parallel agent dispatch again conflict-free — WP-016 owned `config.py`/imports, WP-018 owned `init_schema.py`/tests. Leftover `get_driver()` stub caught by pre-simplify file read and fixed before review. Backlog-review norm identified both WPs as high-value prerequisites for WP-004 before any implementation happened.
- **What to improve:** WP-016 agent left a stale `get_driver()` function in `init_schema.py` (body referenced undefined `neo4j`/`GraphDatabase` names). Agents should do an import-check step after editing to catch this class of error.
- **Simplify findings acted on:** Silent `except Exception: pass` in `get_existing_index_dimension` replaced with explicit warning print; `dict(record)` conversion deferred to matching row only; stale `→ 384-dim` example removed from `embeddings.py` docstring.
- **Deferred to backlog:** WP-019 (expose `capacity` as config setting); URI construction duplication between scripts and `config.get_driver()` (low risk, cosmetic).

### WP-005 (2026-03-20)
- **What went well:** Single-query design (vector search + filters + neighbour expansion) came out clean. Parallel agent dispatch for production code + tests worked conflict-free. The `_add` and `_search` test helpers kept test bodies concise.
- **What to improve:** Graph expansion tests used `if hit is not None:` guards — silently skipping assertions if the target node wasn't in results. This gives false confidence; always assert the hit is found first. Caught by simplify.
- **Simplify findings acted on:** Unused `import pytest` removed; `if tags:` / `if related_ids:` guards changed to `is not None` (empty-list safety); misleading `test_empty_result_returns_empty_list` renamed to `test_search_response_has_correct_shape`; graph expansion tests strengthened with `assert hit is not None` + `limit=50` to reduce ranking noise.
- **Deferred to backlog:** WP-022 (cap unbounded `collect(DISTINCT n.id)` for dense graphs); WP-023 (extract `ServiceUnavailable`/503 try/except into shared context manager); WP-024 (`cleanup_nodes` multi-id-per-label support).

### WP-004 (2026-03-20)
- **What went well:** Plan agent produced a complete, implementable design with all key decisions resolved (repo module, driver injection via `app.state`, Strand MERGE-by-id-only, combined Agent+Memory+PRODUCED_BY in single round-trip). Parallel agents for production code + tests worked cleanly with no file conflicts.
- **What to improve:** Redundant import (`import memory_service.embeddings` in lifespan — now superseded by top-level `from memory_service.embeddings import get_embedding`) and unused `Settings` import in `main.py` were both caught post-implementation during simplify prep. Both were quick fixes, but agents should verify their own imports after editing.
- **Simplify findings acted on:** `importance` default moved from repo magic number to Pydantic `Field(default=3)`; `Settings()` re-instantiation in conftest replaced with module-level singleton; 503 test teardown wrapped in `try/finally`; Agent+Memory+PRODUCED_BY merged into single round-trip; test helpers (`node_exists`, `edge_exists`, `get_memory_node`, `cleanup_nodes`) moved to `conftest.py` for reuse across future test modules; stale `Settings` import removed from `main.py`.
- **Deferred to backlog:** WP-020 (UNWIND for person/strand/related_ids N+1); WP-021 (non-blocking `get_embedding` via `run_in_executor`); `EdgeType` enum for Cypher edge type strings (medium value, deferred until more edge types are used across more files).

### MVP Live Demo (2026-03-20)
- **What went well:** All three CLI commands verified against live Memgraph 3.8.1. `add-memory`, `search-memory` (with vector search, tag/project filters, graph expansion), and `dump-graph` (correctly reporting WP-006 not implemented) all functioned correctly.
- **What to improve / bugs found:** Three Memgraph 3.8 compatibility issues required fixes before the demo worked: (1) vector index DDL syntax changed to `CREATE VECTOR INDEX name ON :Label(prop) WITH CONFIG {"key": val}` with quoted JSON keys; (2) `EXISTS{}` subqueries not supported inside `WITH ... WHERE` — replaced with `OPTIONAL MATCH` + scalar filter pattern; (3) `ORDER BY distance` after `collect()` aggregation requires `distance` to be explicitly included in `RETURN` clause — Memgraph planner bug. Also: `docker-compose.yml` was passing `MEMGRAPH_USER=` (empty string) to the container, causing a startup crash — removed the explicit `environment:` block.
- **Files fixed:** `docker-compose.yml`, `scripts/init_schema.py`, `memory_service/memory_repo.py`.

### WP-015 (2026-03-20)
- **What went well:** Plan agent produced a clear five-file structure with content outlines before any writing. Three parallel review agents (reuse, quality, efficiency) caught all significant issues. Most valuable finding: `created_at` is not returned by the search API, making the stale-todo step unexecutable — fixed before commit.
- **What to improve:** Workflow docs should be validated against the actual API response schema, not just the CLI option names. A quick check of `SearchMemoryResponse` fields earlier would have caught the `created_at` issue before review.
- **Simplify findings acted on:** Parallelised independent searches (contextual-recall, propose-todos, refine-edges); added zero-result early-exit conditions (contextual-recall, propose-todos, refine-edges); fixed unexecutable `created_at` stale-todo step; added pair-selection criterion to refine-edges (weight ≥ 0.6, max 10 pairs); added `memory --help` hint to README.
- **Deferred to backlog:** WP-027 (`memory list-strands` command — strand IDs not discoverable without it).

### WP-007 (2026-03-20)
- **What went well:** Clean package separation — `memory_client/` has zero imports from `memory_service/`. Parallel agent dispatch (production code + tests) worked conflict-free. Plan agent resolved all design questions upfront (httpx sync client, single `API_BASE_URL` env var, `_make_client()` module-level for testability). `respx` mocking kept tests fast and self-contained.
- **What to improve:** `setup.cfg` was needed alongside `pyproject.toml` due to old setuptools (v59.6) lacking PEP 660 editable-install support — a minor packaging surprise. Editable installs via `pip install -e .` should be validated as part of DoS in future WPs that introduce new packages.
- **Simplify findings acted on:** Removed unused `import sys` from `cli.py`; changed `dump-graph` 500/501 handler to exit 1 (was exit 0 — incorrect for script callers); removed duplicate entry-point declaration from `setup.cfg` (kept only in `pyproject.toml`); updated `test_not_implemented_prints_message` to assert `exit_code == 1`.
- **Deferred to backlog:** WP-025 (extract shared CLI error handler — triplicated `except httpx.*` blocks); WP-026 (`MemoryType` mirror in `memory_client` for typed `type` parameter).
