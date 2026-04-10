# WP-127 — File Provenance on Memory Nodes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `files_modified` and `files_read` list properties to Memory nodes, expose them through add/update/search/by-file API endpoints, and extend the Python client.

**Architecture:** Add two optional `list[str]` fields to the Pydantic request/response models, persist them in the existing Cypher write paths (`add_memory` Step 1, `update_memory` scalar SET clause), add two WHERE predicates to the search query template, and add a new `GET /memory/by-file` endpoint that queries purely by file path without a vector search.

**Tech Stack:** FastAPI, Pydantic v2, Memgraph Cypher, neo4j Python driver, pytest, httpx

---

## Files

| File | Change |
|---|---|
| `memory_service/main.py` | Add fields to `AddMemoryRequest`, `UpdateMemoryRequest`, `MemoryHit`, `SearchMemoryRequest`; add `GET /memory/by-file` endpoint; hydrate `files_modified`/`files_read` in search result assembly |
| `memory_service/memory_repo.py` | Add `files_modified`/`files_read` to `add_memory` Cypher; add scalar SET handling in `update_memory`; add `get_memories_by_file()` repo function; extend `search_memories` return rows and query templates |
| `memory_client/client.py` | Add `files_modified`/`files_read` params to `add_memory()`, `update_memory()`; add `get_memories_by_file()` method |
| `tests/test_wp127_file_provenance.py` | All unit and integration tests for this WP |

---

## Task 1: Add fields to Pydantic models

**Files:**
- Modify: `memory_service/main.py` (AddMemoryRequest ~line 100, UpdateMemoryRequest ~line 781, SearchMemoryRequest ~line 202, MemoryHit ~line 224)

- [ ] **Step 1: Write unit tests for model serialisation**

Create `tests/test_wp127_file_provenance.py`:

```python
import pytest
from memory_service.main import (
    AddMemoryRequest,
    UpdateMemoryRequest,
    SearchMemoryRequest,
    MemoryHit,
    MemoryType,
)


# --- AddMemoryRequest ---

def test_add_memory_request_files_modified_serialises():
    req = AddMemoryRequest(
        fact="edited memory_repo.py",
        type=MemoryType.fact,
        agent_id="test-agent",
        files_modified=["memory_service/memory_repo.py"],
    )
    data = req.model_dump()
    assert data["files_modified"] == ["memory_service/memory_repo.py"]
    assert data["files_read"] == []


def test_add_memory_request_files_read_serialises():
    req = AddMemoryRequest(
        fact="read config.py",
        type=MemoryType.fact,
        agent_id="test-agent",
        files_read=["memory_service/config.py"],
    )
    data = req.model_dump()
    assert data["files_read"] == ["memory_service/config.py"]
    assert data["files_modified"] == []


def test_add_memory_request_files_default_empty():
    req = AddMemoryRequest(
        fact="no files",
        type=MemoryType.fact,
        agent_id="test-agent",
    )
    data = req.model_dump()
    assert data["files_modified"] == []
    assert data["files_read"] == []


# --- UpdateMemoryRequest ---

def test_update_memory_request_files_modified_passes_validator():
    req = UpdateMemoryRequest(files_modified=["memory_service/main.py"])
    assert req.files_modified == ["memory_service/main.py"]


def test_update_memory_request_files_read_passes_validator():
    req = UpdateMemoryRequest(files_read=["memory_service/config.py"])
    assert req.files_read == ["memory_service/config.py"]


# --- SearchMemoryRequest ---

def test_search_memory_request_files_modified_field():
    req = SearchMemoryRequest(query="test", files_modified=["memory_service/main.py"])
    assert req.files_modified == ["memory_service/main.py"]
    assert req.files_read is None


def test_search_memory_request_files_default_none():
    req = SearchMemoryRequest(query="test")
    assert req.files_modified is None
    assert req.files_read is None


# --- MemoryHit ---

def test_memory_hit_files_fields_default_empty():
    hit = MemoryHit(
        id="abc",
        text="some text",
        type=MemoryType.fact,
        tags=[],
    )
    assert hit.files_modified == []
    assert hit.files_read == []


def test_memory_hit_files_fields_round_trip():
    hit = MemoryHit(
        id="abc",
        text="some text",
        type=MemoryType.fact,
        tags=[],
        files_modified=["memory_service/main.py"],
        files_read=["memory_service/config.py"],
    )
    data = hit.model_dump()
    assert data["files_modified"] == ["memory_service/main.py"]
    assert data["files_read"] == ["memory_service/config.py"]
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/test_wp127_file_provenance.py -v 2>&1 | head -40
```

