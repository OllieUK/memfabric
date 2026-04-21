# Graph-Memory Fabric – Operating Instructions

## Project purpose

Build a local-first memory service that represents all "memories" as graph nodes with vector embeddings, exposes a simple HTTP API for multiple independent agents, and provides a live graph-cloud visualisation via Memgraph Lab. In v1 the only LLM is Claude Code (this session); the runtime stack has no dependency on external LLM APIs. All embeddings are generated locally via `sentence-transformers`.

## Architecture (v1)

```
[Claude Code / IDE session]
        |
        v
[Memory API Service]  ←  FastAPI + sentence-transformers (local embeddings)
        |                 Built-in scheduler: short-rest every 6h,
        |                 long-rest daily at 03:00 UTC (ASAP if missed)
        v
[Memgraph]            ←  Graph DB + vector index + MAGE procedures
        |
        v
[Memgraph Lab UI]     ←  http://localhost:3000 (graph-cloud visualisation)
```

No server-side LLM calls. No external API dependencies.

## Built-in maintenance scheduler

The service runs its own asyncio scheduler — no external cron or systemd timers required.

| Operation | Default schedule | "ASAP if missed" |
|-----------|-----------------|-----------------|
| short-rest | every 6h (`SHORT_REST_INTERVAL_HOURS`) | yes — runs on next poll if overdue |
| long-rest | 03:00 UTC (`LONG_REST_UTC_HOUR`) | yes — runs on startup if ≥27h elapsed |

Key settings (all in `.env`):

| Setting | Default | Purpose |
|---------|---------|---------|
| `SCHEDULER_ENABLED` | `true` | Set `false` to use external systemd timers instead |
| `SCHEDULER_POLL_INTERVAL_SECONDS` | `300` | How often the scheduler checks (5 min) |
| `SHORT_REST_INTERVAL_HOURS` | `6` | Short-rest cadence |
| `LONG_REST_UTC_HOUR` | `3` | Wall-clock hour for long-rest (UTC) |
| `LONG_REST_MIN_INTERVAL_HOURS` | `20` | Minimum gap — prevents double-run |
| `LONG_REST_OVERDUE_HOURS` | `27` | Run ASAP threshold (missed window) |

The scheduler runs `memory_repo.long_rest` and `memory_repo.short_rest` directly in-process (not via HTTP). Log output goes to the service logger (`memory_service.scheduler`).

## Memory operating model

The shared Mara baseline now owns session wake-up, continuous memory checks, and close-down capture. Do not reintroduce repo-local SessionStart or PostToolUse memory hooks here unless the baseline proves insufficient and the change is explicitly approved.

For work inside this repo:

1. Treat the Graph Memory Fabric as part of the operating environment, not an optional add-on.
2. Refresh the working set with memory search when the topic shifts or when implementation risk depends on prior project decisions.
3. Store durable facts, decisions, insights, and todos as they arise rather than waiting until session end.
4. Use `memory_client/COMPANION.md` as project reference material when you need the client-side operating contract, not as a duplicate startup ritual.

## Working norms

### Before touching any code
Run an **Explore agent** to read the relevant files first. Never propose changes to code you haven't read.

### Before each work package
1. Run a **Plan agent** to validate the approach, identify reusable utilities, and consider alternatives. Capture the plan as a plan file.
2. Run `engineering:testing-strategy` to produce a test plan for the WP — specifying which tests are unit, which are integration (live stack), and what the acceptance criteria are. Attach the test plan to the plan file. **This step is mandatory and must happen before writing any code.**

### After completing each work package
1. Run `/simplify` to review the changed code for reuse, quality, and efficiency. Act on findings immediately if high-value / low-effort; otherwise add to BACKLOG.md with priority.
2. Run `engineering:deploy-checklist` for the WP to confirm all verification gates are met before marking Done.

### Bash commands
Never chain shell commands with `&&`, `;`, or `|` unless the pipeline is the natural form of the command (e.g. `grep ... | sort`). Run each logical step as a separate `Bash` call. Chained commands (e.g. `cd ~/projects && git push`) trigger unnecessary safety prompts.

### Git commits
Always create commits from **Git Bash on Windows** (or PowerShell with git), not from inside WSL. The global git config sets `gpg.ssh.program` to `op-ssh-sign.exe` (a Windows PE binary). When WSL tries to execute it, the shell sees the `MZ` magic bytes and fails with `MZ: not found`. Git Bash runs it as a native Windows process and signing works correctly.

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

## Architecture decisions

