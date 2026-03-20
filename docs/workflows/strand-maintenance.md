# Workflow: Strand Maintenance

Audit existing memories and assign them to Strands (thematic threads), or create new Strands for emerging themes.

**Trigger prompt:**
```
Read docs/workflows/strand-maintenance.md and follow the workflow.
Context: I want to organise memories into strands for <project or theme>.
```

---

## When to use

- After accumulating 20+ memories.
- Before a Memgraph Lab visualisation session — Strand groupings make the graph navigable.
- When a project theme has crystallised that wasn't apparent at memory-creation time.
- Periodic maintenance (monthly or per milestone).

---

## Background

**Strands** are `Strand` nodes connected to `Memory` nodes via `IN_STRAND` edges (with a `weight` property, default 1.0). A memory can belong to multiple strands. Strand categories:

| Category | Use for |
|----------|---------|
| `life` | Personal goals, life areas (health, finance, relationships) |
| `companion` | Ongoing projects and collaborations |
| `shadow` | Tensions, risks, unresolved questions |

**Strand IDs** are arbitrary strings you assign (e.g. `strand-architecture-decisions`, `strand-leadership`). Establish a naming convention and use it consistently — the API does not validate or list strand IDs.

**Suggested convention:** `strand-<category>-<kebab-topic>`, e.g. `strand-companion-graph-memory`, `strand-shadow-technical-debt`.

---

## Step 1 — Survey the memory space

Run broad searches to sample what memories exist:

```bash
memory search-memory "key decisions architecture" --limit 20 --max-hops 0
memory search-memory "insights observations learnings" --limit 20 --max-hops 0
memory search-memory "todo action outstanding" --limit 20 --max-hops 0
```

Collect all results. Group informally by theme (mental or in a scratch doc).

---

## Step 2 — Identify candidate strands

From the grouped results, propose strand definitions. For each candidate strand:

- **Name** — short, human-readable (e.g. "Architecture Decisions").
- **Description** — one sentence describing what belongs here.
- **Category** — `life`, `companion`, or `shadow`.
- **Strand ID** — following the naming convention above.
- **Candidate memory IDs** — the IDs from Step 1 that belong to this strand.

---

## Step 3 — Present for approval

Output a table before making any changes:

| Strand ID | Name | Category | Description | Memory IDs |
|-----------|------|----------|-------------|-----------|
| `strand-companion-graph-memory` | Graph Memory Architecture | companion | Key decisions and insights about the graph-memory-fabric design | `abc12345`, `def67890` |
| `strand-shadow-technical-debt` | Technical Debt | shadow | Known shortcuts, deferred work, and risks | `ghi11223` |

Wait for the user to approve, edit names/categories, add or remove memories, or define additional strands.

---

## Step 4 — Assign memories to approved strands

**v1 limitation:** The API has no `PATCH /memory/{id}/strands` endpoint. The workaround is to store a new `observation` memory with `--strand-id` set, which connects it to the strand via an `IN_STRAND` edge. To assign an *existing* memory to a strand, create a bridging observation that references the existing memory with `--related-id`.

For each memory ID to assign to a strand:

```bash
memory add-memory "Assigning <short summary of original memory> to strand <strand name>" \
  --type observation \
  --importance 2 \
  --tag strand-assignment \
  --strand-id STRAND_ID \
  [--project-id PROJECT_ID] \
  --related-id EXISTING_MEMORY_ID
```

For **new** memories being added fresh (not pre-existing), use `--strand-id` directly in the `add-memory` call — no bridging node needed.

---

## Step 5 — Confirm

Print a summary:

```
Strand assignments complete:
- strand-companion-graph-memory: 3 memories assigned
- strand-shadow-technical-debt: 1 memory assigned
Total bridging observations created: 4
```

---

## Example

```bash
# Broad survey
memory search-memory "architecture decisions design choices" \
  --project-id graph-memory-fabric \
  --limit 20 \
  --max-hops 0

# Assign an existing memory to a strand via bridging observation
memory add-memory "Archiving neo4j driver decision into the architecture strand for visualisation" \
  --type observation \
  --importance 2 \
  --tag strand-assignment \
  --strand-id strand-companion-graph-memory \
  --project-id graph-memory-fabric \
  --related-id abc12345def67890

# Add a new memory directly into a strand (no bridging needed)
memory add-memory "Embedding cache has no eviction policy — will grow unbounded under long-running deployment" \
  --type observation \
  --importance 3 \
  --tag embedding \
  --tag performance \
  --strand-id strand-shadow-technical-debt \
  --project-id graph-memory-fabric
```

---

## v1 limitation note

There is no `list-strands` CLI command or `GET /strand` endpoint. You must track strand IDs yourself (a scratch doc or a `fact` memory works well). Maintain a `fact` memory per project listing the active strand IDs — this makes them discoverable via search.

Example:

```bash
memory add-memory "Active strands for graph-memory-fabric: strand-companion-graph-memory (architecture), strand-shadow-technical-debt (risks)" \
  --type fact \
  --importance 5 \
  --tag strands \
  --project-id graph-memory-fabric
```
