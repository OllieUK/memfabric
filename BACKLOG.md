# Graph-Memory Fabric – Feature Backlog

> **Value:** H = High / M = Medium / L = Low
> **Effort:** S = Small (hrs) / M = Medium (day) / L = Large (days) / XL = Extra-large (week+)
> Completed WPs → [docs/CHANGELOG.md](docs/CHANGELOG.md)

---

## Currently In Progress

| ID | Title | Phase | Value | Effort | Depends on | Notes |
|----|-------|-------|-------|--------|------------|-------|

---

## Prioritised Backlog

> Items ordered by priority: dependency-unblocked H-value work first, then quick wins (S effort), then infrastructure. Do not start a row if its "Depends on" is not in Completed.

| Priority | ID | Title | Value | Effort | Depends on | Notes |
|----------|----|-------|-------|--------|------------|-------|
| 2 | WP-006 | Wire `GET /memory/graph` | M | M | WP-028 ✅, WP-029 ✅ | Filtered subgraph export: project/agent/tag/since/until params; returns `{nodes, edges}`. |
| 2 | WP-040 | Memory maintenance orchestration — Short Rest & Long Rest | H | M | WP-029 ✅ | Session protocol now depends on Short Rest firing at close-session. Triggered/scheduled maintenance: Short Rest (end-of-session decay on active memories) + Long Rest (full decay + edge rediscovery + weak-edge pruning). See detail below. |
| 3 | WP-034 | Add version/build hash to `/health` response | L | S | — | Detect stale service at session startup. Batch with WP-035/036. |
| 3 | WP-035 | Return `strand_ids` in `add-memory` API response | L | S | — | Reduce friction when chaining related memories. Batch with WP-034/036. |
| 3 | WP-036 | Document `### Relevant to today` suppression in COMPANION.md | L | S | — | Avoid companion confusion on small DBs. Batch with WP-034/035. Not covered by the three-tier memory model addition (2026-03-22) — still needed for wake-up output behaviour on sparse graphs. |
| 4 | WP-044 | Fix broken 503 + connect-error tests | M | S | — | `test_returns_503_when_db_down` ×2 and `test_connect_error_exits_nonzero` ×2 pass vacuously — 503 path untested. Fix pattern fully documented. See detail below. |
| 4 | WP-022 | Cap neighbour count in search results | M | S | WP-005 ✅ | `collect(DISTINCT n.id)` unbounded with `max_hops=3` on dense graph — add slice cap (e.g. `[..50]`). Correctness risk as graph grows. |
| 5 | WP-038 | Memory lifecycle operations — update, merge, archive | H | L | WP-037 ✅ | First-class memory maintenance: PATCH, merge, archive, restore. WP-006 dependency removed — graph export is useful for discovery but not technically required. See detail below. |
| 6 | WP-039 | Ephemeral test-memory handling — TTL, tagging, cleanup | H | M | WP-038 | Prevent test artefacts polluting live context. See detail below. |
| 7 | WP-025 | Extract shared CLI error handler | L | S | — | 4+ identical `except httpx.*` blocks in `cli.py`. Extract once. |
| 7 | WP-026 | `MemoryType` mirror in `memory_client` | L | S | WP-007 ✅ | Mirror enum so callers get IDE completion without cross-package import. |
| 7 | WP-023 | Extract `get_session` context manager for 503 handling | L | S | WP-029 ✅ | `try/with driver.session()/except ServiceUnavailable→503` copy-pasted across all endpoints. Do after WP-029 (adds more endpoints). |
| 8 | WP-012 | Pin dependency versions in requirements.txt | M | S | — | Use `>=x,<y` bounds. Stability/reproducibility prerequisite — do before declaring v1 stable. |
| 8 | WP-013 | Pin Docker image tags (no `latest`) | M | S | WP-012 | Replace `latest` tags with specific versions. Do after WP-012. |
| 8 | WP-020 | UNWIND for person/strand/related_ids writes | L | S | WP-004 ✅ | Replace per-item `session.run()` loops in `add_memory` with UNWIND queries. Add `related_ids` max-length cap (e.g. 20). |
| 8 | WP-021 | Non-blocking embedding in async endpoints | L | S | WP-004 ✅, WP-005 ✅ | `get_embedding()` blocks the event loop. Wrap with `run_in_executor` when concurrent usage becomes a problem. |
| 8 | WP-024 | `cleanup_nodes` support multiple ids per label | L | S | — | Change `extra_ids: dict[str, str]` to `dict[str, str \| list[str]]` for multi-node cleanup in tests. |
| 9 | WP-017 | Embedding cache eviction / size cap | L | S | WP-003 ✅ | `EMBEDDING_CACHE_DIR` grows without bound. Add LRU eviction or max-entry cap. |
| 9 | WP-019 | Expose vector index `capacity` as config | L | S | WP-016 ✅ | `capacity: 1000` hardcoded in `init_schema.py`. Add to `Settings`. |
| 10 | WP-014 | Docker resource limits | L | S | — | Add `mem_limit`/`cpus` to docker-compose. |
| 10 | WP-043 | Inline effective_strength sort in search | L | S | WP-029 ✅ | Add Cypher inline decay formula as search sort key. Currently deferred — stored strength post-decay-pass used as v1 proxy. |