Expected: multiple `ImportError` or `ValidationError` — fields not yet defined.

- [ ] **Step 3: Add fields to AddMemoryRequest**

In `memory_service/main.py`, find `AddMemoryRequest` (~line 100). Add after `ephemeral: bool = False`:

```python
files_modified: List[str] = []
files_read: List[str] = []
```

- [ ] **Step 4: Add fields to UpdateMemoryRequest**

In `memory_service/main.py`, find `UpdateMemoryRequest` (~line 781). Add after `org_id: Optional[str] = None`:

```python
files_modified: Optional[List[str]] = None
files_read: Optional[List[str]] = None
```

Update the `at_least_one_field` validator — add `self.files_modified, self.files_read` to the `all(v is None ...)` check:

```python
if all(v is None for v in [
    self.fact, self.so_what, self.tags,
    self.importance, self.person_ids, self.strand_ids,
    self.control_ids, self.doc_ids, self.control_relationship_type, self.org_id,
    self.files_modified, self.files_read,
]):
    raise ValueError("At least one field must be provided for update")
```

- [ ] **Step 5: Add fields to SearchMemoryRequest**

In `memory_service/main.py`, find `SearchMemoryRequest` (~line 202). Add after `neighbour_cap`:

```python
files_modified: Optional[List[str]] = None
files_read: Optional[List[str]] = None
```

- [ ] **Step 6: Add fields to MemoryHit**

In `memory_service/main.py`, find `MemoryHit` (~line 224). Add after `documents`:

```python
files_modified: List[str] = []
files_read: List[str] = []
```

- [ ] **Step 7: Run model unit tests — expect pass**

```bash
pytest tests/test_wp127_file_provenance.py -v -k "not integration"
```

Expected: all model tests pass.

- [ ] **Step 8: Commit**

```bash
git add memory_service/main.py tests/test_wp127_file_provenance.py
git commit -m "WP-127: add files_modified/files_read fields to Pydantic models"
```

---

## Task 2: Persist files_modified/files_read in add_memory

**Files:**
- Modify: `memory_service/memory_repo.py` (add_memory, ~line 78 Cypher)

- [ ] **Step 1: Write unit test for add_memory Cypher params**

Add to `tests/test_wp127_file_provenance.py`:

```python
from unittest.mock import MagicMock, patch
from memory_service import memory_repo
from memory_service.main import AddMemoryRequest, MemoryType


def test_add_memory_passes_files_to_cypher():
    """files_modified and files_read are passed as Cypher params."""
    req = AddMemoryRequest(
        fact="edited main.py",
        type=MemoryType.fact,
        agent_id="test-agent",
        files_modified=["memory_service/main.py"],
        files_read=["memory_service/config.py"],
    )
    req.text = req.fact  # simulate validator

    session = MagicMock()
    session.run.return_value = MagicMock()

    memory_repo.add_memory(
        session, req, "test-id-123", [0.1] * 384, "2026-01-01T00:00:00+00:00", 0.1
    )

    # First session.run call is the main CREATE — inspect kwargs
    call_kwargs = session.run.call_args_list[0]
    # The second positional arg (or kwargs) contains the params
    call_args = call_kwargs[0]  # positional args tuple
    call_kw = call_kwargs[1]    # keyword args dict
    # Params are passed as **kwargs to session.run
    assert call_kw.get("files_modified") == ["memory_service/main.py"]
    assert call_kw.get("files_read") == ["memory_service/config.py"]
```

- [ ] **Step 2: Run test — expect failure**

```bash
pytest tests/test_wp127_file_provenance.py::test_add_memory_passes_files_to_cypher -v
```

Expected: FAIL — `files_modified` not in Cypher params.

- [ ] **Step 3: Update add_memory Cypher and params**

In `memory_service/memory_repo.py`, find the Step 1 `session.run(...)` in `add_memory` (~line 78). Add to the Cypher node creation block:

```cypher
files_modified: $files_modified,
files_read: $files_read,
```

The full CREATE block becomes:

```python
    session.run(
        """
        MERGE (a:Agent {id: $agent_id})
        CREATE (m:Memory {
            id: $id,
            fact: $fact,
            so_what: $so_what,
            text: $text,
            type: $type,
            tags: $tags,
            importance: $importance,
            created_at: $created_at,
            last_used_at: $last_used_at,
            embedding: $embedding,
            strength: $strength,
            min_strength: $min_strength,
            recall_count: 0,
            reinforcement_count: 0,
            last_reinforced_at: $last_reinforced_at,
            decay_rate: $decay_rate,
            status: 'active',
            ephemeral: $ephemeral,
            files_modified: $files_modified,
            files_read: $files_read
        })
        CREATE (m)-[:PRODUCED_BY]->(a)
        """,
        agent_id=req.agent_id,
        id=memory_id,
        fact=req.fact,
        so_what=req.so_what,
        text=req.text,
        type=req.type.value,
        tags=req.tags,
        importance=req.importance,
        created_at=now,
        last_used_at=now,
        embedding=embedding,
        strength=initial_strength_factor * (req.importance / 5.0),
        min_strength=importance_floor_factor * (req.importance / 5.0),
        last_reinforced_at=now,
        decay_rate=decay_rate,
        ephemeral=req.ephemeral,
        files_modified=req.files_modified,
        files_read=req.files_read,
    )
```

- [ ] **Step 4: Run test — expect pass**

```bash
pytest tests/test_wp127_file_provenance.py::test_add_memory_passes_files_to_cypher -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add memory_service/memory_repo.py tests/test_wp127_file_provenance.py
git commit -m "WP-127: persist files_modified/files_read in add_memory Cypher"
```

---

## Task 3: Update update_memory to handle files fields

**Files:**
- Modify: `memory_service/memory_repo.py` (update_memory, ~line 707)
- Modify: `memory_service/main.py` (PATCH endpoint handler, ~line 800)

- [ ] **Step 1: Write unit test**

Add to `tests/test_wp127_file_provenance.py`:

```python
def test_update_memory_sets_files_modified():
    """files_modified is included in the scalar SET clause."""
    session = MagicMock()
    session.run.return_value = MagicMock()

    memory_repo.update_memory(
        session,
        memory_id="test-id",
        patch_fields={"files_modified": ["memory_service/main.py"]},
        new_embedding=None,
        now="2026-01-01T00:00:00+00:00",
    )

    # First session.run is the SET — check the query and params
    call = session.run.call_args_list[0]
    query = call[0][0]
    assert "files_modified" in query
    assert call[1]["files_modified"] == ["memory_service/main.py"]
```

- [ ] **Step 2: Run test — expect failure**

```bash
pytest tests/test_wp127_file_provenance.py::test_update_memory_sets_files_modified -v
```

Expected: FAIL — `files_modified` not handled as scalar key.

- [ ] **Step 3: Verify current scalar_keys logic in update_memory**

Read `memory_service/memory_repo.py` lines 724-741 to confirm that `scalar_keys` is built by excluding `person_ids` and `strand_ids` only. `files_modified` and `files_read` are plain list properties — they should be included automatically in `scalar_keys` without any change to the exclusion logic.

The only thing to verify: the PATCH handler in `main.py` is not stripping them before calling `update_memory`. Check `_BRIDGE_FIELDS` (~line 778 in main.py) — it should NOT include `files_modified` or `files_read`. If it doesn't, no change is needed to main.py for this step.

If `_BRIDGE_FIELDS` does NOT contain these fields, update_memory will handle them automatically via the existing `scalar_keys` loop. Run the test again to confirm.

- [ ] **Step 4: Run test — expect pass**

```bash
pytest tests/test_wp127_file_provenance.py::test_update_memory_sets_files_modified -v
```

Expected: PASS (the existing scalar_keys logic handles list fields as-is).

- [ ] **Step 5: Commit**

```bash
git add tests/test_wp127_file_provenance.py
git commit -m "WP-127: verify update_memory handles files_modified/files_read via scalar_keys"
```

---

## Task 4: Add file filter to search_memories

**Files:**
- Modify: `memory_service/memory_repo.py` (`_SEARCH_QUERY_TEMPLATE`, `_PERSON_SEARCH_QUERY_TEMPLATE`, `search_memories` return rows)
- Modify: `memory_service/main.py` (search_memory handler — pass new filter params; hydrate files fields in MemoryHit assembly)

- [ ] **Step 1: Write unit test for search filter Cypher**

Add to `tests/test_wp127_file_provenance.py`:

```python
def test_search_query_template_contains_files_modified_filter():
    """_SEARCH_QUERY_TEMPLATE includes files_modified ANY predicate when present."""
    from memory_service.memory_repo import _build_file_filter_clause
    clause = _build_file_filter_clause(files_modified=["main.py"], files_read=None)
    assert "ANY(f IN m.files_modified WHERE f IN $files_modified)" in clause


def test_search_query_template_contains_files_read_filter():
    from memory_service.memory_repo import _build_file_filter_clause
    clause = _build_file_filter_clause(files_modified=None, files_read=["config.py"])
    assert "ANY(f IN m.files_read WHERE f IN $files_read)" in clause


def test_search_query_template_no_filter_empty_clause():
    from memory_service.memory_repo import _build_file_filter_clause
    clause = _build_file_filter_clause(files_modified=None, files_read=None)
    assert clause == ""
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/test_wp127_file_provenance.py -k "file_filter" -v
```

