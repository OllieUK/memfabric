> **MCP integration (preferred):** When running in a Claude Desktop or MCP-enabled Claude Code session, use the MCP tools directly:
> `task_add`, `task_list`, `task_get`, `task_update`, `task_complete`, `task_stale`, `task_next`
>
> These are the preferred path — lower latency, structured returns, no shell subprocess.
> The CLI commands documented below remain valid as a fallback for CLI-only environments.

---

# Task Stewardship

Task nodes are the canonical cross-project commitment store in the Graph Memory Fabric. They replace per-project BACKLOG.md files as the authoritative record of what is planned, in progress, and owed.

This document defines how an agent should create, maintain, and query Task nodes — and how Task nodes relate to the episodic memory system described in COMPANION.md.

---

## Task nodes vs. memory todos

Both systems can represent something that needs doing. The distinction is scope and intent:

| | `todo`-type Memory | Task node |
|---|---|---|
| **What it is** | A durable fact that something is owed | A structured commitment with status, scoring, and lifecycle |
| **Lifetime** | Decays via Ebbinghaus curve; survives as long as it is reinforced | Persists until explicitly marked `done` or `abandoned`; does not decay |
| **Querying** | Semantic search only | Structured filters, priority ordering, cross-project queue |
| **Accountability** | None — no commitment clock | `committed_at` starts an accountability clock; `stale` surfaces overdue commitments |
| **When to use** | A soft intention surfaced during a session: "Oliver mentioned wanting to revisit X" | A concrete commitment: something with a clear owner, a definition of done, and a project context |

**Rule of thumb:** if you would write it in a BACKLOG.md or task tracker, it is a Task node. If you would write it in session notes as a follow-up thought, it is a `todo` memory.

---

## Task schema quick reference

| Property | Type | Meaning |
|----------|------|---------|
| `id` | UUID | Assigned on creation |
| `title` | str | Short, action-oriented description |
| `description` | str \| None | Full detail, rationale, acceptance criteria |
| `status` | open \| active \| blocked \| done \| abandoned | Lifecycle state |
| `value` | H \| M \| L \| None | Impact axis for priority scoring |
| `effort` | H \| M \| L \| None | Cost axis for priority scoring |
| `priority_score` | float \| None | Computed: `VE_MAP[value] / VE_MAP[effort]` (H=3, M=2, L=1). H/L = 3.0; H/H = 1.0; L/H = 0.33 |
| `urgency` | 0–5 float \| None | Time-sensitivity independent of value/effort |
| `due_at` | ISO datetime \| None | Hard deadline |
| `snooze_until` | ISO datetime \| None | Suppress from queue until this time |
| `committed_at` | ISO datetime \| None | When the commitment was made — starts the accountability clock |
| `committed_by` | agent_id \| None | Which agent made the commitment |
| `source_ref` | `{slug}:WP-NNN` \| None | Back-reference to an external backlog entry |
| `recurrence` | str \| None | Human-readable recurrence pattern e.g. `weekly` |
| `is_template` | bool | True for recurring parent tasks; excluded from work queue |

**Edges from a Task node:**

| Edge | Target | Meaning |
|------|--------|---------|
| `OWNED_BY` | Agent | Who is responsible |
| `FOR_PROJECT` | Project | Which project this belongs to |
| `RELATES_TO` | Memory | Optional context links |
| `BLOCKS` | Task | This task must complete before the target can start |
| `DEPENDS_ON` | Task | This task cannot start until the target is complete |
| `INSTANCE_OF` | Task | This is a recurring instance of a template parent |

---

## Creating a task

Minimum required fields: `title`, `agent_id`.

For a task to participate in priority sorting, set `value` and `effort`. Without them, `priority_score` is null and the task floats to the bottom of the queue.

```bash
# MCP
task_add(
    title="Implement API authentication",
    agent_id="graph-memory-fabric",
    value="M", effort="M",
    source_ref="gmf:WP-096",
    project_id="graph-memory-fabric",
)

# CLI
memory create-task "Implement API authentication" \
  --agent-id graph-memory-fabric \
  --value M --effort M \
  --source-ref gmf:WP-096 \
  --project-id graph-memory-fabric
```

### source_ref convention

`source_ref` is a qualified back-reference linking a Task node to an external entry in a project's backlog or planning document. Format:

```
{project-slug}:WP-NNN
```

Examples:
- `gmf:WP-096` — WP-096 in the graph-memory-fabric project
- `mara:WP-015` — WP-015 in the mara project

The slug is the `slug` property on the Project node (set when calling `memory create-project --slug gmf`). If a project has no slug set, `source_ref` can be omitted or use the full project ID.

**Cross-project uniqueness:** different projects may have used the same WP number independently. The slug namespaces them: `gmf:WP-015` and `mara:WP-015` are distinct tasks.

---

## The priority queue

`GET /task/next` (MCP: `task_next`) returns open and active non-template tasks sorted by:

1. `priority_score × project.weight` descending
2. `due_at` ascending (tasks with a deadline float up when scores are equal)

This is the answer to "what should I work on next?" across all projects. Call it at the start of a work session when no specific task has been assigned.

### project.weight

Each Project node carries a `weight` (default 1.0). This is a priority multiplier for cross-project balancing:

- Set `weight > 1.0` on a project that deserves more attention than its individual task scores suggest
- Set `weight < 1.0` on a project that should yield to others when scores are tied
- Leave at 1.0 when no relative adjustment is needed

Example: if `graph-memory-fabric` has `weight=1.5` and a task with `priority_score=2.0`, its effective queue score is `3.0` — same as an H/L task in a weight-1.0 project.

Set or update via:
```bash
memory create-project graph-memory-fabric --name "Graph Memory Fabric" --slug gmf --weight 1.5
```

