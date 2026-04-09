# WP-049 Design — Wake-up Companion + Conversant Anchoring

**Date:** 2026-04-09  
**Status:** Approved  
**WP:** WP-049

---

## Problem

Wake-up currently returns the most prominent memories and (optionally) topic-relevant memories. It has no awareness of who the Companion is or who it is speaking with. Identity-critical anchor memories for the Companion and person-specific context for the current conversant are left to chance — they only surface if they happen to be high-strength or topic-adjacent.

The result: a freshly started session may have no grounding in the Companion's identity or in the relationship with the person being addressed.

---

## Approach

Add two new additive sections to the wake-up response: **companion anchors** and **conversant anchors**. Both are purely additive — the existing `core` and `topic` sections are completely unaffected. Sections are omitted (not empty arrays) when no matching memories exist.

**Companion anchor identification** uses a label-agnostic `ABOUT→any-node` graph traversal keyed on `settings.agent_id`. This sidesteps the current Agent/Person node duality — a companion identity node can be Agent, Person, or any other label. It also establishes the foundation for prescriptive per-role identity: to give any agent anchor memories, create a node with `id = agent_id` and attach `ABOUT` edges from its identity memories to that node.

---

## Data Flow

```
GET /memory/wake-up?limit=20&topic=...&person_id=...
                                             │
        ┌────────────────────────────────────┤
        │                                    │
        ▼                                    ▼
[existing — unchanged]              [new — always runs when agent_id set]
core (importance-ranked)            companion_anchors
topic (vector search)               MATCH (m)-[:ABOUT]->(n)
                                    WHERE n.id = settings.agent_id
                                             │
                                    [new — only when person_id set]
                                    conversant_anchors
                                    MATCH (m)-[:ABOUT]->(p)
                                    WHERE p.id = $person_id
```

---

## Config (`memory_service/config.py`)

Two new settings (env-overridable):

```python
wake_up_companion_anchor_limit: int = 5    # WAKE_UP_COMPANION_ANCHOR_LIMIT
wake_up_conversant_anchor_limit: int = 10  # WAKE_UP_CONVERSANT_ANCHOR_LIMIT
```

`settings.agent_id` (already present) identifies which node to query for companion anchors. No new config needed for that.

---

## API (`memory_service/main.py`)

### New query parameters on `GET /memory/wake-up`

| Param | Type | Default | Purpose |
|---|---|---|---|
| `person_id` | `str \| None` | `None` | Fetch conversant anchors for this Person (or any node with matching id) |
| `companion_anchor_limit` | `int` | `settings.wake_up_companion_anchor_limit` | Per-call override |
| `conversant_anchor_limit` | `int` | `settings.wake_up_conversant_anchor_limit` | Per-call override |

### Extended `WakeUpResponse`

```python
class WakeUpResponse(BaseModel):
    memories: List[WakeUpMemoryItem]                              # unchanged
    topic_memories: List[WakeUpMemoryItem]                        # unchanged
    maintenance_status: MaintenanceStatus                         # unchanged
    companion_anchors: Optional[List[WakeUpMemoryItem]] = None    # new
    conversant_anchors: Optional[List[WakeUpMemoryItem]] = None   # new
```

`None` means the section is absent (not requested or no matching memories). `[]` is never returned for these two fields.

### Scoping note

The BACKLOG motivation mentions `person_name` as an alternative to `person_id`. This WP implements `person_id` only — a name-based lookup is ambiguous (Person names are not unique keys) and is out of scope.

---

## Repo Layer (`memory_service/memory_repo.py`)

### Updated signature

```python
def wake_up(
    session,
    limit: int,
    topic_embedding: list | None = None,
    agent_id: str | None = None,
    companion_anchor_limit: int = 5,
    person_id: str | None = None,
    conversant_anchor_limit: int = 10,
) -> dict:
    # Returns:
    # {
    #   "core": [...],
    #   "topic": [...],
    #   "companion_anchors": [...] | None,
    #   "conversant_anchors": [...] | None,
    # }
```

### Companion anchors query

Ordered by importance then strength. Identity memories should be stable anchors, not recency-driven.

```cypher
MATCH (m:Memory)-[:ABOUT]->(n)
WHERE n.id = $agent_id
  AND (m.status IS NULL OR m.status = 'active')
  AND (m.ephemeral IS NULL OR m.ephemeral = false)
OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
WITH DISTINCT m, collect(s.id)[0] AS strand_id
RETURN m.id AS id, m.text AS text, m.type AS type,
       m.tags AS tags, m.importance AS importance,
       m.created_at AS created_at, strand_id
ORDER BY m.importance DESC, coalesce(m.strength, 0.0) DESC
LIMIT $limit
```

Only executed when `agent_id` is set. Returns `None` (not `[]`) when the result set is empty, so the caller can omit the section cleanly.

### Conversant anchors query

Ordered by importance then recency. Relationship context should surface what is most relevant now.

