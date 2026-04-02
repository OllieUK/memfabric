# WP-093: Agent-Optimised Search — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance `POST /memory/search` with three coordinated additions: (1) expose cosine similarity as `score` on each hit, (2) add `min_score` threshold filter, (3) add per-hit `associated` list via graph expansion by edge weight — giving agents the tools to make intelligent context-window budget decisions.

**Architecture:** The vector search already computes `distance` internally but discards it before response assembly. This WP exposes it as `score = 1.0 - distance` on `MemoryHit`, adds `min_score` filtering in the repo layer (post-vector-search), and replaces the flat `neighbours` ID list with a richer `associated` structure that hydrates linked Memory nodes with edge weight. Person-anchored path returns `score: null` and `associated: []`. MCP surface update is out of scope (follow-on task).

**Tech Stack:** FastAPI, Pydantic, neo4j Python driver (Bolt), pytest

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `memory_service/main.py:156-180` | Add `min_score`, `neighbour_cap` to `SearchMemoryRequest`; add `score`, `associated` to `MemoryHit`; add `AssociatedMemoryHit` model |
| Modify | `memory_service/memory_repo.py:183-325` | Expose distance in results; add min_score filtering; replace neighbour expansion with weighted associated lookup |
| Modify | `memory_client/client.py:59-91` | Add `min_score` and `neighbour_cap` to `search_memory()` |
| Create | `tests/test_wp093_agent_search.py` | Unit + integration tests |

---

### Task 1: Add `score` to search response

**Files:**
- Modify: `memory_service/main.py:168-176` (MemoryHit model)
- Modify: `memory_service/memory_repo.py:307-325` (result assembly)
- Create: `tests/test_wp093_agent_search.py`

- [ ] **Step 1: Create test file with score exposure test**

Create `tests/test_wp093_agent_search.py`:

```python
# tests/test_wp093_agent_search.py
"""Tests for WP-093: agent-optimised search."""
import pytest

from tests.conftest import cleanup_nodes

_AGENT_ID = "test-agent-wp093"


def _cleanup(driver, *memory_ids):
    cleanup_nodes(driver, *memory_ids)
    with driver.session() as session:
        session.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)


def _add_body(fact: str, **kwargs) -> dict:
    body = {
        "fact": fact,
        "type": "fact",
        "agent_id": _AGENT_ID,
        "importance": 3,
    }
    body.update(kwargs)
    return body


# ---------------------------------------------------------------------------
# Task 1 — Integration: score field on MemoryHit
# ---------------------------------------------------------------------------
class TestScoreExposure:
    @pytest.mark.integration
    def test_vector_search_returns_score(self, client, test_driver):
        """Vector search hits include a numeric score field."""
        mid = None
        try:
            r = client.post("/memory", json=_add_body("WP093 score exposure test unique xyz"))
            mid = r.json()["memory_id"]

            r2 = client.post("/memory/search", json={
                "query": "WP093 score exposure test unique xyz", "limit": 5,
            })
            assert r2.status_code == 200
            hits = r2.json()["memories"]
            assert len(hits) >= 1
            hit = next(h for h in hits if h["id"] == mid)
            assert "score" in hit
            assert isinstance(hit["score"], float)
            assert 0.0 <= hit["score"] <= 1.0
        finally:
            if mid:
                _cleanup(test_driver, mid)

    @pytest.mark.integration
    def test_person_anchored_returns_null_score(self, client, test_driver):
        """Person-anchored search hits have score=null."""
        mid = None
        person_id = "person-wp093-score"
        try:
            r = client.post("/memory", json=_add_body(
                "WP093 person score test", person_ids=[person_id],
            ))
            mid = r.json()["memory_id"]

            r2 = client.post("/memory/search", json={
                "query": "anything", "person_ids": [person_id], "limit": 5,
            })
            assert r2.status_code == 200
            hits = r2.json()["memories"]
            assert len(hits) >= 1
            hit = next(h for h in hits if h["id"] == mid)
            assert hit["score"] is None
        finally:
            if mid:
                _cleanup(test_driver, mid)
            with test_driver.session() as session:
                session.run("MATCH (p:Person {id: $id}) DETACH DELETE p", id=person_id)
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/test_wp093_agent_search.py::TestScoreExposure -v -m integration`
Expected: FAIL — `score` field not in response.

