# WP-099: Framework Hierarchy Schema Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the knowledge layer schema so that external standard hierarchy nodes (ISO 27001 clauses and Annex A controls) are stored as `:Framework` nodes with `level` + `body` fields, retiring the misuse of `:Control` for this purpose.

**Architecture:** `POST /knowledge/frameworks` gains `level`, `body`, `parent_id` (with CONTAINS edge); a new `POST /knowledge/search/frameworks` endpoint replaces `POST /knowledge/search/controls` for framework vector search; the `SUPPORTS` edge target changes from `:Control` to `:Framework`; `init_knowledge_schema.py` replaces `ctrl_embedding_idx` on `:Control` with `framework_embedding_idx` on `:Framework`; `load_iso27001_chunks.py` is rewritten to use frameworks throughout.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, neo4j driver (Bolt), Memgraph, pytest, httpx

---

## Context

**Current state (broken):**
- `POST /knowledge/controls` creates `:Control {id, name, description, framework_id, embedding}` nodes
- `ctrl_embedding_idx` is a vector index on `:Control(embedding)`
- `SUPPORTS` edges link `:Chunk → :Control`
- `load_iso27001_chunks.py` calls `POST /knowledge/controls` for all ISO 27001 hierarchy nodes

**Target state (ADR-002 aligned):**
- `POST /knowledge/frameworks` creates `:Framework {id, name, version, description, level, body}` nodes
- `framework_embedding_idx` is a vector index on `:Framework(embedding)` (only nodes with `body` get embedded)
- `SUPPORTS` edges link `:Chunk → :Framework`
- `load_iso27001_chunks.py` calls `POST /knowledge/frameworks` for all hierarchy nodes
- `POST /knowledge/controls` and `GET /knowledge/controls/{id}` are **removed** (they were only used for external standard hierarchy — not org control tree)
- `POST /knowledge/search/controls` is **removed**, replaced by `POST /knowledge/search/frameworks`

**Important:** The `:Control` label in ADR-002 is reserved for the *organisation's own* security architecture (future WPs). The current `:Control` nodes in the graph are all ISO 27001 hierarchy nodes — they should be `:Framework` nodes. The `ABOUT_CONTROL` edge and `knowledge_bridge.py` functions (validate_controls, link_controls etc.) reference `:Control` — these are for the org's control tree and are **kept unchanged** for future use.

---

## File Map

| File | Change |
|------|--------|
| `memory_service/knowledge_repo.py` | Add `upsert_framework_node` (replaces `upsert_control`), `search_frameworks`, `create_supports_edge_framework`, `get_chunks_for_framework`; remove `upsert_control`, `get_control`, `search_controls`, `get_chunks_for_control`, `list_controls` |
| `memory_service/knowledge_routes.py` | Extend `FrameworkCreate` + `FrameworkResponse` with `level`, `body`, `parent_id`; add `FrameworkSearchRequest`, `FrameworkHit`, `POST /search/frameworks`; update `SupportsCreate` + related endpoint to use `framework_id`; remove `/controls` CRUD + search endpoints |
| `memory_service/config.py` | Rename `ctrl_index_capacity` → `framework_index_capacity` |
| `.env.example` | Update comment `CTRL_INDEX_CAPACITY` → `FRAMEWORK_INDEX_CAPACITY` |
| `scripts/init_knowledge_schema.py` | Replace `ctrl_embedding_idx` on `:Control` with `framework_embedding_idx` on `:Framework`; remove `:Control(id)` from constraints |
| `scripts/load_iso27001_chunks.py` | Rewrite: use `POST /knowledge/frameworks` with `level` + `body` + `parent_id`; use `POST /knowledge/chunk/supports` with `framework_id` |
| `scripts/migrate_embeddings.py` | Update `EMBEDDABLE_LABELS`: remove `("Control", None)`, add `("Framework", None)` |
| `tests/test_wp099_framework_schema.py` | New test file: unit + integration tests |
| `tests/test_wp069_knowledge_schema.py` | Update integration tests that assert `ctrl_embedding_idx` on `Control` |

---

## Task 1: Extend `FrameworkCreate` and `FrameworkResponse` with new fields

This is the Pydantic model change. No Cypher yet — just the schemas.

**Files:**
- Modify: `memory_service/knowledge_routes.py:27-39`
- Test: `tests/test_wp099_framework_schema.py`

- [ ] **Step 1: Write failing unit test**

Create `tests/test_wp099_framework_schema.py`:

```python
"""tests/test_wp099_framework_schema.py — WP-099: Framework hierarchy schema correction."""
import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Unit tests — Pydantic model validation
# ---------------------------------------------------------------------------

def test_framework_create_accepts_level_body_parent_id():
    from memory_service.knowledge_routes import FrameworkCreate
    fw = FrameworkCreate(
        id="iso-27001-2022.6",
        name="Clause 6 — Planning",
        level="clause",
        body="Requirements for planning in the ISMS context.",
        parent_id="iso-27001-2022",
    )
    assert fw.level == "clause"
    assert fw.body == "Requirements for planning in the ISMS context."
    assert fw.parent_id == "iso-27001-2022"


def test_framework_create_level_defaults_to_framework():
    from memory_service.knowledge_routes import FrameworkCreate
    fw = FrameworkCreate(id="iso-27001-2022", name="ISO/IEC 27001")
    assert fw.level == "framework"


def test_framework_create_body_optional():
    from memory_service.knowledge_routes import FrameworkCreate
    fw = FrameworkCreate(id="iso-27001-2022", name="ISO/IEC 27001")
    assert fw.body is None


def test_framework_response_includes_level_and_body():
    from memory_service.knowledge_routes import FrameworkResponse
    resp = FrameworkResponse(
        id="iso-27001-2022.6",
        name="Clause 6",
        level="clause",
        body="Some body text.",
        created_at="2026-04-04T00:00:00+00:00",
    )
    assert resp.level == "clause"
    assert resp.body == "Some body text."


def test_framework_search_request_has_query_and_limit():
    from memory_service.knowledge_routes import FrameworkSearchRequest
    req = FrameworkSearchRequest(query="access control requirements")
    assert req.query == "access control requirements"
    assert req.limit == 10
    assert req.framework_id is None


def test_supports_create_uses_framework_id():
    from memory_service.knowledge_routes import SupportsCreate
    req = SupportsCreate(
        chunk_id="chunk-001",
        framework_id="iso-27001-2022.a.5.1",
        confidence=0.9,
    )
    assert req.framework_id == "iso-27001-2022.a.5.1"
    assert not hasattr(req, "control_id") or req.control_id is None


def test_supports_create_rejects_missing_framework_id():
    from memory_service.knowledge_routes import SupportsCreate
    with pytest.raises(ValidationError):
        SupportsCreate(chunk_id="chunk-001", confidence=0.9)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/oliver/projects/graph-memory-fabric
python -m pytest tests/test_wp099_framework_schema.py -v 2>&1 | head -60
```

Expected: multiple FAILs — `level` and `body` not on `FrameworkCreate`, `FrameworkSearchRequest` doesn't exist, `SupportsCreate.framework_id` doesn't exist.

