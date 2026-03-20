# Workflow: Propose Todos

Search past memories for items relevant to a current task, then surface actionable todo suggestions.

**Trigger prompt:**
```
Read docs/workflows/propose-todos.md and follow the workflow.
Context: I'm planning <task or feature description> in project <project-id>.
```

---

## When to use

- Start of a work session before writing code.
- Before planning a new feature or refactor.
- Weekly review of outstanding actions.
- When feeling stuck — past memories may reveal a blocker or prior attempt.

---

## Step 1 — Formulate search queries

From the task description, derive 2–4 search queries using different phrasings to improve recall:

- A direct phrase match: `"implement vector search endpoint"`
- A broader domain: `"search API design"`
- A decision angle: `"decision API search POST GET"`
- A blocker angle: `"blocked todo outstanding search"`

---

## Step 2 — Execute searches

Run all queries in parallel (they are independent):

```bash
memory search-memory "QUERY" \
  [--project-id PROJECT_ID] \
  [--tag TAG] \
  --limit 15 \
  --max-hops 1
```

Collect all results. Deduplicate by ID internally — do not present the raw deduplicated list to the user; proceed directly to Step 3.

If the total deduplicated set is empty, inform the user that no relevant memories were found and stop.

---

## Step 3 — Identify action items

For each deduplicated result, evaluate:

- **Existing `todo` memories** — these are outstanding by definition; include all of them.
- **`decision` memories with unresolved next steps** — e.g. "decided to use X, but haven't implemented yet".
- **`insight` memories that suggest follow-up** — e.g. "noticed Y is slow — should investigate".
- **`fact` memories that contradict the current plan** — surface as a flag, not a todo.

Do not include memories that describe completed states or past events with no implication for action.

---

## Step 4 — Draft new todo memories

For each identified action item that does not already exist as a stored `todo`:

- Draft a single-sentence todo text describing the action.
- Set `importance` based on urgency/impact (1–5; default 3).
- Note the source memory ID(s) that prompted this todo.

---

## Step 5 — Present for approval

Output two tables before storing anything:

**Existing todos (from search results):**

| ID (short) | Text | Importance | Age |
|-----------|------|------------|-----|
| `abc12345` | … | 3 | 5 days |

**Proposed new todos:**

| # | Text | Importance | Derived from |
|---|------|------------|--------------|
| 1 | … | 3 | `abc12345` |

Wait for the user to approve, edit, or remove rows before proceeding to Step 6.

---

## Step 6 — Store approved new todos

For each approved new todo, run:

```bash
memory add-memory "TEXT" \
  --type todo \
  --importance N \
  [--tag TAG ...] \
  [--project-id PROJECT_ID] \
  [--related-id SOURCE_MEMORY_ID]
```

Using `--related-id` links the new todo to the memory that prompted it, making the dependency visible in the graph.

---

## Example

```bash
# Step 2: searches
memory search-memory "graph endpoint implementation" \
  --project-id graph-memory-fabric \
  --limit 15 \
  --max-hops 1

memory search-memory "decision API design endpoints" \
  --project-id graph-memory-fabric \
  --limit 10 \
  --max-hops 0

# Step 6: store a new todo derived from a found insight
memory add-memory "Implement GET /memory/graph endpoint (WP-006) to unblock dump-graph CLI command and Memgraph Lab integration" \
  --type todo \
  --importance 4 \
  --tag api \
  --tag graph \
  --project-id graph-memory-fabric \
  --related-id <SOURCE_MEMORY_ID>
```