- [ ] **Step 3: Add `score` to MemoryHit model**

In `memory_service/main.py`, modify `MemoryHit` (line 168-176):

```python
class MemoryHit(BaseModel):
    id: str
    text: str
    type: MemoryType
    tags: List[str]
    importance: Optional[int] = None
    score: Optional[float] = None
    strand_ids: List[str] = []
    neighbours: List[str] = []
```

- [ ] **Step 4: Include `distance` in result assembly and convert to score**

In `memory_service/memory_repo.py`, modify the result assembly in `search_memories()` (lines 307-325). The `distance` column is already returned by the Cypher query but not included in the result dict. Update the dict construction:

```python
        rows.append(
            {
                "id": rid,
                "text": record["text"],
                "type": record["type"],
                "tags": record["tags"],
                "importance": record["importance"],
                "strand_ids": list(record["strand_ids"]),
                "neighbours": record["neighbours"],
                "score": round(1.0 - record["distance"], 4) if "distance" in record.keys() else None,
            }
        )
```

For the person-anchored path, `distance` is not in the result set, so `score` will be `None`.

- [ ] **Step 5: Update endpoint handler to pass score through**

In `memory_service/main.py`, in the `search_memory` handler, ensure `score` is passed when constructing `MemoryHit`:

The existing list comprehension that builds `MemoryHit` objects from result dicts should already pick up `score` since it's now in the dict and the model. Verify the mapping code and adjust if it uses explicit field assignment rather than `**spread`.

- [ ] **Step 6: Run tests — expect PASS**

Run: `pytest tests/test_wp093_agent_search.py::TestScoreExposure -v -m integration`
Expected: PASS

- [ ] **Step 7: Run existing search tests for regressions**

Run: `pytest tests/test_search_memory.py -v`
Expected: All pass — `score` is an additive optional field.

- [ ] **Step 8: Commit**

```bash
git add memory_service/main.py memory_service/memory_repo.py tests/test_wp093_agent_search.py
git commit -m "WP-093: expose score (1-distance) on search results"
```

---

### Task 2: Add `min_score` filter

**Files:**
- Modify: `memory_service/main.py:156-165` (SearchMemoryRequest)
- Modify: `memory_service/memory_repo.py:230-325` (search_memories)
- Test: `tests/test_wp093_agent_search.py`

- [ ] **Step 1: Add min_score tests**

Append to `tests/test_wp093_agent_search.py`:

