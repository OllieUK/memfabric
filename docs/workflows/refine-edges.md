# Workflow: Refine Edges

Identify Memory nodes that are semantically or causally related but lack explicit `RELATED_TO` edges, and add those links.

**Trigger prompt:**
```
Read docs/workflows/refine-edges.md and follow the workflow.
Context: I want to refine edges in the topic area of <description> [, project <project-id>].
```

---

## When to use

- After a batch ingestion session (`summarise-session.md`).
- Before inspecting the graph in Memgraph Lab (`http://localhost:3000`).
- When a search with `--max-hops 1` returns noticeably fewer results than a pure vector search, suggesting the graph is under-connected.

---

## Background

`RELATED_TO` edges are created automatically at insert time via vector similarity (k=5, cosine distance < 0.5). This threshold catches strong semantic overlap but misses:

- **Weaker relationships** — two memories that are causally linked but phrased differently.
- **Temporal sequences** — events that occurred in order.
- **Retrospective links** — a new memory makes an old one relevant in a way that wasn't apparent at insert time.

This workflow adds explicit `RELATED_TO` edges by creating a bridging `observation` memory (see v1 limitation note below).

---

## Step 1 — Search for candidate memories (no hop expansion)

Use `--max-hops 0` to retrieve only vector-matched nodes, bypassing existing `RELATED_TO` edges. This surfaces memories the graph has not yet explicitly connected.

```bash
memory search-memory "TOPIC" \
  --max-hops 0 \
  --limit 20 \
  [--project-id PROJECT_ID]
```

Run 2–3 searches in parallel (they are independent). Collect all result IDs and texts. Deduplicate by ID. If all searches return zero results, inform the user and stop.

---

## Step 2 — Identify candidate pairs

From the deduplicated results, propose pairs of memories that should be linked. Only propose a pair if you can answer "yes" to: *does one memory directly explain, constrain, or temporally precede the other?* Limit to a maximum of 10 proposed pairs per run to avoid graph bloat.

For each pair, classify the relationship:

- **semantic** — similar topic or concept.
- **temporal** — one event preceded and led to another.
- **causal** — one decision or fact caused or constrained the other.
- **contradictory** — the memories are in tension (flag for user review; do not auto-link).

Assign a proposed edge weight (only propose pairs with weight ≥ 0.6):
- `0.6` — medium (clearly related)
- `0.9` — strong (directly linked, one explains the other)

---

## Step 3 — Present for approval

Output a table before making any changes:

| Memory A (short ID + text) | Memory B (short ID + text) | Relationship | Weight |
|---------------------------|---------------------------|-------------|--------|
| `abc12345`: decided to use neo4j driver | `def67890`: Bolt protocol is Memgraph-compatible | causal | 0.9 |

Wait for the user to approve, edit, or remove rows.

---

## Step 4 — Add approved edges

**v1 limitation:** The API has no `PATCH /memory/{id}/edges` endpoint. The workaround is to store a new `observation` memory referencing both targets via `--related-id`. The service auto-creates `RELATED_TO` edges from the new node to each referenced ID.

For each approved pair:

```bash
memory add-memory "BRIDGING OBSERVATION TEXT" \
  --type observation \
  --importance 2 \
  --tag edge-refinement \
  [--project-id PROJECT_ID] \
  --related-id MEMORY_A_ID \
  --related-id MEMORY_B_ID
```

Write a bridging observation text that captures **why** these memories are related (one sentence). Avoid generic text like "these are related" — the text should add value if encountered in a future search.

Example bridging text: `"neo4j driver choice and Bolt protocol compatibility are causally linked: the neo4j driver was chosen specifically because Memgraph supports the Bolt protocol."`

---

## Step 5 — Confirm

Print a summary of edges added:

```
Added N bridging observations:
- <uuid>: A[abc12345] ↔ B[def67890] (causal, weight 0.9)
```

---

## Inspecting the result

Open Memgraph Lab at `http://localhost:3000` and run:

```cypher
MATCH (m:Memory)-[r:RELATED_TO]-(n:Memory)
WHERE m.id = '<one of your IDs>'
RETURN m, r, n
```

The newly created edges will appear in the graph view.

---

## v1 limitation note

The bridging `observation` approach creates an extra node in the graph for each edge added. This is a known v1 constraint. A future `PATCH /memory/{id}/edges` endpoint (not yet planned) would allow direct edge creation without the extra node. For now, using `tag=edge-refinement` and `importance=2` makes these bridging nodes identifiable and low-priority in search results.