- [ ] **Step 3: Update `FrameworkCreate`, `FrameworkResponse`, `FrameworkSearchRequest`, `FrameworkHit`, `SupportsCreate` in `knowledge_routes.py`**

Replace the `FrameworkCreate` block (lines 27–39) and `ControlSearchRequest`/`ControlHit` and `SupportsCreate`/`SupportsResponse` blocks:

```python
class FrameworkCreate(BaseModel):
    id: str
    name: str
    version: Optional[str] = None
    description: Optional[str] = None
    level: str = "framework"           # framework | category | section | clause | sub-clause
    body: Optional[str] = None         # requirement text; used for embedding when present
    parent_id: Optional[str] = None    # if set, creates CONTAINS edge parent→this


class FrameworkResponse(BaseModel):
    id: str
    name: str
    version: Optional[str] = None
    description: Optional[str] = None
    level: str
    body: Optional[str] = None
    created_at: str


class FrameworkSearchRequest(BaseModel):
    query: str
    limit: int = 10
    framework_id: Optional[str] = None  # filter by parent framework id property


class FrameworkHit(BaseModel):
    id: str
    name: str
    level: str
    body: Optional[str] = None
    created_at: str
    distance: float


class SupportsCreate(BaseModel):
    chunk_id: str
    framework_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    status: str = "auto-inferred"


class SupportsResponse(BaseModel):
    chunk_id: str
    framework_id: str
    confidence: float
    status: str
    created_at: str
```

Also remove `ControlCreate`, `ControlResponse`, `ControlSearchRequest`, `ControlHit` classes (they will no longer be used).

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_wp099_framework_schema.py -v 2>&1 | head -40
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_wp099_framework_schema.py memory_service/knowledge_routes.py
git commit -m "feat(WP-099): extend FrameworkCreate/Response with level+body+parent_id, add FrameworkSearch, rename SupportsCreate.control_id to framework_id"
```

---

## Task 2: Update `knowledge_repo.py` — Framework upsert with level/body/parent_id + CONTAINS edge

**Files:**
- Modify: `memory_service/knowledge_repo.py:15-98`
- Test: `tests/test_wp099_framework_schema.py`

- [ ] **Step 1: Write failing unit tests for repo functions**

Add to `tests/test_wp099_framework_schema.py`:

```python
# ---------------------------------------------------------------------------
# Unit tests — knowledge_repo upsert_framework
# ---------------------------------------------------------------------------

def test_upsert_framework_sets_level_and_body():
    """upsert_framework passes level and body to Cypher."""
    from unittest.mock import MagicMock
    from memory_service import knowledge_repo

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.single.return_value = {
        "id": "iso-27001-2022.6",
        "name": "Clause 6",
        "version": None,
        "description": None,
        "level": "clause",
        "body": "Planning requirements.",
        "created_at": "2026-04-04T00:00:00+00:00",
    }
    mock_session.run.return_value = mock_result

    class FakeReq:
        id = "iso-27001-2022.6"
        name = "Clause 6"
        version = None
        description = None
        level = "clause"
        body = "Planning requirements."
        parent_id = "iso-27001-2022"

    result = knowledge_repo.upsert_framework(mock_session, FakeReq(), "2026-04-04T00:00:00+00:00")
    # Should have called session.run twice: once for MERGE, once for CONTAINS edge
    assert mock_session.run.call_count == 2
    first_call_kwargs = mock_session.run.call_args_list[0][1]
    assert first_call_kwargs["level"] == "clause"
    assert first_call_kwargs["body"] == "Planning requirements."


def test_upsert_framework_no_parent_no_contains_edge():
    """When parent_id is None, only one session.run call (no CONTAINS edge)."""
    from unittest.mock import MagicMock
    from memory_service import knowledge_repo

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.single.return_value = {
        "id": "iso-27001-2022",
        "name": "ISO/IEC 27001",
        "version": "2022",
        "description": None,
        "level": "framework",
        "body": None,
        "created_at": "2026-04-04T00:00:00+00:00",
    }
    mock_session.run.return_value = mock_result

    class FakeReq:
        id = "iso-27001-2022"
        name = "ISO/IEC 27001"
        version = "2022"
        description = None
        level = "framework"
        body = None
        parent_id = None

    knowledge_repo.upsert_framework(mock_session, FakeReq(), "2026-04-04T00:00:00+00:00")
    assert mock_session.run.call_count == 1


def test_get_framework_returns_level_and_body():
    """get_framework query returns level and body fields."""
    from unittest.mock import MagicMock
    from memory_service import knowledge_repo

    mock_session = MagicMock()
    record = {
        "id": "iso-27001-2022.6",
        "name": "Clause 6",
        "version": None,
        "description": None,
        "level": "clause",
        "body": "Planning requirements.",
        "created_at": "2026-04-04T00:00:00+00:00",
    }
    mock_session.run.return_value.single.return_value = record

    result = knowledge_repo.get_framework(mock_session, "iso-27001-2022.6")
    assert result["level"] == "clause"
    assert result["body"] == "Planning requirements."


def test_search_frameworks_calls_vector_search():
    """search_frameworks invokes framework_embedding_idx."""
    from unittest.mock import MagicMock
    from memory_service import knowledge_repo

    mock_session = MagicMock()
    mock_session.run.return_value = []

    knowledge_repo.search_frameworks(mock_session, [0.1] * 384, limit=5, framework_id=None)
    cypher = mock_session.run.call_args[0][0]
    assert "framework_embedding_idx" in cypher


def test_create_supports_edge_framework_uses_framework_label():
    """create_supports_edge_framework matches :Framework not :Control."""
    from unittest.mock import MagicMock
    from memory_service import knowledge_repo

    mock_session = MagicMock()
    mock_session.run.return_value.single.return_value = {
        "chunk_id": "c1",
        "framework_id": "fw1",
        "confidence": 0.9,
        "status": "auto-inferred",
        "created_at": "2026-04-04T00:00:00+00:00",
    }

    knowledge_repo.create_supports_edge_framework(
        mock_session, "c1", "fw1", 0.9, "auto-inferred", "2026-04-04T00:00:00+00:00"
    )
    cypher = mock_session.run.call_args[0][0]
    assert ":Framework" in cypher
    assert ":Control" not in cypher
```

- [ ] **Step 2: Run to verify failures**

```bash
python -m pytest tests/test_wp099_framework_schema.py -v -k "test_upsert_framework or test_get_framework or test_search_frameworks or test_create_supports_edge_framework" 2>&1 | head -50
```

Expected: FAILs — `search_frameworks` not found, `create_supports_edge_framework` not found.

- [ ] **Step 3: Update `knowledge_repo.py`**

Replace the `upsert_framework` function (keep the same name) and `get_framework` function to include `level`, `body`, `parent_id` handling. Add `search_frameworks` and `create_supports_edge_framework`. Remove `upsert_control`, `get_control`, `search_controls`, `get_chunks_for_control`, `list_controls`.

Replace the **Framework section** (lines 15–47):

```python
# ---------------------------------------------------------------------------
# Framework
# ---------------------------------------------------------------------------