```python
# ---------------------------------------------------------------------------
# Task 2 — Integration: min_score filter
# ---------------------------------------------------------------------------
class TestMinScoreFilter:
    @pytest.mark.integration
    def test_min_score_filters_low_hits(self, client, test_driver):
        """Only hits with score >= min_score are returned."""
        mid = None
        try:
            r = client.post("/memory", json=_add_body("WP093 min_score test unique abc"))
            mid = r.json()["memory_id"]

            # Search with impossibly high min_score
            r2 = client.post("/memory/search", json={
                "query": "completely unrelated topic about marine biology",
                "min_score": 0.99,
                "limit": 10,
            })
            assert r2.status_code == 200
            hits = r2.json()["memories"]
            # All returned hits should have score >= 0.99
            for h in hits:
                assert h["score"] >= 0.99
        finally:
            if mid:
                _cleanup(test_driver, mid)

    @pytest.mark.integration
    def test_min_score_empty_list_valid(self, client, test_driver):
        """min_score that excludes everything returns empty list, not error."""
        r = client.post("/memory/search", json={
            "query": "random query for wp093",
            "min_score": 0.9999,
            "limit": 10,
        })
        assert r.status_code == 200
        # Empty list is valid
        assert isinstance(r.json()["memories"], list)

    @pytest.mark.integration
    def test_min_score_ignored_with_person_ids(self, client, test_driver):
        """min_score is ignored when person_ids is set."""
        mid = None
        person_id = "person-wp093-minscore"
        try:
            r = client.post("/memory", json=_add_body(
                "WP093 person min_score bypass", person_ids=[person_id],
            ))
            mid = r.json()["memory_id"]

            r2 = client.post("/memory/search", json={
                "query": "anything",
                "person_ids": [person_id],
                "min_score": 0.99,
                "limit": 10,
            })
            assert r2.status_code == 200
            hits = r2.json()["memories"]
            hit_ids = [h["id"] for h in hits]
            assert mid in hit_ids
        finally:
            if mid:
                _cleanup(test_driver, mid)
            with test_driver.session() as session:
                session.run("MATCH (p:Person {id: $id}) DETACH DELETE p", id=person_id)

    @pytest.mark.integration
    def test_no_min_score_returns_all(self, client, test_driver):
        """Omitting min_score returns all results (backward compatible)."""
        mid = None
        try:
            r = client.post("/memory", json=_add_body("WP093 no min_score test"))
            mid = r.json()["memory_id"]

            r2 = client.post("/memory/search", json={
                "query": "WP093 no min_score test", "limit": 10,
            })
            assert r2.status_code == 200
            assert len(r2.json()["memories"]) >= 1
        finally:
            if mid:
                _cleanup(test_driver, mid)
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/test_wp093_agent_search.py::TestMinScoreFilter -v -m integration`
Expected: FAIL — `min_score` not accepted by request model.

- [ ] **Step 3: Add `min_score` to SearchMemoryRequest**

In `memory_service/main.py`, add to `SearchMemoryRequest` (after `min_importance`):

```python
    min_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
```

- [ ] **Step 4: Apply min_score filtering in search_memories**

In `memory_service/memory_repo.py`, modify `search_memories()`. After the result assembly loop (after line 325), add min_score filtering. This must happen in Python (not Cypher) because `distance` is a YIELD value, not a node property, and Memgraph's vector_search returns a fixed top-N.

Replace the result assembly block with:

```python
    min_score = getattr(req, "min_score", None)
    use_min_score = min_score is not None and not req.person_ids

    seen: set[str] = set()
    rows = []
    for record in result:
        rid = record["id"]
        if rid in seen:
            continue
        seen.add(rid)

        score = round(1.0 - record["distance"], 4) if "distance" in record.keys() else None

        if use_min_score and score is not None and score < min_score:
            continue

        rows.append(
            {
                "id": rid,
                "text": record["text"],
                "type": record["type"],
                "tags": record["tags"],
                "importance": record["importance"],
                "strand_ids": list(record["strand_ids"]),
                "neighbours": record["neighbours"],
                "score": score,
            }
        )
    return rows
```

- [ ] **Step 5: Run tests — expect PASS**