Expected: FAIL — `_build_file_filter_clause` not defined.

- [ ] **Step 3: Add `_build_file_filter_clause` helper to memory_repo.py**

Add after the `_PERSON_SEARCH_QUERY_TEMPLATE` definition in `memory_service/memory_repo.py`:

```python
def _build_file_filter_clause(
    files_modified: list[str] | None,
    files_read: list[str] | None,
) -> str:
    """Build AND predicates for file provenance filtering.

    Returns a string of zero or more AND clauses to append to a WHERE block.
    Empty string means no file filter is active.
    """
    parts = []
    if files_modified:
        parts.append("AND ANY(f IN m.files_modified WHERE f IN $files_modified)")
    if files_read:
        parts.append("AND ANY(f IN m.files_read WHERE f IN $files_read)")
    return "\n".join(parts)
```

- [ ] **Step 4: Run helper tests — expect pass**

```bash
pytest tests/test_wp127_file_provenance.py -k "file_filter" -v
```

Expected: all three PASS.

- [ ] **Step 5: Wire file filter into search_memories**

In `memory_service/memory_repo.py`, update `search_memories` to accept and apply the file filter. The function signature currently takes `req` generically, so no signature change is needed — just use `getattr` to read the new fields safely:

In `search_memories`, just before the `if req.person_ids:` branch (~line 329), add:

```python
files_modified = getattr(req, "files_modified", None)
files_read = getattr(req, "files_read", None)
file_filter = _build_file_filter_clause(files_modified, files_read)
```

Then update `_SEARCH_QUERY_TEMPLATE` to include `{file_filter}` in the WHERE block. Find the template (~line 233) and update the WHERE section:

```python
_SEARCH_QUERY_TEMPLATE = """\
CALL vector_search.search("mem_embedding_idx", $limit, $query_vec)
YIELD node AS m, distance
WITH m, distance
WHERE (m.status IS NULL OR m.status = 'active')
AND   (m.ephemeral IS NULL OR m.ephemeral = false)
AND   ($tags IS NULL OR ANY(t IN m.tags WHERE t IN $tags))
AND   ($min_importance IS NULL OR m.importance >= $min_importance)
{file_filter}
OPTIONAL MATCH (m)-[:PRODUCED_BY]->(a:Agent)
WITH m, distance, a
WHERE ($agent_ids IS NULL OR a.id IN $agent_ids)
OPTIONAL MATCH (m)-[:ABOUT]->(p:Project)
WITH m, distance, p
WHERE ($project_ids IS NULL OR p.id IN $project_ids)
OPTIONAL MATCH (m)-[:ABOUT]->(per:Person)
WITH m, distance, per
WHERE ($person_ids IS NULL OR per.id IN $person_ids)
OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
WITH DISTINCT m, distance, collect(DISTINCT s.id) AS strand_ids
{neighbour_clause}
RETURN m.id AS id, m.text AS text, m.type AS type, m.tags AS tags,
       m.importance AS importance, distance, strand_ids,
       coalesce(m.files_modified, []) AS files_modified,
       coalesce(m.files_read, []) AS files_read,
       {neighbour_return}
ORDER BY distance ASC\
"""
```

Do the same for `_PERSON_SEARCH_QUERY_TEMPLATE`:

```python
_PERSON_SEARCH_QUERY_TEMPLATE = """\
MATCH (m:Memory)-[:ABOUT]->(per:Person)
WHERE per.id IN $person_ids
AND   (m.status IS NULL OR m.status = 'active')
AND   (m.ephemeral IS NULL OR m.ephemeral = false)
AND   ($tags IS NULL OR ANY(t IN m.tags WHERE t IN $tags))
AND   ($min_importance IS NULL OR m.importance >= $min_importance)
{file_filter}
OPTIONAL MATCH (m)-[:PRODUCED_BY]->(a:Agent)
WITH m, a
WHERE ($agent_ids IS NULL OR a.id IN $agent_ids)
OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
WITH DISTINCT m, collect(DISTINCT s.id) AS strand_ids
{neighbour_clause}
RETURN m.id AS id, m.text AS text, m.type AS type, m.tags AS tags,
       m.importance AS importance, coalesce(m.strength, 0.0) AS strength, strand_ids,
       coalesce(m.files_modified, []) AS files_modified,
       coalesce(m.files_read, []) AS files_read,
       {neighbour_return}
ORDER BY importance DESC, strength DESC
LIMIT $limit\
"""
```