```cypher
MATCH (m:Memory)-[:ABOUT]->(p)
WHERE p.id = $person_id
  AND (m.status IS NULL OR m.status = 'active')
  AND (m.ephemeral IS NULL OR m.ephemeral = false)
OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
WITH DISTINCT m, collect(s.id)[0] AS strand_id
RETURN m.id AS id, m.text AS text, m.type AS type,
       m.tags AS tags, m.importance AS importance,
       m.created_at AS created_at, strand_id
ORDER BY m.importance DESC, m.created_at DESC
LIMIT $limit
```

Only executed when `person_id` is set. Returns `None` when empty.

Both new queries reuse the existing `_record_to_memory_dict()` helper — no new mapping logic.

---

## Client (`memory_client/client.py`)

`wake_up_split()` is changed to return a **plain dict** (the raw API response) instead of a 3-tuple. This eliminates the growing tuple-fragility problem (WP-089 already documents breakage when the tuple grew from 2 to 3 items) and naturally accommodates the two new optional fields.

```python
def wake_up_split(
    self,
    *,
    limit: int = 20,
    topic: str | None = None,
    person_id: str | None = None,
    companion_anchor_limit: int | None = None,
    conversant_anchor_limit: int | None = None,
) -> dict:
    """GET /memory/wake-up. Returns the full response dict.

    Keys always present: memories, topic_memories, maintenance_status
    Keys present when populated: companion_anchors, conversant_anchors
    """
```

The legacy `wake_up()` method (returns only `memories` list) is left unchanged.

All existing callers of `wake_up_split` (`mcp_server/server.py`, `memory_client/cli.py`) are updated to use dict key access. The three tests in `test_wp033_mcp_server.py` mocking `wake_up_split` as a 2-tuple (the WP-089 pre-existing failures) are fixed as a side-effect.

---

## CLI (`memory_client/cli.py`)

One new flag on `wake-up`:

```
memory wake-up [--topic TEXT] [--limit N] [--person-id TEXT]
```

Rendering: uses the existing `_render_section()` helper with two new section headers:
- `### Companion` — rendered when `companion_anchors` is present in the response
- `### Conversant` — rendered when `conversant_anchors` is present in the response

Sections are skipped entirely (no header printed) when the corresponding response field is `None`.

---

## MCP (`mcp_server/server.py`)

`memory_wake_up` gains one new parameter:

```python
def memory_wake_up(
    topic: str | None = None,
    limit: int = 20,
    person_id: str | None = None,   # new
) -> str:
```

Plain-text rendering adds:
- `### Companion` block when `companion_anchors` is present
- `### Conversant` block when `conversant_anchors` is present

Both use the existing `_render_section()` helper.

---

## Seeding Script (`scripts/seed_companion_anchors.py`)

One-time idempotent script for existing installations that have companion identity memories not yet linked via `ABOUT` edges.

**Arguments:**
- `--agent-id` (default: `settings.agent_id`)
- `--strand-ids` (comma-separated, default: `strand-companion-ai-anchor`)

**Logic:**
1. Ensure identity node exists: `MERGE (n {id: $agent_id})` (label-agnostic)
2. For each Memory in the specified strands without an existing `ABOUT→n` edge: `CREATE (m)-[:ABOUT]->(n)`
3. Print counts: edges created vs already existing

**Convention going forward:** new companion anchor memories should be written with `person_ids=[agent_id]` in their `POST /memory` payload, which creates the `ABOUT` edge automatically at write time.

---

## Tests

### Unit tests

- `wake_up()` with `agent_id` set and no matching nodes returns `companion_anchors: None`
- `wake_up()` with `person_id` set and no matching nodes returns `conversant_anchors: None`
- `WakeUpResponse` serialises with `companion_anchors=None` omitting the field (or returning null, not `[]`)

### Integration tests (live Memgraph + FastAPI)

One integration test covers both new sections:

1. Create an identity node `(n {id: "test-companion-wp049"})`
2. Seed 3 Memory nodes with `ABOUT→n` edges (varying importance/strength)
3. Create a Person node `(p {id: "test-person-wp049"})`
4. Seed 3 Memory nodes with `ABOUT→p` edges (varying importance/recency)
5. Call `GET /memory/wake-up?companion_anchor_limit=2&person_id=test-person-wp049`
6. Assert `companion_anchors` contains exactly 2 items, ordered by importance DESC then strength DESC
7. Assert `conversant_anchors` contains 3 items, ordered by importance DESC then created_at DESC
8. Call without `person_id` — assert `conversant_anchors` is absent
9. Teardown: DETACH DELETE all seeded nodes (ephemeral=true or explicit cleanup)

---

## Definition of Success (from BACKLOG)

- [ ] Wake-up response includes a `companion_anchors` section with Companion identity memories
- [ ] When `person_id` is supplied, response includes a `conversant_anchors` section
- [ ] Both sections respect their configured limits
- [ ] Sections are omitted (not empty arrays) when there are no matching memories
- [ ] CLI and MCP updated
- [ ] Integration test: seed Companion anchor memories and a Person with ABOUT memories; confirm they appear in the correct sections
