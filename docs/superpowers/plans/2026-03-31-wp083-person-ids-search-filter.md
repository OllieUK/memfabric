# WP-083: `person_ids` Filter on `POST /memory/search` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional `person_ids: list[str]` filter to `POST /memory/search` so callers can retrieve memories anchored on specific Person nodes via `ABOUT` edges, mirroring how `add_memory` already writes `person_ids`.

**Architecture:** The Cypher search query already has a `project_ids` filter using `OPTIONAL MATCH (m)-[:ABOUT]->(p:Project)`. The `person_ids` filter follows the exact same pattern with `Person` nodes. The change touches the query template in `memory_repo.py`, the request schema in `main.py`, the Python client in `memory_client/client.py`, the MCP server in `mcp_server/server.py`, and the marabot caller in `marabot/wake_up.py`.

**Tech Stack:** FastAPI, neo4j Python driver (Bolt), Pydantic v2, pytest (integration tests against live Memgraph + FastAPI TestClient), httpx (MemoryClient), FastMCP (MCP server)

---

## File Map

| File | Change |
|------|--------|
| `memory_service/main.py` | Add `person_ids` field to `SearchMemoryRequest` |
| `memory_service/memory_repo.py` | Extend `_SEARCH_QUERY_TEMPLATE` and `search_memories()` |
| `memory_client/client.py` | Add `person_ids` kwarg to `search_memory()` |
| `mcp_server/server.py` | Add `person_ids` param to `memory_search` tool |
| `marabot/wake_up.py` | Switch `_query_person` to use `person_ids` filter |
| `tests/test_search_memory.py` | Add integration tests for `person_ids` filter |

---

## Task 1: Extend the Cypher query template and repo function

**Files:**
- Modify: `memory_service/memory_repo.py` (lines 182–274)

The existing template has this structure for `project_ids`:

```
OPTIONAL MATCH (m)-[:ABOUT]->(p:Project)
WITH m, distance, p
WHERE ($project_ids IS NULL OR p.id IN $project_ids)
```

We add the same pattern for `person_ids` immediately after, using a `Person` node alias `per` (to avoid collision with the `p` alias already used for `Project`).

- [ ] **Step 1: Write a failing integration test first** (see Task 4 — write that test now before touching implementation so it fails cleanly)

  Actually: write the test in Task 4's test file first, run it to confirm it fails with a `422 Unprocessable Entity` (field not accepted yet), then come back and implement here. Skip ahead to Task 4 Step 1 now, then return here.

