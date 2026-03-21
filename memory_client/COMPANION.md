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

### Adding memories

Use `memory add-memory` whenever you learn something worth retaining:

```bash
memory add-memory --text "..." --type <type> --strand-id <strand-id>
```

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
| 3 | Normal (default) — include when contextually relevant |
| 2 | Low — background context, rarely surfaced |
| 1 | Ephemeral — expected to decay quickly |

### Checking available strands

```bash
memory list-strands
```

Use strand IDs to route memories to the correct area of the fabric. Always use an existing strand ID rather than inventing one.

### Searching for specific memories

```bash
memory search-memory "your query here"
memory search-memory "ADHD coping strategies" --tag strand-core-health --limit 5
```

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
memory wake-up

... session work ...

memory add-memory --text "Oliver decided to defer WP-035 until after WP-032" --type decision --strand-id strand-companion-graph-memory-fabric --importance 4
memory add-memory --text "Oliver prefers short feedback loops and frequent commits" --type insight --strand-id strand-core-health --importance 4

memory close-session
[end]
```

---

## Notes

- `close-session` is local-only — it requires no API connection.
- `wake-up` requires the memory service to be running (`docker compose up -d`).
- `AGENT_ID` in `.env` identifies which agent produced each memory. Default: `claude-code`.
- `API_BASE_URL` in `.env` points to the memory service. Default: `http://localhost:8000`.
