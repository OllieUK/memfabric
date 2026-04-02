# Graph-Memory Fabric — Completed Work Packages

Chronological record of delivered WPs, retrospectives, and the Retrospective Log.

---

## WP-084 — API health and response polish

**Completed:** 2026-04-02

- `GET /health` now returns `version` (from package metadata via `importlib.metadata`) and `build` (7-char git commit hash, falls back to `"unknown"` if git unavailable); both computed once at import time
- `POST /memory` response now includes `strand_ids: List[str]` — echoes the strand IDs passed in the request for new memories; empty list for deduplicated memories
- `MemoryClient.add_memory()` return type changed from `str` to `dict` with keys `memory_id`, `deduplicated`, `strand_ids`
- `mcp_server.memory_add` return type changed from `str` to `dict` (FastMCP serialises automatically)
- CLI updated to extract `result["memory_id"]` from dict return
- `COMPANION.md` documents `### Relevant to today` suppression on small/sparse graphs

**Retrospective:** Three independent improvements batched correctly — combined effort was Low as predicted. The `MemoryClient.add_memory` return type change required updating all callers (CLI + mocks); these were few but worth verifying carefully. MCP return type initially returned `str(result)` (Python repr) which was caught in code quality review and fixed before merge.

---

## WP-089 — Fix wake-up 2-tuple unpacking after WP-054 3-tuple change

**Completed:** 2026-04-02

- `memory_client/cli.py`: updated `wake-up` command to unpack `(core, topic_memories, _maintenance_status)` — was unpacking 2 values from a 3-tuple since WP-054 added `maintenance_status` to `wake_up_split()`, causing `ValueError: too many values to unpack` on every CLI wake-up call
- `tests/test_wp033_mcp_server.py`: updated 3 mock return values (test_u3, test_u6, test_u7) from 2-tuple to 3-tuple `([memories], [], {})`
- `tests/test_wake_up_close_session.py`: updated `TestWakeUpSplitClient.test_returns_core_and_topic_lists` to unpack 3-tuple
- All 25 unit tests in `test_wp033_mcp_server.py` + `test_wake_up_close_session.py` passing

**Retrospective:** WP-054 correctly updated the MCP server and client but missed the CLI unpacking and three test mocks. Bug surfaced in production (Marabot startup failure) rather than CI. Root cause: no regression run against CLI path in WP-054 DoD.

---

## WP-056 — Process log for lifecycle and maintenance operations

**Completed:** 2026-04-02

- Added `_OPERATION_LOG_CAP = 200`, `get_operation_log(session)`, and `append_operation_log(session, entry)` to `memory_service/memory_repo.py` — parallel to the WP-054 maintenance log pair; stores entries as JSON in `sys.operation_log` on the System singleton node
- Added `OperationLogEntry` and `OperationLogResponse` Pydantic models to `memory_service/main.py`
- Added `GET /memory/operation/log` endpoint returning all operation log entries
- Wired `append_operation_log` into all four lifecycle handlers: `update` (with `fields_updated`), `merge` (with `target_id`), `archive`, and `restore`; added `now` computation to `merge_memory` and `restore_memory` handlers which previously lacked it
- Log is written on success path only — failed operations (ValueError → 404) never produce a log entry
- Added `memory_operation_log()` MCP tool to `mcp_server/server.py` returning plain-text summary (most recent first)
- Added `operation_log()` method to `memory_client/client.py`
- Extracted `make_mock_driver()` helper to `tests/conftest.py` (previously inline in test files)
- Fixed redundant `req.model_dump()` call in `update_memory` handler — captures `requested_fields` before `patch_fields` mutation
- 22 tests: 16 unit + 6 integration against live Memgraph; all passing

**New backlog items:**
- WP-091: Add `agent_id` to lifecycle operation log entries — lifecycle endpoints don't currently accept `agent_id`; deferred to follow-up WP (L value, L effort)

**Retrospective:** The parallel structure between `get_operation_log`/`append_operation_log` and the WP-054 maintenance log pair made the repo layer mechanical. The main judgement call was where to write the log: handler vs. repo function — handler was correct because it separates the log from the repo primitive and ensures failed ops don't log. The simplify pass caught a meaningful redundant `model_dump()` call in the update handler, and the test helper extraction to conftest paid off immediately (used by 6 test classes). One latent concern deferred to BACKLOG: the read-modify-write pattern for `append_operation_log` has a theoretical race condition under concurrent lifecycle ops — accepted for v1 single-agent use.

---

## WP-088 — Graph dedup enforcement and agent-ID attribution

**Completed:** 2026-04-01

- Added `memory_dedup_threshold: float = 0.05` to `Settings` in `memory_service/config.py`
- Added `find_duplicate_memory(session, fact, embedding, threshold) -> str | None` to `memory_service/memory_repo.py` — two-stage check: exact case-insensitive `fact` match first, then vector similarity via `vector_search.search`; excludes merged/archived nodes
- Extended `AddMemoryResponse` with `deduplicated: bool = False` (backward-compatible)
- Updated `POST /memory` handler: generates embedding before dedup check; on hit reinforces canonical and returns early with `deduplicated=True`; UUID generation moved after dedup check to avoid scoping issues
- Made `agent_id` a required positional parameter in MCP `memory_add` tool (`mcp_server/server.py`) — removed `or settings.agent_id` silent fallback
- Created `scripts/dedup_cleanup.py` — one-time batch script: finds exact and semantic duplicate groups using union-find + cosine distance (stdlib `math`), merges each group into canonical node (oldest `created_at`; tie-break: highest `importance`), reinforces canonical once per group; supports `--dry-run` and `--similarity-threshold` flags
- Updated `tests/test_add_memory.py::TestPostMemoryFactSoWhat` to UUID-suffix fact strings (pre-existing fragility exposed by the dedup gate)
- Updated `tests/test_wp033_mcp_server.py` to pass explicit `agent_id` (old fallback test updated to test new required behaviour)
- 17 new tests (11 unit, 6 integration); 135 integration tests passing; 0 new regressions