Update both `.format(...)` calls in `search_memories` to pass `file_filter=file_filter`:

```python
query = _SEARCH_QUERY_TEMPLATE.format(
    neighbour_clause=neighbour_clauses,
    neighbour_return=neighbour_return,
    file_filter=file_filter,
)
```

and:

```python
query = _PERSON_SEARCH_QUERY_TEMPLATE.format(
    neighbour_clause=neighbour_clauses,
    neighbour_return=neighbour_return,
    file_filter=file_filter,
)
```

Also add `files_modified` and `files_read` to the params dict passed to `session.run` in each branch:

```python
result = session.run(
    query,
    query_vec=query_embedding,
    limit=req.limit,
    tags=req.tags,
    agent_ids=req.agent_ids,
    project_ids=req.project_ids,
    person_ids=None,
    min_importance=req.min_importance,
    files_modified=files_modified,
    files_read=files_read,
)
```

And for the person branch:

```python
result = session.run(
    query,
    person_ids=req.person_ids,
    limit=req.limit,
    tags=req.tags,
    agent_ids=req.agent_ids,
    min_importance=req.min_importance,
    files_modified=files_modified,
    files_read=files_read,
)
```

Update the return rows in `search_memories` (the `rows.append(...)` block ~line 375) to include the new fields:

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
        "score": score,
        "files_modified": list(record.get("files_modified") or []),
        "files_read": list(record.get("files_read") or []),
    }
)
```

- [ ] **Step 6: Hydrate files fields in search_memory handler**

In `memory_service/main.py`, update the `MemoryHit(...)` assembly in `search_memory` (~line 284) to pass the new fields:

```python
MemoryHit(
    id=r["id"],
    text=r["text"],
    type=r["type"],
    tags=r["tags"],
    importance=r["importance"],
    score=r.get("score"),
    strand_ids=r["strand_ids"],
    neighbours=r["neighbours"],
    associated=[AssociatedMemoryHit(**a) for a in associated_map.get(r["id"], [])],
    controls=hydration.get(r["id"], {}).get("controls", []),
    documents=hydration.get(r["id"], {}).get("documents", []),
    files_modified=r.get("files_modified", []),
    files_read=r.get("files_read", []),
)
```

- [ ] **Step 7: Run model tests — expect still pass**

```bash
pytest tests/test_wp127_file_provenance.py -v -k "not integration"
```

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add memory_service/memory_repo.py memory_service/main.py tests/test_wp127_file_provenance.py
git commit -m "WP-127: file filter in search_memories; files fields in MemoryHit"
```

---

## Task 5: Add GET /memory/by-file endpoint

**Files:**
- Modify: `memory_service/memory_repo.py` (add `get_memories_by_file()`)
- Modify: `memory_service/main.py` (add `GET /memory/by-file` endpoint)

- [ ] **Step 1: Write unit test for repo function**

Add to `tests/test_wp127_file_provenance.py`:

```python
def test_get_memories_by_file_role_modified_uses_correct_predicate():
    """role=modified queries files_modified only."""
    session = MagicMock()
    session.run.return_value = iter([])

    memory_repo.get_memories_by_file(session, path="memory_service/main.py", role="modified", limit=10)

    call = session.run.call_args_list[0]
    query = call[0][0]
    assert "m.files_modified" in query
    assert "m.files_read" not in query
    assert call[1]["path"] == "memory_service/main.py"


def test_get_memories_by_file_role_read_uses_correct_predicate():
    session = MagicMock()
    session.run.return_value = iter([])

    memory_repo.get_memories_by_file(session, path="memory_service/config.py", role="read", limit=10)

    call = session.run.call_args_list[0]
    query = call[0][0]
    assert "m.files_read" in query
    assert "m.files_modified" not in query


def test_get_memories_by_file_role_any_uses_both_predicates():
    session = MagicMock()
    session.run.return_value = iter([])

    memory_repo.get_memories_by_file(session, path="memory_service/main.py", role="any", limit=10)

    call = session.run.call_args_list[0]
    query = call[0][0]
    assert "m.files_modified" in query
    assert "m.files_read" in query
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/test_wp127_file_provenance.py -k "get_memories_by_file" -v
```