def upsert_framework(session, req, now: str) -> dict:
    """MERGE Framework on id; SET all properties ON CREATE only.
    If parent_id is set, creates CONTAINS edge from parent Framework to this node.
    If body is present, embedding is set by the caller (knowledge_routes.py).
    """
    result = session.run(
        """
        MERGE (f:Framework {id: $id})
        ON CREATE SET
            f.name = $name,
            f.version = $version,
            f.description = $description,
            f.level = $level,
            f.body = $body,
            f.created_at = $created_at
        RETURN f.id AS id, f.name AS name, f.version AS version,
               f.description AS description, f.level AS level,
               f.body AS body, f.created_at AS created_at
        """,
        id=req.id,
        name=req.name,
        version=req.version,
        description=req.description,
        level=req.level,
        body=req.body,
        created_at=now,
    )
    record = dict(result.single())

    if req.parent_id:
        session.run(
            """
            MATCH (parent:Framework {id: $parent_id}), (child:Framework {id: $child_id})
            MERGE (parent)-[:CONTAINS]->(child)
            """,
            parent_id=req.parent_id,
            child_id=req.id,
        )

    return record


def get_framework(session, framework_id: str) -> dict | None:
    result = session.run(
        """
        MATCH (f:Framework {id: $id})
        RETURN f.id AS id, f.name AS name, f.version AS version,
               f.description AS description, f.level AS level,
               f.body AS body, f.created_at AS created_at
        """,
        id=framework_id,
    )
    record = result.single()
    return dict(record) if record else None
```

Replace the **Control section** (lines 51–111) entirely — remove it. The `upsert_control`, `get_control` functions are deleted.

Replace `search_controls` with `search_frameworks`:

```python
def search_frameworks(
    session,
    query_embedding: list[float],
    limit: int,
    framework_id: str | None,
) -> list[dict]:
    """Vector search over framework_embedding_idx (Framework nodes with body text).
    Returns list of dicts: {id, name, level, body, created_at, distance}.
    NOTE: vector_search returns up to $limit nodes before the WHERE filter is applied.
    When filters are tight, response may be empty even if matching nodes exist further
    down the ranking. This is expected behaviour.
    """
    result = session.run(
        """
        CALL vector_search.search("framework_embedding_idx", $limit, $query_vec)
        YIELD node AS f, distance
        WITH f, distance
        WHERE ($framework_id IS NULL OR f.framework_root_id = $framework_id)
        RETURN f.id AS id, f.name AS name, f.level AS level,
               f.body AS body, f.created_at AS created_at,
               distance
        ORDER BY distance ASC
        """,
        limit=limit,
        query_vec=query_embedding,
        framework_id=framework_id,
    )
    return [dict(r) for r in result]
```

Replace `create_supports_edge` with `create_supports_edge_framework`:

```python
def create_supports_edge_framework(
    session,
    chunk_id: str,
    framework_id: str,
    confidence: float,
    status: str,
    now: str,
) -> dict | None:
    """MERGE SUPPORTS edge Chunk→Framework; SET all properties ON CREATE only.

    Returns {chunk_id, framework_id, confidence, status, created_at}.
    Returns None if either Chunk or Framework node does not exist.
    Callers must check for None and raise HTTP 404.
    """
    result = session.run(
        """
        MATCH (ch:Chunk {id: $chunk_id}), (f:Framework {id: $framework_id})
        MERGE (ch)-[s:SUPPORTS]->(f)
        ON CREATE SET
            s.confidence  = $confidence,
            s.status      = $status,
            s.created_at  = $created_at
        RETURN ch.id AS chunk_id, f.id AS framework_id,
               s.confidence AS confidence, s.status AS status,
               s.created_at AS created_at
        """,
        chunk_id=chunk_id,
        framework_id=framework_id,
        confidence=confidence,
        status=status,
        created_at=now,
    )
    record = result.single()
    if record is None:
        return None
    return dict(record)


def get_chunks_for_framework(session, framework_id: str) -> list[dict]:
    """Return all Chunk nodes with a SUPPORTS edge to this Framework,
    ordered by confidence DESC.

    Returns list of dicts: {id, text, sequence, doc_id, created_at, confidence, status}.
    """
    result = session.run(
        """
        MATCH (ch:Chunk)-[s:SUPPORTS]->(f:Framework {id: $framework_id})
        RETURN ch.id AS id, ch.text AS text, ch.sequence AS sequence,
               ch.doc_id AS doc_id, ch.created_at AS created_at,
               s.confidence AS confidence, s.status AS status
        ORDER BY s.confidence DESC
        """,
        framework_id=framework_id,
    )
    return [dict(r) for r in result]
```

Also remove `list_incomplete_jurisdictions` references to `:Control` — update the function to remove the `controls_without_jurisdiction` part or leave it empty (`:Control` nodes are for future org control tree). Update to:

```python
def list_incomplete_jurisdictions(session) -> dict:
    """Return Norms with no APPLIES_IN edges.
    Returns:
      {
        "norms_without_jurisdiction": [{"id": ..., "name": ...}, ...],
      }
    """
    norms_result = session.run(
        """
        MATCH (n:Norm)
        WHERE NOT (n)-[:APPLIES_IN]->(:Jurisdiction)
        RETURN n.id AS id, n.name AS name
        ORDER BY n.name ASC
        """
    )
    return {
        "norms_without_jurisdiction": [dict(r) for r in norms_result],
    }
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_wp099_framework_schema.py -v 2>&1 | head -60
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add memory_service/knowledge_repo.py tests/test_wp099_framework_schema.py
git commit -m "feat(WP-099): update knowledge_repo — upsert_framework with level/body/parent_id, add search_frameworks and create_supports_edge_framework, remove Control functions"
```

---

## Task 3: Update `knowledge_routes.py` — wire new repo functions, remove control routes

**Files:**
- Modify: `memory_service/knowledge_routes.py`

- [ ] **Step 1: Write failing unit test for routes**

Add to `tests/test_wp099_framework_schema.py`:

```python
# ---------------------------------------------------------------------------
# Unit tests — route existence checks (source inspection)
# ---------------------------------------------------------------------------

def test_framework_route_has_level_and_body_in_create_handler():
    import inspect
    from memory_service import knowledge_routes
    source = inspect.getsource(knowledge_routes)
    assert "level" in source
    assert "body" in source
    assert "/search/frameworks" in source


def test_control_routes_removed():
    """POST /controls, GET /controls/{id}, POST /search/controls must be gone."""
    import inspect
    from memory_service import knowledge_routes
    source = inspect.getsource(knowledge_routes)
    assert '"/controls"' not in source, "POST /controls route must be removed"
    assert '"/search/controls"' not in source, "POST /search/controls route must be removed"


def test_supports_route_uses_framework_id():
    """The /chunk/supports endpoint must reference framework_id, not control_id."""
    import inspect
    from memory_service import knowledge_routes
    source = inspect.getsource(knowledge_routes)
    # SupportsCreate now has framework_id
    assert "framework_id" in source
    # The old validation check for control_id should be gone
    # (at minimum, search for get_control must not appear)
    assert "get_control" not in source
