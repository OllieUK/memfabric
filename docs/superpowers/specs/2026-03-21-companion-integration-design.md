# Companion Integration Design
**Date:** 2026-03-21
**Status:** Approved
**Work packages:** WP-027, WP-030, WP-031, WP-032, WP-033

---

## 1. Problem statement

The Memory API and CLI exist and are functional (MVP complete). However, the memory fabric has never been used in a real companion session with real memories. There is no defined session lifecycle, no structured way for a companion to orient itself at session start, and no close-out ritual to capture what was learned. The companion has no integration package it can pick up and drop into its environment.

The goal of this design is to close that gap: deliver a working, validated end-to-end companion session loop using Claude Code first, then extend to Claude Desktop and Claude.ai via MCP.

---

## 2. Scope

**In scope (v1 — this design):**
- Extend `memory_client/` into a self-contained companion integration package
- New CLI commands: `memory list-strands`, `memory wake-up`, `memory close-session`
- Companion-facing protocol document (`COMPANION.md`)
- Per-environment wiring guide (`WIRING.md`)
- High-level explanatory doc in `docs/`
- End-to-end validation session with real memories
- MCP server for Claude Desktop / Claude.ai access (after validation)

**Out of scope (v2+):**
- Subject/object schema on nodes (every Memory node having an explicit `subject` and `object` field, rather than implying "the user" as subject — see Section 10)
- Headless/scheduled agent framework
- Remote/mobile access
- Authentication beyond `AGENT_ID`

**Language convention (applies immediately):**
All strand descriptions, memory content, and companion-facing documentation use **"the user"** as the subject — not "you" (ambiguous when read by an LLM) and not a specific name (non-portable). This applies to all memory content, strand descriptions, and companion instructions throughout this design and going forward.

---

## 3. Package structure

`memory_client/` is extended to be the self-contained companion integration artifact. It can be dropped into any target environment and contains everything needed to go from zero to a working memory-integrated companion.

```
memory_client/
  __init__.py
  config.py          # ClientSettings: API_BASE_URL, AGENT_ID
  client.py          # MemoryClient: synchronous httpx wrapper around REST API
  cli.py             # Typer CLI: all companion-facing commands
  COMPANION.md       # Companion-facing session protocol
  WIRING.md          # Per-environment setup instructions
  requirements.txt
```

**Packaging note:** `pyproject.toml` and `setup.cfg` currently live at the repo root (not inside `memory_client/`), so the editable install targets the repo root. True self-contained packaging — where `memory_client/` ships its own `pyproject.toml` and can be installed independently — is a v2 item. For now, WIRING.md documents the repo-root install path.

Additionally, `docs/companion-integration.md` lives in this repo as a high-level explanatory overview. It describes the purpose of the package, what it enables, and points to `COMPANION.md` and `WIRING.md` for details. It is not shipped with the package.

---

## 4. New CLI commands

### 4.1 `memory list-strands` (WP-027)

Lists all Strand nodes from the DB: ID, name, category, description. Output is formatted for human and companion readability (table or structured list, not raw JSON).

**Strand description language:** All strand descriptions must use "the user" as subject. Example: *"The user's physical and mental health, energy levels, and wellbeing practices."* — not "your health" and not a specific name. This makes the data unambiguous when read by an LLM acting as companion.

Adds `GET /strands` to the API and `memory list-strands` to the CLI.

**Dependency note:** WP-032 (end-to-end validation) uses the current single-`text` `memory add-memory` command. WP-028 (causal graph) will replace `text` with `fact` + `so_what` and requires a corresponding CLI update to `add-memory`. The session protocol validated in WP-032 will need a follow-up update after WP-028 lands. This is expected and does not block WP-032.

### 4.2 `memory wake-up [--topic "..."] [--limit N]` (WP-030)

Produces a structured context briefing for session start. Runs two searches:

1. **Primary memories** — top N memories ordered by importance descending then recency. Default N: 20. Configurable via `--limit N`. No static importance threshold — the limit is the tuning knob, so the briefing stays manageable as the memory fabric grows.
2. **Topic-relevant memories** — semantic search on the `--topic` string (if provided), pulling the top 10 most relevant results.

Output format:

```
## Memory briefing — [topic | "general session"]

### Core context
[primary memories, grouped by strand, up to --limit total]

### Relevant to today
[topic-search results — this section is omitted entirely if --topic is not provided]
```

The companion reads this briefing at session start before doing anything else.

### 4.3 `memory close-session` (WP-030)

Outputs a structured scaffold the companion uses to review the session and decide what to store. The command prints the scaffold and exits — the companion decides what to store and issues `memory add-memory` calls accordingly.

**Scaffold content:**

```
## Session close-out

Review this session and answer the following before ending:

1. What decisions were made? (store as type: decision)
   → memory add-memory --text "..." --type decision --strand <strand-id>

2. What was learned or observed about the user? (store as type: insight or observation)
   → memory add-memory --text "..." --type insight --strand <strand-id>

3. What actions were committed to? (store as type: todo)
   → memory add-memory --text "..." --type todo --strand <strand-id>

4. What context should a future session know that isn't already in the fabric?
   → memory add-memory --text "..." --type fact --strand <strand-id>

Run `memory list-strands` if strand IDs are uncertain.
Do not end the session without running at least one `memory add-memory` if any of the above apply.
```

> **Note:** The `--text` flag is the current CLI interface. After WP-028 lands, `--text` becomes `--fact` (with optional `--so-what`). The scaffold will be updated at that point.

---

## 5. COMPANION.md

The companion-facing session protocol. Lives inside `memory_client/` and is shipped with the package. Written as instructions for the companion.

---

### Wake-up

At the start of every session, run:

```
memory wake-up --topic "<brief description of today's focus>"
```

Read the briefing in full before responding to the user. This is how the companion orients itself: it knows who the user is, what matters to them, and what is relevant today. Do not respond until the briefing has been read.

For a general session with no specific topic, run `memory wake-up` without `--topic`.

---

### In-session

**Search before proposing.** When about to make a recommendation, recall a fact about the user, or suggest an approach — run `memory search-memory` first to check whether the fabric already holds relevant context. Do not propose something the user has already decided, or repeat a fact the fabric already knows.

**Add memories as they arise.** Do not batch memory writes to the end of the session. When something new and durable is established — a decision, insight, observation, or todo — add it immediately with:

```
memory add-memory --text "<statement>" --type <type> --strand <strand-id>
```

A memory is worth storing if it would be useful to a future companion session that has no knowledge of this conversation.

**Use "the user" as subject in all memory content.** Write facts as: *"The user prefers structured planning over open-ended brainstorming."* — not "you prefer" and not a specific name. This keeps memories portable and unambiguous.

**Assign strand IDs correctly.** Every memory must have at least one primary strand. Run `memory list-strands` if strand IDs are uncertain.

---

### Close-out

Before ending the session, run:

```
memory close-session
```

Use the scaffold it outputs to review the session. Store anything that wasn't captured inline. Do not end the session without completing close-out, even if the session was brief.

---

## 6. WIRING.md

Per-environment setup instructions. Lives inside `memory_client/`. Three sections:

### Claude Code (WP-031 — delivered now)

Prerequisites: Memory API service running (`uvicorn memory_service.main:app`), Memgraph running, strands seeded (`python scripts/seed_strands.py`).

1. Install the package from the repo root:
   ```
   pip install -e /path/to/graph-memory-fabric/
   ```

2. Add to the companion project's `.env`:
   ```
   API_BASE_URL=http://localhost:8000
   AGENT_ID=claude-code
   ```

3. Copy `COMPANION.md` from the `memory_client/` source directory into the companion project root:
   ```
   cp /path/to/graph-memory-fabric/memory_client/COMPANION.md /path/to/companion-project/
   ```