Run: `pytest tests/test_wp093_agent_search.py::TestMinScoreFilter -v -m integration`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add memory_service/main.py memory_service/memory_repo.py tests/test_wp093_agent_search.py
git commit -m "WP-093: add min_score filter to search"
```

---

### Task 3: Add `associated` per-hit expansion

**Files:**
- Modify: `memory_service/main.py` (add `AssociatedMemoryHit` model, update `MemoryHit`)
- Modify: `memory_service/main.py` (update handler)
- Modify: `memory_service/memory_repo.py` (add associated lookup function)
- Modify: `memory_service/main.py:156-165` (add `neighbour_cap` to `SearchMemoryRequest`)
- Test: `tests/test_wp093_agent_search.py`

- [ ] **Step 1: Add associated expansion tests**

Append to `tests/test_wp093_agent_search.py`:

```python
# ---------------------------------------------------------------------------
# Task 3 — Integration: associated expansion
# ---------------------------------------------------------------------------
class TestAssociatedExpansion:
    @pytest.mark.integration
    def test_associated_returns_linked_memories(self, client, test_driver):
        """Search returns associated memories via RELATED_TO edges."""
        mid_a = mid_b = None
        try:
            # Create two related memories
            r1 = client.post("/memory", json=_add_body("WP093 the original fact about graph databases"))
            mid_a = r1.json()["memory_id"]
            r2 = client.post("/memory", json=_add_body(
                "WP093 observation about graph databases being fast",
                related_ids=[mid_a],
            ))
            mid_b = r2.json()["memory_id"]

            # Search for the observation — the original fact should appear in associated
            r3 = client.post("/memory/search", json={
                "query": "WP093 observation about graph databases being fast",
                "limit": 5,
                "neighbour_cap": 3,
            })
            assert r3.status_code == 200
            hits = r3.json()["memories"]
            hit_b = next((h for h in hits if h["id"] == mid_b), None)
            if hit_b is not None:
                assoc_ids = [a["id"] for a in hit_b.get("associated", [])]
                assert mid_a in assoc_ids
        finally:
            if mid_a:
                _cleanup(test_driver, mid_a)
            if mid_b:
                _cleanup(test_driver, mid_b)

    @pytest.mark.integration
    def test_associated_has_edge_weight(self, client, test_driver):
        """Associated entries include edge_weight."""
        mid_a = mid_b = None
        try:
            r1 = client.post("/memory", json=_add_body("WP093 weight test original"))
            mid_a = r1.json()["memory_id"]
            r2 = client.post("/memory", json=_add_body(
                "WP093 weight test related",
                related_ids=[mid_a],
            ))
            mid_b = r2.json()["memory_id"]

            r3 = client.post("/memory/search", json={
                "query": "WP093 weight test related",
                "limit": 5,
                "neighbour_cap": 3,
            })
            hits = r3.json()["memories"]
            hit_b = next((h for h in hits if h["id"] == mid_b), None)
            if hit_b and hit_b.get("associated"):
                for a in hit_b["associated"]:
                    assert "edge_weight" in a
                    assert isinstance(a["edge_weight"], (int, float))
        finally:
            if mid_a:
                _cleanup(test_driver, mid_a)
            if mid_b:
                _cleanup(test_driver, mid_b)

    @pytest.mark.integration
    def test_primary_hit_excluded_from_associated(self, client, test_driver):
        """A memory that is a primary hit does not appear in any associated list."""
        mid_a = mid_b = None
        try:
            r1 = client.post("/memory", json=_add_body("WP093 dedup primary alpha"))
            mid_a = r1.json()["memory_id"]
            r2 = client.post("/memory", json=_add_body(
                "WP093 dedup primary beta",
                related_ids=[mid_a],
            ))
            mid_b = r2.json()["memory_id"]

            r3 = client.post("/memory/search", json={
                "query": "WP093 dedup primary",
                "limit": 10,
                "neighbour_cap": 5,
            })
            hits = r3.json()["memories"]
            primary_ids = {h["id"] for h in hits}
            for hit in hits:
                for a in hit.get("associated", []):
                    assert a["id"] not in primary_ids, \
                        f"Primary hit {a['id']} should not appear in associated list"
        finally:
            if mid_a:
                _cleanup(test_driver, mid_a)
            if mid_b:
                _cleanup(test_driver, mid_b)

    @pytest.mark.integration
    def test_person_anchored_returns_empty_associated(self, client, test_driver):
        """Person-anchored search returns associated=[] for all hits."""
        mid = None
        person_id = "person-wp093-assoc"
        try:
            r = client.post("/memory", json=_add_body(
                "WP093 person assoc test", person_ids=[person_id],
            ))
            mid = r.json()["memory_id"]

            r2 = client.post("/memory/search", json={
                "query": "anything",
                "person_ids": [person_id],
                "limit": 5,
            })
            hits = r2.json()["memories"]
            for h in hits:
                assert h.get("associated", []) == []
        finally:
            if mid:
                _cleanup(test_driver, mid)
            with test_driver.session() as session:
                session.run("MATCH (p:Person {id: $id}) DETACH DELETE p", id=person_id)

    @pytest.mark.integration
    def test_neighbour_cap_zero_returns_empty(self, client, test_driver):
        """neighbour_cap=0 returns empty associated lists."""
        mid = None
        try:
            r = client.post("/memory", json=_add_body("WP093 cap zero test"))
            mid = r.json()["memory_id"]

            r2 = client.post("/memory/search", json={
                "query": "WP093 cap zero test",
                "limit": 5,
                "neighbour_cap": 0,
            })
            hits = r2.json()["memories"]
            for h in hits:
                assert h.get("associated", []) == []
        finally:
            if mid:
                _cleanup(test_driver, mid)
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/test_wp093_agent_search.py::TestAssociatedExpansion -v -m integration`
Expected: FAIL — `associated` not in response, `neighbour_cap` not accepted.

- [ ] **Step 3: Add Pydantic models**

In `memory_service/main.py`, add before `MemoryHit`:

```python
class AssociatedMemoryHit(BaseModel):
    id: str
    text: str
    type: MemoryType
    importance: Optional[int] = None
    edge_weight: float