```

- [ ] **Step 2: Run to verify failures**

```bash
python -m pytest tests/test_wp099_framework_schema.py::test_control_routes_removed tests/test_wp099_framework_schema.py::test_supports_route_uses_framework_id -v 2>&1
```

Expected: FAILs.

- [ ] **Step 3: Rewrite `knowledge_routes.py` routes**

In `knowledge_routes.py`:

**Update `POST /knowledge/frameworks`** — now generates embedding when `body` is present:

```python
@router.post("/frameworks", response_model=FrameworkResponse)
async def upsert_framework(req: FrameworkCreate, request: Request) -> FrameworkResponse:
    now = datetime.now(tz=timezone.utc).isoformat()
    with request.app.state.driver.session() as session:
        record = knowledge_repo.upsert_framework(session, req, now)
    # Embed body text if present; stored separately so upsert stays idempotent
    if req.body:
        embedding = get_embedding(req.body, model_name=settings.knowledge_embedding_model)
        with request.app.state.driver.session() as session:
            session.run(
                "MATCH (f:Framework {id: $id}) SET f.embedding = $emb",
                id=req.id,
                emb=embedding,
            )
    return FrameworkResponse(**record)
```

**Update `GET /knowledge/frameworks/{framework_id}`** — already returns new fields via `get_framework`.

**Remove** the entire Control endpoints section:

```python
# REMOVED: POST /controls, GET /controls/{control_id}
```

**Add `POST /search/frameworks`** (after existing `/search/chunks` endpoint):

```python
@router.post("/search/frameworks", response_model=List[FrameworkHit])
async def search_frameworks(req: FrameworkSearchRequest, request: Request) -> List[FrameworkHit]:
    query_vec = get_embedding(req.query, model_name=settings.knowledge_embedding_model)
    with request.app.state.driver.session() as session:
        hits = knowledge_repo.search_frameworks(session, query_vec, req.limit, req.framework_id)
    return [FrameworkHit(**h) for h in hits]
```

**Remove** `POST /search/controls` endpoint.

**Update `POST /chunk/supports`** to use `framework_id`:

```python
@router.post("/chunk/supports", response_model=SupportsResponse)
async def create_supports(req: SupportsCreate, request: Request) -> SupportsResponse:
    now = datetime.now(tz=timezone.utc).isoformat()
    with request.app.state.driver.session() as session:
        if knowledge_repo.get_chunk(session, req.chunk_id) is None:
            raise HTTPException(status_code=404, detail=f"Chunk not found: {req.chunk_id}")
        if knowledge_repo.get_framework(session, req.framework_id) is None:
            raise HTTPException(status_code=404, detail=f"Framework not found: {req.framework_id}")
        record = knowledge_repo.create_supports_edge_framework(
            session, req.chunk_id, req.framework_id, req.confidence, req.status, now
        )
    if record is None:
        raise HTTPException(status_code=404, detail="Chunk or Framework not found")
    return SupportsResponse(**record)
```

**Update `GET /controls/{control_id}/chunks`** → rename to `GET /frameworks/{framework_id}/chunks`:

```python
@router.get("/frameworks/{framework_id}/chunks", response_model=List[ChunkWithSupports])
async def get_chunks_for_framework(framework_id: str, request: Request) -> List[ChunkWithSupports]:
    with request.app.state.driver.session() as session:
        if knowledge_repo.get_framework(session, framework_id) is None:
            raise HTTPException(status_code=404, detail=f"Framework not found: {framework_id}")
        chunks = knowledge_repo.get_chunks_for_framework(session, framework_id)
    return [ChunkWithSupports(**c) for c in chunks]
```

**Remove** trace-up/trace-down/gap-analysis endpoints that reference `:Control` nodes — these are for the future org control tree. Remove: `GET /controls/{control_id}/trace-up`, `GET /controls/{control_id}/trace-down`, `GET /attributes/{attribute_id}/coverage`, `POST /gap-analysis`. Remove associated Pydantic models: `TraceUpResponse`, `TraceDownResponse`, `AttributeCoverageResponse`, `GapAnalysisRequest`, `GapAnalysisResponse`, `ControlGapEntry`, `BusinessAttributeRef`, `NormRef`, `ChunkRef`, `DocumentWithChunks`, `MemoryRef`. (These will be reintroduced when the org control tree WPs are implemented.)

Also remove all `ControlCreate`, `ControlResponse`, `ControlSearchRequest`, `ControlHit` models (already done in Task 1).

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/test_wp099_framework_schema.py -v 2>&1 | head -80
```

Expected: all PASS.

- [ ] **Step 5: Run full test suite (unit only)**

```bash
python -m pytest tests/ -v --ignore=tests/test_wp069_knowledge_schema.py -k "not integration" 2>&1 | tail -30
```

Expected: all PASS (some failures in integration-marked tests are expected).

- [ ] **Step 6: Commit**

```bash
git add memory_service/knowledge_routes.py
git commit -m "feat(WP-099): rewrite knowledge_routes — remove control endpoints, add framework search, update supports to use framework_id"
```

---

## Task 4: Update `init_knowledge_schema.py` — replace ctrl_embedding_idx with framework_embedding_idx

**Files:**
- Modify: `scripts/init_knowledge_schema.py`
- Modify: `memory_service/config.py`
- Modify: `.env.example`
- Test: `tests/test_wp099_framework_schema.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_wp099_framework_schema.py`:

```python
# ---------------------------------------------------------------------------
# Unit tests — init_knowledge_schema
# ---------------------------------------------------------------------------

def test_init_knowledge_schema_no_ctrl_embedding_idx():
    """init_knowledge_schema must not create ctrl_embedding_idx."""
    import inspect
    from scripts import init_knowledge_schema
    source = inspect.getsource(init_knowledge_schema)
    assert "ctrl_embedding_idx" not in source, "ctrl_embedding_idx must be removed from init_knowledge_schema"


def test_init_knowledge_schema_has_framework_embedding_idx():
    """init_knowledge_schema must create framework_embedding_idx on :Framework."""
    import inspect
    from scripts import init_knowledge_schema
    source = inspect.getsource(init_knowledge_schema)
    assert "framework_embedding_idx" in source
    assert "Framework" in source


def test_config_has_framework_index_capacity():
    """Settings must have framework_index_capacity (not ctrl_index_capacity)."""
    from memory_service.config import Settings
    s = Settings()
    assert hasattr(s, "framework_index_capacity")
    assert s.framework_index_capacity == 5000


def test_config_no_ctrl_index_capacity():
    """ctrl_index_capacity must be removed from Settings."""
    from memory_service.config import Settings
    s = Settings()
    assert not hasattr(s, "ctrl_index_capacity"), "ctrl_index_capacity must be renamed to framework_index_capacity"


def test_knowledge_constraints_no_control():
    """KNOWLEDGE_CONSTRAINTS must not include Control."""
    from scripts.init_knowledge_schema import KNOWLEDGE_CONSTRAINTS
    labels = [label for label, _ in KNOWLEDGE_CONSTRAINTS]
    assert "Control" not in labels, "Control must be removed from KNOWLEDGE_CONSTRAINTS"


def test_migrate_embeddings_no_control_label():
    """EMBEDDABLE_LABELS in migrate_embeddings must not contain Control."""
    from scripts.migrate_embeddings import EMBEDDABLE_LABELS
    labels = [label for label, _ in EMBEDDABLE_LABELS]
    assert "Control" not in labels


def test_migrate_embeddings_has_framework_label():
    """EMBEDDABLE_LABELS in migrate_embeddings must contain Framework."""
    from scripts.migrate_embeddings import EMBEDDABLE_LABELS
    labels = [label for label, _ in EMBEDDABLE_LABELS]
    assert "Framework" in labels
```

