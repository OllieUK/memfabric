> **MCP integration (preferred):** When running in a Claude Desktop or MCP-enabled Claude Code session, use the MCP tools directly:
> `memory_wake_up`, `memory_add`, `memory_search`, `memory_list_strands`, `memory_close_session`
>
> These are the preferred path — lower latency, structured returns, no shell subprocess.
> The CLI commands documented below remain valid as a fallback for CLI-only environments.

---

# Memory Model

Before following the session protocol, understand the three tiers of memory you are operating across. Each tier has a different scope, lifespan, and purpose.

## Tier 1 — Context window (in-session, managed by the LLM runtime)

Your active context window is your working memory. Everything currently visible to you — the conversation history, the system prompt, wake-up output, search results — lives here. It is fast, rich, and immediately accessible.

**Key properties:**
- Exists only for the duration of the current session
- Has a fixed capacity; older content scrolls out of reach as the session grows
- You cannot persist anything here — when the session ends, it is gone
- You do not need to "manage" it explicitly; the runtime handles it

**What belongs here:** The current conversation, retrieved memories (from wake-up and search), working hypotheses, in-progress reasoning, and anything that is only relevant to this session's immediate task.

## Tier 2 — Session working set (in-session, curated by you)

Within a session, not everything in the context window is equally important. The working set is the subset of retrieved memories and in-session observations that you are actively using to guide your responses. You manage this implicitly through what you attend to and how you weight it.

**Key properties:**
- Derived from Tier 1 — it is a cognitive selection, not a separate store
- Grows as you search and retrieve memories mid-session
- Should be refreshed (via `memory search`) when the conversation topic shifts significantly
- In-session facts (things the user tells you now) live here until the session ends

**What belongs here:** Retrieved fabric memories relevant to the current topic, user corrections or new facts stated this session, context that shapes your immediate recommendations.

**Critical:** Do not confuse recency with importance. A memory surfaced by wake-up this morning and never referenced again carries less weight than a memory the user just explicitly confirmed. Your working set should reflect active relevance, not arrival order.

## Tier 3 — The fabric (persistent, managed by the memory service)

The Graph Memory Fabric (Memgraph) is your long-term memory. It persists across all sessions, accumulates over time, and is the only tier that survives when the context window closes.

**Key properties:**
- Persists indefinitely; decays gradually via the reinforcement model (see below)
- Organised as a graph: Memory nodes connected by typed edges (`RELATED_TO`, `LEADS_TO`, `ABOUT`, `IN_STRAND`)
- Retrieved via semantic vector search and graph traversal, not exact lookup
- Strengthened by use (recall increments), weakened by disuse (decay), reinforced by explicit signal
- **Wake-up does not strengthen memories** — it is passive priming, not recall. Only search and explicit reinforce produce strength signals.

**What belongs here:** Durable facts, decisions, insights, and todos that would be useful to a future session with no knowledge of this conversation.

---

## The orchestration model

The three tiers form a pipeline in both directions:

### Inward (fabric → context): loading

1. **Session start:** `wake-up` loads the highest-importance, most-recently-reinforced memories into Tier 1. This is your baseline context.
2. **Mid-session:** `search` retrieves semantically relevant memories as the conversation evolves. Add retrieved memories to your active working set (Tier 2) when they are relevant to the current topic.
3. **Eviction:** As the context window fills, older retrieved memories scroll out of reach. This is normal. Re-search if you need something you can no longer see.

### Outward (context → fabric): persistence

1. **As they arise:** When a durable fact, decision, or insight is established, write it to the fabric immediately via `memory add`. Do not defer to session end — mid-session writes ensure nothing is lost if the session is interrupted.
2. **At session close:** `close-session` scaffolds a review of what happened. Add anything durable that was not already written.
3. **Reinforce selectively:** After close-session, explicitly reinforce memories that genuinely shaped the session's decisions. These are the memories that should decay slowest. Do not reinforce everything — the signal has value only if it is selective.

### What not to persist

Not everything in Tier 1 or Tier 2 belongs in the fabric. Do not store:
- Intermediate reasoning steps or working hypotheses that were superseded
- Information the user stated this session but did not confirm as durable ("I'm thinking about X" is not a decision)
- Ephemeral session logistics ("let's come back to that" — unless it becomes a committed todo)
- Duplicates of things already in the fabric (search before writing)

The test: *would a future session with no knowledge of this conversation benefit from knowing this?* If yes, store it. If it only makes sense in the current context, let it stay in Tier 1 and expire.

---

## Reinforcement and decay — what this means for you

The fabric is not an inert store. Memories have `strength` (0–1) that decays over time and grows with use:

- **Search hits** automatically increment strength (background task, no action needed from you)
- **Explicit reinforce** (`memory reinforce-memory`) applies a stronger signal — use this for memories that genuinely drove a decision or insight this session
- **Decay** runs periodically (nightly Long Rest, end-of-session Short Rest when WP-040 is implemented) — unused memories gradually fade