---

## v2+ — Future phases (not in scope for v1)

| ID | Title | Value | Effort | Depends on | Notes |
|----|-------|-------|--------|------------|-------|
| WP-041 | Subject/object schema on Memory nodes | H | L | WP-028 ✅ | Add explicit `subject` and `object` fields. Required before multi-user or shared-memory scenarios. Avoid hard-coded subject assumptions in ingestion APIs. |
| WP-042 | Self-contained `memory_client` packaging | M | S | WP-031 ✅ | Move `pyproject.toml` into `memory_client/` for independent install. |
| WP-008 | LLMClient abstraction | M | M | WP-007 ✅ | `LLMClient.ask(system, prompt, model)` wrappers for Claude/OpenAI/Ollama. |
| WP-009 | Headless agent framework | M | L | WP-008 | `BaseAgent` using `memory_client` + `LLMClient`; scheduled/event-driven tasks. |
| WP-010 | Remote/mobile access | L | XL | WP-009 | Tailscale/VPS hosting + TLS + API key auth. |
| WP-011 | Custom graph-cloud UI | L | XL | WP-006 | React + D3.js/vis-network consuming `GET /memory/graph`. |

> **Note:** v2+ WP-034 and WP-035 from the old backlog have been renumbered WP-041 and WP-042 to avoid collision with the v1 WP-034/035/036 companion-polish items.

---

## Detail Specs

### WP-040 — Memory maintenance orchestration: Short Rest & Long Rest

#### Motivation

WP-029 adds the mechanics of decay/reinforcement but leaves triggering entirely manual. The fabric needs to self-maintain on a schedule — decaying stale memories, discovering newly-relevant connections as the graph grows, pruning edges that have never fired.

#### Short Rest (cheap, frequent — end-of-session)

**Scope:** Memory nodes where `last_used_at` within `SHORT_REST_RECENCY_DAYS` (default 7) OR `recall_count > 0`. Adjacent edges.

**Operations:** Decay pass on scoped nodes + adjacent edges.

**Returns:** `{nodes_decayed, edges_decayed}`

**Trigger:** `POST /memory/maintenance/short-rest` · CLI `memory short-rest` · MCP `memory_short_rest`
*Companion calls `memory_short_rest()` before `memory_close_session()` at session end.*

#### Long Rest (thorough, infrequent — nightly)

**Scope:** All nodes and edges.

**Operations:**
1. Full decay pass (all nodes + edges)
2. **Edge rediscovery:** For each Memory with `strength >= REDISCOVERY_STRENGTH_THRESHOLD` (0.3), re-run vector search and MERGE new `RELATED_TO` edges for pairs within `_AUTO_RELATED_MAX_DISTANCE` that don't exist yet. Bounded to O(k·log n) where k = active memories.
3. **Weak-edge pruning:** List edges below `EDGE_HARD_PRUNE_FLOOR` (0.01) with no activation for `EDGE_HARD_PRUNE_MIN_DAYS` (90). Hard-delete opt-in via `?prune=true`.

**Returns:** `{nodes_decayed, edges_decayed, edges_discovered, edges_pruned}`

**Trigger:** `POST /memory/maintenance/long-rest` · CLI `memory long-rest` · MCP `memory_long_rest` · OS cron / Claude Code `/cron`

#### Edge-modulated decay (elaborative encoding)

Nodes that are richly cross-referenced should decay slower — mirroring how elaborative encoding in human memory makes well-connected facts more resistant to forgetting. Each associative pathway provides an independent retrieval route; the memory survives because its neighbours keep priming it.

**Design:** During `decay_pass`, modulate each node's effective decay rate by the weight of its incoming edges:

```
effective_decay_rate = base_decay_rate / (1 + k * sum(incoming_edge_weights))
```

Where `k = EDGE_MODULATION_FACTOR` (default 0.5). A node with total incoming weight 2.0 decays at `base / 2.0`; an isolated node decays at `base`. Cap the divisor to prevent indestructible super-nodes (e.g. max 10× reduction).

This is computed in Python during the existing fetch → compute → UNWIND cycle in `decay_pass` — no schema changes required; one extra Cypher clause to fetch incoming edge weights per node.

#### New config variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SHORT_REST_RECENCY_DAYS` | 7 | Lookback window for Short Rest scope |
| `REDISCOVERY_STRENGTH_THRESHOLD` | 0.3 | Min strength to participate in edge rediscovery |
| `EDGE_HARD_PRUNE_FLOOR` | 0.01 | Effective weight below which edges are hard-prune candidates |
| `EDGE_HARD_PRUNE_MIN_DAYS` | 90 | Min days of no activation before eligible for hard pruning |
| `EDGE_MODULATION_FACTOR` | 0.5 | How strongly incoming edge weight reduces a node's decay rate |
| `EDGE_MODULATION_CAP` | 10.0 | Maximum decay rate reduction factor (prevents indestructible nodes) |

#### Definition of Success

