# Graph-Memory Fabric – Feature Backlog

> **Value:** H = High / M = Medium / L = Low
> **Effort:** S = Small (hrs) / M = Medium (day) / L = Large (days) / XL = Extra-large (week+)

---

## Currently In Progress

| ID | Title |
|----|-------|
| — | *(none — WP-001 just completed)* |

---

## Prioritised Backlog

| ID | Title | Phase | Value | Effort | Notes |
|----|-------|-------|-------|--------|-------|
| WP-002 | Memgraph schema + vector index | 2 | H | M | Cypher init script; `Memory`/`Agent`/`Person`/`Project` constraints; `CREATE VECTOR INDEX` on `Memory(embedding)`; smoke test inserts one node and runs `CALL vector_search.search(...)` |
| WP-003 | Local embeddings module | 3 | H | M | `memory_service/embeddings.py`: `get_embedding(text) -> list[float]`; model loaded once at startup via lifespan; model name from `settings.embedding_model`; optional on-disk cache |
| WP-004 | Wire POST /memory | 4 | H | L | Full implementation: embed text, upsert Agent/Project/Person nodes, create Memory node, create PRODUCED_BY/ABOUT edges, auto RELATED_TO via vector search if `related_ids` not provided |
| WP-005 | Wire POST /memory/search | 4 | H | M | Vector search on `Memory.embedding` + tag/agent/project filters + graph expansion up to `max_hops` |
| WP-006 | Wire GET /memory/graph | 4 | M | M | Filtered subgraph export: project/agent/tag/since/until params; returns `{nodes, edges}` |
| WP-007 | memory_client.py + Typer CLI | 5 | H | M | `memory_client.py` wrapping HTTP API; Typer CLI with `add-memory`, `search-memory`, `dump-graph` commands |
| WP-008 | LLMClient abstraction | 7 | M | M | v2+: `LLMClient.ask(system, prompt, model)` wrappers for Claude/OpenAI/Ollama |
| WP-009 | Headless agent framework | 7 | M | L | v2+: `BaseAgent` using `memory_client` + `LLMClient`; scheduled/event-driven tasks |
| WP-010 | Remote/mobile access | 8 | L | XL | v2+: Tailscale/VPS hosting + TLS + API key auth |
| WP-011 | Custom graph-cloud UI | 9 | L | XL | v2+: React + D3.js/vis-network consuming `GET /memory/graph` |
| WP-012 | Pin dependency versions in requirements.txt | 1 | M | S | Use `>=x,<y` bounds for reproducibility; research compatible version matrix |
| WP-013 | Pin Docker image tags (no `latest`) | 1 | M | S | Replace `memgraph/memgraph-mage:latest` + `memgraph/lab:latest` with specific versions once stack stabilises |
| WP-014 | Docker resource limits | 1 | L | S | Add `mem_limit`/`cpus` to docker-compose to prevent runaway resource use |

---

## Completed

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