---

## The commitment clock

Setting `committed_at` on a task starts an accountability clock. A task is **stale** when:

```
committed_at IS NOT NULL AND updated_at = created_at
```

This means: someone committed to this task, but it was created and never touched afterwards.

`GET /task/stale` (MCP: `task_stale`) surfaces these tasks ordered by `committed_at` ascending — oldest commitment first.

**When to set committed_at:**
- When you explicitly tell Oliver (or another agent) "I will do X" — record that commitment
- When a task is picked up from the queue for this session — set `committed_at` and advance status to `active`

**When a task moves off the stale list:**
- Any `PATCH /task/{id}` call updates `updated_at`, clearing the stale condition
- Marking `done` or `abandoned` also removes it (stale query excludes terminal states)

### Commitment as a session anchor

At the start of a work session, the recommended pattern is:

1. Call `task_stale` — surface any overdue commitments and decide: continue, defer (patch with updated status), or abandon
2. Call `task_next` — get the priority queue for new work
3. Pick one task, set its status to `active` and set `committed_at` if not already set

This takes ~3 API calls and gives a clear "what I'm doing this session" signal that survives into future sessions.

---

## Task lifecycle

```
open → active → done
         ↓
      blocked → active
         ↓
      abandoned
```

| Transition | When | How |
|-----------|------|-----|
| `open → active` | Picked up for work | `task_update(id, status="active", committed_at=now)` |
| `active → done` | Work complete | `task_complete(id)` or `task_update(id, status="done")` |
| `active → blocked` | External blocker encountered | `task_update(id, status="blocked")` |
| `blocked → active` | Blocker resolved | `task_update(id, status="active")` |
| `any → abandoned` | Decided not to do | `task_update(id, status="abandoned")` |

**`done` vs. `abandoned`:**
- `done` — the work was completed. The task stays as a provenance record.
- `abandoned` — decided this will not be done (deprioritised, superseded, no longer relevant). Also a valid terminal state; do not leave tasks open indefinitely just because they are low priority.

---

## Recurring tasks

The fabric supports a lazy recurring model. Create a **template** parent once, then spawn instances for each recurrence.

### Create the template
```bash
memory create-task "Weekly backlog review" \
  --agent-id graph-memory-fabric \
  --recurrence weekly \
  --is-template \
  --value M --effort L
```

Templates are excluded from `task_next` and `task_list` by default. They are parent nodes only.

### Spawn an instance

Create a new task via `task_add`, then link it to the template via `POST /task/{instance_id}/link` with `rel_type=INSTANCE_OF`.

There is no automatic spawn — instances are created explicitly when the recurrence fires (e.g. from a scheduled agent or at session start). This keeps the model simple: no phantom future tasks in the queue.

---

## Task dependency edges

Use `BLOCKS` and `DEPENDS_ON` edges to model structural dependencies:

```bash
# POST /task/{from_id}/link
# body: {"target_id": "...", "rel_type": "BLOCKS"}
```

- `A BLOCKS B` — task A must be completed before task B can start
- `A DEPENDS_ON B` — task A cannot start until task B is complete

These edges are informational — the API does not enforce blocked status automatically. They are for traversal queries: "what is this task waiting on?" and "what does completing this task unlock?"

---

## Filtering and listing

```bash
# All open tasks for a project
memory list-tasks --status open --project-id graph-memory-fabric

# All committed tasks owned by this agent
memory list-tasks --agent-id graph-memory-fabric --committed-only

# Top 10 tasks across all projects (cross-project queue)
memory next-task --limit 10

# Stale commitments
# (no CLI command yet — use API directly or MCP task_stale)
curl https://memfabric.carr-it.net/task/stale
```

---

## Integration with episodic memory

Task nodes and Memory nodes are complementary, not competing. A task may carry `memory_ids` at creation time to wire `RELATES_TO` edges — linking the task to the context that motivated it.

Example: a Memory node records "Oliver decided to prioritise WP-096 because the service is now publicly exposed". The Task node for WP-096 carries a `RELATES_TO` edge to that memory. Future sessions can traverse from the task to its motivation.

Do not duplicate task content into memory todos. The task node is the authoritative commitment record. A `todo` memory saying "need to do WP-096" alongside a Task node for WP-096 is noise.

---

## MCP tool reference

| Tool | Purpose |
|------|---------|
| `task_add(title, agent_id, ...)` | Create a Task node |
| `task_list(status, agent_id, project_id, committed_only)` | List tasks with filters |
| `task_get(task_id)` | Get a single task by UUID |
| `task_update(task_id, ...)` | Update fields; priority_score recomputed automatically |
| `task_complete(task_id)` | Shorthand for `task_update(status="done")` |
| `task_stale()` | Surface committed tasks with no update since creation |
| `task_next(limit)` | Cross-project priority queue |

---

## CLI quick reference

```bash
# Create
memory create-task TITLE --agent-id ID [--value H|M|L] [--effort H|M|L]
  [--status open|active|blocked|done|abandoned]
  [--urgency 0-5] [--due-at ISO] [--committed-at ISO] [--committed-by ID]
  [--source-ref SLUG:WP-NNN] [--project-id ID]
  [--recurrence PATTERN] [--is-template]

# List
memory list-tasks [--status STATUS] [--agent-id ID] [--project-id ID] [--committed-only]

# Priority queue
memory next-task [--limit N]

# Update
memory update-task UUID [--status STATUS] [--value H|M|L] [--effort H|M|L]
  [--urgency 0-5] [--due-at ISO] [--source-ref REF]
  [--committed-at ISO] [--committed-by ID]

# Complete
memory complete-task UUID
```
