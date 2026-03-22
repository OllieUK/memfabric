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
| 3 | WP-034 | Add version/build hash to `/health` response | L | S | — | Detect stale service at session startup. Batch with WP-035/036. |
| 3 | WP-035 | Return `strand_ids` in `add-memory` API response | L | S | — | Reduce friction when chaining related memories. Batch with WP-034/036. |
| 3 | WP-036 | Document `### Relevant to today` suppression in COMPANION.md | L | S | — | Avoid companion confusion on small DBs. Batch with WP-034/035. |
| 4 | WP-022 | Cap neighbour count in search results | M | S | WP-005 ✅ | `collect(DISTINCT n.id)` unbounded with `max_hops=3` on dense graph — add slice cap (e.g. `[..50]`). Correctness risk as graph grows. |
| 5 | WP-040 | Memory maintenance orchestration — Short Rest & Long Rest | H | M | WP-029 ✅ | Triggered/scheduled maintenance: Short Rest (end-of-session decay on active memories) + Long Rest (full decay + edge rediscovery + weak-edge pruning). See detail below. |
| 6 | WP-038 | Memory lifecycle operations — update, merge, archive | H | L | WP-006, WP-037 ✅ | First-class memory maintenance: PATCH, merge, archive, restore. See detail below. |
| 6 | WP-039 | Ephemeral test-memory handling — TTL, tagging, cleanup | H | M | WP-038 | Prevent test artefacts polluting live context. See detail below. |
| 7 | WP-025 | Extract shared CLI error handler | L | S | — | 4+ identical `except httpx.*` blocks in `cli.py`. Extract once. |
| 7 | WP-026 | `MemoryType` mirror in `memory_client` | L | S | WP-007 ✅ | Mirror enum so callers get IDE completion without cross-package import. |
| 7 | WP-023 | Extract `get_session` context manager for 503 handling | L | S | WP-029 ✅ | `try/with driver.session()/except ServiceUnavailable→503` copy-pasted across all endpoints. Do after WP-029 (adds more endpoints). |
| 8 | WP-020 | UNWIND for person/strand/related_ids writes | L | S | WP-004 ✅ | Replace per-item `session.run()` loops in `add_memory` with UNWIND queries. Add `related_ids` max-length cap (e.g. 20). |
| 8 | WP-021 | Non-blocking embedding in async endpoints | L | S | WP-004 ✅, WP-005 ✅ | `get_embedding()` blocks the event loop. Wrap with `run_in_executor` when concurrent usage becomes a problem. |
| 8 | WP-024 | `cleanup_nodes` support multiple ids per label | L | S | — | Change `extra_ids: dict[str, str]` to `dict[str, str \| list[str]]` for multi-node cleanup in tests. |
| 9 | WP-017 | Embedding cache eviction / size cap | L | S | WP-003 ✅ | `EMBEDDING_CACHE_DIR` grows without bound. Add LRU eviction or max-entry cap. |
| 9 | WP-019 | Expose vector index `capacity` as config | L | S | WP-016 ✅ | `capacity: 1000` hardcoded in `init_schema.py`. Add to `Settings`. |
| 10 | WP-012 | Pin dependency versions in requirements.txt | M | S | — | Use `>=x,<y` bounds. Do before stack is considered stable. |
| 10 | WP-013 | Pin Docker image tags (no `latest`) | M | S | WP-012 | Replace `latest` tags with specific versions. Do after WP-012. |
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

#### New config variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SHORT_REST_RECENCY_DAYS` | 7 | Lookback window for Short Rest scope |
| `REDISCOVERY_STRENGTH_THRESHOLD` | 0.3 | Min strength to participate in edge rediscovery |
| `EDGE_HARD_PRUNE_FLOOR` | 0.01 | Effective weight below which edges are hard-prune candidates |
| `EDGE_HARD_PRUNE_MIN_DAYS` | 90 | Min days of no activation before eligible for hard pruning |

#### Definition of Success

- [ ] `POST /memory/maintenance/short-rest` decays recently-active nodes/edges only; returns `{nodes_decayed, edges_decayed}`
- [ ] `POST /memory/maintenance/long-rest` runs full decay + edge rediscovery + prune report; returns full summary
- [ ] `?prune=true` hard-deletes edges below floor after min-days
- [ ] CLI `memory short-rest` / `memory long-rest`; MCP `memory_short_rest` / `memory_long_rest`
- [ ] Edge rediscovery bounded to `strength >= REDISCOVERY_STRENGTH_THRESHOLD` anchors
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
