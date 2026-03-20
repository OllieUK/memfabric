# Workflow: Contextual Recall

Retrieve relevant past memories before starting a task, to prime the session with prior context.

**Trigger prompt:**
```
Read docs/workflows/contextual-recall.md and follow the workflow.
Context: I'm about to work on <task description> in project <project-id>.
```

---

## When to use

- Beginning of any coding or design session.
- Picking up a task after a gap of days or weeks.
- Context-switching between projects.
- When a search seems to be missing conceptually linked memories.

---

## Step 1 — Decompose the task into recall dimensions

From the task description, identify:

- **Domain/topic** — the primary technical or conceptual area.
- **Relevant decisions** — past choices that constrain the current task.
- **Outstanding todos** — known action items that may be relevant.
- **People or projects** — any named associations to scope results.

---

## Step 2 — Execute targeted searches

Run all three searches in parallel (they are independent). Use `--max-hops 1` to pull in graph neighbours (semantically linked memories that would not appear in a pure vector search).

```bash
# Run these three concurrently:

# Primary topic search
memory search-memory "DOMAIN TOPIC" --project-id PROJECT_ID --limit 10 --max-hops 1

# Prior decisions in this area
memory search-memory "decision ASPECT" --project-id PROJECT_ID --tag decision --limit 5 --max-hops 0

# Outstanding todos
memory search-memory "todo action item ASPECT" --project-id PROJECT_ID --limit 10 --max-hops 0
```

Collect all result IDs. Deduplicate across searches by ID. If all searches return zero results, inform the user that no relevant memories were found and stop.

---

## Step 3 — Rank and organise

Sort the deduplicated results:

1. `todo` type first — outstanding actions should be visible immediately.
2. `decision` type second — constraining context.
3. `insight` and `observation` third — supporting understanding.
4. `fact` and `event` last — background reference.

Within each group, sort by `importance` descending (5 = highest).

---

## Step 4 — Present context summary

Output a compact markdown block the user can read or paste into their working context:

```
## Session context: <task description>

### Outstanding actions
- [<short-id>] (importance: N) <memory text>

### Prior decisions
- [<short-id>] (importance: N) <memory text>

### Relevant insights
- [<short-id>] (importance: N) <memory text>
```

Keep each memory to one line. Use the first 8 characters of the UUID as the short ID.

---

## Step 5 — Flag potentially stale todos

For any `todo` memory in the results, flag it for the user's attention — the current API does not return timestamps, so age cannot be determined automatically:

- Flag each todo: "⚠ Todo [ID]: <text> — is this still outstanding?"
- Ask the user for each: mark done (store a new `fact` memory describing the outcome), keep active, or dismiss.

Do not automatically delete or modify todos — wait for user instruction.

---

## Example

```bash
memory search-memory "vector index schema configuration" \
  --project-id graph-memory-fabric \
  --limit 10 \
  --max-hops 1

memory search-memory "decision embedding model" \
  --project-id graph-memory-fabric \
  --limit 5 \
  --max-hops 0

memory search-memory "outstanding todo graph memory" \
  --project-id graph-memory-fabric \
  --limit 10 \
  --max-hops 0
```
