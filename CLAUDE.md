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

## Session startup

Before responding substantively in any new companion or user session:

1. Read `memory_client/COMPANION.md`.
2. Run `memory wake-up` or the MCP equivalent `memory_wake_up`.
3. Treat the wake-up briefing as baseline context, then refresh the working set with memory search when the topic shifts.
4. Store durable facts, decisions, insights, and todos as they arise rather than waiting until session end.
5. Use `memory close-session` or the MCP equivalent `memory_close_session` before ending the session to review what should persist.

The Graph Memory Fabric is part of the operating environment, not an optional add-on. Use it proactively and quietly so continuity does not depend on the user having to remind you.

## Working norms

### Before touching any code
Run an **Explore agent** to read the relevant files first. Never propose changes to code you haven't read.

### Before each work package
1. Run a **Plan agent** to validate the approach, identify reusable utilities, and consider alternatives. Capture the plan as a plan file.
2. Run `engineering:testing-strategy` to produce a test plan for the WP — specifying which tests are unit, which are integration (live stack), and what the acceptance criteria are. Attach the test plan to the plan file. **This step is mandatory and must happen before writing any code.**

### After completing each work package
1. Run `/simplify` to review the changed code for reuse, quality, and efficiency. Act on findings immediately if high-value / low-effort; otherwise add to BACKLOG.md with priority.
2. Run `engineering:deploy-checklist` for the WP to confirm all verification gates are met before marking Done.

### Parallelism
Where a work package has independent sub-tasks, launch **parallel agents** in a single message to reduce wall-clock time.

## Definition of Done (every work package)

**Before starting:** Move the WP to "Currently In Progress" in BACKLOG.md.

1. Test plan produced (`engineering:testing-strategy`) and attached to the plan file — unit tests, integration tests against live Memgraph + running FastAPI service, and acceptance criteria all specified upfront
2. All unit tests written and passing (`pytest`)
3. All integration tests written and run against the **live stack** (Memgraph + FastAPI service must be running) — not mocked
4. Acceptance criteria verified manually or via smoke test script against the live service
5. `/simplify` run; findings acted on or explicitly deferred to BACKLOG.md with ID
6. `engineering:deploy-checklist` completed — all gates green
7. BACKLOG.md updated: WP moved to Completed, any new items added with priority
8. Retrospective note added to BACKLOG.md (what went well, what to improve)
9. Git commit created: `WP-NNN: <title>`

> **Rule:** Never claim a WP is Done if integration tests have not been run against the live stack. "Tests written" ≠ "tests run". Evidence before assertions.

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

## Memgraph Cypher gotchas

- `DETACH DELETE` does not support a `RETURN` clause — count nodes before deleting, not after
- Strand linking uses `MATCH` (not `MERGE`): strand nodes must be pre-seeded via `seed_strands.py`; unknown `strand_ids` are silently skipped
- Integration tests in `TestGetStrandsIntegration` skip via the `test_driver` fixture (not `@pytest.mark.integration`); new integration tests should add the mark explicitly for `-m integration` filtering
- `test_core_wake_up_prefers_stronger_reinforced_memory` is a known pre-existing flaky test — not a regression indicator
- The patch endpoint function is `update_memory` in `memory_repo.py` (not `patch_memory`)

## Data model quick-reference

**Nodes:** `Memory`, `Strand`, `Agent`, `Person`, `Project`

**Edges:**
- `RELATED_TO` (Memory→Memory): semantic/associative similarity (auto-linked by vector search); properties: `weight float`
- `LEADS_TO` (Memory→Memory): explicit causal edge — this fact produces or enables that consequence; directional, asymmetric; enables upstream ("why?") and downstream ("what does this affect?") traversal
- `PRODUCED_BY` (Memory→Agent): which agent created this memory
- `ABOUT` (Memory→Person|Project): contextual association
- `IN_STRAND` (Memory→Strand): strand membership; properties: `weight float` (primary=1.0, secondary=0.5–0.9)

**Key Memory properties:** `id` (UUID), `fact` (raw statement), `so_what` (impact/meaning, optional), `text` (derived: fact+so_what, used for embedding), `type` (fact/decision/insight/todo/event/observation), `tags[]`, `created_at`, `last_used_at`, `importance` (1–5), `strength` (0–1, reinforcement level, decays via Ebbinghaus curve), `recall_count`, `reinforcement_count`, `last_reinforced_at`, `decay_rate`, `embedding` (vector)

**Key edge reinforcement properties** (on `RELATED_TO` and `LEADS_TO`): `weight` (0–1, Hebbian activation strength), `activation_count`, `last_activated_at`, `decay_rate`

**Key Strand properties:** `id` (kebab-case string e.g. `strand-core-health`), `name`, `description`, `category` (Core Life Domains / Companion Domain / Shadow Domain)

**Key Agent properties:** `id` (string, from AGENT_ID env var), `name`
