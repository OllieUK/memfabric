# Companion Integration Overview

How a companion agent connects to the Graph Memory Fabric to maintain persistent memory across sessions.

---

## What "companion" means

A **companion agent** is any AI assistant (Claude Code, Claude Desktop, or other) that uses the memory fabric to:

1. **Remember context** across independent sessions
2. **Accumulate knowledge** about the user — preferences, decisions, working norms
3. **Share memory** across multiple agent instances (one fabric, many agents)

The fabric is local-first and requires no external LLM API. All embeddings run locally.

---

## How it works

```
[Session start]
  ↓
memory wake-up              → fetch top memories by importance + optional topic search
  ↓
[Companion reads briefing, responds to user]
  ↓
memory add-memory (×N)      → store decisions, insights, todos, facts during session
  ↓
memory close-session        → structured scaffold prompts final memory captures
  ↓
[Session end]
```

Each session begins with a briefing drawn from the graph, and ends with new memories added back. Over time the fabric accumulates a rich, queryable model of the user's context.

---

## Key files

| File | Purpose |
|------|---------|
| `memory_client/COMPANION.md` | Full session protocol — what to run, when, and why |
| `memory_client/WIRING.md` | Environment-specific setup: Claude Code (active), Claude Desktop + MCP (planned) |
| `memory_client/cli.py` | CLI entry point (`memory wake-up`, `memory add-memory`, etc.) |
| `memory_client/client.py` | Python client library (`MemoryClient`) |

---

## Current state (post WP-030)

| Capability | Status |
|-----------|--------|
| `memory wake-up` | Working — importance-ranked + optional topic search |
| `memory add-memory` | Working — stores to graph with strand/tag/importance |
| `memory search-memory` | Working — vector similarity search |
| `memory list-strands` | Working — lists available strands |
| `memory close-session` | Working — local scaffold, no API required |
| MCP server (Claude Desktop) | Planned — WP-033 |
| Remote access | Planned — WP-010 |

---

## Quick-start (Claude Code)

```bash
# 1. Start the stack
docker compose up -d
uvicorn memory_service.main:app --reload

# 2. At session start
python -m memory_client.cli wake-up

# 3. Store a memory
python -m memory_client.cli add-memory \
  --text "Oliver decided to tackle WP-031 before WP-032" \
  --type decision \
  --strand-id strand-companion-graph-memory-fabric \
  --importance 4

# 4. At session end
python -m memory_client.cli close-session
```

See `memory_client/COMPANION.md` for the full protocol and `memory_client/WIRING.md` for wiring details.
