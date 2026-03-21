# Companion Session Protocol

This document defines how a companion agent (Claude Code or other) should open and close a session using the Graph Memory Fabric.

---

## Session start — `memory wake-up`

At the beginning of every session, run:

```bash
memory wake-up
```

Optional flags:

| Flag | Purpose |
|------|---------|
| `--topic "..."` | Focus the briefing on a specific topic (runs semantic search + merges with importance-ranked results) |
| `--limit N` | Cap total memories returned (default 20) |

**Examples:**

```bash
memory wake-up
memory wake-up --topic "health and ADHD management"
memory wake-up --topic "coding project graph-memory-fabric" --limit 30
```

The output is a structured briefing grouped by strand. Read it fully before responding to the user's first message. It establishes:

- Active decisions that constrain what you can suggest
- Known preferences and working norms
- Outstanding todos that may be relevant
- Contextual facts about the user, project, and relationships

---

## During the session

### Search before proposing

Before making a recommendation, recalling a fact, or suggesting an approach, check whether the fabric already holds relevant context:

```bash
memory search-memory "your query" [--tag strand-id] [--limit N]
```

Do not propose something the user has already decided, or repeat a fact the fabric already knows.

### Add memories as they arise

Do not batch memory writes to the end of the session. When something new and durable is established — a decision, insight, observation, or todo — add it immediately:

```bash
memory add-memory --text "..." --type <type> --strand-id <strand-id> [--importance 1-5]
```

A memory is worth storing if it would be useful to a future session that has no knowledge of this conversation.

**Types:**

| Type | When to use |
|------|-------------|
| `fact` | Stable, verifiable information about the user, project, or world |
| `decision` | A choice made that constrains future actions |
| `insight` | An observation about patterns, preferences, or behaviour |
| `observation` | A single data point — less certain than an insight |
| `todo` | A committed action not yet done |
| `event` | Something that happened (timestamped occurrence) |

**Importance:**

| Value | Meaning |
|-------|---------|
| 5 | Critical — always include in wake-up |
| 4 | High — include when relevant strand is active |
| 3 | Normal (default) |
| 2 | Low — background context, rarely surfaced |
| 1 | Ephemeral — expected to decay quickly |

Run `memory list-strands` if strand IDs are uncertain. Always use an existing strand ID — never invent one.

### Wording convention

Write all memory content with "the user" as subject: *"The user prefers short feedback loops over long planning phases."* — not "you prefer" (ambiguous when read by an LLM) and not a specific name (non-portable).

---

## Session close — `memory close-session`

At the end of every session, run:

```bash
memory close-session
```

This prints a structured scaffold with four questions. Work through each question and add the relevant memories before ending the session:

1. **Decisions made** → `--type decision`
2. **Learned or observed about the user** → `--type insight` or `--type observation`
3. **Actions committed to** → `--type todo`
4. **Context a future session should know** → `--type fact`

Do not end the session without running at least one `memory add-memory` if any of the above apply.

---

## Minimal session pattern

```
[session start]
memory wake-up [--topic "..."]

... session work ...

# store durables as they arise
memory add-memory --text "The user decided to ..." --type decision --strand-id <strand-id> --importance 4
memory add-memory --text "The user prefers ..." --type insight --strand-id <strand-id> --importance 3

# review and close
memory close-session
[end]
```

---

## Notes

- `close-session` is local-only — it requires no API connection.
- `wake-up` requires the memory service to be running (`docker compose up -d`).
- `AGENT_ID` in `.env` identifies which agent produced each memory. Default: `claude-code`.
- `API_BASE_URL` in `.env` points to the memory service. Default: `http://localhost:8000`.