- [ ] **Step 2: Update `_SEARCH_QUERY_TEMPLATE` in `memory_service/memory_repo.py`**

  Replace the current template (lines 182–199) with:

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
  OPTIONAL MATCH (m)-[:ABOUT]->(per:Person)
  WITH m, distance, per
  WHERE ($person_ids IS NULL OR per.id IN $person_ids)
  WITH DISTINCT m.id AS id, m.text AS text, m.type AS type, m.tags AS tags, m.importance AS importance, distance, m
  {neighbour_clause}
  RETURN id, text, type, tags, importance, distance, {neighbour_return}
  ORDER BY distance ASC\
  """
  ```

- [ ] **Step 3: Update `search_memories()` to pass `person_ids` as a Cypher parameter**

  In `search_memories()` (lines 254–262), the `session.run()` call currently passes:
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

  Change to:
  ```python
  result = session.run(
      query,
      query_vec=query_embedding,
      limit=req.limit,
      tags=req.tags,
      agent_ids=req.agent_ids,
      project_ids=req.project_ids,
      person_ids=getattr(req, "person_ids", None),
      min_importance=req.min_importance,
  )
  ```

  Also update the docstring for `search_memories()` to list `person_ids` among the `req` fields (line 207):
  ```python
  """Run vector search with optional filters and graph expansion.

  Args:
      session: open neo4j Session
      req: SearchMemoryRequest (query, tags, agent_ids, project_ids, person_ids,
           limit, max_hops, traversal_direction, min_importance)
      query_embedding: pre-computed embedding for req.query
      neighbour_cap: max neighbours returned per traversal direction; total per hit
          is at most 3 × neighbour_cap (RELATED_TO + causes + effects)

  Returns:
      List of dicts with keys: id, text, type, tags, importance, neighbours
  """
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add memory_service/memory_repo.py
  git commit -m "feat(search): add person_ids Cypher filter to search query template"
  ```

---

## Task 2: Add `person_ids` to the API request schema

**Files:**
- Modify: `memory_service/main.py` (lines 110–118)

- [ ] **Step 1: Add `person_ids` field to `SearchMemoryRequest`**

  Current class (lines 110–118):
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

  Change to:
  ```python
  class SearchMemoryRequest(BaseModel):
      query: str
      tags: Optional[List[str]] = None
      agent_ids: Optional[List[str]] = None
      project_ids: Optional[List[str]] = None
      person_ids: Optional[List[str]] = None
      limit: int = Field(default=10, ge=1, le=100)
      max_hops: int = Field(default=1, ge=0, le=3)
      traversal_direction: Literal["none", "causes", "effects", "both"] = "none"
      min_importance: Optional[int] = Field(default=None, ge=1, le=5)
  ```

- [ ] **Step 2: Run the integration test from Task 4 to confirm it now passes**

  ```bash
  pytest tests/test_search_memory.py::TestPersonIdsFilter -v
  ```

  Expected: all tests in `TestPersonIdsFilter` PASS.

- [ ] **Step 3: Commit**

  ```bash
  git add memory_service/main.py
  git commit -m "feat(search): expose person_ids filter in SearchMemoryRequest"
  ```

---

## Task 3: Extend `MemoryClient.search_memory()` and MCP tool

**Files:**
- Modify: `memory_client/client.py`
- Modify: `mcp_server/server.py`

### Part A — Python client

- [ ] **Step 1: Add `person_ids` kwarg to `search_memory()`**

  Current signature (lines 59–70 in `memory_client/client.py`):
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
  ```

  Change to:
  ```python
  def search_memory(
      self,
      query: str,
      *,
      tags: list[str] | None = None,
      agent_ids: list[str] | None = None,
      project_ids: list[str] | None = None,
      person_ids: list[str] | None = None,
      limit: int = 10,
      max_hops: int = 1,
      traversal_direction: str = "none",
      min_importance: int | None = None,
  ) -> list[dict]:
  ```

- [ ] **Step 2: Pass `person_ids` in the request body**

  In the same method, the `body` construction currently ends:
  ```python
  if project_ids is not None:
      body["project_ids"] = project_ids
  if min_importance is not None:
      body["min_importance"] = min_importance
  ```

  Change to:
  ```python
  if project_ids is not None:
      body["project_ids"] = project_ids
  if person_ids is not None:
      body["person_ids"] = person_ids
  if min_importance is not None:
      body["min_importance"] = min_importance
  ```

### Part B — MCP server

- [ ] **Step 3: Add `person_ids` to the `memory_search` MCP tool**

  Current tool in `mcp_server/server.py`:
  ```python
  @mcp.tool
  def memory_search(
      query: str,
      tags: list[str] | None = None,
      agent_ids: list[str] | None = None,
      limit: int = 10,
      traversal_direction: str = "none",
  ) -> list[dict]:
      """Search the memory fabric by semantic similarity."""
      with MemoryClient(base_url=settings.api_base_url) as client:
          return client.search_memory(
              query,
              tags=tags,
              agent_ids=agent_ids,
              limit=limit,
              traversal_direction=traversal_direction,
          )
  ```

  Change to:
  ```python
  @mcp.tool
  def memory_search(
      query: str,
      tags: list[str] | None = None,
      agent_ids: list[str] | None = None,
      person_ids: list[str] | None = None,
      limit: int = 10,
      traversal_direction: str = "none",
  ) -> list[dict]:
      """Search the memory fabric by semantic similarity.

      Pass person_ids to restrict results to memories linked via ABOUT edges
      to the specified Person nodes (e.g. ["mara", "oliver"]).
      """
      with MemoryClient(base_url=settings.api_base_url) as client:
          return client.search_memory(
              query,
              tags=tags,
              agent_ids=agent_ids,
              person_ids=person_ids,
              limit=limit,
              traversal_direction=traversal_direction,
          )
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add memory_client/client.py mcp_server/server.py
  git commit -m "feat(search): propagate person_ids through MemoryClient and MCP tool"
  ```

---

## Task 4: Integration tests

**Files:**
- Modify: `tests/test_search_memory.py`

Write these tests *before* implementing Tasks 1–2 (TDD). Run them first to confirm they fail with a 422, then implement, then run again to confirm they pass.

- [ ] **Step 1: Add `_add_with_person` helper and `TestPersonIdsFilter` class**

  Add the following to `tests/test_search_memory.py` (append after the existing test classes):

  ```python
  # ---------------------------------------------------------------------------
  # WP-083: person_ids filter
  # ---------------------------------------------------------------------------

  _PERSON_ID_MARA = "test-search-person-mara"
  _PERSON_ID_OLIVER = "test-search-person-oliver"


  def _ensure_person(driver, person_id: str) -> None:
      """Create a Person node if it does not exist."""
      with driver.session() as session:
          session.run(
              "MERGE (p:Person {id: $id})",
              id=person_id,
          )


  def _cleanup_persons(driver, *person_ids) -> None:
      with driver.session() as session:
          for pid in person_ids:
              session.run("MATCH (p:Person {id: $id}) DETACH DELETE p", id=pid)


  def _add_with_person(client, driver, text: str, person_id: str) -> str:
      """Insert a Memory linked to a Person node; return the memory id."""
      _ensure_person(driver, person_id)
      body = {
          "text": text,
          "type": "fact",
          "agent_id": _AGENT_ID,
          "person_ids": [person_id],
      }
      r = client.post("/memory", json=body)
      assert r.status_code == 200, f"Failed to insert memory: {r.text}"
      return r.json()["memory_id"]


  @pytest.mark.integration
  class TestPersonIdsFilter:
      def test_person_ids_filters_to_correct_person(self, client, test_driver):
          """Only memories ABOUT the specified person are returned."""
          mid_mara = _add_with_person(client, test_driver,
                                      "Mara tends to rush the last 20% of any task",
                                      _PERSON_ID_MARA)
          mid_oliver = _add_with_person(client, test_driver,
                                        "Oliver prefers async communication over meetings",
                                        _PERSON_ID_OLIVER)
          try:
              r = _search(client, "work habits", person_ids=[_PERSON_ID_MARA], limit=20)
              assert r.status_code == 200
              ids = [m["id"] for m in r.json()["memories"]]
              assert mid_mara in ids, "mara memory should be in results"
              assert mid_oliver not in ids, "oliver memory must not appear when filtering for mara"
          finally:
              _cleanup(test_driver, mid_mara, mid_oliver)
              _cleanup_persons(test_driver, _PERSON_ID_MARA, _PERSON_ID_OLIVER)

      def test_person_ids_or_semantics_across_multiple_persons(self, client, test_driver):
          """Passing two person_ids returns memories for either person."""
          mid_mara = _add_with_person(client, test_driver,
                                      "Mara is detail-oriented in written communication",
                                      _PERSON_ID_MARA)
          mid_oliver = _add_with_person(client, test_driver,
                                        "Oliver focuses on high-level strategy first",
                                        _PERSON_ID_OLIVER)
          try:
              r = _search(client, "communication style",
                          person_ids=[_PERSON_ID_MARA, _PERSON_ID_OLIVER], limit=20)
              assert r.status_code == 200
              ids = [m["id"] for m in r.json()["memories"]]
              assert mid_mara in ids
              assert mid_oliver in ids
          finally:
              _cleanup(test_driver, mid_mara, mid_oliver)
              _cleanup_persons(test_driver, _PERSON_ID_MARA, _PERSON_ID_OLIVER)

      def test_omitting_person_ids_returns_all_memories(self, client, test_driver):
          """Omitting person_ids (None) does not filter by person — existing behaviour unchanged."""
          mid_mara = _add_with_person(client, test_driver,
                                      "Mara values clear boundaries in work hours",
                                      _PERSON_ID_MARA)
          mid_oliver = _add_with_person(client, test_driver,
                                        "Oliver values clear boundaries in work hours",
                                        _PERSON_ID_OLIVER)
          try:
              r = _search(client, "work hours boundaries", limit=20)
              assert r.status_code == 200
              ids = [m["id"] for m in r.json()["memories"]]
              assert mid_mara in ids
              assert mid_oliver in ids
          finally:
              _cleanup(test_driver, mid_mara, mid_oliver)
              _cleanup_persons(test_driver, _PERSON_ID_MARA, _PERSON_ID_OLIVER)

      def test_person_ids_filter_composes_with_tags(self, client, test_driver):
          """person_ids and tags filters apply together (AND semantics)."""
          mid_tagged = _add_with_person(client, test_driver,
                                        "Mara excels at rapid prototyping",
                                        _PERSON_ID_MARA)
          # Add tag via update — or just seed with tags directly
          mid_tagged_with_tag = None
          with test_driver.session() as session:
              session.run(
                  "MATCH (m:Memory {id: $id}) SET m.tags = ['skills']",
                  id=mid_tagged,
              )
          mid_no_tag = _add_with_person(client, test_driver,
                                        "Mara prefers detailed written specs",
                                        _PERSON_ID_MARA)
          try:
              r = _search(client, "Mara capabilities",
                          person_ids=[_PERSON_ID_MARA], tags=["skills"], limit=20)
              assert r.status_code == 200
              ids = [m["id"] for m in r.json()["memories"]]
              assert mid_tagged in ids, "tagged mara memory should appear"
              assert mid_no_tag not in ids, "untagged mara memory must not appear"
          finally:
              _cleanup(test_driver, mid_tagged, mid_no_tag)
              _cleanup_persons(test_driver, _PERSON_ID_MARA)
  ```

- [ ] **Step 2: Run the tests before implementing — confirm they fail**

  ```bash
  pytest tests/test_search_memory.py::TestPersonIdsFilter -v
  ```

  Expected: FAIL — the `person_ids` field is not yet accepted (`422 Unprocessable Entity`) or the filter has no effect.

- [ ] **Step 3: Implement Tasks 1 and 2 (repo + schema), then re-run**

  ```bash
  pytest tests/test_search_memory.py::TestPersonIdsFilter -v
  ```

  Expected: all 4 tests PASS.

- [ ] **Step 4: Run the full search test suite to confirm no regressions**

  ```bash
  pytest tests/test_search_memory.py -v
  ```

  Expected: all existing tests still PASS.

- [ ] **Step 5: Commit the tests**

  ```bash
  git add tests/test_search_memory.py
  git commit -m "test(search): integration tests for person_ids filter (WP-083)"
  ```

---

## Task 5: Update `marabot/wake_up.py`

**Files:**
- Modify: `/home/oliver/projects/marabot/wake_up.py`

> **Note:** This task touches the marabot project, not graph-memory-fabric. Make sure the updated `MemoryClient` (Task 3) is installed or available to marabot before running any marabot tests.

- [ ] **Step 1: Read the current `_query_person` function**

  Open `/home/oliver/projects/marabot/wake_up.py` and locate `_query_person` (currently around lines 147–191 based on earlier exploration).

- [ ] **Step 2: Update the `client.search_memory` call to use `person_ids`**

  The current call:
  ```python
  results = client.search_memory(
      query=person_id,
      max_hops=max_hops,
      limit=limit,
  )
  ```

  Change to:
  ```python
  results = client.search_memory(
      query="",
      person_ids=[person_id],
      max_hops=max_hops,
      limit=limit,
  )
  ```

  **Why `query=""`:** The API requires `query` (it's a non-optional `str`). For a pure person filter, the semantic ranking is not meaningful — all memories anchored on the person are equally relevant. Passing an empty string produces a near-zero embedding; distance ordering is arbitrary but results are correct. This is consistent with how `project_ids` works when no semantic query is needed.

- [ ] **Step 3: Remove the client-side `min_importance` filter if it was only there because server-side wasn't exposed**

  The comment in `_query_person` says:
  > "Apply min_importance filter client-side (not supported by installed client)"

  Now that `MemoryClient.search_memory` supports `min_importance` server-side, pass it directly instead:

  ```python
  results = client.search_memory(
      query="",
      person_ids=[person_id],
      max_hops=max_hops,
      limit=limit,
      min_importance=min_importance,
  )
  ```

  Remove the client-side filter line:
  ```python
  # DELETE this line:
  results = [m for m in results if m.get("importance", 1) >= min_importance]
  ```

  Update the docstring to remove the stale note about min_importance not being supported.

- [ ] **Step 4: Commit**

  ```bash
  cd /home/oliver/projects/marabot
  git add wake_up.py
  git commit -m "fix(wake_up): use person_ids filter instead of querying by person ID string (WP-083)"
  ```

---

## Task 6: Final verification

- [ ] **Step 1: Run the full graph-memory-fabric test suite**

  From `/home/oliver/projects/graph-memory-fabric`:
  ```bash
  pytest tests/ -v -m "not integration"
  ```
  Expected: all unit tests PASS.

- [ ] **Step 2: Run integration tests against live stack**

  Ensure Memgraph is running and the FastAPI service is started (`uvicorn memory_service.main:app`), then:
  ```bash
  pytest tests/test_search_memory.py -v
  ```
  Expected: all tests PASS including `TestPersonIdsFilter`.

- [ ] **Step 3: Manual smoke test**

  ```bash
  curl -s -X POST http://localhost:8000/memory/search \
    -H "Content-Type: application/json" \
    -d '{"query": "", "person_ids": ["mara"], "limit": 5}' | python3 -m json.tool
  ```

  Expected: JSON response with `"memories": [...]` containing only memories linked via `ABOUT` to the `mara` Person node. No 422 or 500.

- [ ] **Step 4: Final commit (BACKLOG.md update)**

  Move WP-083 to Completed in BACKLOG.md and add a retrospective note, then:
  ```bash
  git add BACKLOG.md
  git commit -m "WP-083: person_ids filter on POST /memory/search"
  ```