- [ ] `POST /memory/maintenance/short-rest` decays recently-active nodes/edges only; returns `{nodes_decayed, edges_decayed}`
- [ ] `POST /memory/maintenance/long-rest` runs full decay + edge rediscovery + prune report; returns full summary
- [ ] `?prune=true` hard-deletes edges below floor after min-days
- [ ] CLI `memory short-rest` / `memory long-rest`; MCP `memory_short_rest` / `memory_long_rest`
- [ ] Edge rediscovery bounded to `strength >= REDISCOVERY_STRENGTH_THRESHOLD` anchors
- [ ] Decay pass applies edge-modulated decay rate per node (isolated nodes decay faster than well-connected nodes)
- [ ] Short Rest completes in < 1s on graphs up to 1000 nodes
- [ ] Integration test: two similar memories → long-rest → new `RELATED_TO` edge discovered
- [ ] All config vars in `Settings` + `.env.example`

---

### WP-038 — Memory lifecycle operations: update, merge, archive

#### Motivation

The fabric can add and search memories but cannot maintain them. Three lifecycle operations are essential:
- **Update** when facts change or wording improves
- **Merge** duplicates without losing provenance or graph continuity
- **Archive** memories that should no longer surface normally but remain historically recoverable

#### Data model additions

| Property | Type | Description |
|----------|------|-------------|
| `status` | str | `active` (default), `archived`, `merged` |
| `superseded_by` | str \| None | UUID of active replacement |
| `archived_at` | datetime \| None | Set on archive |
| `updated_at` | datetime \| None | Set on in-place update |

New edge: `MERGED_INTO` (Memory → Memory)

#### New endpoints

```
PATCH /memory/{id}          — update fact/so_what/tags/importance/person_ids/strand_ids; recomputes embedding
POST  /memory/{id}/merge    — body: {target_id, strategy}; marks source merged, rewires links
POST  /memory/{id}/archive  — sets status=archived, archived_at
POST  /memory/{id}/restore  — returns archived memory to active
```

**Search and wake-up** exclude `status in ('archived', 'merged')` by default.

#### Definition of Success

- [ ] All four endpoints implemented; `active`/`archived`/`merged` status respected in search/wake-up
- [ ] Merge rewires `ABOUT`, `IN_STRAND`, explicit `LEADS_TO`, explicit `RELATED_TO` to target
- [ ] Client + CLI + MCP updated
- [ ] Integration tests cover all status transitions

---

### WP-039 — Ephemeral test-memory handling: TTL, tagging, cleanup

#### Motivation

Integration tests write real memories to the live graph. Without explicit ephemeral semantics, test artefacts accumulate and corrupt companion context. Need: test memories excluded from normal retrieval + auto-cleaned once no longer needed.

#### Design

- `Memory.ephemeral: bool` property (default `false`); set via `POST /memory` with `"ephemeral": true`
- Ephemeral memories excluded from `POST /memory/search` and `GET /memory/wake-up` by default
- `POST /memory/maintenance/purge-ephemeral` — hard-deletes all ephemeral memories
- CLI `memory purge-ephemeral`; MCP `memory_purge_ephemeral`

#### Definition of Success

- [ ] `POST /memory` accepts `ephemeral: true`
- [ ] Search and wake-up exclude ephemeral memories by default
- [ ] `POST /memory/maintenance/purge-ephemeral` returns count deleted
- [ ] Integration tests updated to use `ephemeral: true` for test writes

---

### WP-044 — Fix broken 503 + connect-error tests

#### Root cause

Two failure modes, both causing tests to pass vacuously:

**`test_returns_503_when_db_down`** (in `test_add_memory.py` and `test_search_memory.py`):
Tests inject a mock driver via `app.state.driver = mock_driver` after the lifespan startup has already wired the real driver. The mock is ignored because the endpoint resolves the driver from the already-running app state set at startup.
Fix: use FastAPI's `app.dependency_overrides` (or patch `request.app.state.driver` via a proper fixture that runs before the TestClient starts) so the mock driver is actually seen by the endpoint.

**`test_connect_error_exits_nonzero`** (in `test_list_strands.py` and `test_wp037_person_nodes.py`):
Tests pass `env={"API_BASE_URL": "http://localhost:19999"}` to Typer's `CliRunner.invoke`. Pydantic-settings reads env vars at import time, so the override arrives too late — the settings object already has `localhost:8000`. The real service is running on 8000 and responds successfully, giving exit_code=0.
Fix: follow the pattern used in `test_wake_up_close_session.py` — use `respx.mock` with `side_effect=httpx.ConnectError(...)` instead of redirecting the URL.

#### Definition of Success

- [ ] `test_returns_503_when_db_down` in `test_add_memory.py` and `test_search_memory.py` actually exercises the 503 path and passes
- [ ] `test_connect_error_exits_nonzero` in `test_list_strands.py` and `test_wp037_person_nodes.py` actually exercises the connect-error path and passes
- [ ] No new test infrastructure added — reuse `respx.mock` pattern already present in `test_wake_up_close_session.py`
- [ ] 4 pre-existing failures eliminated; total test count unchanged