**New backlog items from /simplify:**
- WP-089: Fix 3 pre-existing failing tests in `test_wp033_mcp_server.py` (test_u3, test_u6, test_u7) — `memory_wake_up` mock expects 2-tuple but `wake_up_split` now returns 3-tuple (M value, L effort)
- WP-090: Handle non-`ServiceUnavailable` exceptions in `find_duplicate_memory` (e.g. MAGE not loaded) — currently propagates as 500 instead of 503 (L value, L effort)

**Retrospective:** The dedup gate immediately exposed a latent fragility: several integration tests in `test_add_memory.py` used well-known fact strings ("Oliver has ADHD.") that matched live DB data. UUID-suffixing is the correct fix. The pre-write semantic dedup threshold (0.05) works well with `all-MiniLM-L6-v2` but needed empirical phrase selection for the integration test — the plan's suggested phrases were too distant with UUID suffixes. The `WITH node, distance` Cypher fix (missed in initial implementation, caught by code review) validates the value of the `WITH`-before-`WHERE` codebase pattern. Requiring explicit `agent_id` in the MCP tool is a breaking change that will immediately surface any callers that were relying on the silent fallback — this is the intended effect.

---

## WP-054 — Maintenance audit trail and startup escalation loop

**Completed:** 2026-04-01

- Added `get_maintenance_log(session) -> list` and `append_maintenance_log(session, entry)` to `memory_service/memory_repo.py` — stores JSON audit entries on the `System` node (`maintenance_log` property, capped at 100)
- Wired `append_maintenance_log` into `short_rest()` and `long_rest()` — entries written on real runs only (not dry-run)
- Added `GET /memory/maintenance/log` endpoint, `MaintenanceLogEntry` and `MaintenanceLogResponse` Pydantic models to `memory_service/main.py`
- Replaced `maintenance_warning: Optional[str]` on `WakeUpResponse` with `maintenance_status: MaintenanceStatus` — structured object with `short_rest_overdue`, `long_rest_overdue`, `short_rest_days_ago`, `long_rest_days_ago`, `recommended_action`; checks both maintenance types (previously only long-rest)
- Added `_compute_maintenance_status()` pure helper in `main.py` with priority-ordered `recommended_action` logic
- Added `maintenance_log()` to `memory_client/client.py`; updated `wake_up_split()` return to 3-tuple including `maintenance_status`
- Updated `memory_wake_up` MCP tool to surface maintenance alert block prominently at top of briefing when action is needed; added `memory_maintenance_log` MCP tool
- Updated stale WP-040 tests that checked for the old `maintenance_warning` field
- 29 unit tests + 4 integration tests (live stack), all passing

**Retrospective:** Replacing the single string `maintenance_warning` with a structured `MaintenanceStatus` object was the right call — it lets the MCP surface a clear actionable prompt rather than a passive note, and it exposes both short-rest and long-rest overdue state (the old implementation only checked long-rest). The JSON-on-System-node approach for the audit log keeps the schema minimal (no new node type), which fits v1 constraints well. Watch for: if the audit log needs richer queries (filter by operation type, date range), a dedicated `Operation` node would be warranted — WP-056 is already planned for this.

---

## WP-052 — Expose `person_ids` in MCP `memory_update`

**Completed:** 2026-04-01

- Added `person_ids: list[str] | None = None` parameter to `memory_update` MCP tool in `mcp_server/server.py`
- Updated tool docstring to clarify that `person_ids` is a full replacement (existing ABOUT edges are removed and recreated)
- Threaded `person_ids` through to the underlying `MemoryClient.update_memory()` call which already supported the parameter
- Added unit test U8 to `tests/test_wp033_mcp_server.py`: verifies the parameter is passed through to the client correctly via mock
- Added integration test I6 to `tests/test_wp033_mcp_server.py`: creates a memory linked to one person, updates via MCP to link to a different person, verifies old link is gone and new link is present via HTTP search filter
- All 8 unit tests and 6 integration tests passing

**Retrospective:** Minimal change — single parameter addition to an existing tool; HTTP API, repo layer, and Python client already handled `person_ids` correctly. The implementation surface was straightforward once the pattern was identified. The test plan validated that HTTP PATCH, Python client, and MCP tool all needed to expose the same parameter for true parity, and all three now do.

---

## WP-045 — Make Local Startup Deterministic Offline

**Completed:** 2026-04-01

- Replaced the TCP-only bash healthcheck (`exec 3<>/dev/tcp`) in `docker-compose.yml` with a Python `socket.create_connection` check; increased `start_period` to 30s and `retries` to 10 for more robust cold-start behaviour
- Added `wait_for_memgraph()` to `scripts/start-local-stack.sh` — polls `docker inspect` until the container is `healthy` before launching uvicorn; configurable timeout via `MEMGRAPH_WAIT_TIMEOUT` (default 60s); uses `return 1` (not `exit 1`) for composability with `set -e`
- Documented `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`, `EMBEDDING_PRELOAD_ON_STARTUP`, and `MEMORY_SERVICE_RELOAD` in `.env.example` with accurate comments; added context comment on `EMBEDDING_LOCAL_FILES_ONLY` as the primary offline control

**Retrospective:** Purely operational — no API or schema changes. The code review surfaced that `exit 1` inside a bash function bypasses trap handlers and the unused `sys` import in the healthcheck one-liner was dead code. Both caught pre-merge. The `.env.example` comment for `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` initially misrepresented the control flow (the embeddings module derives these from `EMBEDDING_LOCAL_FILES_ONLY`, not the other way around) — code review caught it. Good signal that doc changes need the same review rigour as code.

