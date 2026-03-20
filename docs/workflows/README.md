# Memory Workflow Patterns

Repeatable prompt patterns for using the Graph-Memory Fabric CLI from an IDE session (Claude Code or similar).

---

## How to invoke a workflow

Paste a trigger prompt into your Claude Code session citing the relevant file:

```
Read docs/workflows/<name>.md and follow the workflow.
Context: <brief description of what you're working on>.
```

Claude Code will read the file and execute the steps autonomously, pausing at explicit approval gates.

---

## Workflows

| File | Purpose | When to use |
|------|---------|-------------|
| [contextual-recall.md](contextual-recall.md) | Retrieve relevant past memories before starting a task | Beginning of any session; picking up work after a gap |
| [summarise-session.md](summarise-session.md) | Convert session notes into structured Memory records | End of a coding session; after a design conversation |
| [propose-todos.md](propose-todos.md) | Surface action items from past memories | Planning a feature; weekly review |
| [refine-edges.md](refine-edges.md) | Identify and add missing RELATED_TO links | After batch ingestion; before a Memgraph Lab session |
| [strand-maintenance.md](strand-maintenance.md) | Assign memories to thematic Strands | After 20+ memories accumulated; before graph visualisation |

---

## Prerequisites

- Memory service running: `uvicorn memory_service.main:app --reload`
- `.env` configured (see `.env.example`)
- CLI installed: `pip install -e .` or run via `python -m memory_client.cli`
- Memgraph running: `docker compose up -d`

---

## MemoryType reference

| Type | Use when |
|------|----------|
| `fact` | Objective, stable information (a library exists, a constraint applies) |
| `decision` | A choice made with rationale (chose X over Y because Z) |
| `insight` | A realisation or non-obvious understanding |
| `todo` | An action that still needs to be taken |
| `event` | Something that happened at a point in time |
| `observation` | An empirical note from direct experience (tests passed, latency measured) |

---

## CLI quick reference

```bash
memory add-memory "TEXT" --type TYPE [--tag TAG ...] [--importance 1-5] \
  [--project-id ID] [--person-id ID ...] [--strand-id ID ...] [--related-id ID ...]

memory search-memory "QUERY" [--tag TAG ...] [--agent-id ID] [--project-id ID] \
  [--limit 1-100] [--max-hops 0-3]

memory dump-graph [--project-id ID] [--agent-id ID] [--tag TAG]   # requires WP-006
```

For a full list of options and sub-commands: `memory --help` or `memory COMMAND --help`.
