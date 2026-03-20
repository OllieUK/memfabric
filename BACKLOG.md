# Graph-Memory Fabric – Feature Backlog

> **Value:** H = High / M = Medium / L = Low
> **Effort:** S = Small (hrs) / M = Medium (day) / L = Large (days) / XL = Extra-large (week+)

---

## Currently In Progress

| ID | Title |
|----|-------|
| — | *(none)* |

---

## Prioritised Backlog

> **MVP** = minimum to store and retrieve memories via CLI day-to-day.
> Complete MVP work packages in order before moving to post-MVP items.

### 🎯 MVP — Store + retrieve memories via CLI

*(MVP complete — all items delivered)*

### Post-MVP — Complete v1 feature set

| ID | Title | Phase | Value | Effort | Depends on | Notes |
|----|-------|-------|-------|--------|------------|-------|
| WP-006 | Wire GET /memory/graph | 4 | M | M | WP-004 | Filtered subgraph export: project/agent/tag/since/until params; returns `{nodes, edges}` |
| WP-012 | Pin dependency versions in requirements.txt | 1 | M | S | — | Use `>=x,<y` bounds for reproducibility; research compatible version matrix. Do before stack is considered stable. |
| WP-013 | Pin Docker image tags (no `latest`) | 1 | M | S | WP-012 | Replace `memgraph/memgraph-mage:latest` + `memgraph/lab:latest` with specific versions. Do after stack stabilises (after WP-012). |
| WP-014 | Docker resource limits | 1 | L | S | — | Add `mem_limit`/`cpus` to docker-compose to prevent runaway resource use |
| WP-017 | Embedding cache eviction / size cap | 3 | L | S | WP-003 | `EMBEDDING_CACHE_DIR` grows without bound. Add LRU eviction or max-entry cap before long-running deployments. `/simplify` finding from WP-003. |
| WP-019 | Expose vector index `capacity` as config | 3 | L | S | WP-016 | `capacity: 1000` is hardcoded in `init_schema.py`'s index query. Add `vector_index_capacity: int = 1000` to `Settings` and use it in `create_vector_index`. `/simplify` finding from WP-018. |
| WP-020 | UNWIND for person/strand/related_ids writes | 4 | L | S | WP-004 | Steps 3/4/5a in `memory_repo.add_memory` loop with one `session.run()` per item. Replace with UNWIND queries for bulk-friendly writes. Negligible at v1 cardinality; add `related_ids` max-length cap (e.g. 20) at same time. `/simplify` finding from WP-004. |
| WP-021 | Non-blocking embedding in async endpoints | 4 | L | S | WP-004, WP-005 | `get_embedding()` is synchronous and blocks the event loop in both `/memory` and `/memory/search`. Wrap with `run_in_executor` when concurrent usage makes this a real problem. `/simplify` finding from WP-004. |
| WP-022 | Cap neighbour count in search results | 4 | M | S | WP-005 | `collect(DISTINCT n.id)` in search query is unbounded; with `max_hops=3` on a dense graph this can return thousands of UUIDs per result row. Add a slice cap (e.g. `[..50]`) in `_SEARCH_QUERY_TEMPLATE`. `/simplify` finding from WP-005. |
| WP-023 | Extract `get_session` context manager for 503 handling | 4 | L | S | WP-005, WP-006 | The `try/with driver.session()/except ServiceUnavailable→503` block is copy-pasted across all endpoints. Extract to a context manager or dependency helper; best done alongside WP-006 when a 3rd endpoint would create a 3rd copy. `/simplify` finding from WP-005. |
| WP-024 | `cleanup_nodes` support multiple ids per label | 5 | L | S | — | `extra_ids: dict[str, str]` only supports one node per label; test modules that need to clean two Agent or Project nodes must open a second session. Change to `dict[str, str \| list[str]]`. `/simplify` finding from WP-005. |
| WP-027 | `memory list-strands` CLI command | 5 | M | S | WP-007 | Strand IDs are user-assigned strings with no discovery path. Workflow docs must instruct users to track strand IDs manually. A `list-strands` command (and corresponding `GET /strand` endpoint) would make strand IDs discoverable. `/simplify` finding from WP-015. |
| WP-026 | `MemoryType` mirror in `memory_client` | 5 | L | S | WP-007 | `add_memory(type: str)` accepts any string; mirror `MemoryType` enum from `memory_service/main.py` into `memory_client/` so callers get IDE completion without cross-package import. `/simplify` finding from WP-007. |
| WP-025 | Extract shared CLI error handler in `cli.py` | 5 | L | S | WP-007 | `add-memory`, `search-memory`, `dump-graph` each repeat identical `except httpx.HTTPStatusError / ConnectError` blocks (~6 lines × 3). Extract when a 4th CLI command is added. `/simplify` finding from WP-007. |

### v2+ — Future phases (not in scope for v1)

| ID | Title | Phase | Value | Effort | Depends on | Notes |
|----|-------|-------|-------|--------|------------|-------|
| WP-008 | LLMClient abstraction | 7 | M | M | WP-007 | v2+: `LLMClient.ask(system, prompt, model)` wrappers for Claude/OpenAI/Ollama |
| WP-009 | Headless agent framework | 7 | M | L | WP-008 | v2+: `BaseAgent` using `memory_client` + `LLMClient`; scheduled/event-driven tasks |
| WP-010 | Remote/mobile access | 8 | L | XL | WP-009 | v2+: Tailscale/VPS hosting + TLS + API key auth |
| WP-011 | Custom graph-cloud UI | 9 | L | XL | WP-006 | v2+: React + D3.js/vis-network consuming `GET /memory/graph` |

---

## Completed

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