```

Update `MemoryHit` to add `associated`:

```python
class MemoryHit(BaseModel):
    id: str
    text: str
    type: MemoryType
    tags: List[str]
    importance: Optional[int] = None
    score: Optional[float] = None
    strand_ids: List[str] = []
    neighbours: List[str] = []
    associated: List[AssociatedMemoryHit] = []
```

Add `neighbour_cap` to `SearchMemoryRequest`:

```python
    neighbour_cap: int = Field(default=3, ge=0, le=10)
```

- [ ] **Step 4: Add `fetch_associated` function to memory_repo.py**

In `memory_service/memory_repo.py`, add a new function:

```python
def fetch_associated(
    session, memory_ids: list[str], cap: int, exclude_ids: set[str]
) -> dict[str, list[dict]]:
    """For each memory_id, fetch up to cap associated memories via RELATED_TO/LEADS_TO.

    Returns dict mapping memory_id -> list of associated dicts.
    Excludes any node whose id is in exclude_ids (primary hit dedup).
    """
    if not memory_ids or cap <= 0:
        return {mid: [] for mid in memory_ids}

    result = session.run(
        """
        UNWIND $ids AS src_id
        MATCH (m:Memory {id: src_id})-[r:RELATED_TO|LEADS_TO]->(n:Memory)
        WHERE (n.status IS NULL OR n.status = 'active')
          AND (n.ephemeral IS NULL OR n.ephemeral = false)
        RETURN src_id,
               n.id AS assoc_id, n.text AS text, n.type AS type,
               n.importance AS importance,
               coalesce(r.weight, 0.5) AS edge_weight
        ORDER BY src_id, edge_weight DESC
        """,
        ids=memory_ids,
    )

    from collections import defaultdict
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in result:
        src = record["src_id"]
        aid = record["assoc_id"]
        if aid in exclude_ids:
            continue
        if len(grouped[src]) >= cap:
            continue
        grouped[src].append({
            "id": aid,
            "text": record["text"],
            "type": record["type"],
            "importance": record["importance"],
            "edge_weight": round(record["edge_weight"], 4),
        })

    return {mid: grouped.get(mid, []) for mid in memory_ids}
```

- [ ] **Step 5: Wire associated expansion into the search handler**

In `memory_service/main.py`, modify the `search_memory` endpoint handler. After getting `results` from `search_memories()`, add the associated lookup:

```python
    # Fetch associated memories for each primary hit
    primary_ids = {r["id"] for r in results}
    cap = req.neighbour_cap if not req.person_ids else 0
    associated_map = memory_repo.fetch_associated(
        session, [r["id"] for r in results], cap, primary_ids
    )
    for r in results:
        r["associated"] = associated_map.get(r["id"], [])