Expected: FAIL — `get_memories_by_file` not defined.

- [ ] **Step 3: Add get_memories_by_file to memory_repo.py**

Add after `get_memory_for_update` in `memory_service/memory_repo.py`:

```python
def get_memories_by_file(
    session,
    path: str,
    role: str = "any",
    limit: int = 20,
) -> list[dict]:
    """Return active memories where path appears in files_modified, files_read, or both.

    Args:
        session: open neo4j Session
        path: exact file path string to match against list elements
        role: 'modified' | 'read' | 'any'
        limit: max results

    Returns:
        List of dicts with keys: id, text, type, tags, importance, strand_ids,
        files_modified, files_read
    """
    if role == "modified":
        where_clause = "ANY(f IN m.files_modified WHERE f = $path)"
    elif role == "read":
        where_clause = "ANY(f IN m.files_read WHERE f = $path)"
    else:  # any
        where_clause = (
            "(ANY(f IN m.files_modified WHERE f = $path) "
            "OR ANY(f IN m.files_read WHERE f = $path))"
        )

    result = session.run(
        f"""
        MATCH (m:Memory)
        WHERE (m.status IS NULL OR m.status = 'active')
          AND (m.ephemeral IS NULL OR m.ephemeral = false)
          AND {where_clause}
        OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
        WITH DISTINCT m, collect(DISTINCT s.id) AS strand_ids
        RETURN m.id AS id, m.text AS text, m.type AS type, m.tags AS tags,
               m.importance AS importance,
               coalesce(m.files_modified, []) AS files_modified,
               coalesce(m.files_read, []) AS files_read,
               strand_ids
        ORDER BY m.importance DESC, m.created_at DESC
        LIMIT $limit
        """,
        path=path,
        limit=limit,
    )
    return [
        {
            "id": record["id"],
            "text": record["text"],
            "type": record["type"],
            "tags": record["tags"],
            "importance": record["importance"],
            "strand_ids": list(record["strand_ids"]),
            "files_modified": list(record["files_modified"] or []),
            "files_read": list(record["files_read"] or []),
        }
        for record in result
    ]
```

- [ ] **Step 4: Run repo unit tests — expect pass**

```bash
pytest tests/test_wp127_file_provenance.py -k "get_memories_by_file" -v
```

Expected: all PASS.

- [ ] **Step 5: Add GET /memory/by-file endpoint to main.py**

In `memory_service/main.py`, add after the `search_memory` endpoint (~line 303):

```python
class ByFileResponse(BaseModel):
    memories: List[MemoryHit]


@app.get("/memory/by-file", response_model=ByFileResponse)
async def get_memories_by_file(
    request: Request,
    path: str = Query(..., description="File path to match (exact)"),
    role: Literal["modified", "read", "any"] = Query(default="any"),
    limit: int = Query(default=20, ge=1, le=100),
) -> ByFileResponse:
    try:
        with request.app.state.driver.session() as session:
            results = memory_repo.get_memories_by_file(session, path=path, role=role, limit=limit)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return ByFileResponse(
        memories=[
            MemoryHit(
                id=r["id"],
                text=r["text"],
                type=r["type"],
                tags=r["tags"],
                importance=r["importance"],
                strand_ids=r["strand_ids"],
                files_modified=r["files_modified"],
                files_read=r["files_read"],
            )
            for r in results
        ]
    )
```

Also add `Literal` to the imports at the top of `main.py` if not already present (it is already used for `control_relationship_type`, so it should be there).

- [ ] **Step 6: Run all unit tests**

```bash
pytest tests/test_wp127_file_provenance.py -v -k "not integration"
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add memory_service/memory_repo.py memory_service/main.py tests/test_wp127_file_provenance.py
git commit -m "WP-127: add get_memories_by_file repo function and GET /memory/by-file endpoint"
```

---

## Task 6: Extend memory_client

**Files:**
- Modify: `memory_client/client.py`

- [ ] **Step 1: Write client unit tests**

Add to `tests/test_wp127_file_provenance.py`:

```python
import httpx
import respx
from memory_client.client import MemoryClient


@respx.mock
def test_client_add_memory_passes_files_modified():
    respx.post("http://localhost:8000/memory").mock(
        return_value=httpx.Response(200, json={"memory_id": "abc", "deduplicated": False, "strand_ids": []})
    )
    with MemoryClient(base_url="http://localhost:8000") as client:
        client.add_memory(
            fact="edited main.py",
            type="fact",
            agent_id="test-agent",
            files_modified=["memory_service/main.py"],
        )
    request = respx.calls[0].request
    import json
    body = json.loads(request.content)
    assert body["files_modified"] == ["memory_service/main.py"]


@respx.mock
def test_client_get_memories_by_file():
    respx.get("http://localhost:8000/memory/by-file").mock(
        return_value=httpx.Response(200, json={"memories": []})
    )
    with MemoryClient(base_url="http://localhost:8000") as client:
        result = client.get_memories_by_file("memory_service/main.py", role="modified")
    assert result == []
    request = respx.calls[0].request
    assert "path=memory_service" in str(request.url)
    assert "role=modified" in str(request.url)
```

- [ ] **Step 2: Run client tests — expect failure**

```bash
pytest tests/test_wp127_file_provenance.py -k "client" -v
```

Expected: FAIL — `files_modified` not in `add_memory`; `get_memories_by_file` not defined.

- [ ] **Step 3: Update add_memory in client.py**

In `memory_client/client.py`, find `add_memory` (~line 19). Add two keyword params:

```python
def add_memory(
    self,
    fact: str,
    type: str,
    agent_id: str,
    *,
    so_what: str | None = None,
    cause_ids: list[str] | None = None,
    effect_ids: list[str] | None = None,
    tags: list[str] | None = None,
    importance: int = 3,
    strand_ids: list[str] | None = None,
    person_ids: list[str] | None = None,
    project_id: str | None = None,
    related_ids: list[str] | None = None,
    control_ids: list[str] | None = None,
    doc_ids: list[str] | None = None,
    control_relationship_type: str | None = None,
    org_id: str | None = None,
    files_modified: list[str] | None = None,
    files_read: list[str] | None = None,
) -> dict:
```

In the body, add to the `body` dict construction (alongside the existing `if org_id is not None:` block):

```python
if files_modified is not None:
    body["files_modified"] = files_modified
if files_read is not None:
    body["files_read"] = files_read
```

- [ ] **Step 4: Update update_memory in client.py**

Find `update_memory` (~line 198). Add the two new params:

```python
files_modified: list[str] | None = None,
files_read: list[str] | None = None,
```

In the body construction:

```python
if files_modified is not None:
    body["files_modified"] = files_modified
if files_read is not None:
    body["files_read"] = files_read
```

- [ ] **Step 5: Add get_memories_by_file to client.py**

After `update_memory`, add:

```python
def get_memories_by_file(
    self,
    path: str,
    *,
    role: str = "any",
    limit: int = 20,
) -> list[dict]:
    """GET /memory/by-file. Returns list of MemoryHit dicts filtered by file path."""
    params: dict = {"path": path, "role": role, "limit": limit}
    response = self._http.get("/memory/by-file", params=params)
    response.raise_for_status()
    return response.json()["memories"]
```

- [ ] **Step 6: Run client tests — expect pass**

```bash
pytest tests/test_wp127_file_provenance.py -k "client" -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add memory_client/client.py tests/test_wp127_file_provenance.py
git commit -m "WP-127: extend memory_client with files_modified/files_read and get_memories_by_file"
```

---

## Task 7: Integration tests (live stack required)

**Prerequisite:** Memgraph running, FastAPI service running (`uvicorn memory_service.main:app`).

**Files:**
- Modify: `tests/test_wp127_file_provenance.py`

- [ ] **Step 1: Write integration tests**

Add to `tests/test_wp127_file_provenance.py`:

```python
import pytest
from memory_client.client import MemoryClient


@pytest.fixture
def mem_client():
    with MemoryClient(base_url="http://localhost:8000") as c:
        yield c


@pytest.fixture
def cleanup_memory(mem_client):
    """Track memory IDs created during test and delete them after."""
    created_ids = []
    yield created_ids
    # Cleanup: archive each created memory (no hard delete in v1)
    for mid in created_ids:
        try:
            mem_client._http.post(f"/memory/{mid}/archive")
        except Exception:
            pass


@pytest.mark.integration
def test_integration_add_and_retrieve_by_file_modified(mem_client, cleanup_memory):
    result = mem_client.add_memory(
        fact="Integration test: refactored add_memory to support file provenance",
        type="fact",
        agent_id="test-agent",
        importance=2,
        files_modified=["memory_service/memory_repo.py"],
        tags=["wp127-test"],
    )
    mid = result["memory_id"]
    cleanup_memory.append(mid)

    hits = mem_client.get_memories_by_file(
        "memory_service/memory_repo.py", role="modified"
    )
    ids = [h["id"] for h in hits]
    assert mid in ids


@pytest.mark.integration
def test_integration_role_read_excludes_modified_only(mem_client, cleanup_memory):
    result = mem_client.add_memory(
        fact="Integration test: file stored as modified only",
        type="fact",
        agent_id="test-agent",
        importance=2,
        files_modified=["memory_service/memory_repo.py"],
        tags=["wp127-test"],
    )
    mid = result["memory_id"]
    cleanup_memory.append(mid)

    # role=read should NOT return this memory
    hits = mem_client.get_memories_by_file(
        "memory_service/memory_repo.py", role="read"
    )
    ids = [h["id"] for h in hits]
    assert mid not in ids


@pytest.mark.integration
def test_integration_role_any_returns_both(mem_client, cleanup_memory):
    r1 = mem_client.add_memory(
        fact="Integration test: modified file",
        type="fact",
        agent_id="test-agent",
        importance=2,
        files_modified=["memory_service/main.py"],
        tags=["wp127-test"],
    )
    r2 = mem_client.add_memory(
        fact="Integration test: read file",
        type="fact",
        agent_id="test-agent",
        importance=2,
        files_read=["memory_service/main.py"],
        tags=["wp127-test"],
    )
    cleanup_memory.extend([r1["memory_id"], r2["memory_id"]])

    hits = mem_client.get_memories_by_file("memory_service/main.py", role="any")
    ids = [h["id"] for h in hits]
    assert r1["memory_id"] in ids
    assert r2["memory_id"] in ids


@pytest.mark.integration
def test_integration_search_with_files_modified_filter(mem_client, cleanup_memory):
    r = mem_client.add_memory(
        fact="Integration test: search filter for file provenance",
        type="fact",
        agent_id="test-agent",
        importance=3,
        files_modified=["memory_service/config.py"],
        tags=["wp127-test"],
    )
    cleanup_memory.append(r["memory_id"])

    results = mem_client.search_memory(
        "file provenance integration test",
        files_modified=["memory_service/config.py"],
    )
    ids = [m["id"] for m in results]
    assert r["memory_id"] in ids


@pytest.mark.integration
def test_integration_memory_hit_includes_files_fields(mem_client, cleanup_memory):
    r = mem_client.add_memory(
        fact="Integration test: MemoryHit should include files fields",
        type="fact",
        agent_id="test-agent",
        importance=3,
        files_modified=["memory_service/main.py"],
        files_read=["memory_service/config.py"],
        tags=["wp127-test"],
    )
    cleanup_memory.append(r["memory_id"])

    hits = mem_client.get_memories_by_file("memory_service/main.py", role="modified")
    matching = [h for h in hits if h["id"] == r["memory_id"]]
    assert matching, "Memory not found in by-file results"
    hit = matching[0]
    assert "memory_service/main.py" in hit["files_modified"]
    assert "memory_service/config.py" in hit["files_read"]
```

- [ ] **Step 2: Check service is running**

```bash
curl -s http://localhost:8000/health
```

Expected: `{"status":"ok",...}`

- [ ] **Step 3: Run integration tests**

```bash
pytest tests/test_wp127_file_provenance.py -m integration -v
```

Expected: all 5 PASS.

- [ ] **Step 4: Run full unit test suite to check for regressions**

```bash
pytest tests/ -v -k "not integration" --tb=short 2>&1 | tail -20
```

Expected: no new failures.

- [ ] **Step 5: Commit**

```bash
git add tests/test_wp127_file_provenance.py
git commit -m "WP-127: integration tests for file provenance endpoints"
```

---

## Task 8: Update BACKLOG.md

**Files:**
- Modify: `BACKLOG.md`

- [ ] **Step 1: Move WP-127 to Completed**

In `BACKLOG.md`:
1. Delete the WP-127 row from the priority table
2. Add to the Completed section in `docs/CHANGELOG.md` (or inline if CHANGELOG doesn't exist, add to BACKLOG Completed section):

```
### WP-127 — `files_modified` and `files_read` properties on Memory nodes
Completed 2026-04-10. Added `files_modified`/`files_read` list properties to Memory nodes. Extended AddMemoryRequest, UpdateMemoryRequest, SearchMemoryRequest, MemoryHit. Added GET /memory/by-file endpoint (role=modified|read|any). Extended memory_client. 7 integration tests passing.
Retrospective: scalar_keys in update_memory handled list properties automatically — no special-casing needed. Cypher `coalesce(m.files_modified, [])` essential for nodes created before this WP.
```

- [ ] **Step 2: Commit**

```bash
git add BACKLOG.md
git commit -m "WP-127: complete — move to done in BACKLOG"
```
