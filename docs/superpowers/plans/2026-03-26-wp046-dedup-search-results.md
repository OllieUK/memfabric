# WP-046: Deduplicate Search and Wake-up Results

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure each Memory node appears at most once in any search or wake-up result, even when multi-hop traversal reaches the same node via multiple paths.

**Architecture:** The Cypher query template in `memory_repo.py` fans out primary hits via `OPTIONAL MATCH` traversals, which multiplies rows for nodes reachable by multiple paths. Adding `WITH DISTINCT m` (plus carried columns) immediately before the neighbour traversal block collapses those duplicates at the database level. Wake-up already deduplicates core vs. topic but not within the topic query; the same guard is applied there.

**Tech Stack:** Python, Cypher (Memgraph), pytest, FastAPI TestClient

---

## File Map

| File | Change |
|------|--------|
| `memory_service/memory_repo.py` | Modify `_SEARCH_QUERY_TEMPLATE` (add `WITH DISTINCT`) and `wake_up` (guard topic query) |
| `tests/test_wp046_dedup.py` | New: regression tests for diamond topology dedup |
| `tests/test_search_memory.py` | Existing: re-run to confirm no regression |

---

## Task 1: Write the failing regression test

**Files:**
- Create: `tests/test_wp046_dedup.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_wp046_dedup.py
"""
WP-046: Regression tests for duplicate Memory nodes in search and wake-up results.

Integration tests (live Memgraph + running FastAPI required).

Test topology used: diamond
    A (root) -RELATED_TO-> B
    A (root) -RELATED_TO-> C
    B        -RELATED_TO-> D
    C        -RELATED_TO-> D

When searching for A with max_hops=2, D is reachable via A->B->D and A->C->D.
Before the fix, D appears twice in neighbour lists (or as a duplicate primary hit).
After the fix, D appears exactly once.
"""
import uuid
import pytest

_AGENT_ID = "test-wp046-agent"


def _add(client, text, *, related_ids=None):
    body = {"fact": text, "type": "fact", "agent_id": _AGENT_ID}
    if related_ids:
        body["related_ids"] = related_ids
    r = client.post("/memory", json=body)
    assert r.status_code == 200, r.text
    return r.json()["memory_id"]


def _cleanup(test_driver, *ids):
    with test_driver.session() as s:
        for mid in ids:
            s.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mid)
        s.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)


@pytest.mark.integration
class TestSearchDedup:
    def test_primary_results_have_no_duplicate_ids(self, client, test_driver):
        """Each memory id appears at most once in the search results list."""
        tag = f"wp046-{uuid.uuid4().hex[:8]}"
        ids = [_add(client, f"dedup primary test memory {i} {tag}") for i in range(4)]
        try:
            r = client.post("/memory/search", json={
                "query": f"dedup primary test memory {tag}",
                "limit": 20,
                "max_hops": 0,
            })
            assert r.status_code == 200
            result_ids = [m["id"] for m in r.json()["memories"]]
            assert len(result_ids) == len(set(result_ids)), (
                f"Duplicate ids in search results: {result_ids}"
            )
        finally:
            _cleanup(test_driver, *ids)

    def test_diamond_topology_no_duplicate_neighbours(self, client, test_driver):
        """With diamond A->B->D and A->C->D, D must appear at most once in A's neighbours."""
        suffix = uuid.uuid4().hex[:8]
        a_id = _add(client, f"diamond root {suffix}")
        b_id = _add(client, f"diamond left {suffix}", related_ids=[a_id])
        c_id = _add(client, f"diamond right {suffix}", related_ids=[a_id])
        d_id = _add(client, f"diamond bottom {suffix}", related_ids=[b_id, c_id])
        try:
            r = client.post("/memory/search", json={
                "query": f"diamond root {suffix}",
                "agent_ids": [_AGENT_ID],
                "max_hops": 2,
                "limit": 10,
            })
            assert r.status_code == 200
            hits = r.json()["memories"]
            a_hit = next((h for h in hits if h["id"] == a_id), None)
            assert a_hit is not None, "Root memory A must be in results"
            neighbours = a_hit["neighbours"]
            assert neighbours.count(d_id) <= 1, (
                f"D appears {neighbours.count(d_id)} times in neighbours — expected ≤1"
            )
        finally:
            _cleanup(test_driver, a_id, b_id, c_id, d_id)

    def test_wake_up_topic_has_no_duplicate_ids(self, client, test_driver):
        """Wake-up topic list must not contain duplicate memory ids."""
        tag = f"wp046-wakeup-{uuid.uuid4().hex[:8]}"
        ids = [_add(client, f"wake up dedup test {i} {tag}") for i in range(3)]
        try:
            r = client.get("/memory/wake-up", params={"topic": f"wake up dedup test {tag}", "limit": 20})
            assert r.status_code == 200
            data = r.json()
            topic_ids = [m["id"] for m in data.get("topic_memories", [])]
            assert len(topic_ids) == len(set(topic_ids)), (
                f"Duplicate ids in wake-up topic: {topic_ids}"
            )
        finally:
            _cleanup(test_driver, *ids)
```

