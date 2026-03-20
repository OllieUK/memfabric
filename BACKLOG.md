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

| ID | Title | Phase | Value | Effort | Depends on | Notes |
|----|-------|-------|-------|--------|------------|-------|
| WP-004 | Wire POST /memory | 4 | H | L | WP-002, WP-003 | Full implementation: embed text, upsert Agent/Project/Person nodes, create Memory node, create PRODUCED_BY/ABOUT edges, auto RELATED_TO via vector search if `related_ids` not provided |
| WP-005 | Wire POST /memory/search | 4 | H | M | WP-002, WP-003 | Vector search on `Memory.embedding` + tag/agent/project filters + graph expansion up to `max_hops` |
| WP-007 | memory_client.py + Typer CLI | 5 | H | M | WP-004, WP-005 | `memory_client.py` wrapping HTTP API; Typer CLI with `add-memory`, `search-memory`, `dump-graph` commands. **Does not require WP-006.** |

### Post-MVP — Complete v1 feature set

| ID | Title | Phase | Value | Effort | Depends on | Notes |
|----|-------|-------|-------|--------|------------|-------|
| WP-006 | Wire GET /memory/graph | 4 | M | M | WP-004 | Filtered subgraph export: project/agent/tag/since/until params; returns `{nodes, edges}` |
| WP-015 | In-session LLM workflow patterns | 6 | M | S | WP-007 | Define repeatable prompt patterns for the IDE LLM: summarise notes into Memory records, propose todos from past memories, refine edges. Delivered as `docs/workflows/` markdown files, no runtime changes |
| WP-012 | Pin dependency versions in requirements.txt | 1 | M | S | — | Use `>=x,<y` bounds for reproducibility; research compatible version matrix |
| WP-013 | Pin Docker image tags (no `latest`) | 1 | M | S | — | Replace `memgraph/memgraph-mage:latest` + `memgraph/lab:latest` with specific versions once stack stabilises |
| WP-014 | Docker resource limits | 1 | L | S | — | Add `mem_limit`/`cpus` to docker-compose to prevent runaway resource use |
| WP-016 | Shared config module (`memory_service/config.py`) | 3 | M | S | WP-002, WP-003 | `Settings` class and `get_driver()` are duplicated across `main.py`, `init_schema.py`, `smoke_test.py`. Extract to shared module. `/simplify` finding from WP-002/003. |
| WP-017 | Embedding cache eviction / size cap | 3 | L | S | WP-003 | `EMBEDDING_CACHE_DIR` grows without bound. Add LRU eviction or max-entry cap before long-running deployments. `/simplify` finding from WP-003. |
| WP-018 | Vector index dimension from model at runtime | 2 | M | S | WP-002, WP-003 | `init_schema.py` hardcodes `dimension: 384`. Should derive from `SentenceTransformer(settings.embedding_model).get_sentence_embedding_dimension()` so changing `EMBEDDING_MODEL` doesn't silently break vector search. `/simplify` finding from WP-002. |

### v2+ — Future phases (not in scope for v1)

| ID | Title | Phase | Value | Effort | Depends on | Notes |
|----|-------|-------|-------|--------|------------|-------|
| WP-008 | LLMClient abstraction | 7 | M | M | WP-007 | v2+: `LLMClient.ask(system, prompt, model)` wrappers for Claude/OpenAI/Ollama |
| WP-009 | Headless agent framework | 7 | M | L | WP-008 | v2+: `BaseAgent` using `memory_client` + `LLMClient`; scheduled/event-driven tasks |
| WP-010 | Remote/mobile access | 8 | L | XL | WP-009 | v2+: Tailscale/VPS hosting + TLS + API key auth |
| WP-011 | Custom graph-cloud UI | 9 | L | XL | WP-006 | v2+: React + D3.js/vis-network consuming `GET /memory/graph` |

---

## Completed

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
