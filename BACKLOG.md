# Graph-Memory Fabric – Feature Backlog

> **Value:** H = High / M = Medium / L = Low
> **Effort:** H = High / M = Medium / L = Low
> **Priority score:** `Value / Effort` using `H=3`, `M=2`, `L=1`
> Completed WPs → [docs/CHANGELOG.md](docs/CHANGELOG.md)

---

## Currently In Progress

| ID | Title | Phase | Value | Effort | Depends on | Notes |
|----|-------|-------|-------|--------|------------|-------|
| WP-044 | Fix broken 503 + connect-error tests | Implementation | M | L | — | 4 vacuous tests; fix pattern documented in BACKLOG detail spec |

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
| 1 | R1 | WP-044 | Fix broken 503 + connect-error tests | M | L | 2.0 | — | `test_returns_503_when_db_down` ×2 and `test_connect_error_exits_nonzero` ×2 pass vacuously — 503 path untested. Fix pattern fully documented. See detail below. |
| 2 | R1 | WP-022 | Cap neighbour count in search results | M | L | 2.0 | WP-005 ✅ | `collect(DISTINCT n.id)` unbounded with `max_hops=3` on dense graph — add slice cap (e.g. `[..50]`). Correctness risk as graph grows. |
| 3 | R1 | WP-012 | Pin dependency versions in requirements.txt | M | L | 2.0 | — | Use `>=x,<y` bounds. Stability/reproducibility prerequisite — do before declaring a stable first release. |
| 4 | R1 | WP-013 | Pin Docker image tags (no `latest`) | M | L | 2.0 | WP-012 | Replace `latest` tags with specific versions. Do after WP-012. |
| 5 | R1 | WP-045 | Make local startup deterministic offline | M | L | 2.0 | — | Fix misleading Memgraph healthcheck and add a documented/scripted API startup path that works with cached embeddings offline (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`). Prevent false “memory service unreachable” failures at session start. |
| 6 | R1 | WP-034 | Add version/build hash to `/health` response | M | L | 2.0 | — | Detect stale or mismatched service instances at mandatory session startup. Promoted from low value because startup operability is part of the core working loop. Batch with WP-035/036. |
| 7 | R1 | WP-038 | Memory lifecycle operations — update, merge, archive | H | H | 1.0 | WP-037 ✅ | First-class memory maintenance: PATCH, merge, archive, restore. Kept immediately ahead of WP-039 because it is the prerequisite for the stronger next branch. See detail below. |
| 8 | R1 | WP-039 | Ephemeral test-memory handling — TTL, tagging, cleanup | H | M | 1.5 | WP-038 | Prevent test artefacts polluting live context. See detail below. |
| 9 | R2 | WP-006 | Wire `GET /memory/graph` | M | M | 1.0 | WP-028 ✅, WP-029 ✅ | Filtered subgraph export: project/agent/tag/since/until params; returns `{nodes, edges}`. |
| 10 | R2 | WP-035 | Return `strand_ids` in `add-memory` API response | L | L | 1.0 | — | Reduce friction when chaining related memories. Batch with WP-034/036. |
| 11 | R2 | WP-036 | Document `### Relevant to today` suppression in COMPANION.md | L | L | 1.0 | — | Avoid companion confusion on small DBs. Batch with WP-034/035. Not covered by the three-tier memory model addition (2026-03-22) — still needed for wake-up output behaviour on sparse graphs. |
| 12 | R2 | WP-043 | Inline effective_strength sort in search | L | L | 1.0 | WP-029 ✅ | Add Cypher inline decay formula as search sort key. Currently deferred — stored strength post-decay-pass used as the current proxy. |
| 13 | R2 | WP-025 | Extract shared CLI error handler | L | L | 1.0 | — | 4+ identical `except httpx.*` blocks in `cli.py`. Extract once. |
| 14 | R2 | WP-026 | `MemoryType` mirror in `memory_client` | L | L | 1.0 | WP-007 ✅ | Mirror enum so callers get IDE completion without cross-package import. |
| 15 | R2 | WP-023 | Extract `get_session` context manager for 503 handling | L | L | 1.0 | WP-029 ✅ | `try/with driver.session()/except ServiceUnavailable→503` copy-pasted across all endpoints. Do after WP-029 (adds more endpoints). |
| 16 | R2 | WP-020 | UNWIND for person/strand/related_ids writes | L | L | 1.0 | WP-004 ✅ | Replace per-item `session.run()` loops in `add_memory` with UNWIND queries. Add `related_ids` max-length cap (e.g. 20). |
| 17 | R2 | WP-021 | Non-blocking embedding in async endpoints | L | L | 1.0 | WP-004 ✅, WP-005 ✅ | `get_embedding()` blocks the event loop. Wrap with `run_in_executor` when concurrent usage becomes a problem. |
| 18 | R2 | WP-024 | `cleanup_nodes` support multiple ids per label | L | L | 1.0 | — | Change `extra_ids: dict[str, str]` to `dict[str, str \| list[str]]` for multi-node cleanup in tests. |
| 19 | R2 | WP-017 | Embedding cache eviction / size cap | L | L | 1.0 | WP-003 ✅ | `EMBEDDING_CACHE_DIR` grows without bound. Add LRU eviction or max-entry cap. |
| 20 | R2 | WP-019 | Expose vector index `capacity` as config | L | L | 1.0 | WP-016 ✅ | `capacity: 1000` hardcoded in `init_schema.py`. Add to `Settings`. |
| 21 | R2 | WP-014 | Docker resource limits | L | L | 1.0 | — | Add `mem_limit`/`cpus` to docker-compose. |
| 22 | R2 | WP-041 | Subject/object schema on Memory nodes | H | H | 1.0 | WP-028 ✅ | Add explicit `subject` and `object` fields. Required before multi-user or shared-memory scenarios. Avoid hard-coded subject assumptions in ingestion APIs. |
| 23 | R3 | WP-042 | Self-contained `memory_client` packaging | L | L | 1.0 | WP-031 ✅ | Move `pyproject.toml` into `memory_client/` for independent install. Re-scored from medium value because it is packaging polish rather than core product capability. |
| 24 | R3 | WP-008 | LLMClient abstraction | M | M | 1.0 | WP-007 ✅ | `LLMClient.ask(system, prompt, model)` wrappers for Claude/OpenAI/Ollama. |
| 25 | R3 | WP-009 | Headless agent framework | M | H | 0.67 | WP-008 | `BaseAgent` using `memory_client` + `LLMClient`; scheduled/event-driven tasks. |
| 26 | R3 | WP-010 | Remote/mobile access | L | H | 0.33 | WP-009 | Tailscale/VPS hosting + TLS + API key auth. |
| 27 | R3 | WP-011 | Custom graph-cloud UI | L | H | 0.33 | WP-006 | React + D3.js/vis-network consuming `GET /memory/graph`. |

> **Note:** old backlog items once grouped under `v2+` are now part of the same continuous backlog with `Release` assignments.
> Old v2+ WP-034 and WP-035 were renumbered WP-041 and WP-042 to avoid collision with the current WP-034/035/036 items.

---

## Detail Specs

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
