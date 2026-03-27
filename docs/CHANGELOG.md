# Graph-Memory Fabric — Completed Work Packages

Chronological record of delivered WPs, retrospectives, and the Retrospective Log.

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
