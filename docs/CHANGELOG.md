# Graph-Memory Fabric — Completed Work Packages

Chronological record of delivered WPs, retrospectives, and the Retrospective Log.

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
