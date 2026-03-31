# WP-080: Server-side min_importance Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional `min_importance` parameter to `POST /memory/search` so that importance filtering happens server-side in Cypher rather than requiring callers to post-filter the result set.

**Architecture:** Add `min_importance: Optional[int]` to `SearchMemoryRequest`, thread it through `memory_repo.search_memories()` into the Cypher WHERE clause alongside the existing `$tags` filter, and expose the same parameter on `MemoryClient.search_memory()`. When omitted, `$min_importance IS NULL` short-circuits the filter — zero behavioural change for existing callers.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, neo4j Bolt driver, pytest (integration tests against live Memgraph)

---

## Files

| File | Change |
|------|--------|
| `memory_service/main.py` | Add `min_importance` field to `SearchMemoryRequest` |
| `memory_service/memory_repo.py` | Add `$min_importance` filter to `_SEARCH_QUERY_TEMPLATE`; pass param in `search_memories()` |
| `memory_client/client.py` | Add `min_importance` keyword arg to `search_memory()` |
| `tests/test_search_memory.py` | Add `TestSearchMinImportance` class |

---

## Task 1: Add `min_importance` to `SearchMemoryRequest`

**Files:**
- Modify: `memory_service/main.py` (the `SearchMemoryRequest` class, around line 110)

- [ ] **Step 1: Read the current SearchMemoryRequest**

  Open `memory_service/main.py` and locate `SearchMemoryRequest`. It currently looks like:

  ```python
  class SearchMemoryRequest(BaseModel):
      query: str
      tags: Optional[List[str]] = None
      agent_ids: Optional[List[str]] = None
      project_ids: Optional[List[str]] = None
      limit: int = Field(default=10, ge=1, le=100)
      max_hops: int = Field(default=1, ge=0, le=3)
      traversal_direction: Literal["none", "causes", "effects", "both"] = "none"
  ```

- [ ] **Step 2: Add the new field**

  Add `min_importance` at the end of the model, after `traversal_direction`:

  ```python
  class SearchMemoryRequest(BaseModel):
      query: str
      tags: Optional[List[str]] = None
      agent_ids: Optional[List[str]] = None
      project_ids: Optional[List[str]] = None
      limit: int = Field(default=10, ge=1, le=100)
      max_hops: int = Field(default=1, ge=0, le=3)
      traversal_direction: Literal["none", "causes", "effects", "both"] = "none"
      min_importance: Optional[int] = Field(default=None, ge=1, le=5)
  ```

  No other changes to `main.py` at this step.

- [ ] **Step 3: Verify the service still starts (smoke check)**

  ```bash
  cd /home/oliver/projects/graph-memory-fabric
  python -c "from memory_service.main import app; print('OK')"
  ```

  Expected output: `OK`

---

## Task 2: Add `min_importance` filter to the Cypher query template

**Files:**
- Modify: `memory_service/memory_repo.py` (the `_SEARCH_QUERY_TEMPLATE` string and `search_memories()` function)

