# Graph-Memory Fabric – Feature Backlog

> **Value:** H = High / M = Medium / L = Low
> **Effort:** H = High / M = Medium / L = Low
> **Priority score:** `Value / Effort` using `H=3`, `M=2`, `L=1`
> Completed WPs → [docs/CHANGELOG.md](docs/CHANGELOG.md)

---

## Currently In Progress

| ID | Title | Phase | Value | Effort | Depends on | Notes |
|----|-------|-------|-------|--------|------------|-------|

---

## Prioritised Backlog

> Items ordered as a dependency-safe executable sequence informed by `Priority score`.
> Higher score is better, but `Depends on` always wins for execution order.
> When a lower-score prerequisite unlocks a stronger branch, keep the prerequisite immediately ahead of that branch.
> Within an equal-score block, preserve the existing order unless a newly identified dependency requires a move.
> Add new work packages at the bottom of their equal-score block unless dependency constraints require otherwise.
> `Release` is planning metadata only. The backlog stays continuous and contiguous; release numbers indicate target package, not a separate queue.

| Priority | Release | ID | Title | Value | Effort | Priority score | Depends on | Notes |
|----------|---------|----|-------|-------|--------|----------------|------------|-------|
| 1 | R1 | WP-048 | Two-speed decay + importance floor to protect core memories | H | M | 1.5 | — | Core memories (people, relationships, long-term history) are being crowded out by day-to-day activity. Fix: (1) lower initial strength so new memories fade fast if never recalled; (2) first recall “consolidates” to a slower decay rate; (3) per-node `min_strength` derived from importance so high-importance memories can never decay to zero. See detail below. |
| 2 | R1 | WP-022 | Cap neighbour count in search results | M | L | 2.0 | WP-005 ✅ | `collect(DISTINCT n.id)` unbounded with `max_hops=3` on dense graph — add slice cap (e.g. `[..50]`). |
| 3 | R1 | WP-038 | Memory lifecycle operations — update, merge, archive | H | H | 1.0 | WP-037 ✅ | First-class memory manipulation: PATCH, merge, archive, restore. Becoming essential as duplicate and stale memories accumulate. Required before WP-047. See detail below. |
| 4 | R1 | WP-047 | Near-duplicate detection for memory review | H | M | 1.5 | WP-038 | Surface semantically similar memories (cosine similarity above configurable threshold) so they can be reviewed and merged via WP-038 merge endpoint. Feeds into short-rest/long-rest cleanup loop. See detail below. |
| 5 | R1 | WP-039 | Ephemeral test-memory handling — TTL, tagging, cleanup | H | M | 1.5 | WP-038 | Prevent test artefacts polluting live context. See detail below. |
| 6 | R1 | WP-012 | Pin dependency versions in requirements.txt | M | L | 2.0 | — | Use `>=x,<y` bounds. Stability/reproducibility prerequisite — do before declaring a stable first release. |
| 7 | R1 | WP-013 | Pin Docker image tags (no `latest`) | M | L | 2.0 | WP-012 | Replace `latest` tags with specific versions. Do after WP-012. |
| 8 | R1 | WP-045 | Make local startup deterministic offline | M | L | 2.0 | — | Fix misleading Memgraph healthcheck and add a documented/scripted API startup path that works with cached embeddings offline (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`). Prevent false “memory service unreachable” failures at session start. |
| 9 | R1 | WP-034 | Add version/build hash to `/health` response | M | L | 2.0 | — | Detect stale or mismatched service instances at mandatory session startup. Promoted from low value because startup operability is part of the core working loop. Batch with WP-035/036. |
| 10 | R2 | WP-006 | Wire `GET /memory/graph` | M | M | 1.0 | WP-028 ✅, WP-029 ✅ | Filtered subgraph export: project/agent/tag/since/until params; returns `{nodes, edges}`. |
| 11 | R2 | WP-035 | Return `strand_ids` in `add-memory` API response | L | L | 1.0 | — | Reduce friction when chaining related memories. Batch with WP-034/036. |
| 12 | R2 | WP-036 | Document `### Relevant to today` suppression in COMPANION.md | L | L | 1.0 | — | Avoid companion confusion on small DBs. Batch with WP-034/035. Not covered by the three-tier memory model addition (2026-03-22) — still needed for wake-up output behaviour on sparse graphs. |
| 13 | R2 | WP-043 | Inline effective_strength sort in search | L | L | 1.0 | WP-029 ✅ | Add Cypher inline decay formula as search sort key. Currently deferred — stored strength post-decay-pass used as the current proxy. |
| 14 | R2 | WP-025 | Extract shared CLI error handler | L | L | 1.0 | — | 4+ identical `except httpx.*` blocks in `cli.py`. Extract once. |
| 15 | R2 | WP-026 | `MemoryType` mirror in `memory_client` | L | L | 1.0 | WP-007 ✅ | Mirror enum so callers get IDE completion without cross-package import. |
| 16 | R2 | WP-023 | Extract `get_session` context manager for 503 handling | L | L | 1.0 | WP-029 ✅ | `try/with driver.session()/except ServiceUnavailable→503` copy-pasted across all endpoints. Do after WP-029 (adds more endpoints). |
| 17 | R2 | WP-020 | UNWIND for person/strand/related_ids writes | L | L | 1.0 | WP-004 ✅ | Replace per-item `session.run()` loops in `add_memory` with UNWIND queries. Add `related_ids` max-length cap (e.g. 20). |
| 18 | R2 | WP-021 | Non-blocking embedding in async endpoints | L | L | 1.0 | WP-004 ✅, WP-005 ✅ | `get_embedding()` blocks the event loop. Wrap with `run_in_executor` when concurrent usage becomes a problem. |
| 19 | R2 | WP-024 | `cleanup_nodes` support multiple ids per label | L | L | 1.0 | — | Change `extra_ids: dict[str, str]` to `dict[str, str \| list[str]]` for multi-node cleanup in tests. |
| 20 | R2 | WP-017 | Embedding cache eviction / size cap | L | L | 1.0 | WP-003 ✅ | `EMBEDDING_CACHE_DIR` grows without bound. Add LRU eviction or max-entry cap. |
| 21 | R2 | WP-019 | Expose vector index `capacity` as config | L | L | 1.0 | WP-016 ✅ | `capacity: 1000` hardcoded in `init_schema.py`. Add to `Settings`. |
| 22 | R2 | WP-014 | Docker resource limits | L | L | 1.0 | — | Add `mem_limit`/`cpus` to docker-compose. |
| 23 | R2 | WP-041 | Subject/object schema on Memory nodes | H | H | 1.0 | WP-028 ✅ | Add explicit `subject` and `object` fields. Required before multi-user or shared-memory scenarios. Avoid hard-coded subject assumptions in ingestion APIs. |
| 24 | R3 | WP-042 | Self-contained `memory_client` packaging | L | L | 1.0 | WP-031 ✅ | Move `pyproject.toml` into `memory_client/` for independent install. Re-scored from medium value because it is packaging polish rather than core product capability. |
| 25 | R3 | WP-008 | LLMClient abstraction | M | M | 1.0 | WP-007 ✅ | `LLMClient.ask(system, prompt, model)` wrappers for Claude/OpenAI/Ollama. |
| 26 | R3 | WP-009 | Headless agent framework | M | H | 0.67 | WP-008 | `BaseAgent` using `memory_client` + `LLMClient`; scheduled/event-driven tasks. |
| 27 | R3 | WP-010 | Remote/mobile access | L | H | 0.33 | WP-009 | Tailscale/VPS hosting + TLS + API key auth. |
| 28 | R3 | WP-011 | Custom graph-cloud UI | L | H | 0.33 | WP-006 | React + D3.js/vis-network consuming `GET /memory/graph`. |

> **Note:** old backlog items once grouped under `v2+` are now part of the same continuous backlog with `Release` assignments.
> Old v2+ WP-034 and WP-035 were renumbered WP-041 and WP-042 to avoid collision with the current WP-034/035/036 items.

---

## Detail Specs

### WP-048 — Two-speed decay + importance floor to protect core memories

#### Motivation

Core memories — who people are, what relationships exist, what has been built over 18 months — are being crowded out by high-volume day-to-day activity. The root cause is two compounding issues:

1. **Initial strength is too high.** `strength = importance / 5.0` means a freshly written importance=3 memory starts at 0.60. With `decay_rate = 0.01` its half-life is ~69 days — it takes nearly a year to fade meaningfully, even if never referenced again. Day-to-day memories accumulate and fill search/wake-up windows before older core memories get a chance to surface.

2. **Importance has no floor effect.** A high-importance memory (person profile, long-term relationship, historical milestone) decays toward zero over time just like any other, unless it happens to be frequently recalled. It should instead have a minimum strength it can never drop below.

#### Design

**Three coordinated changes:**

**1. Lower initial strength — recency-driven by default**

New memories start low and earn their place through recall. Initial strength becomes:

```
strength = initial_strength_factor * (importance / 5.0)
```

With `initial_strength_factor = 0.4` (configurable), an importance=3 memory starts at 0.24 instead of 0.60.

**2. Two-speed decay — fast initial, slow post-consolidation**

Each memory stores its own `decay_rate`. On creation this is set to `memory_initial_decay_rate` (fast, e.g. 0.07 — half-life ~10 days). On the **first explicit reinforcement** (`reinforcement_count == 0 → 1`), `reinforce_memory` also writes `decay_rate = memory_consolidated_decay_rate` (slow, e.g. 0.01 — current default). After that, normal strength increments apply.

This means: if a memory is never recalled it decays and fades within weeks. If it is recalled even once, it consolidates and decays slowly thereafter.

**3. Per-node importance floor (`min_strength`)**

Add `min_strength: float` as a stored property on each Memory node, set at creation:

```
min_strength = importance_floor_factor * (importance / 5.0)
```

With `importance_floor_factor = 0.3` (configurable), an importance=5 memory has a floor of 0.30 — it will always surface in searches even if never recalled. Importance=1 has a floor of 0.06 — effectively zero. The existing global `min_memory_strength` config becomes the absolute backstop (default 0.0).

The decay functions `_apply_decay` and `_apply_decay_modulated` already accept a `min_strength` parameter — the repo functions just need to pass `node["min_strength"]` instead of the global config value.

#### New config values

| Key | Default | Replaces / notes |
|-----|---------|-----------------|
| `initial_strength_factor` | `0.4` | New. Multiplier on `importance / 5.0` for initial strength. |
| `memory_initial_decay_rate` | `0.07` | Replaces role of `memory_decay_rate` on creation. Fast: ~10-day half-life. |
| `memory_consolidated_decay_rate` | `0.01` | New. Slow rate applied after first reinforcement. Equals current `memory_decay_rate`. |
| `importance_floor_factor` | `0.3` | New. Multiplier on `importance / 5.0` for per-node `min_strength`. |

`memory_decay_rate` remains in config (used by `run_decay` and long-rest for nodes that predate this WP) but is superseded for new memories by the two-speed pair above.

#### Data model addition

`Memory.min_strength: float` — set at creation, readable but not updated by decay passes.

#### Migration note

Existing memories without `min_strength` fall back to the global `min_memory_strength` (0.0). No backfill required for correctness; a one-off migration script is optional but not part of this WP.

#### Definition of Success

- [ ] New memories created with `strength = initial_strength_factor * importance / 5.0` and `decay_rate = memory_initial_decay_rate`
- [ ] First reinforcement switches `decay_rate` to `memory_consolidated_decay_rate`; subsequent reinforcements do not change it
- [ ] `min_strength` stored on each new Memory node; decay passes use it as the floor
- [ ] Existing memories without `min_strength` continue to work (fall back to global `min_memory_strength`)
- [ ] All four config values documented in `.env.example`
- [ ] Integration test: write a memory, run decay for 30 simulated days, confirm strength < 0.20 (fast decay); reinforce once, run decay again, confirm half-life is ~69 days (slow decay)
- [ ] Integration test: write importance=5 memory, run full decay, confirm strength never drops below `importance_floor_factor * 1.0`

---

### WP-047 — Near-duplicate detection for memory review

#### Motivation

As the fabric grows, semantically similar memories accumulate that should ideally be merged. Currently the only way to find them is manual inspection or coincidence during a search. A dedicated endpoint that surfaces near-duplicates enables a systematic review-and-merge loop using the WP-038 merge endpoint.

#### Design

- `GET /memory/duplicates?threshold=0.92&limit=20` — returns a list of candidate pairs `[{a: {id, text}, b: {id, text}, similarity: float}]` ordered by similarity descending.
- Implementation: iterate all Memory node pairs that have an existing `RELATED_TO` edge (already implies semantic proximity) and filter to those where cosine similarity of stored embeddings exceeds `threshold`. This avoids a full O(n²) scan by using the graph structure as a pre-filter.
- Alternatively (if no `RELATED_TO` edge yet): run the vector index search for each node and check top-k against `threshold`. Use the pre-existing `RELATED_TO` approach first; document the limitation.
- `threshold` and `limit` configurable via query param; defaults from `Settings`.
- CLI: `memory find-duplicates [--threshold 0.92] [--limit 20]`
- MCP: `memory_find_duplicates`

#### Definition of Success

- [ ] `GET /memory/duplicates` returns correct pairs above threshold, ordered by similarity
- [ ] Result excludes archived and merged memories (status filter from WP-038)
- [ ] CLI and MCP wired
- [ ] Integration test: seed two nearly-identical memories, confirm they appear as a pair; seed two unrelated memories, confirm they do not

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