4. Add to the companion project's `CLAUDE.md`:
   ```
   ## Memory fabric
   This project has access to a persistent memory fabric via the `memory` CLI.
   Read and follow `COMPANION.md` (in this project root) at the start of every session.
   ```

5. Verify: `memory list-strands` — should return all 20 strands.

### Claude Desktop (WP-033 — placeholder)

*To be completed when WP-033 (MCP server) lands. Claude Desktop integration uses the MCP server.*

### Claude.ai / MCP (WP-033 — placeholder)

*To be completed when WP-033 (MCP server) lands.*

---

## 7. End-to-end validation (WP-032)

A real companion session is run from wake-up to close-out with real memories in the DB. Validation criteria:

- [ ] `memory wake-up` returns a non-empty briefing with at least one memory grouped by strand
- [ ] At least one memory from the briefing is directly referenced or used during the session
- [ ] At least one new memory is added during the session using a strand ID retrieved from `memory list-strands` (validates the discovery workflow end-to-end)
- [ ] `memory close-session` scaffold is used and produces at least one `memory add-memory` call
- [ ] The memory added at close-out appears in the next `memory wake-up` briefing

Findings (what worked, what was awkward, what's missing) are documented and fed back into the backlog before WP-028 begins.

---

## 8. MCP server (WP-033)

After WP-032 validates the CLI-based loop, an MCP server wraps the same REST API for Claude Desktop and Claude.ai access.

**Exposed tools:**

| Tool | Maps to | Return value |
|------|---------|-------------|
| `memory_add` | `POST /memory` | Created memory ID and confirmation |
| `memory_search` | `POST /memory/search` | List of matching memories as structured data |
| `memory_wake_up` | Wake-up briefing logic | Briefing text as a single string (same format as CLI output) |
| `memory_list_strands` | `GET /strands` | List of strands as structured data |
| `memory_close_session` | Close-out scaffold | Scaffold text as a single string (same content as CLI output — the companion issues `memory_add` calls from there) |

Note: `memory_close_session` as an MCP tool returns the scaffold text as a structured string response, not a side effect — the companion reads it and decides what to store via subsequent `memory_add` calls.

`WIRING.md` Claude Desktop and MCP sections are completed at this point. `COMPANION.md` is updated to reference MCP tools as the preferred integration path when available, with CLI as fallback.

---

## 9. Revised backlog order

| Position | WP | Title | Rationale |
|----------|----|-------|-----------|
| 1 | WP-027 | `memory list-strands` | Immediately actionable; strand visibility needed for all memory ingestion |
| 2 | WP-030 | `memory wake-up` + `memory close-session` | CLI commands the protocol depends on |
| 3 | WP-031 | Companion package: COMPANION.md + WIRING.md + docs/companion-integration.md | Protocol + wiring; no code, only docs |
| 4 | WP-032 | End-to-end companion validation | Prove the loop works before building on it |
| 5 | WP-028 | Causal graph: `fact`/`so_what` + `LEADS_TO` | Enriches what companion can work with; CLI updated to `fact`/`so_what` at this point |
| 6 | WP-029 | Memory + edge reinforcement | Self-organising graph |
| 7 | WP-006 | `GET /memory/graph` | After schema is final |
| 8 | WP-033 | MCP server + Claude Desktop wiring | Extends validated loop to Claude Desktop / Claude.ai |
| 9+ | Tech debt | WP-012, 013, 014, 017, 019–026 | As before |

---

## 10. Future: subject/object schema (v2+)

Currently all memory nodes imply "the user" as the subject. A future work package will add explicit `subject` and `object` fields to Memory nodes, making the schema portable across multiple users and enabling memories about third parties (e.g., "the user's manager said X"). This is out of scope for v1 but should be kept in mind when designing memory ingestion APIs — avoid hard-coding assumptions about subject that would be expensive to undo.

Additionally, the current packaging setup (`pyproject.toml` at repo root) means `memory_client/` cannot be installed independently. A future work package should give `memory_client/` its own `pyproject.toml` so it can be distributed and installed without the full repo.