- [ ] **Step 1: Locate `_SEARCH_QUERY_TEMPLATE`**

  Open `memory_service/memory_repo.py`. The template is around line 182 and looks like:

  ```python
  _SEARCH_QUERY_TEMPLATE = """\
  CALL vector_search.search("mem_embedding_idx", $limit, $query_vec)
  YIELD node AS m, distance
  WITH m, distance
  WHERE (m.status IS NULL OR m.status = 'active')
  AND   ($tags IS NULL OR ANY(t IN m.tags WHERE t IN $tags))
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

- [ ] **Step 2: Add the importance filter**

  Insert the `min_importance` WHERE condition immediately after the `$tags` line (both conditions are simple property filters on `m` with no intervening MATCH, so they belong together):

  ```python
  _SEARCH_QUERY_TEMPLATE = """\
  CALL vector_search.search("mem_embedding_idx", $limit, $query_vec)
  YIELD node AS m, distance
  WITH m, distance
  WHERE (m.status IS NULL OR m.status = 'active')
  AND   ($tags IS NULL OR ANY(t IN m.tags WHERE t IN $tags))
  AND   ($min_importance IS NULL OR m.importance >= $min_importance)
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

- [ ] **Step 3: Pass `min_importance` in `search_memories()`**

  Locate the `session.run()` call inside `search_memories()` (around line 255). It currently passes:

  ```python
  result = session.run(
      query,
      query_vec=query_embedding,
      limit=req.limit,
      tags=req.tags,
      agent_ids=req.agent_ids,
      project_ids=req.project_ids,
  )
  ```

  Add the new parameter:

  ```python
  result = session.run(
      query,
      query_vec=query_embedding,
      limit=req.limit,
      tags=req.tags,
      agent_ids=req.agent_ids,
      project_ids=req.project_ids,
      min_importance=req.min_importance,
  )
  ```

- [ ] **Step 4: Smoke check**

  ```bash
  cd /home/oliver/projects/graph-memory-fabric
  python -c "from memory_service.memory_repo import search_memories; print('OK')"
  ```

  Expected output: `OK`

---

## Task 3: Expose `min_importance` on `MemoryClient`

**Files:**
- Modify: `memory_client/client.py` (the `search_memory()` method)

- [ ] **Step 1: Locate `search_memory()` in the client**

  Open `memory_client/client.py`. The method signature is around line 59:

  ```python
  def search_memory(
      self,
      query: str,
      *,
      tags: list[str] | None = None,
      agent_ids: list[str] | None = None,
      project_ids: list[str] | None = None,
      limit: int = 10,
      max_hops: int = 1,
      traversal_direction: str = "none",
  ) -> list[dict]:
  ```

  And the body dict construction:

  ```python
  body: dict = {
      "query": query,
      "limit": limit,
      "max_hops": max_hops,
      "traversal_direction": traversal_direction,
  }
  if tags is not None:
      body["tags"] = tags
  if agent_ids is not None:
      body["agent_ids"] = agent_ids
  if project_ids is not None:
      body["project_ids"] = project_ids
  ```

- [ ] **Step 2: Add `min_importance` parameter and body injection**

  Update the signature and body construction:

  ```python
  def search_memory(
      self,
      query: str,
      *,
      tags: list[str] | None = None,
      agent_ids: list[str] | None = None,
      project_ids: list[str] | None = None,
      limit: int = 10,
      max_hops: int = 1,
      traversal_direction: str = "none",
      min_importance: int | None = None,
  ) -> list[dict]:
      """POST /memory/search. Returns list of MemoryHit dicts."""
      body: dict = {
          "query": query,
          "limit": limit,
          "max_hops": max_hops,
          "traversal_direction": traversal_direction,
      }
      if tags is not None:
          body["tags"] = tags
      if agent_ids is not None:
          body["agent_ids"] = agent_ids
      if project_ids is not None:
          body["project_ids"] = project_ids
      if min_importance is not None:
          body["min_importance"] = min_importance
      response = self._http.post("/memory/search", json=body)
      response.raise_for_status()
      return response.json()["memories"]
  ```

- [ ] **Step 3: Smoke check**

  ```bash
  cd /home/oliver/projects/graph-memory-fabric
  python -c "from memory_client.client import MemoryClient; print('OK')"
  ```

  Expected output: `OK`

---

## Task 4: Write integration tests for `min_importance`

**Files:**
- Modify: `tests/test_search_memory.py` (add `TestSearchMinImportance` class at the end of the file, before any closing comments)

The `_add()` helper in this file does not expose `importance`. The add endpoint (`POST /memory`) accepts `importance` as an int field (default 3). We need to pass it directly in the body. Use the existing `client.post("/memory", json=body)` pattern rather than `_add()`.

- [ ] **Step 1: Write the failing tests**

  Add this class at the end of `tests/test_search_memory.py`:

  ```python
  class TestSearchMinImportance:
      """Server-side importance filtering via min_importance parameter."""

      def _add_with_importance(self, client, text, importance):
          """Insert a Memory with an explicit importance level and return its id."""
          r = client.post("/memory", json={
              "text": text,
              "type": "fact",
              "agent_id": _AGENT_ID,
              "importance": importance,
          })
          assert r.status_code == 200, f"Failed to insert memory: {r.text}"
          return r.json()["memory_id"]

      def test_min_importance_excludes_below_threshold(self, client, test_driver):
          """Memories with importance < min_importance are not returned."""
          low_id = self._add_with_importance(
              client, "low importance zebra fact alpha", importance=2
          )
          high_id = self._add_with_importance(
              client, "high importance zebra fact alpha", importance=4
          )
          try:
              r = _search(client, "zebra fact alpha", min_importance=3, limit=10)
              assert r.status_code == 200
              ids = [m["id"] for m in r.json()["memories"]]
              assert low_id not in ids, "Memory with importance=2 should be excluded by min_importance=3"
              assert high_id in ids, "Memory with importance=4 should be included by min_importance=3"
          finally:
              _cleanup(test_driver, low_id, high_id)

      def test_min_importance_includes_at_threshold(self, client, test_driver):
          """A memory whose importance equals min_importance is included."""
          exact_id = self._add_with_importance(
              client, "exact importance zebra threshold beta", importance=3
          )
          try:
              r = _search(client, "exact importance zebra threshold beta", min_importance=3, limit=10)
              assert r.status_code == 200
              ids = [m["id"] for m in r.json()["memories"]]
              assert exact_id in ids, "Memory with importance=3 should be included by min_importance=3"
          finally:
              _cleanup(test_driver, exact_id)

      def test_min_importance_omitted_returns_all(self, client, test_driver):
          """When min_importance is omitted, all importances are returned."""
          low_id = self._add_with_importance(
              client, "omitted filter zebra fact gamma", importance=1
          )
          high_id = self._add_with_importance(
              client, "omitted filter zebra fact gamma high", importance=5
          )
          try:
              r = _search(client, "omitted filter zebra fact gamma", limit=10)
              assert r.status_code == 200
              ids = [m["id"] for m in r.json()["memories"]]
              assert low_id in ids, "importance=1 memory should appear when min_importance is omitted"
              assert high_id in ids, "importance=5 memory should appear when min_importance is omitted"
          finally:
              _cleanup(test_driver, low_id, high_id)

      def test_min_importance_zero_rejected(self, client, test_driver):
          """min_importance=0 is below the valid range (1–5) and should return 422."""
          r = _search(client, "any query", min_importance=0)
          assert r.status_code == 422

      def test_min_importance_six_rejected(self, client, test_driver):
          """min_importance=6 is above the valid range (1–5) and should return 422."""
          r = _search(client, "any query", min_importance=6)
          assert r.status_code == 422
  ```

- [ ] **Step 2: Run the new tests to confirm they fail (red phase)**

  ```bash
  cd /home/oliver/projects/graph-memory-fabric
  pytest tests/test_search_memory.py::TestSearchMinImportance -v
  ```

  Expected: all 5 tests FAIL (the parameter does not exist yet in this test-first run — if you are doing the tasks in order the implementation is already in place, so they should PASS; this step confirms tests are syntactically valid).

---

## Task 5: Run the full search test suite and commit

- [ ] **Step 1: Run the full test file against the live stack**

  The live stack (Memgraph + FastAPI) must be running. If not:
  ```bash
  cd /home/oliver/projects/graph-memory-fabric
  bash scripts/start-local-stack.sh
  ```

  Then run:
  ```bash
  pytest tests/test_search_memory.py -v
  ```

  Expected: all tests PASS, including the 5 new `TestSearchMinImportance` tests.

- [ ] **Step 2: Run the broader test suite for regressions**

  ```bash
  pytest tests/ -v --ignore=tests/test_wake_up_close_session.py
  ```

  Expected: all tests PASS. (`test_wake_up_close_session.py` requires special setup — skip unless already running.)

- [ ] **Step 3: Move WP-080 to Currently In Progress in BACKLOG.md**

  In `BACKLOG.md`, add a row to the "Currently In Progress" table:

  ```
  | WP-080 | Server-side `min_importance` filter on memory search | R1 | H | L | — |
  ```

- [ ] **Step 4: Commit**

  ```bash
  cd /home/oliver/projects/graph-memory-fabric
  git add memory_service/main.py memory_service/memory_repo.py memory_client/client.py tests/test_search_memory.py BACKLOG.md
  git commit -m "WP-080: server-side min_importance filter on memory search"
  ```

---

## Task 6: Update BACKLOG.md to mark WP-080 Done

- [ ] **Step 1: Move WP-080 to Completed**

  Remove the WP-080 row from "Currently In Progress" and add it to `docs/CHANGELOG.md` (following the existing pattern for completed WPs).

- [ ] **Step 2: Renumber Order-IDs in Prioritised Backlog**

  WP-080 was at position 1. Remove it from the table and decrement every subsequent Order-ID by 1 so the sequence stays contiguous.

- [ ] **Step 3: Add retrospective note to BACKLOG.md**

  Under a `## Retrospective` section (or inline with the completed entry in CHANGELOG.md), add:
  > **WP-080:** Went well — straightforward parameter threading with zero behavioural change for existing callers. Consider extending the same pattern to `min_strength` in future if callers need decay-aware filtering server-side.

- [ ] **Step 4: Final commit**

  ```bash
  git add BACKLOG.md docs/CHANGELOG.md
  git commit -m "WP-080: mark Done, update backlog and changelog"
  ```