Architectural decisions are recorded in `docs/architecture/` as ADRs. Consult these before implementing work packages that touch architectural boundaries.

| ADR | Decision | Review triggers |
|-----|----------|-----------------|
| [ADR-001](docs/architecture/ADR-001-knowledge-layer-placement.md) | InfoSec knowledge layer lives inside this project as a feature-flagged peer module with separate embedding config and a bridge module for cross-layer edges | Multi-user requirement, knowledge code >50% of total, non-InfoSec domain requested, cross-layer edges >10k |
| [ADR-002](docs/architecture/ADR-002-knowledge-layer-graph-model.md) | Knowledge layer graph model: control tree as spine, norm trees, precepts as convergence layer, frameworks (structural) vs norms (prescriptive), threat intelligence with JEOPARDISES→Precept→BusinessAttribute strategic path, metric-based fulfilment, org-scoping on edges, temporal norm lifecycle | Metric schemas need dedicated nodes, CONTAINS overload causes ambiguity, non-SABSA framework adopted, CMDB integration needed, Norm/Framework distinction untenable |

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

**Nodes:** `Memory`, `Strand`, `Agent`, `Person`, `Project`, `Task`

**Edges:**
- `RELATED_TO` (Memory→Memory): semantic/associative similarity (auto-linked by vector search); properties: `weight float`
- `LEADS_TO` (Memory→Memory): explicit causal edge — this fact produces or enables that consequence; directional, asymmetric; enables upstream ("why?") and downstream ("what does this affect?") traversal
- `PRODUCED_BY` (Memory→Agent): which agent created this memory
- `ABOUT` (Memory→Person|Project): contextual association
- `IN_STRAND` (Memory→Strand): strand membership; properties: `weight float` (primary=1.0, secondary=0.5–0.9)
- `OWNED_BY` (Task→Agent): which agent owns this task
- `FOR_PROJECT` (Task→Project): project this task belongs to
- `RELATES_TO` (Task→Memory): optional context link from task to memory/knowledge nodes
- `BLOCKS` (Task→Task): this task blocks that one
- `DEPENDS_ON` (Task→Task): this task depends on that one
- `INSTANCE_OF` (Task→Task): child instance of a recurring parent; properties: `instance_seq int`

**Key Memory properties:** `id` (UUID), `fact` (raw statement), `so_what` (impact/meaning, optional), `text` (derived: fact+so_what, used for embedding), `type` (fact/decision/insight/todo/event/observation), `tags[]`, `created_at`, `last_used_at`, `importance` (1–5), `strength` (0–1, reinforcement level, decays via Ebbinghaus curve), `recall_count`, `reinforcement_count`, `last_reinforced_at`, `decay_rate`, `embedding` (vector)

**Key edge reinforcement properties** (on `RELATED_TO` and `LEADS_TO`): `weight` (0–1, Hebbian activation strength), `activation_count`, `last_activated_at`, `decay_rate`

**Key Strand properties:** `id` (kebab-case string e.g. `strand-core-health`), `name`, `description`, `category` (Core Life Domains / Companion Domain / Shadow Domain)

**Key Agent properties:** `id` (string, from AGENT_ID env var), `name`

**Key Task properties:** `id` (UUID), `title`, `description`, `status` (open|active|blocked|done|abandoned), `value` (H|M|L), `effort` (H|M|L), `priority_score` (computed: value_num/effort_num; H=3,M=2,L=1), `urgency` (0–5 float), `due_at`, `snooze_until`, `created_at`, `updated_at`, `committed_at` (accountability clock start — staleness signal when `updated_at = created_at`), `committed_by` (agent_id), `last_checked_at`, `source_ref` (qualified: `{project-slug}:WP-NNN`), `recurrence`, `is_template` (bool, template parents excluded from work queue)

**Key Project properties (extended):** `id`, `name`, `description`, `slug` (short alias for source_ref namespace, e.g. `gmf`), `weight` (float, default 1.0, cross-project priority multiplier — `GET /task/next` sorts by `priority_score × weight DESC`)

## Security posture

Proceed/Report/Confirm/Refuse tiers; 4-question check; R1 untrusted-input rule. Crown jewels: `.env` deny; `.claude/settings*.json`, `.mcp.json`, `docker-compose.yml`, `CLAUDE.md`, `BACKLOG.md`, `data/frameworks/**`, `data/threats/**`, `scripts/{seed_strands,dump_db,restore_db,init_schema,init_knowledge_schema}.py` ask; `seed_strands.py` deny exec. See `docs/security/`.