**Implication for you:** You do not need to manage decay or strength directly. But you should call explicit reinforce at close-session for the 2–4 memories most central to what happened. Over time this shapes the fabric toward what is actually useful, not just what was stored most recently.

---

# Companion Session Protocol

This document defines how a companion agent (Claude Code or other) should open and close a session using the Graph Memory Fabric.

---

## Session start — `memory wake-up`

At the beginning of every session, run a wake-up **before responding to the user's first message**. Do not send a generic greeting or ask a clarifying question first — the wake-up briefing is what tells you what context you are walking into.

Recommended default for Mara-on workspaces: run a plain `memory wake-up`. The client/service resolve the structured startup profile in code so the call surface stays simple.

```bash
memory wake-up
```

This returns four startup sections:

- Global Mara baseline
- Global user baseline
- Project Mara persona
- Project baseline

Identity resolution should come from scope-local startup config:

- global: `~/.claude/startup.json`
- project: `<repo>/.claude/startup.json`

Those files should declare the global companion identity, the global user identity, the project identity, and the project persona. The caller should not need to pass those explicitly during normal startup.

Optional topic refinement can still be layered onto the same call when the first prompt already has a clear focus:

```bash
memory wake-up --topic "authentication bug triage"
```

Use a plain general wake-up only for legacy callers or when the workspace does not have the structured identities available yet:

```bash
memory wake-up
```

Optional flags:

| Flag | Purpose |
|------|---------|
| `--topic "..."` | Focus the briefing on a specific topic (runs semantic search + merges with importance-ranked results) |
| `--limit N` | Cap total memories returned (default 20) |
| `--scope-profile ...` | Optional override/debug control for the startup profile |
| `--global-agent-id ...` | Optional override/debug control for the global Mara baseline id |
| `--project-agent-id ...` | Optional override/debug control for the project persona id |
| `--project-id ...` | Optional override/debug control for the project baseline id |
| `--person-id ...` | Optional override/debug control for the conversant `Person` id |

**Examples:**

```bash
memory wake-up
memory wake-up --limit 10
memory wake-up --topic "health and ADHD management"
memory wake-up
memory wake-up --topic "coding project graph-memory-fabric"
```

> **Note — `### Relevant to today` suppression:** On small or sparse graphs (roughly fewer than 50 memories, or any brand-new installation), the `### Relevant to today` section is omitted entirely from wake-up output. This is expected — topic-based semantic search only produces a distinct, useful result set once the graph has enough memories for meaningful recall. Its absence is not an error; proceed with the core memories that were returned. As the fabric grows, the section will appear automatically.

Recommended pattern:

- Prefer one plain `wake-up` for startup continuity
- Let the structured sections be resolved behind that call
- Use topic refinement only when the initial user prompt clearly narrows the current work
- Fall back to the legacy general/topic sequence only for older callers

The output is a structured briefing grouped by strand. Read it fully before responding to the user's first message. It establishes:

- Active decisions that constrain what you can suggest
- Known preferences and working norms
- Outstanding todos that may be relevant
- Contextual facts about the user, project, and relationships

---

## During the session

### The fabric is a living reference, not a log

The fabric is not a journal you write at the end of a session. It is your working memory — a store of facts, decisions, and insights you should be drawing on and adding to continuously as the conversation unfolds.

**This means two things in practice:**

1. **Search before you assume.** Before making a recommendation, recalling a preference, or proposing an approach, check whether the fabric already holds relevant context. If you are about to say "I think Oliver prefers X" or "last time we did Y" — stop and search first. The fabric is the authoritative source; your in-session impression is not.

2. **Write as facts land, not later.** When a durable fact, decision, or insight is established, write it to the fabric immediately — not at close-session, not at the end of your response. Mid-session writes ensure nothing is lost if the session is interrupted, and they make the fabric useful to you later in the same session.

Mechanical compliance (wake-up at start, close-session at end) without active mid-session use is not enough. The fabric should function as a living reference that shapes what you say next, not a log of what already happened.

### Search before proposing

Before making a recommendation, recalling a fact, or suggesting an approach, check whether the fabric already holds relevant context:

```bash
memory search-memory "your query" [--tag strand-id] [--limit N]
```

Do not propose something the user has already decided, or repeat a fact the fabric already knows. When the conversation topic shifts, refresh your working set with a new search — do not coast on the wake-up results alone.

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

**Importance — blast radius of absence:**

The question to ask at write time: *"If a future session has no knowledge of this memory, what is the worst that happens?"* Rate by the consequence of absence, not by how significant the memory feels in the moment.

