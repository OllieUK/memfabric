# Workflow: Summarise Session

Convert rough session notes, code comments, or a conversation transcript into structured Memory records stored via the CLI.

**Trigger prompt:**
```
Read docs/workflows/summarise-session.md and follow the workflow.
Context: <paste notes here, or reference a file path>.
```

---

## When to use

- End of a coding or design session.
- After a long conversation that produced decisions or insights.
- After reading a document, spec, or codebase area for the first time.
- After a meeting or pair session.

---

## Step 1 — Gather source material

Read the provided file(s) or use the current conversation as source. Do not discard anything yet — a full pass happens in Step 2.

If the user provides file paths, read each file in full before proceeding.

---

## Step 2 — Extract candidate memories

Iterate over the source material. For each discrete piece of information, draft a **single-sentence memory text** covering:

- A fact that was established.
- A decision that was made (include the rationale).
- An insight or realisation.
- An event that occurred.
- An observation from direct experience.
- An action that still needs to be taken.

**Targets:** 5–15 memories per session. Discard duplicate, trivial, or purely procedural items (e.g. "opened a file").

For each candidate, assign:
- **type** — from the MemoryType table in `docs/workflows/README.md`.
- **importance** — 1 (low) to 5 (critical); use 3 as the default.

---

## Step 3 — Classify and tag

For each candidate memory:

- Assign **tags** — concise lowercase strings describing the domain (e.g. `architecture`, `testing`, `performance`, `auth`).
- Identify **project_id** if the memory clearly belongs to a project.
- Identify **person_id** if a named person is associated.
- Identify **strand_id** if the memory clearly belongs to a known Strand (skip if unsure — use `strand-maintenance.md` later).

---

## Step 4 — Present draft list for approval

Output a markdown table before storing anything:

| # | Text | Type | Importance | Tags | project_id | strand_id |
|---|------|------|------------|------|-----------|-----------|
| 1 | … | decision | 4 | architecture, memgraph | graph-memory-fabric | |
| 2 | … | todo | 3 | testing | | |

Wait for the user to approve, edit, or remove rows before proceeding to Step 5.

---

## Step 5 — Store approved memories

For each approved row, run:

```bash
memory add-memory "TEXT" \
  --type TYPE \
  --importance N \
  --tag TAG1 \
  --tag TAG2 \
  [--project-id PROJECT_ID] \
  [--person-id PERSON_ID] \
  [--strand-id STRAND_ID]
```

Capture and log the returned UUID for each memory.

---

## Step 6 — Confirm

Print a summary:

```
Stored N memories:
- <uuid-1>: <type> — <first 60 chars of text>
- <uuid-2>: …
```

---

## Example

```bash
memory add-memory "Decided to use neo4j Python driver for Bolt compatibility with Memgraph rather than a native Memgraph driver" \
  --type decision \
  --importance 4 \
  --tag architecture \
  --tag memgraph \
  --project-id graph-memory-fabric

memory add-memory "Vector index capacity is hardcoded at 1000 in init_schema.py — needs to become a config value before production use" \
  --type todo \
  --importance 3 \
  --tag configuration \
  --tag vector-index \
  --project-id graph-memory-fabric
```