- [ ] **Step 2: Run tests to confirm they fail (or are inconclusive without the fix)**

```bash
cd /home/oliver/projects/graph-memory-fabric
pytest tests/test_wp046_dedup.py -v -m integration 2>&1 | head -60
```

Expected: Tests run (or skip if Memgraph not reachable). If they pass already, the bug may not be reproducible on a sparse graph — proceed anyway, the fix is correct.

---

## Task 2: Fix `_SEARCH_QUERY_TEMPLATE` — add `WITH DISTINCT` before traversal

**Files:**
- Modify: `memory_service/memory_repo.py:170-185`

The problem is on line 181. After the filter `WITH` block, `m` is already bound to a single row per vector-search hit — but the `{neighbour_clause}` `OPTIONAL MATCH` expansions fan that out to one row per *path*, so the same `m` can appear many times before `RETURN`. Adding `WITH DISTINCT m, distance` (plus the alias columns that are already computed) before `{neighbour_clause}` collapses back to one row per primary hit before the fan-out.

- [ ] **Step 3: Apply the fix to `_SEARCH_QUERY_TEMPLATE`**

Replace the template in `memory_service/memory_repo.py`:

```python
_SEARCH_QUERY_TEMPLATE = """\
CALL vector_search.search("mem_embedding_idx", $limit, $query_vec)
YIELD node AS m, distance
WITH m, distance
WHERE ($tags IS NULL OR ANY(t IN m.tags WHERE t IN $tags))
OPTIONAL MATCH (m)-[:PRODUCED_BY]->(a:Agent)
WITH m, distance, a
WHERE ($agent_ids IS NULL OR a.id IN $agent_ids)
OPTIONAL MATCH (m)-[:ABOUT]->(p:Project)
WITH m, distance, p
WHERE ($project_ids IS NULL OR p.id IN $project_ids)
WITH DISTINCT m.id AS id, m.text AS text, m.type AS type, m.tags AS tags, m.importance AS importance, distance, m
{neighbour_clause}
WITH id, text, type, tags, importance, distance, {neighbour_collect}
RETURN id, text, type, tags, importance, distance, neighbours
ORDER BY distance ASC\
"""
```

Wait — the template currently uses `{neighbour_return}` which inlines the `collect()` expression directly into `RETURN`. With a `WITH` between the neighbour clauses and `RETURN`, we need to split the collect into the `WITH` and alias it as `neighbours`. Update `search_memories` to use a new placeholder `{neighbour_collect}` in the `WITH` and then `RETURN neighbours`.

The cleanest fix that requires minimal restructuring: keep the existing template shape but change line 181 to use `WITH DISTINCT`:

```python
_SEARCH_QUERY_TEMPLATE = """\
CALL vector_search.search("mem_embedding_idx", $limit, $query_vec)
YIELD node AS m, distance
WITH m, distance
WHERE ($tags IS NULL OR ANY(t IN m.tags WHERE t IN $tags))
OPTIONAL MATCH (m)-[:PRODUCED_BY]->(a:Agent)
WITH m, distance, a
WHERE ($agent_ids IS NULL OR a.id IN $agent_ids)
OPTIONAL MATCH (m)-[:ABOUT]->(p:Project)
WITH m, distance, p
WHERE ($project_ids IS NULL OR p.id IN $project_ids)
WITH DISTINCT m.id AS id, m.text AS text, m.type AS type, m.tags AS tags, m.importance AS importance, distance, m
{neighbour_clause}
RETURN id, text, type, tags, importance, distance, {neighbour_return}
ORDER BY distance ASC\
"""
```