| Value | Blast radius of absence | Examples |
|-------|------------------------|---------|
| **5** | **A breach.** A future session acts in direct violation of an active constraint, crosses a boundary, or fundamentally misreads the relationship or situation. Getting it wrong is actively worse than knowing nothing. | Safety pacts, hard relationship rules, blacklisted contacts, irreversible decisions with active force |
| **4** | **A significant miss.** A recommendation ignores something already decided, a plan contradicts established context, or the response is meaningfully miscalibrated. The interaction proceeds but produces the wrong outcome. | Active project decisions, current working constraints, key preferences that shape recommendations |
| **3** | **A quality loss.** The response is generically correct but imprecise — less personal, missing nuance, slightly off. No material harm, just reduced value. **Default for most memories.** | Background facts, general preferences, historical context, insights about patterns |
| **2** | **Barely noticeable.** The response is complete and correct without this. Supplementary detail that enriches but is not structurally needed. | Secondary observations, supporting data, peripheral context |
| **1** | **No future impact.** Only relevant in the session it was created. Expected to decay quickly. | Ephemeral state, test memories, single data points with no lasting relevance |

**Calibration notes:**
- When in doubt, use **3**. Promotion to 4 or 5 requires a concrete answer to "what breaks without this?"
- Blast radius can change over time — an active application is importance-4 now and importance-2 once closed. Recalibrate on lifecycle events.
- Importance also sets initial strength and decay floor (`importance / 5.0`), so inflation has mechanical consequences: over-rated memories resist decay and crowd out genuinely critical ones in wake-up.

Run `memory list-strands` if strand IDs are uncertain. Always use an existing strand ID — never invent one.

---

### Weekly priority stack and commitment pressure

Two scheduling constructs live in the fabric alongside Tasks. They are distinct and should not be conflated.

#### Weekly priority stack

A single memory tagged `priority-stack` that declares which project domains get first claim on discretionary time this week. Set every Monday at Week Start. Overwrite the previous week's entry — only the current stack matters.

```bash
memory add-memory \
  --text "Week of 2026-04-20 priority stack: JFLP > CARR Cyber > Systems. Sanity (gym, lunch, recovery) is non-negotiable and sits outside the stack." \
  --type decision \
  --strand-id strand-companion-protocols-systems \
  --tag priority-stack \
  --importance 4
```

**How it differs from Tasks:** Tasks answer *"what needs doing and by when."* The priority stack answers *"when two things compete for the same slot, which wins."* Tasks are granular and numerous; the priority stack is a single short-lived declaration. Do not mix them.

The morning brief should surface the current priority stack at the top of the day view so both Oliver and Mara know the allocation lens for the day.

#### Commitment pressure signals

When a hard commitment is made inside a project — e.g. "application out by EOB today" in JFLP — write it to the fabric as a `todo` with an explicit deadline. This is separate from the project's internal task tracker; it is the signal that crosses the project boundary into Mara's scheduling awareness.

```bash
memory add-memory \
  --text "JFLP: submit Contilia application by EOB 2026-04-20. Hard deadline — committed." \
  --type todo \
  --strand-id strand-core-work-career \
  --tag commitment-pressure \
  --importance 4
```

The morning brief must query for `commitment-pressure` tagged todos due today and promote them above the priority stack in the day view. If the schedule does not have sufficient protected time for a due-today commitment, flag it explicitly — do not silently leave it unprotected.

**Relationship to JFLP DB:** JFLP's SQLite pipeline DB tracks internal project commitments. The fabric `commitment-pressure` tag is the bridge that surfaces project-level deadlines into Mara's cross-project scheduling view. Both are needed; they serve different scopes.

### Wording convention

Use the person's established name once identity is known. In this graph, write memory content with "Oliver" as subject: *"Oliver prefers short feedback loops over long planning phases."* Use *"The User"* only as a generic placeholder before identity has been established. Do not use "you" as subject because it is ambiguous when read by an LLM.

When using the `fact` / `so_what` split, write `so_what` so it can stand on its own as a consequence statement. It should still make sense if surfaced independently or later promoted into its own Memory node via `LEADS_TO`. Avoid pronouns whose meaning depends on the paired `fact`.

Good:

- `fact`: *"Oliver has ADHD."*
- `so_what`: *"Structure and short feedback loops matter more than motivation."*

Bad:

- `fact`: *"The User has ADHD."*  # when identity is already known
- `so_what`: *"This means it helps."*

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
memory add-memory --text "Oliver decided to ..." --type decision --strand-id <strand-id> --importance 4
memory add-memory --text "Oliver prefers ..." --type insight --strand-id <strand-id> --importance 3

# review and close
memory close-session
[end]
```

---

## Notes

- `close-session` is local-only — it requires no API connection.
- `wake-up` requires the full local stack to be running (`./scripts/start-local-stack.sh` preferred).
- `AGENT_ID` in `.env` identifies which agent produced each memory. Default: `claude-code`.
- `API_BASE_URL` in `.env` points to the memory service. Default: `https://memfabric.carr-it.net`.
