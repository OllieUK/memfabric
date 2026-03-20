# Graph-Memory Fabric – Operating Instructions

## Project purpose

Build a local-first memory service that represents all "memories" as graph nodes with vector embeddings, exposes a simple HTTP API for multiple independent agents, and provides a live graph-cloud visualisation via Memgraph Lab. In v1 the only LLM is Claude Code (this session); the runtime stack has no dependency on external LLM APIs. All embeddings are generated locally via `sentence-transformers`.

## Architecture (v1)

```
[Claude Code / IDE session]
        |
        v
[Memory API Service]  ←  FastAPI + sentence-transformers (local embeddings)
        |
        v
[Memgraph]            ←  Graph DB + vector index + MAGE procedures
        |
        v
[Memgraph Lab UI]     ←  http://localhost:3000 (graph-cloud visualisation)
```

No server-side LLM calls. No external API dependencies.

## Working norms

### Before touching any code
Run an **Explore agent** to read the relevant files first. Never propose changes to code you haven't read.

### Before each work package
Run a **Plan agent** to validate the approach, identify reusable utilities, and consider alternatives. Capture the plan as a plan file.

### After completing each work package
Run `/simplify` to review the changed code for reuse, quality, and efficiency. Act on findings immediately if high-value / low-effort; otherwise add to BACKLOG.md with priority.

### Parallelism
Where a work package has independent sub-tasks, launch **parallel agents** in a single message to reduce wall-clock time.

## Definition of Done (every work package)

**Before starting:** Move the WP to "Currently In Progress" in BACKLOG.md.

1. All DoS checklist items verified — commands run, outputs match expected
2. `/simplify` run; findings acted on or explicitly deferred to BACKLOG.md with ID
3. BACKLOG.md updated: WP moved to Completed, any new items added with priority
4. Retrospective note added to BACKLOG.md (what went well, what to improve)
5. Git commit created: `WP-NNN: <title>`

## Naming conventions

| Concept | Convention |
|---------|-----------|
| Graph node labels | PascalCase: `Memory`, `Agent`, `Person`, `Project` |
| Edge types | SCREAMING_SNAKE: `RELATED_TO`, `DEPENDS_ON`, `PRODUCED_BY`, `ABOUT` |
| Python identifiers | snake_case |
| CLI commands | kebab-case: `add-memory`, `search-memory` |
| Work package IDs | `WP-NNN` (zero-padded three digits) |

## Directory conventions

| Directory | Purpose |
|-----------|---------|
| `memory_service/` | FastAPI application code |
| `tests/` | pytest test suite; one file per work package or feature area |
| `scripts/` | One-off operational scripts (schema init, smoke tests, migrations); never called by the running service |
| `docs/` | Project brief, design specs, workflow patterns |

All scripts in `scripts/` read config from `.env` via `pydantic-settings`. Never hardcode hosts or ports in scripts.

## Configuration

All tuneable values live in `.env` / `pydantic-settings`. Never hardcode hosts, ports, credentials, or model names in source files. Reference `.env.example` for the full list of supported variables.

## API design decisions

| Decision | Rationale |
|----------|-----------|
| `POST /memory/search` (not `GET`) | Search takes a structured body (query text, list filters, pagination). GET query strings handle lists poorly and have length limits; POST body is cleaner and more extensible. |
| `GET /memory/graph` | Graph export is a simple filtered read with scalar params; GET with query params is appropriate here. |

## Key constraints (v1)

- No external LLM API calls inside any running service
- All embeddings generated locally (`sentence-transformers`, model from `EMBEDDING_MODEL` env var)
- Python driver for Memgraph: `neo4j` (Bolt-compatible, no native build step)
- Target environment: WSL2 (Ubuntu 22.04) + Docker Desktop

## Data model quick-reference

**Nodes:** `Memory`, `Strand`, `Agent`, `Person`, `Project`

**Edges:**
- `RELATED_TO` (Memory→Memory): semantic/temporal/causal similarity; properties: `weight float`
- `PRODUCED_BY` (Memory→Agent): which agent created this memory
- `ABOUT` (Memory→Person|Project): contextual association
- `IN_STRAND` (Memory→Strand): strand membership; properties: `weight float` (default 1.0)

**Key Memory properties:** `id` (UUID), `text`, `type` (fact/decision/insight/todo/event/observation), `tags[]`, `created_at`, `last_used_at`, `importance` (1–5), `embedding` (vector)

**Key Strand properties:** `id` (UUID), `name`, `description`, `category` (life/companion/shadow)

**Key Agent properties:** `id` (string, from AGENT_ID env var), `name`