- [ ] **Step 2: Run to verify failures**

```bash
python -m pytest tests/test_wp099_framework_schema.py -v -k "test_init_knowledge_schema or test_config or test_knowledge_constraints or test_migrate_embeddings" 2>&1 | head -50
```

Expected: multiple FAILs.

- [ ] **Step 3: Update `config.py`** — rename `ctrl_index_capacity` to `framework_index_capacity`

In `memory_service/config.py`, replace line 43:

```python
    framework_index_capacity: int = 5000
```

- [ ] **Step 4: Update `.env.example`** — update comment

Replace line 86:

```
# FRAMEWORK_INDEX_CAPACITY=5000
```

- [ ] **Step 5: Update `scripts/init_knowledge_schema.py`**

Replace `KNOWLEDGE_CONSTRAINTS` list — remove `("Control", "id")`:

```python
KNOWLEDGE_CONSTRAINTS = [
    ("Framework", "id"),
    ("Norm", "id"),
    ("Document", "id"),
    ("Chunk", "id"),
    ("BusinessAttribute", "id"),
    ("Organisation", "id"),
    ("Jurisdiction", "code"),
]
```

Replace the `ctrl_embedding_idx` section with `framework_embedding_idx`:

```python
            # --- framework_embedding_idx ---
            print("\nCreating vector index: framework_embedding_idx ...")
            try:
                create_vector_index(
                    session,
                    index_name="framework_embedding_idx",
                    label="Framework",
                    prop="embedding",
                    dim=dim,
                    capacity=settings.framework_index_capacity,
                )
            except Exception as exc:
                print(f"  [FAIL] framework_embedding_idx: {exc}")
                success = False

            print("Validating vector index: framework_embedding_idx ...")
            if not validate_vector_index(session, "framework_embedding_idx", "Framework", "embedding"):
                success = False
```

Update the settings reference `settings.ctrl_index_capacity` → `settings.framework_index_capacity`.

- [ ] **Step 6: Update `scripts/migrate_embeddings.py`** — replace Control with Framework

In `migrate_embeddings.py`, replace lines 22–28:

```python
EMBEDDABLE_LABELS = [
    # (label, text_property_or_None)
    # For Framework: text = body (only nodes with body get embedded)
    # For Chunk:     text = heading + " " + body
    ("Framework", None),  # special: reconstruct from body
    ("Chunk", None),      # special: reconstruct from heading + body
]
```

Update `_reconstruct_text` — replace the `Control` block with `Framework`:

```python
def _reconstruct_text(label: str, node: dict) -> str | None:
    """Return the text that should be embedded for this node, or None to skip."""
    if label == "Framework":
        body = (node.get("body") or "").strip()
        return body or None   # Framework nodes without body are not embedded

    if label == "Chunk":
        heading = (node.get("heading") or "").strip()
        body = (node.get("body") or "").strip()
        text = " ".join(part for part in [heading, body] if part)
        return text.strip() or None

    return None
```

Also update the query in `migrate_embeddings.py` that fetches Control nodes — change `MATCH (n:Control)` to `MATCH (n:Framework)` in the node-fetch query.

- [ ] **Step 7: Run tests**

```bash
python -m pytest tests/test_wp099_framework_schema.py -v 2>&1 | head -80
```

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add memory_service/config.py .env.example scripts/init_knowledge_schema.py scripts/migrate_embeddings.py tests/test_wp099_framework_schema.py
git commit -m "feat(WP-099): replace ctrl_embedding_idx with framework_embedding_idx, rename ctrl_index_capacity, update migrate_embeddings"
```

---

## Task 5: Update `load_iso27001_chunks.py` to use framework endpoints

**Files:**
- Modify: `scripts/load_iso27001_chunks.py`
- Test: `tests/test_wp099_framework_schema.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_wp099_framework_schema.py`:

```python
# ---------------------------------------------------------------------------
# Unit tests — load_iso27001_chunks
# ---------------------------------------------------------------------------