```

Note: This requires the `session` to still be open. The associated fetch must happen inside the `with request.app.state.driver.session() as session:` block, before building the response.

- [ ] **Step 6: Run tests — expect PASS**

Run: `pytest tests/test_wp093_agent_search.py::TestAssociatedExpansion -v -m integration`
Expected: PASS

- [ ] **Step 7: Run full search test suite**

Run: `pytest tests/test_search_memory.py tests/test_wp093_agent_search.py -v`
Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add memory_service/main.py memory_service/memory_repo.py tests/test_wp093_agent_search.py
git commit -m "WP-093: add associated expansion with edge weight and primary dedup"
```

---

### Task 4: Update MemoryClient

**Files:**
- Modify: `memory_client/client.py:59-91`
- Test: `tests/test_wp093_agent_search.py`

- [ ] **Step 1: Add client unit tests**

Append to `tests/test_wp093_agent_search.py`:

```python
import json
import httpx
import respx

from memory_client.client import MemoryClient

_BASE_URL = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Task 4 — Unit: MemoryClient passes new params
# ---------------------------------------------------------------------------
class TestClientSearchParams:
    @respx.mock
    def test_passes_min_score(self):
        respx.post(f"{_BASE_URL}/memory/search").mock(
            return_value=httpx.Response(200, json={"memories": []})
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            client.search_memory("test", min_score=0.8)
        body = json.loads(respx.calls.last.request.content)
        assert body["min_score"] == 0.8

    @respx.mock
    def test_passes_neighbour_cap(self):
        respx.post(f"{_BASE_URL}/memory/search").mock(
            return_value=httpx.Response(200, json={"memories": []})
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            client.search_memory("test", neighbour_cap=5)
        body = json.loads(respx.calls.last.request.content)
        assert body["neighbour_cap"] == 5

    @respx.mock
    def test_omitting_new_params_backward_compatible(self):
        respx.post(f"{_BASE_URL}/memory/search").mock(
            return_value=httpx.Response(200, json={"memories": []})
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            client.search_memory("test")
        body = json.loads(respx.calls.last.request.content)
        assert "min_score" not in body
        assert "neighbour_cap" not in body
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/test_wp093_agent_search.py::TestClientSearchParams -v`
Expected: FAIL — `min_score` / `neighbour_cap` not accepted.

- [ ] **Step 3: Update MemoryClient.search_memory()**

In `memory_client/client.py`, modify `search_memory()` signature. Add keyword-only params:

```python
    min_score: float | None = None,
    neighbour_cap: int | None = None,
```

In the body construction, add (conditionally, to preserve backward compat):

```python
    if min_score is not None:
        body["min_score"] = min_score
    if neighbour_cap is not None:
        body["neighbour_cap"] = neighbour_cap
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/test_wp093_agent_search.py::TestClientSearchParams -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memory_client/client.py tests/test_wp093_agent_search.py
git commit -m "WP-093: add min_score and neighbour_cap to MemoryClient.search_memory"
```

---

### Task 5: Full regression and integration test pass

- [ ] **Step 1: Run all unit tests**

Run: `pytest tests/ -v -k "not integration" --timeout=30`
Expected: All pass.

- [ ] **Step 2: Run all integration tests**

Run: `pytest tests/ -v -m integration --timeout=60`
Expected: All pass (requires live Memgraph + FastAPI).

- [ ] **Step 3: Commit test file if any additions**

```bash
git add tests/test_wp093_agent_search.py
git commit -m "WP-093: full test suite green"
```

---

### Task 6: Finalise — BACKLOG update and /simplify

- [ ] **Step 1: Move WP-093 to Completed in BACKLOG.md**
- [ ] **Step 2: Run `/simplify`**
- [ ] **Step 3: Final commit**

```bash
git add BACKLOG.md
git commit -m "WP-093: update BACKLOG — mark complete"
```