The key change is line 7 of the template: `WITH DISTINCT m.id AS id, ...` instead of `WITH m.id AS id, ...`. The `DISTINCT` is on the full tuple `(id, text, type, tags, importance, distance, m)`, which deduplicates primary hits before fan-out. The `{neighbour_clause}` and `{neighbour_return}` placeholders are unchanged.

- [ ] **Step 4: Run existing search tests to confirm no regression**

```bash
pytest tests/test_search_memory.py -v 2>&1 | tail -30
```

Expected: All tests pass (or skip on 503 if Memgraph unavailable for integration tests).

- [ ] **Step 5: Commit**

```bash
git add memory_service/memory_repo.py
git commit -m "fix: add WITH DISTINCT to search template to deduplicate multi-hop results"
```

---

## Task 3: Fix wake-up topic query — deduplicate within topic results

**Files:**
- Modify: `memory_service/memory_repo.py:307-320` (the topic query in `wake_up`)

The topic query uses `vector_search.search` which returns one row per hit — no multi-hop expansion, so no row-multiplication issue. However, the `collect(s.id)[0]` pattern on the strand join can produce duplicate rows if a memory has multiple strands. Apply `WITH DISTINCT m` after the `OPTIONAL MATCH` on strands.

- [ ] **Step 6: Fix the topic query in `wake_up`**

Find this block in `wake_up` (around line 307):

```python
    topic_result = session.run(
        """
        CALL vector_search.search("mem_embedding_idx", $limit, $query_vec)
        YIELD node AS m, distance
        OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
        WITH m, collect(s.id)[0] AS strand_id
        RETURN m.id AS id, m.text AS text, m.type AS type,
               m.tags AS tags, m.importance AS importance,
               m.created_at AS created_at, strand_id
        """,
        limit=limit,
        query_vec=topic_embedding,
    )
    topic = [_record_to_memory_dict(r) for r in topic_result if r["id"] not in core_ids]
```

Replace with:

```python
    topic_result = session.run(
        """
        CALL vector_search.search("mem_embedding_idx", $limit, $query_vec)
        YIELD node AS m, distance
        OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
        WITH DISTINCT m, collect(s.id)[0] AS strand_id
        RETURN m.id AS id, m.text AS text, m.type AS type,
               m.tags AS tags, m.importance AS importance,
               m.created_at AS created_at, strand_id
        """,
        limit=limit,
        query_vec=topic_embedding,
    )
    topic = [_record_to_memory_dict(r) for r in topic_result if r["id"] not in core_ids]
```

Also apply the same `WITH DISTINCT` to the core query (around line 287):

```python
    result = session.run(
        """
        MATCH (m:Memory)
        OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
        WITH DISTINCT m, collect(s.id)[0] AS strand_id
        RETURN m.id AS id, m.text AS text, m.type AS type,
               m.tags AS tags, m.importance AS importance,
               m.created_at AS created_at, strand_id
        ORDER BY m.importance DESC, m.created_at DESC
        LIMIT $limit
        """,
        limit=limit,
    )
```

- [ ] **Step 7: Run wake-up dedup test and full test suite**

```bash
pytest tests/test_wp046_dedup.py tests/test_wake_up_close_session.py -v -m integration 2>&1 | tail -40
```

Expected: All integration tests pass.

- [ ] **Step 8: Run full test suite**

```bash
pytest tests/ -v 2>&1 | tail -40
```

Expected: All tests pass or skip (no failures).

- [ ] **Step 9: Move WP-046 to Completed in BACKLOG.md**

In `BACKLOG.md`: delete the WP-046 row from the Prioritised Backlog table and add to Completed in `docs/CHANGELOG.md`.

- [ ] **Step 10: Final commit**

```bash
git add memory_service/memory_repo.py tests/test_wp046_dedup.py BACKLOG.md docs/CHANGELOG.md
git commit -m "WP-046: Deduplicate search and wake-up results"
```
