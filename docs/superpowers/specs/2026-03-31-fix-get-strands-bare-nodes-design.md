# Fix: GET /strands 500 on bare Strand nodes

**Date:** 2026-03-31
**Type:** Bugfix
**Scope:** `memory_service/memory_repo.py`, `memory_service/main.py`, `scripts/`, `tests/test_list_strands.py`

---

## Problem

`POST /memory` accepts `strand_ids` and executes `MERGE (s:Strand {id: $strand_id})`, silently creating bare Strand nodes (id only, all other properties null) when an unknown strand ID is passed. `GET /strands` later tries to deserialise all Strand nodes into `StrandItem(id, name, description, category)`, but bare nodes have `None` for the required fields, causing Pydantic `ValidationError` → HTTP 500.

Root causes:
1. `add_memory` (Step 4) and `patch_memory` (strand_ids block) both use `MERGE` on Strand nodes, creating bare nodes for unknown IDs.
2. `StrandItem` declares `name`, `description`, `category` as required `str` fields.

---

## Fix

### memory_repo.py — MERGE → MATCH (two locations)

**add_memory Step 4** (line ~105):
```cypher
-- BEFORE
MERGE (s:Strand {id: $strand_id})
WITH s
MATCH (m:Memory {id: $memory_id})
CREATE (m)-[:IN_STRAND {weight: 1.0}]->(s)

-- AFTER
MATCH (s:Strand {id: $strand_id})
WITH s
MATCH (m:Memory {id: $memory_id})
CREATE (m)-[:IN_STRAND {weight: 1.0}]->(s)
```

**patch_memory strand_ids block** (line ~482): identical swap.

If the strand does not exist, `MATCH` finds nothing and the query is a no-op — no edge, no bare node.

### memory_repo.py — defensive filter in list_strands

Add `WHERE s.name IS NOT NULL` to the `list_strands` query:
```cypher
MATCH (s:Strand) WHERE s.name IS NOT NULL
RETURN s.id AS id, s.name AS name, s.description AS description, s.category AS category
ORDER BY s.category, s.name
```

Bare nodes already in the DB are excluded from the response even before cleanup.

### main.py — StrandItem optional fields

```python
class StrandItem(BaseModel):
    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
```

Belt-and-braces: if a bare node slips past the repo filter, the endpoint returns 200 instead of 500.

### scripts/cleanup_bare_strands.py — one-off cleanup

New script that runs:
```cypher
MATCH (s:Strand) WHERE s.name IS NULL DETACH DELETE s
```

Follows existing scripts pattern: reads config from `.env` via pydantic-settings, never called by the running service.

### tests/test_list_strands.py — new tests

**Unit test (mocked):** POST /memory with unknown `strand_id`, then GET /strands → assert 200, unknown strand ID not in response.

**Integration test (live stack):** Same scenario end-to-end — POST /memory with unknown strand_id → GET /strands returns 200 with no bare strand in the list.

---

## What is not changing

- Strand nodes must still be pre-seeded via `seed_strands.py` with valid metadata.
- No change to the `GET /strands` sort order (category then name).
- No change to valid strand_id behaviour — edges are still created correctly when the strand exists.

---

## Acceptance criteria

1. `POST /memory` with an unknown `strand_id` returns 201 (not 500, not 422).
2. `GET /strands` after the above returns 200 with no bare strand in the list.
3. No new bare Strand nodes exist in the DB after running the cleanup script.
4. All existing tests continue to pass.