---

## WP-083 — `person_ids` filter on `POST /memory/search`

**Completed:** 2026-03-31

- Added `person_ids: Optional[List[str]] = None` to `SearchMemoryRequest` in `memory_service/main.py`
- Extended `_SEARCH_QUERY_TEMPLATE` in `memory_service/memory_repo.py` with `OPTIONAL MATCH (m)-[:ABOUT]->(per:Person)` / `WHERE ($person_ids IS NULL OR per.id IN $person_ids)` — identical pattern to existing `project_ids` filter
- Propagated `person_ids` through `MemoryClient.search_memory` in `memory_client/client.py`
- Exposed `person_ids` in MCP `memory_search` tool in `mcp_server/server.py` with docstring explaining semantics
- Added `TestPersonIdsFilter` (4 integration tests) to `tests/test_search_memory.py`: single-person filter, multi-person OR, backward-compat with omitted filter, composition with `tags`
- All 31 search tests passing

**Retrospective:** The `project_ids` filter was an exact template for this change — implementation was mechanical once the pattern was identified. TDD caught a Pydantic silent-drop behaviour (unknown fields aren't rejected by default) which meant tests initially showed 2 passing instead of all failing; the correct TDD-red signal was 2 assertion failures on the filter-dependent tests. The `getattr` defensive guard introduced during implementation was caught in code review and replaced with direct attribute access — consistent with all adjacent params.

---

## WP-012 + WP-013 — Pin Dependency and Docker Image Versions (2026-03-31)

- Added `<next_major` upper bounds to all three `requirements.txt` files (`memory_service`, `memory_client`, `mcp_server`); original lower bounds preserved
- Replaced `memgraph/memgraph-mage:latest` and `memgraph/lab:latest` with `3.9.0` in `docker-compose.yml`
- `pip check` shows no new conflicts introduced (pre-existing `pygobject`/`docling-core` warnings unchanged)

**Retrospective:** Purely mechanical config change. The installed versions at time of pinning are: fastapi 0.135.1, uvicorn 0.42.0, neo4j 6.1.0, sentence-transformers 5.3.0, pydantic 2.12.5, fastmcp 3.1.1, memgraph 3.9.0. When any package crosses its ceiling, bump intentionally after reviewing the changelog.

---

## WP-055 — Fix Long-Rest Edge Discovery Reporting Mismatch (2026-03-31)

- Replaced per-node `count(r)` accumulation in the live rediscovery path of `long_rest()` with a single post-loop Cypher count query: `MATCH ()-[r:RELATED_TO]->() WHERE r.last_activated_at = $now_iso AND r.activation_count = 0 RETURN count(r)`
- `edges_discovered` now equals the count of edges verifiable in the graph by timestamp + activation_count, eliminating the mismatch observed on 2026-03-27 (reported 8, graph had 15)
- Dry-run path unchanged: continues accumulating `would_discover` per-node as a forward-looking estimate
- Added `test_long_rest_edges_discovered_matches_graph` integration test to `TestLongRest`

**Retrospective:** Straightforward single-query replacement. The post-loop count pattern is more trustworthy than per-MERGE accumulation for any future maintenance operations that write edges in bulk.

---

## WP-080 — Server-side `min_importance` filter on memory search

**Completed:** 2026-03-31

- Added `min_importance: Optional[int]` (range 1–5) to `SearchMemoryRequest` in `memory_service/main.py`
- Added `AND ($min_importance IS NULL OR m.importance >= $min_importance)` to `_SEARCH_QUERY_TEMPLATE` in `memory_service/memory_repo.py`
- Passed `min_importance` through `search_memories()` to the Cypher query
- Added `min_importance: int | None = None` keyword parameter to `MemoryClient.search_memory()` in `memory_client/client.py`
- 5 integration tests added to `tests/test_search_memory.py` (`TestSearchMinImportance`)
- When omitted, behaviour is unchanged (no filtering applied)

**Retrospective:** Straightforward parameter threading. Consider extending the same pattern to `min_strength` if callers need decay-aware filtering server-side.

---

## WP-079 — Importance recalibration pass

**Date:** 2026-03-28

- Reviewed all active memories at `importance >= 4` against the blast-radius-of-absence definition introduced in `memory_client/COMPANION.md`
- Recalibrated `145` of the `174` reviewed memories by updating `importance` only; no memory text or graph structure changed
- One additional active `importance=4` memory discovered outside the initial export was downgraded during verification, for `146` total live updates
- High-priority pool reduced from `174` memories (`58` fives, `116` fours) to `52` (`13` fives, `39` fours)
- Final active-memory distribution after the pass: `13` at `5`, `39` at `4`, `174` at `3`, `26` at `2`, `3` at `1`
- Surviving `5` memories are now concentrated on hard boundaries, startup / HITL protocol, Mara identity anchors, Umbrella safety cues, and primary-relationship constraints
- Surviving `4` memories are now concentrated on live project constraints, current job-search rules, material communication guidance, and high-impact personal calibration such as ADHD support needs
- Added a data-pass plan and verification note at `docs/superpowers/plans/2026-03-28-wp-079-importance-recalibration.md`

**Retrospective:** The main risk was not under-correcting single memories but preserving whole inflated categories. Reviewing by blast radius rather than emotional salience cleaned this up quickly: relationship texture, biography, project history, and ritual detail mostly belong at `3`, not `4` or `5`. The one extra `importance=4` memory found during verification is a good reminder that future recalibration tooling should query live data again immediately before mutation, not rely only on a single export snapshot.

---

## WP-069 — Cybersecurity knowledge layer: schema, indexes, multilingual model

**Date:** 2026-03-28

- New `scripts/init_cybersec_schema.py` — idempotent Memgraph setup for the knowledge layer: 7 uniqueness constraints (`Standard.id`, `Control.id`, `Document.id`, `Chunk.id`, `BusinessAttribute.id`, `Organisation.id`, `Jurisdiction.code`), two vector indexes (`ctrl_embedding_idx ON :Control(embedding)`, `chunk_embedding_idx ON :Chunk(embedding)`), post-creation validation via `SHOW INDEX INFO`, legacy capacity advisory for `mem_embedding_idx`
- New `memory_service/cybersec_schemas.py` — shared enum-like frozensets: `SABSA_LAYERS`, `CONTROL_DOMAINS`, `CONTROL_RELATIONSHIP_TYPES`, `DOCUMENT_POLICY_LEVELS`, `JURISDICTION_TYPES`, `ORGANISATION_TYPES`
- New `scripts/migrate_embeddings.py` — one-time re-embedding migration for `Memory`, `Control`, and `Chunk` nodes after switching `EMBEDDING_MODEL`; idempotent (skips nodes where `embedding_model_name` already matches); `--dry-run` and `--batch-size` flags
- `memory_service/config.py` — added `memory_index_capacity: int = 5000`, `ctrl_index_capacity: int = 5000`, `chunk_index_capacity: int = 10000`
- `memory_service/main.py` — `NodeLabel` enum extended with 7 knowledge-layer labels: `Standard`, `Control`, `Document`, `Chunk`, `BusinessAttribute`, `Organisation`, `Jurisdiction`
- `scripts/init_schema.py` — fixed `SHOW INDEX INFO` column name (`"index type"` with space); `create_vector_index` now accepts configurable `capacity` parameter; `mem_embedding_idx` capacity defaults to `settings.memory_index_capacity` (5000)
- `scripts/dump_db.py` — edge query broadened from `:Memory`-scoped `RELATED_TO|LEADS_TO` to label-agnostic `WHERE type(r) IN [...]` covering all 13 edge types including the knowledge layer
- `scripts/restore_db.py` — `ALLOWED_EDGE_TYPES` frozenset expanded to all 13 edge types; hoisted to module level (was inside loop)
- WP-019 closed (superseded): `ctrl_index_capacity` and `chunk_index_capacity` config fields, plus `mem_embedding_idx` capacity bump to 5000, fold in WP-019's scope
- 12 unit tests + 4 integration tests in `tests/test_wp069_cybersec_schema.py`

**Retrospective:** Memgraph's `SHOW INDEX INFO` and `SHOW CONSTRAINT INFO` use space-containing column names (`"index type"`, `"constraint type"`, `"properties"` as list) not the simple `"type"` or `"property"` names you'd expect. All record lookups need `.get("index type") or .get("type")` fallback chains. Deferred to WP-077: `create_constraint()` and `get_embedding_dimension()` are duplicated identically between `init_schema.py` and `init_cybersec_schema.py` — worth extracting to `scripts/schema_utils.py` once there are three init scripts.

---

## WP-051 — Fix merge rewiring dedup for weighted relationships

**Date:** 2026-03-28

- `merge_memory()` previously used `MERGE (tgt)-[:IN_STRAND {weight: ...}]->(s)` and `MERGE (tgt)-[:RELATED_TO {weight: ...}]->(rel)` — because Memgraph matches the entire pattern including inline properties, these created duplicate parallel edges when the target already had the same topological edge with a different weight
- Fixed by switching to topology-only MERGE (`MERGE (tgt)-[existing:IN_STRAND]->(s)`) with `ON CREATE SET` / `ON MATCH SET` to populate or reconcile properties
- IN_STRAND reconciliation: `weight = max(existing, source)`
- RELATED_TO reconciliation: `weight = max`, `activation_count = sum`, `last_activated_at = more recent`, `decay_rate = min` (lower rate = more consolidated)
- Dropped internal-only `now_iso` parameter from `merge_memory()`; generated unconditionally inside the function
- Moved `count_edges` and `get_edge_props` helpers to `tests/conftest.py` alongside existing graph inspection helpers
- 5 new integration tests: IN_STRAND dedup (target wins, source wins), RELATED_TO full property reconciliation, sparse edge with missing properties, pure rewire

**Retrospective:** Memgraph does not support `min()` as a scalar function in Cypher. The first attempt used `min(existing.weight, 1.0)` for a weight cap — dead code in any case since weights are bounded 0–1. Removed on `/simplify` review. The topology-only MERGE pattern (MERGE then SET) is the right approach for any edge carrying properties that may be written from multiple sources.

---

## WP-038 — Memory lifecycle operations: update, merge, archive, restore

**Date:** 2026-03-27

- Added `status: 'active'` to all new Memory nodes at creation; search and wake-up now filter `WHERE (m.status IS NULL OR m.status = 'active')` for backwards compatibility with pre-WP-038 nodes
- `PATCH /memory/{id}`: in-place update of fact, so_what, tags, importance, person_ids, strand_ids; recomputes embedding when text content changes; person_ids/strand_ids are full replacements
- `POST /memory/{id}/merge`: rewires ABOUT, IN_STRAND, LEADS_TO (both directions), RELATED_TO (both directions) from source to target; creates MERGED_INTO tombstone edge; sets `source.status='merged'`, `source.superseded_by=target_id`
- `POST /memory/{id}/archive`: sets `status='archived'`, `archived_at`; excluded from search and wake-up
- `POST /memory/{id}/restore`: returns archived memory to active, clears `archived_at`; merged memories cannot be restored
- `get_memory_for_update` repo helper fetches current fact/so_what for merge-then-recompute pattern; PATCH endpoint uses single session for both read and write
- Client, CLI, and MCP updated with `update_memory`, `merge_memory`, `archive_memory`, `restore_memory`
- New `tests/test_wp038_lifecycle.py`: 14 unit tests (Pydantic validation, Cypher filter assertions, HTTP client/CLI wire-up) + 21 integration tests covering all status transitions, edge rewiring, and exclusion from search/wake-up

**Retrospective:** /simplify caught three issues post-implementation: a redundant existence check in `update_memory` (the endpoint already validates via `get_memory_for_update`), two separate DB sessions in the PATCH endpoint that could be one, and a dead `now` parameter in `merge_memory` that was accepted but never used. All fixed before commit.

---

## WP-022 — Cap neighbour count in search results

**Date:** 2026-03-27

- Added `search_neighbour_cap: int = 50` to `Settings` (config.py) and `.env.example`; prevents response bloat from highly-connected nodes on dense graphs
- `search_memories` in `memory_repo.py` now requires a `neighbour_cap: int` argument; each `collect(DISTINCT x.id)` Cypher expression carries `[..{neighbour_cap}]` so the database slices before serialisation
- `main.py` call site passes `settings.search_neighbour_cap`
- New `tests/test_wp022_neighbour_cap.py`: 4 unit tests (Cypher string assertions) + 3 integration tests; uses `monkeypatch` for settings override

**Retrospective:** Integration tests initially failed because `add_memory` auto-creates `RELATED_TO` edges, making exact neighbour counts unpredictable. Fixed by using `max_hops=0` to isolate LEADS_TO traversal and switching the below-cap test to assert `>=` rather than exact equality.

---

## WP-048 — Two-speed decay + importance floor to protect core memories

**Date:** 2026-03-26

- Added 4 new config fields: `initial_strength_factor` (0.4), `memory_initial_decay_rate` (0.07), `memory_consolidated_decay_rate` (0.01), `importance_floor_factor` (0.3)
- `add_memory`: initial strength = `initial_strength_factor * importance/5` (was `importance/5`); decay rate = `memory_initial_decay_rate` (fast); `min_strength` = `importance_floor_factor * importance/5` stored on node
- `reinforce_memory`: first reinforcement switches `decay_rate` to `memory_consolidated_decay_rate` using pre-increment count check via WITH clause
- `decay_pass` + `short_rest`: read per-node `min_strength` as decay floor; fall back to global `min_memory_strength` for nodes without the property
- Updated `tests/test_wp029_reinforcement.py` for new initial-strength expectations
- New `tests/test_wp048_two_speed_decay.py`: 8 unit tests + 8 integration tests covering all acceptance criteria

**Retrospective:** The Memgraph evaluation-order nuance in the consolidation Cypher (needing a `WITH` to capture pre-increment `reinforcement_count`) was the only implementation surprise. Per-node `min_strength` fallback for pre-existing memories requires no migration — `coalesce` handles it cleanly.

---

## WP-046 — Deduplicate search and wake-up results

**Date:** 2026-03-26

- Added `WITH DISTINCT` to `_SEARCH_QUERY_TEMPLATE` so primary search hits are deduplicated before multi-hop OPTIONAL MATCH traversal fan-out
- Added `WITH DISTINCT` to both core and topic queries in `wake_up` to guard against duplicate rows from multi-strand OPTIONAL MATCH joins
- Regression tests in `tests/test_wp046_dedup.py`: diamond-topology neighbour dedup, primary results dedup, wake-up topic dedup
- All 3 dedup tests pass; no regression in 22 existing search tests

**Retrospective:** Fix was surgical — one `DISTINCT` keyword in each of three Cypher queries. The diamond-topology test correctly documents the expected invariant even though it passed before the fix (sparse graph); it will catch regressions on a denser graph.

---

## WP-044 — Fix broken 503 + connect-error tests

**Date:** 2026-03-25

- `test_returns_503_when_db_down` (×2): moved mock-driver assignment inside `TestClient` context so lifespan no longer overwrites it; removed `test_driver` fixture dep (no live DB needed)
- `test_connect_error_exits_nonzero` (×2): replaced env-redirect approach (ignored by pydantic-settings at import time) with `respx.mock` + `side_effect=httpx.ConnectError`, matching existing pattern in `test_wake_up_close_session.py`
- All 4 tests now exercise the intended failure paths; 121 passing (was 119), no regressions

**Retrospective:** Root causes were well-documented in the backlog — execution was straightforward once the patterns were clear. The `test_driver` fixture dependency on the 503 tests was an easy miss (tests looked like integration tests but were really unit tests).

---

## WP-040 — Memory maintenance orchestration: Short Rest & Long Rest

**Date:** 2026-03-22

- 7 new Settings fields: `short_rest_recency_days`, `long_rest_recency_days`, `rediscovery_strength_threshold`, `edge_hard_prune_floor`, `edge_hard_prune_min_days`, `edge_modulation_factor`, `edge_modulation_cap`
- `System` singleton node created by `init_schema.py` (MERGE, idempotent); stores `last_short_rest_at` / `last_long_rest_at`
- `_apply_decay_modulated()` — edge-modulated decay: `effective_rate = base_rate / min(1 + factor * incoming_weight_sum, cap)` — well-connected nodes decay slower (elaborative encoding)
- `decay_pass()` extended with `node_ids`, `edge_modulation_factor`, `edge_modulation_cap`, `dry_run` kwargs; UNWIND writes gated on `if not dry_run`; incoming edge weights fetched via `OPTIONAL MATCH`
- `short_rest()` — scoped decay: Python-side recency filtering (`recall_count > 0 OR last_used_at within recency window`); updates `last_short_rest_at`
- `long_rest()` — 4-step: full decay_pass + per-node vector rediscovery + prune candidates + system node update
- `maintenance_stats()` — node/edge health snapshot + overdue flags vs. `short_rest_recency_days` / `long_rest_recency_days`
- `POST /memory/maintenance/short-rest[?dry_run=true]` / `POST /memory/maintenance/long-rest[?dry_run=true][&prune=true]` / `GET /memory/maintenance/stats` — all registered before `POST /memory/{memory_id}/reinforce` (route ordering)
- `GET /memory/wake-up` extended: `maintenance_warning` field surfaced when `last_long_rest_at` is stale (best-effort, never fails wake-up)
- `MemoryClient.short_rest()`, `.long_rest()`, `.maintenance_stats()` + CLI `memory short-rest`, `memory long-rest`, `memory status`
- MCP `memory_short_rest`, `memory_long_rest`, `memory_maintenance_stats` tools
- `scripts/dump_db.py` + `scripts/restore_db.py` — pre-maintenance snapshot + MERGE-based restore with edge-type allowlist
- 23 new tests (unit + integration); 220 passing; 4 pre-existing failures unchanged
- **Key finding:** `edge_modulation_cap` default of `1.0` makes modulation inert — plan review caught and corrected to `10.0` before implementation. Division-by-zero guard (`max(..., 1e-9)`) added to `_apply_decay_modulated`. Plan review also caught WHERE clause operator precedence bug in `short_rest` Cypher.

**Retrospective:** Three plan-review catches before a line of code was written saved at least one full debug cycle each. Quality review on Task 7 (CLI) surfaced output-placement inconsistency (`console.print` outside try block) and a false-positive dry-run test — both fixed before Task 10. Subagent-driven development worked cleanly across 10 tasks with no regressions. The per-node rediscovery loop in `long_rest` is O(k) vector queries — noted as a known scalability limit for large graphs; deferred to v2.

---

## WP-029 — Memory + edge reinforcement (strength, decay, Hebbian activation)

**Date:** 2026-03-22

- 8 new Settings fields (`memory_decay_rate`, `edge_decay_rate`, `recall_strength_increment`, `explicit_strength_increment`, `edge_recall_increment`, `edge_explicit_increment`, `edge_prune_threshold`, `min_memory_strength`)
- Memory nodes created with `strength = importance / 5.0`, `recall_count=0`, `reinforcement_count=0`, `last_reinforced_at`, `decay_rate`
- `recall_increment()` — non-blocking background task fires after every search; increments node strength (capped 1.0) and activates `RELATED_TO|LEADS_TO` edges within result set
- `decay_pass()` — Python-side computation (Memgraph does not support `duration.between()` on datetime types); fetches nodes/edges, applies `strength * exp(-rate * days)`, writes back via UNWIND
- `reinforce_memory()` — explicit signal; updates `last_reinforced_at`, increments `reinforcement_count`, Hebbian UNWIND×UNWIND over co-recalled edges
- `POST /memory/maintenance/decay` and `GET /memory/maintenance/weak-edges` registered before `POST /memory/{memory_id}/reinforce` (FastAPI route ordering critical)
- `memory reinforce-memory`, `memory run-decay` CLI commands; `memory_reinforce`, `memory_run_decay` MCP tools
- `scripts/migrate_reinforcement_defaults.py`: backfills pre-existing nodes/edges; ran against live DB (0 nodes, 123 edges updated)
- **Key finding:** Memgraph does not support `duration.between()` on datetime types — Python-side decay computation required. Cypher `localDateTime()` rejects `+00:00` suffix — `strftime("%Y-%m-%dT%H:%M:%S")` required for any Cypher date arithmetic.

**Retrospective:** Route ordering catch (Task 4 before Task 5) was the highest-risk item — the plan review caught it preemptively and the shadow test `test_decay_pass_not_shadowed_by_reinforce_route` confirms it at runtime. Memgraph `duration.between()` incompatibility required Python-side decay (2-round-trip design); functionally equivalent. Subagent-driven development with spec+quality review per task caught no regressions across 8 tasks.

---

## WP-037 — Person nodes + `ABOUT` edges

**Date:** 2026-03-21

- `PersonItem`, `PersonsResponse`, `CreatePersonRequest` Pydantic models added; `GET /person` and `POST /person` endpoints (MERGE + SET upsert semantics)
- `list_persons()` and `upsert_person()` added to `memory_repo.py`; `upsert_person` guards `result.single()` with RuntimeError on unexpected None
- `MemoryClient.list_persons()` and `MemoryClient.create_person()` added to `memory_client/client.py`
- CLI `list-persons` (Rich table) and `create-person` (positional id + `--name` + `--description`) added to `memory_client/cli.py`
- MCP `memory_list_persons` and `memory_create_person` tools added to `mcp_server/server.py`
- `scripts/migrate_person_nodes.py`: JSON-line stdin/stdout, `--dry-run`, `--pre-created-persons`, `coalesce` name heuristic preserves explicit names
- `scripts/__init__.py` created for package resolution under pytest
- **Key finding:** `person_ids`, `ABOUT` edge creation (step 3 in `add_memory`), and `Person` schema constraint were already implemented — WP-037 added the management endpoints and migration only
- 59 new tests (32 unit, 27 integration); 175 total passing; 4 pre-existing failures unchanged

**Retrospective:** Parallel subagent dispatch (Tasks 6–7 and 8–9 in parallel; 10–11 and 12–13 in parallel) shaved significant wall-clock time. Review-loop quality gate caught the `result.single()` None guard in Task 3 — caught before integration tests ran. Tasks 12–13 required `scripts/__init__.py` for dotted imports under pytest — not in the original plan but a 1-line fix.

---

## WP-028 — Causal graph: `fact`/`so_what` fields + `LEADS_TO` edge

**Date:** 2026-03-21

- `AddMemoryRequest` split into `fact` + `so_what`; `text` deprecated as alias via `model_validator(mode="before")`; `text` derived as `fact + " " + so_what` and used for embeddings
- `cause_ids`/`effect_ids` on `AddMemoryRequest`; steps 6 & 7 in `memory_repo.add_memory()` create `LEADS_TO` edges using `OPTIONAL MATCH + WHERE IS NOT NULL + MERGE` (missing UUIDs silently skipped)
- `traversal_direction` on `SearchMemoryRequest` (`none|causes|effects|both`); `search_memories()` builds LEADS_TO clauses independently of `max_hops`; `hop_depth = max(hops, 1)` ensures traversal even when `max_hops=0`
- `memory_client/client.py`, `cli.py`, `mcp_server/server.py` all updated; `close-session` scaffolds updated to use `fact=`/`so_what=` and include causal link step
- `scripts/migrate_fact_so_what.py`: JSON-line stdin/stdout protocol, `--dry-run`, idempotent (WHERE m.fact IS NULL, always fetches from SKIP 0)
- 6 unit tests + 9 integration tests; 117 passing, 3 pre-existing mock failures

**Retrospective:** Three rounds of plan review were needed — each caught real bugs: Pydantic v2 `Optional[str] = None` vs `str = ""` sentinel, migration pagination bug (SKIP 0 not offset), vacuous test assertions. Two-stage review (spec then quality) paid off — quality review caught the `not fact` vs `is None` issue which was a genuine correctness hazard.

---

## WP-033 — MCP server + Claude Code/Desktop wiring

**Date:** 2026-03-21

- FastMCP-based server in `mcp_server/` exposing 5 tools via STDIO: `memory_add`, `memory_search`, `memory_wake_up`, `memory_list_strands`, `memory_close_session`
- `pyproject.toml` consolidated (removed `setup.cfg`), `memory-mcp` entry point registered
- `.mcp.json` created at repo root for Claude Code auto-discovery
- `WIRING.md` fully updated: Claude Code MCP + CLI wiring, Claude Desktop entry-point + fallback configs
- `COMPANION.md` updated: MCP tools as preferred path, CLI as fallback
- 7 unit tests + 5 integration tests all passing

**Retrospective:** FastMCP decorator syntax is clean; fresh-client-per-call pattern safe for concurrent requests; plain-text briefing assembly avoids Rich dependency in server; `.mcp.json` auto-discovery in Claude Code works out of the box. Setup.cfg/pyproject.toml conflict required removing setup.cfg and using `--no-build-isolation` for editable installs in this environment.

---

## WP-032 — End-to-end companion validation

**Date:** 2026-03-21

- Ran full companion validation session against live stack; all five criteria passed
- Identified and resolved a pre-existing service-restart issue (stale uvicorn process) causing strand_id to be absent from wake-up API responses
- Created `docs/wp-032-validation-evidence.md` with PASS/FAIL evidence, gap analysis, and three new backlog items (WP-034, WP-035, WP-036)

**Retrospective:** The audit against the spec (Section 4.2) before starting WP-032 caught two deviations from WP-030: grouping by tag instead of strand_id, and missing the topic section. The stale-service bug (no `--reload` on uvicorn start) was invisible from the CLI — argues for a version hash in `/health` (WP-034).

---

## WP-031 — `memory_client` companion package: COMPANION.md + WIRING.md + docs

**Date:** 2026-03-21

- Created `memory_client/COMPANION.md` — full session protocol: wake-up, add-memory, close-session; type/importance reference; minimal session pattern
- Created `memory_client/WIRING.md` — Claude Code wiring (active), Claude Desktop + MCP placeholder (WP-033), generic HTTP/Python fallback
- Created `docs/companion-integration.md` — high-level overview, current capability status table, quick-start snippet

**Retrospective:** Pure docs WP — fast to execute.

---

## WP-030 — `memory wake-up` + `memory close-session` CLI commands

**Date:** 2026-03-21

- Added `wake_up(session, limit, topic_embedding)` to `memory_repo.py`: importance-ranked query merged with optional vector search, deduplicated, capped at limit; extracted `_record_to_memory_dict()` helper
- Added `WakeUpMemoryItem`, `WakeUpResponse` Pydantic models and `GET /memory/wake-up` endpoint with `Query()` params
- Added `MemoryClient.wake_up()` to `memory_client/client.py`
- Added `memory wake-up` and `memory close-session` CLI commands to `memory_client/cli.py`
- Created `tests/test_wake_up_close_session.py`: 15 tests (12 unit, 3 integration); all passing

**Retrospective:** `/simplify` caught a two-HTTP-call design flaw in the CLI (server already handles merge server-side). `Field()` vs `Query()` for FastAPI query params is a subtle footgun — always use `Query()` in endpoint function signatures.

---

## WP-027 — `memory list-strands` CLI command

**Date:** 2026-03-21

- Fixed all 20 strand descriptions in `scripts/seed_strands.py` to use "the user"/"the Companion" language convention
- Added `list_strands(session)` to `memory_repo.py`, `StrandItem`/`StrandsResponse` models and `GET /strands` endpoint
- Added `MemoryClient.list_strands()` and `memory list-strands` CLI command (grouped by category)
- Created `tests/test_list_strands.py`: 15 tests all passing

**Retrospective:** `/simplify` identified CLI error handler duplication at 4 copies — WP-025 trigger condition met.

---

## WP-015 — In-session LLM workflow patterns

**Date:** 2026-03-20

- Created `docs/workflows/` with five workflow files and index README: `contextual-recall.md`, `summarise-session.md`, `propose-todos.md`, `refine-edges.md`, `strand-maintenance.md`

**Retrospective:** Workflow docs must be validated against the actual API response schema — `created_at` not returned by search API; caught and fixed before commit.

---

## WP-007 — memory_client.py + Typer CLI

**Date:** 2026-03-20

- Created `memory_client/` package: `config.py`, `client.py` (`MemoryClient` httpx wrapper), `cli.py` (Typer `add-memory`, `search-memory`, `dump-graph`)
- Created `pyproject.toml` + `setup.cfg` for editable install and `memory` entry point
- Created `tests/test_cli.py`: 17 unit tests using `typer.testing.CliRunner` + `respx` mocks

---

## WP-005 — Wire POST /memory/search

**Date:** 2026-03-20

- Added `_SEARCH_QUERY_TEMPLATE` and `search_memories()` to `memory_repo.py`: single Cypher query combining vector search, tag/agent/project filters, and optional neighbour expansion
- Implemented `search_memory` endpoint in `main.py`
- Created `tests/test_search_memory.py`: 18 tests across 8 classes

---

## WP-004 — Wire POST /memory

**Date:** 2026-03-20

- Created `memory_service/memory_repo.py`: `add_memory()` — Agent+Memory+PRODUCED_BY in one round-trip; Project/Person/Strand upserts; auto + explicit RELATED_TO
- Updated `main.py` with driver lifecycle, `strand_ids`, `importance` validation, 503 handling
- Updated `tests/conftest.py`: `test_driver`, `client` fixtures; shared graph helpers (`node_exists`, `edge_exists`, `get_memory_node`, `cleanup_nodes`)
- Created `tests/test_add_memory.py`: 14 integration tests

---

## WP-016 — Shared config module

**Date:** 2026-03-20

- Created `memory_service/config.py`: canonical `Settings`, `get_driver()`, module-level `settings` singleton
- Removed duplicate `Settings`/`get_driver()` from `main.py`, `init_schema.py`, `smoke_test.py`

---

## WP-018 — Vector index dimension from model at runtime

**Date:** 2026-03-20

- Added `get_embedding_dimension()` and `get_existing_index_dimension()` to `init_schema.py`; detects dimension mismatch before create with actionable error message
- Updated `tests/test_embeddings.py` to use model-reported dimension instead of hardcoded 384

---

## WP-002 — Memgraph schema + vector index

**Date:** 2026-03-20

- Created `scripts/init_schema.py`: uniqueness constraints on all node labels + cosine vector index on `Memory(embedding)`. Idempotent.
- Created `scripts/smoke_test.py`: insert → vector search → assert → cleanup

---

## WP-003 — Local embeddings module

**Date:** 2026-03-20

- Created `memory_service/embeddings.py`: `get_embedding(text) -> list[float]`; model loaded once at import; optional on-disk cache via `EMBEDDING_CACHE_DIR`
- Created `tests/test_embeddings.py`: 4 tests (shape, determinism, distinct texts, cache)

---

## WP-001 — Project framework + Phase 1 scaffold

**Date:** 2026-03-20

- Created `.gitignore`, `.env`, `.env.example`, `docker-compose.yml` env passthrough
- Created `memory_service/requirements.txt`, `memory_service/main.py` with `Settings`
- Created `CLAUDE.md`, `BACKLOG.md`, `README.md`
- Initialised git repo

---

## Retrospective Log

### WP-001
- **What went well:** Existing partial scaffold was correct and required only additive changes.
- **Deferred:** WP-012 (pin dep versions), WP-013 (pin Docker image tags), WP-014 (Docker resource limits).

### WP-002 + WP-003
- **What went well:** Parallel agent dispatch conflict-free.
- **What to improve:** `Settings`/`get_driver()` ended up triplicated — future WPs adding scripts should import from shared module from the start.
- **Deferred:** WP-016 (shared config), WP-017 (cache eviction), WP-018 (vector dimension from model).

### WP-016 + WP-018
- **What went well:** Parallel dispatch conflict-free — each agent owned different files.
- **What to improve:** WP-016 agent left stale `get_driver()` with undefined names in `init_schema.py`. Agents should import-check after editing.
- **Deferred:** WP-019 (expose `capacity` as config).

### WP-005
- **What went well:** Single-query design clean. Parallel dispatch for code + tests conflict-free.
- **What to improve:** Graph expansion tests used `if hit is not None:` guards — silently skipping assertions. Always assert the hit is found first.
- **Deferred:** WP-022 (cap unbounded collect), WP-023 (extract 503 context manager), WP-024 (cleanup_nodes multi-id).

### WP-004
- **What went well:** Plan agent resolved all design questions upfront. Parallel agents conflict-free.
- **What to improve:** Agents should verify their own imports after editing (redundant/stale imports found during simplify).
- **Deferred:** WP-020 (UNWIND for N+1 loops), WP-021 (non-blocking embedding).

### MVP Live Demo (2026-03-20)
- **Memgraph 3.8 compatibility fixes required:** (1) vector index DDL syntax changed; (2) `EXISTS{}` subqueries not supported inside `WITH ... WHERE` — replaced with `OPTIONAL MATCH` + scalar filter; (3) `ORDER BY distance` after `collect()` aggregation requires `distance` in `RETURN` clause. Also: empty `MEMGRAPH_USER=` env var caused startup crash — removed explicit `environment:` block from docker-compose.

### WP-015
- **What went well:** Three parallel review agents caught all significant issues.
- **What to improve:** Workflow docs should be validated against actual API response schema, not just CLI option names.
- **Deferred:** WP-027 (list-strands command).

### WP-007
- **What went well:** Clean package separation; `respx` mocking kept tests self-contained.
- **What to improve:** `setup.cfg` needed due to old setuptools — editable installs should be validated as part of DoS.
- **Deferred:** WP-025 (shared CLI error handler), WP-026 (`MemoryType` mirror in client).