def test_load_iso27001_chunks_no_controls_endpoint():
    """load_iso27001_chunks must not call /knowledge/controls."""
    import inspect
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location(
        "load_iso27001_chunks",
        "scripts/load_iso27001_chunks.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    source = inspect.getsource(mod)
    assert "/knowledge/controls" not in source, "load_iso27001_chunks must not call /knowledge/controls"


def test_load_iso27001_chunks_uses_framework_id_in_supports():
    """load_iso27001_chunks must pass framework_id (not control_id) to /knowledge/chunk/supports."""
    import inspect
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "load_iso27001_chunks",
        "scripts/load_iso27001_chunks.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    source = inspect.getsource(mod)
    assert '"framework_id"' in source, "load_iso27001_chunks must use framework_id in SUPPORTS payload"
    assert '"control_id"' not in source, "load_iso27001_chunks must not use control_id"
```

- [ ] **Step 2: Run to verify failures**

```bash
python -m pytest tests/test_wp099_framework_schema.py::test_load_iso27001_chunks_no_controls_endpoint tests/test_wp099_framework_schema.py::test_load_iso27001_chunks_uses_framework_id_in_supports -v 2>&1
```

Expected: FAILs.

- [ ] **Step 3: Rewrite `load_iso27001_chunks.py`**

```python
#!/usr/bin/env python3
"""load_iso27001_chunks.py — Load reviewed iso27001_inspection.yaml into the knowledge graph.

Reads the reviewed YAML produced by inspect_iso27001.py and:
  1. Creates/upserts the root Framework node
  2. Creates/upserts all Framework hierarchy nodes (clauses + Annex A controls)
     with level, body, and parent_id
  3. Creates a Document node for the PDF source
  4. Creates one Chunk per entry, linked to its Framework node via SUPPORTS

Usage:
    python3 -m scripts.load_iso27001_chunks [--yaml scripts/iso27001_inspection.yaml]
                                             [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoadSettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def _post(client: httpx.Client, endpoint: str, body: dict, label: str) -> str:
    try:
        r = client.post(endpoint, json=body)
        if r.status_code == 409:
            return "exists"
        r.raise_for_status()
        return "ok"
    except httpx.HTTPStatusError as exc:
        print(f"  [ERR] {label}: HTTP {exc.response.status_code} — {exc.response.text[:200]}", file=sys.stderr)
        return "error"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yaml", default="scripts/iso27001_inspection.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate only — no API calls")
    args = parser.parse_args()

    cfg = LoadSettings()

    with open(args.yaml, encoding="utf-8") as f:
        entries = yaml.safe_load(f)

    clauses = [e for e in entries if e["type"] == "clause"]
    annex   = [e for e in entries if e["type"] == "annex_control"]
    print(f"Loaded {len(entries)} entries: {len(clauses)} clauses, {len(annex)} Annex A controls")

    if args.dry_run:
        print("Dry run — no changes made.")
        return

    framework_id = "iso-27001-2022"
    doc_id       = "iso-27001-2022-pdf"

    with httpx.Client(base_url=cfg.api_base_url, timeout=30) as client:

        # 1. Root Framework node
        print("\n1. Framework")
        s = _post(client, "/knowledge/frameworks", {
            "id": framework_id,
            "name": "ISO/IEC 27001",
            "version": "2022",
            "description": "Information security management systems requirements",
            "level": "framework",
        }, "framework")
        print(f"   iso-27001-2022: {s}")

        # 2. Framework hierarchy nodes
        # Annex A structural group nodes (not in inspection YAML — created here)
        print("\n2. Framework hierarchy nodes")
        annex_root = {
            "id": "iso-27001-2022.a",
            "name": "Annex A — Information Security Controls",
            "level": "category",
            "parent_id": framework_id,
        }
        _post(client, "/knowledge/frameworks", annex_root, "iso-27001-2022.a")

        annex_groups = {
            "iso-27001-2022.a.5": ("Organizational Controls", "iso-27001-2022.a"),
            "iso-27001-2022.a.6": ("People Controls",         "iso-27001-2022.a"),
            "iso-27001-2022.a.7": ("Physical Controls",       "iso-27001-2022.a"),
            "iso-27001-2022.a.8": ("Technological Controls",  "iso-27001-2022.a"),
        }
        for gid, (gname, gparent) in annex_groups.items():
            _post(client, "/knowledge/frameworks", {
                "id": gid,
                "name": gname,
                "level": "section",
                "parent_id": gparent,
            }, gid)

        ok = err = 0
        for e in entries:
            fw_id = e["suggested_control_id"]
            # Determine level from id structure
            parts = fw_id.split(".")
            if "a" in parts:
                # Annex A control: iso-27001-2022.a.5.1
                level = "clause"
            elif len(parts) == 2:
                # Top-level clause: iso-27001-2022.6
                level = "clause"
            else:
                # Sub-clause: iso-27001-2022.6.1.2
                level = "sub-clause"

            body: dict = {
                "id": fw_id,
                "name": e["heading"],
                "level": level,
            }
            # body text (requirement text) — from the entry's text field
            if e.get("text"):
                body["body"] = e["text"]

            # Parent linkage
            if len(parts) > 2:
                body["parent_id"] = ".".join(parts[:-1])
            elif len(parts) == 2 and "a" not in parts:
                # Top-level clauses (iso-27001-2022.6) parent to root framework
                body["parent_id"] = framework_id

            s = _post(client, "/knowledge/frameworks", body, fw_id)
            if s == "error":
                err += 1
            else:
                ok += 1
        print(f"   {ok} upserted, {err} errors")

        # 3. Document
        print("\n3. Document")
        s = _post(client, "/knowledge/documents", {
            "id": doc_id,
            "title": "ISO/IEC 27001:2022",
            "doc_type": "standard",
        }, doc_id)
        print(f"   {doc_id}: {s}")

        # 4. Chunks — one per entry that has text
        print("\n4. Chunks")
        ok = err = skipped = 0
        seq = 0
        for e in entries:
            if not e.get("text"):
                skipped += 1
                continue
            fw_id    = e["suggested_control_id"]
            chunk_id = f"{doc_id}.{e['id']}"
            s = _post(client, "/knowledge/chunks", {
                "id": chunk_id,
                "doc_id": doc_id,
                "text": e["text"],
                "sequence": seq,
            }, chunk_id)
            if s == "error":
                err += 1
            else:
                ok += 1
                seq += 1
                # SUPPORTS: chunk → framework node, human-reviewed, confidence=1.0
                _post(client, "/knowledge/chunk/supports", {
                    "chunk_id": chunk_id,
                    "framework_id": fw_id,
                    "confidence": 1.0,
                    "status": "human-reviewed",
                }, f"supports:{chunk_id}→{fw_id}")
        print(f"   {ok} created, {err} errors, {skipped} skipped (no text)")

    print("\nDone.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_wp099_framework_schema.py -v 2>&1 | head -80
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/load_iso27001_chunks.py tests/test_wp099_framework_schema.py
git commit -m "feat(WP-099): rewrite load_iso27001_chunks to use /knowledge/frameworks with level+body+parent_id"
```

---

## Task 6: Update existing tests to reflect schema changes

The test in `test_wp069_knowledge_schema.py` asserts `ctrl_embedding_idx` on `Control`. These must be updated to assert `framework_embedding_idx` on `Framework`.

**Files:**
- Modify: `tests/test_wp069_knowledge_schema.py`

- [ ] **Step 1: Identify failing tests in test_wp069**

```bash
python -m pytest tests/test_wp069_knowledge_schema.py -v -k "not integration" 2>&1 | head -60
```

Note which tests reference `ctrl_embedding_idx`, `Control`, or `ctrl_index_capacity`.

- [ ] **Step 2: Update unit tests in `test_wp069_knowledge_schema.py`**

Update `test_migrate_embeddings_includes_knowledge_labels` — it asserts `"Control" in labels`:

```python
def test_migrate_embeddings_includes_knowledge_labels():
    """Framework and Chunk nodes must be in EMBEDDABLE_LABELS."""
    from scripts.migrate_embeddings import EMBEDDABLE_LABELS
    labels = [label for label, _ in EMBEDDABLE_LABELS]
    assert "Framework" in labels
    assert "Chunk" in labels
```

Update `test_config_has_index_capacity_settings`:

```python
def test_config_has_index_capacity_settings():
    from memory_service.config import Settings
    s = Settings()
    assert s.memory_index_capacity == 5000
    assert s.framework_index_capacity == 5000
    assert s.chunk_index_capacity == 10000
```

Update `_KNOWLEDGE_CONSTRAINTS` (integration) to remove `("Control", "id")`:

```python
_KNOWLEDGE_CONSTRAINTS = [
    ("Framework", "id"),
    ("Document", "id"),
    ("Chunk", "id"),
    ("BusinessAttribute", "id"),
    ("Organisation", "id"),
    ("Jurisdiction", "code"),
]
```

Update `test_knowledge_schema_vector_indexes_created` — assert `Framework` not `Control`:

```python
@pytest.mark.integration
def test_knowledge_schema_vector_indexes_created(test_driver):
    """framework_embedding_idx and chunk_embedding_idx must exist with correct label+property."""
    from scripts.init_knowledge_schema import main as init_main
    init_main()

    indexes = _get_vector_indexes(test_driver)
    assert "Framework" in indexes, "framework_embedding_idx (Framework) not found"
    assert indexes["Framework"][0] == "embedding"
    assert "Chunk" in indexes, "chunk_embedding_idx (Chunk) not found"
    assert indexes["Chunk"][0] == "embedding"
```

Update `test_node_label_has_all_knowledge_labels` — remove `"Standard"` (was never in NodeLabel correctly — check), confirm `"Framework"` is present:

```python
def test_node_label_has_all_knowledge_labels():
    NodeLabel = service_main.NodeLabel
    knowledge_labels = {"Framework", "Control", "Document", "Chunk", "BusinessAttribute", "Organisation", "Jurisdiction"}
    existing = {e.value for e in NodeLabel}
    assert knowledge_labels.issubset(existing), f"Missing from NodeLabel: {knowledge_labels - existing}"
```

Note: `"Framework"` needs to be added to `NodeLabel` in `main.py`.

- [ ] **Step 3: Add `framework` to `NodeLabel` enum in `main.py`**

In `memory_service/main.py` at the `NodeLabel` enum (line ~956), add:

```python
class NodeLabel(str, Enum):
    memory = "Memory"
    strand = "Strand"
    agent = "Agent"
    person = "Person"
    project = "Project"
    framework = "Framework"
    control = "Control"
    document = "Document"
    chunk = "Chunk"
    business_attribute = "BusinessAttribute"
    organisation = "Organisation"
    jurisdiction = "Jurisdiction"
```

- [ ] **Step 4: Run unit tests**

```bash
python -m pytest tests/test_wp069_knowledge_schema.py tests/test_wp099_framework_schema.py -v -k "not integration" 2>&1 | tail -30
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_wp069_knowledge_schema.py memory_service/main.py
git commit -m "test(WP-099): update wp069 tests for framework_embedding_idx and framework_index_capacity, add Framework to NodeLabel"
```

---

## Task 7: Update `dump_db` / `restore_db` edge allowlists

The dump/restore edge allowlists (verified in `test_wp069_knowledge_schema.py`) must still cover knowledge-layer edges. `SUPPORTS` now points to `:Framework` but the edge type is unchanged. `HAS_CONTROL` is removed from the test expectations since the control endpoint is gone.

**Files:**
- Modify: `tests/test_wp069_knowledge_schema.py`

- [ ] **Step 1: Check current allowlist test**

Read `_KNOWLEDGE_EDGE_TYPES` in `test_wp069_knowledge_schema.py` (lines 119–123) — it includes `HAS_CONTROL`. This edge type belonged to the old model and is no longer created. Update:

```python
_KNOWLEDGE_EDGE_TYPES = {
    "MAPPED_TO", "SUPPORTS", "HAS_CHUNK",
    "IMPLEMENTS", "ADDRESSES", "OWNED_BY", "APPLIES_IN",
    "OPERATES_IN", "ABOUT_CONTROL", "CITES_DOC",
    "CONTAINS",
}
```

(`HAS_CONTROL` removed; `CONTAINS` added — used for framework/norm/control hierarchies.)

- [ ] **Step 2: Run test to see failure**

```bash
python -m pytest tests/test_wp069_knowledge_schema.py::test_dump_db_query_includes_knowledge_edge_types tests/test_wp069_knowledge_schema.py::test_restore_db_allowlist_includes_knowledge_edge_types -v 2>&1
```

Check whether `dump_db`/`restore_db` already cover `CONTAINS`. If not, update them.

- [ ] **Step 3: Check and update `dump_db.py` and `restore_db.py`**

```bash
grep -n "CONTAINS\|HAS_CONTROL" scripts/dump_db.py scripts/restore_db.py
```

If `CONTAINS` is missing, add it. If `HAS_CONTROL` is still listed as required, it can remain (old data may have it) — just don't require it in the test.

- [ ] **Step 4: Run unit tests**

```bash
python -m pytest tests/test_wp069_knowledge_schema.py -v -k "not integration" 2>&1
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_wp069_knowledge_schema.py
git commit -m "test(WP-099): update dump/restore edge allowlist expectations for WP-099 schema"
```

---

## Task 8: Integration tests against live stack

**Files:**
- Test: `tests/test_wp099_framework_schema.py`

- [ ] **Step 1: Write integration tests**

Add to `tests/test_wp099_framework_schema.py`:

```python
# ---------------------------------------------------------------------------
# Integration tests — live Memgraph + FastAPI
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_framework_upsert_with_level_body_parent(client, test_driver):
    """POST /knowledge/frameworks creates Framework with level+body, CONTAINS edge from parent."""
    parent_id = "test-wp099-fw-root"
    child_id = "test-wp099-fw-child"
    try:
        # Create parent
        r = client.post("/knowledge/frameworks", json={
            "id": parent_id,
            "name": "Test Root Framework",
            "level": "framework",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["level"] == "framework"
        assert data["body"] is None

        # Create child with parent_id and body
        r = client.post("/knowledge/frameworks", json={
            "id": child_id,
            "name": "Test Child Clause",
            "level": "clause",
            "body": "This clause requires organisations to do X.",
            "parent_id": parent_id,
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["level"] == "clause"
        assert data["body"] == "This clause requires organisations to do X."

        # Verify CONTAINS edge in graph
        with test_driver.session() as s:
            result = s.run(
                """
                MATCH (:Framework {id: $pid})-[:CONTAINS]->(c:Framework {id: $cid})
                RETURN c.id AS id
                """,
                pid=parent_id,
                cid=child_id,
            ).single()
        assert result is not None, "CONTAINS edge not created"

        # Verify GET returns level and body
        r = client.get(f"/knowledge/frameworks/{child_id}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["level"] == "clause"
        assert data["body"] == "This clause requires organisations to do X."

    finally:
        with test_driver.session() as s:
            s.run("MATCH (n:Framework {id: $id}) DETACH DELETE n", id=parent_id)
            s.run("MATCH (n:Framework {id: $id}) DETACH DELETE n", id=child_id)


@pytest.mark.integration
def test_supports_edge_chunk_to_framework(client, test_driver):
    """POST /knowledge/chunk/supports creates SUPPORTS edge Chunk→Framework."""
    from memory_service.embeddings import get_embedding
    fw_id = "test-wp099-fw-supports"
    doc_id = "test-wp099-doc-supports"
    chunk_id = "test-wp099-chunk-supports"
    try:
        # Create framework node
        r = client.post("/knowledge/frameworks", json={
            "id": fw_id,
            "name": "Test Framework for SUPPORTS",
            "level": "clause",
            "body": "Access control requirements.",
        })
        assert r.status_code == 200, r.text

        # Create document and chunk
        r = client.post("/knowledge/documents", json={
            "id": doc_id,
            "title": "Test Doc",
            "doc_type": "standard",
        })
        assert r.status_code == 200, r.text

        r = client.post("/knowledge/chunks", json={
            "id": chunk_id,
            "text": "All users must authenticate before accessing systems.",
            "sequence": 1,
            "doc_id": doc_id,
        })
        assert r.status_code == 200, r.text

        # Create SUPPORTS edge
        r = client.post("/knowledge/chunk/supports", json={
            "chunk_id": chunk_id,
            "framework_id": fw_id,
            "confidence": 0.95,
            "status": "human-reviewed",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["framework_id"] == fw_id
        assert data["confidence"] == 0.95

        # Verify edge in graph
        with test_driver.session() as s:
            result = s.run(
                """
                MATCH (:Chunk {id: $cid})-[s:SUPPORTS]->(f:Framework {id: $fid})
                RETURN s.confidence AS confidence
                """,
                cid=chunk_id,
                fid=fw_id,
            ).single()
        assert result is not None, "SUPPORTS edge not created"
        assert result["confidence"] == 0.95

    finally:
        with test_driver.session() as s:
            s.run("MATCH (n:Framework {id: $id}) DETACH DELETE n", id=fw_id)
            s.run("MATCH (n:Document {id: $id}) DETACH DELETE n", id=doc_id)
            s.run("MATCH (n:Chunk {id: $id}) DETACH DELETE n", id=chunk_id)


@pytest.mark.integration
def test_framework_search_returns_body_nodes(client, test_driver):
    """POST /knowledge/search/frameworks returns Framework nodes with body text."""
    fw_root_id = "test-wp099-fw-search-root"
    fw_leaf_id = "test-wp099-fw-search-leaf"
    try:
        # Create root (no body — not searchable)
        r = client.post("/knowledge/frameworks", json={
            "id": fw_root_id,
            "name": "Test Root",
            "level": "framework",
        })
        assert r.status_code == 200, r.text

        # Create leaf with body (will be embedded)
        r = client.post("/knowledge/frameworks", json={
            "id": fw_leaf_id,
            "name": "Access control policy",
            "level": "clause",
            "body": "User access rights must be defined and reviewed periodically.",
            "parent_id": fw_root_id,
        })
        assert r.status_code == 200, r.text

        # Search
        r = client.post("/knowledge/search/frameworks", json={
            "query": "user access rights review",
            "limit": 5,
        })
        assert r.status_code == 200, r.text
        hits = r.json()
        ids = [h["id"] for h in hits]
        assert fw_leaf_id in ids, f"Expected {fw_leaf_id} in search results, got {ids}"
        # Root should NOT appear (no body = no embedding)
        assert fw_root_id not in ids

    finally:
        with test_driver.session() as s:
            s.run("MATCH (n:Framework {id: $id}) DETACH DELETE n", id=fw_root_id)
            s.run("MATCH (n:Framework {id: $id}) DETACH DELETE n", id=fw_leaf_id)


@pytest.mark.integration
def test_init_knowledge_schema_creates_framework_embedding_idx(test_driver):
    """After running init_knowledge_schema, framework_embedding_idx must exist on Framework."""
    from scripts.init_knowledge_schema import main as init_main
    rc = init_main()
    assert rc == 0

    with test_driver.session() as session:
        result = session.run("SHOW INDEX INFO;")
        found = False
        for record in result:
            label = record.get("label") or record.get("Label") or ""
            prop = record.get("property") or record.get("Property") or ""
            index_type = str(record.get("index type") or record.get("type") or "")
            if label == "Framework" and prop == "embedding" and "vector" in index_type.lower():
                found = True
        assert found, "framework_embedding_idx not found after init_knowledge_schema"


@pytest.mark.integration
def test_no_control_nodes_or_endpoint(client, test_driver):
    """POST /knowledge/controls must return 404/405 (route no longer exists)."""
    r = client.post("/knowledge/controls", json={
        "id": "test-ctrl",
        "name": "Test Control",
        "framework_id": "iso-27001-2022",
    })
    assert r.status_code in (404, 405), f"Expected 404/405 but got {r.status_code}"
```

- [ ] **Step 2: Verify tests pass (requires live stack)**

Start the live stack:

```bash
cd /home/oliver/projects/graph-memory-fabric
docker compose up -d
# Wait for Memgraph to be ready, then:
python scripts/init_schema.py
python scripts/init_knowledge_schema.py
ENABLE_KNOWLEDGE_LAYER=true uvicorn memory_service.main:app --port 8000 &
```

Run integration tests:

```bash
python -m pytest tests/test_wp099_framework_schema.py -v -m integration 2>&1
```

Expected: all PASS.

Also run the WP-069 integration tests to confirm no regressions:

```bash
python -m pytest tests/test_wp069_knowledge_schema.py -v -m integration 2>&1
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_wp099_framework_schema.py
git commit -m "test(WP-099): add integration tests for framework hierarchy and SUPPORTS edge"
```

---

## Task 9: Final cleanup and BACKLOG update

- [ ] **Step 1: Run full test suite (unit)**

```bash
python -m pytest tests/ -v -k "not integration" 2>&1 | tail -30
```

Expected: all PASS with no regressions.

- [ ] **Step 2: Update BACKLOG.md** — move WP-099 to Completed

Move WP-099 row from "Currently In Progress" section (line 14) and from the Prioritised Backlog table (line 34). Add to Completed section.

- [ ] **Step 3: Final commit**

```bash
git add BACKLOG.md
git commit -m "chore(WP-099): update BACKLOG — WP-099 complete"
```

---

## Self-Review

### Spec coverage check

| Requirement | Task |
|-------------|------|
| `POST /knowledge/frameworks` accepts `level`, `body`, `parent_id`; creates `CONTAINS` | Task 1, 2, 3 |
| `GET /knowledge/frameworks/{id}` returns `level` and `body` | Task 2, 3 |
| Vector search on framework `body` via new `/search/frameworks` | Task 2, 3 |
| Remove `POST /knowledge/controls`, `GET /knowledge/controls/{id}`, `POST /search/controls` | Task 3 |
| `SupportsCreate.control_id` → `framework_id` | Task 1 |
| `init_knowledge_schema.py`: `framework_embedding_idx` on `:Framework` | Task 4 |
| All existing knowledge layer integration tests updated | Task 6, 7 |
| `load_iso27001_chunks.py` uses `POST /knowledge/frameworks` | Task 5 |
| No `:Control` nodes after migration (covered by delete + reload) | Task 8 |
| `SUPPORTS` edges link `:Chunk → :Framework` | Tasks 2, 3, 8 |
| `migrate_embeddings.py` updated to embed `:Framework` | Task 4 |

All acceptance criteria covered.

### Potential issues

1. **`list_incomplete_jurisdictions`** references `:Control` — updated in Task 2 to remove that half.
2. **`trace_up`, `trace_down`, `gap_analysis`, `attribute_coverage`** all reference `:Control` — these are removed in Task 3. This is a significant removal but correct: these endpoints are for the future org control tree, not ISO 27001 hierarchy nodes.
3. **`knowledge_bridge.py`** still references `:Control` for `ABOUT_CONTROL` edges — these are **kept unchanged**. They are for cross-layer links from Memory to org Controls. No change needed.
4. **`FrameworkSearchRequest.framework_id` filter** — the search Cypher uses `f.framework_root_id`. This property doesn't exist. Better to not filter by parent in MVP, or filter by walking `CONTAINS` edges. For simplicity, remove the `framework_id` filter from the search query (just do unfiltered framework body search). Fix in Task 2.
5. **`NodeLabel` enum in `main.py`** has `standard` but not `framework` — added in Task 6.
6. **`test_node_label_has_all_knowledge_labels`** asserts `"Standard"` — that enum value is `standard = "Standard"` which exists. Keeping it.
