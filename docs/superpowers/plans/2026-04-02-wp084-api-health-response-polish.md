# WP-084 API Health and Response Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three small improvements: (1) add `version` and `build` hash to `/health`; (2) return `strand_ids` in `POST /memory` response; (3) document `### Relevant to today` suppression in `COMPANION.md`.

**Architecture:** All changes are additive and backwards-compatible. The `/health` response gains two new optional fields; `AddMemoryResponse` gains one new field; `COMPANION.md` gains a new prose section. No schema migrations, no new endpoints, no breaking changes.

**Tech Stack:** FastAPI + Pydantic (service), Python `subprocess`/`importlib.metadata` (version), pytest (tests), Markdown (docs).

---

## File Map

| File | Change |
|------|--------|
| `memory_service/main.py` | Add `version` + `build` to `HealthResponse`; add `strand_ids` to `AddMemoryResponse`; populate both in their handlers |
| `memory_client/client.py` | Update `add_memory` return type from `str` to `dict` (returns full response dict including `strand_ids`) |
| `mcp_server/server.py` | Update `memory_add` to return `dict` (pass through full `add_memory` response) |
| `tests/test_add_memory.py` | Add unit + integration tests for `strand_ids` in response |
| `tests/test_wp084_health_polish.py` | New file: unit tests for health endpoint fields and `add_memory` response shape |
| `memory_client/COMPANION.md` | Add `### Relevant to today` suppression explanation under wake-up section |

---

## Task 1: Add `version` and `build` to `/health`

**Files:**
- Modify: `memory_service/main.py` (lines 44–54)

### What to build

`GET /health` currently returns `{"status": "ok"}`. After this task it returns:

```json
{"status": "ok", "version": "0.1.0", "build": "ae71acb"}
```

- `version` — read from `pyproject.toml` via `importlib.metadata.version("graph-memory-fabric")`
- `build` — first 7 characters of the current git commit hash, obtained at startup via `subprocess.run(["git", "rev-parse", "HEAD"], ...)`. If git is unavailable or the directory is not a repo, fall back to `"unknown"`.

Both values are computed once at module import time (top of `main.py`) and embedded in the response — no per-request overhead.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_wp084_health_polish.py`:

```python
"""Unit tests for WP-084: /health version/build fields and add_memory strand_ids response."""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# /health — version and build fields
# ---------------------------------------------------------------------------

class TestHealthVersionBuild:
    def test_health_includes_version_field(self):
        from memory_service.main import app
        with TestClient(app) as c:
            resp = c.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0

    def test_health_includes_build_field(self):
        from memory_service.main import app
        with TestClient(app) as c:
            resp = c.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "build" in data
        assert isinstance(data["build"], str)
        assert len(data["build"]) > 0

    def test_health_build_is_7_chars_or_unknown(self):
        from memory_service.main import app
        with TestClient(app) as c:
            resp = c.get("/health")
        build = resp.json()["build"]
        assert build == "unknown" or len(build) == 7

    def test_health_still_returns_status_ok(self):
        from memory_service.main import app
        with TestClient(app) as c:
            resp = c.get("/health")
        assert resp.json()["status"] == "ok"
```

- [ ] **Step 2: Run test to verify they fail**

```bash
cd /home/oliver/projects/graph-memory-fabric
pytest tests/test_wp084_health_polish.py::TestHealthVersionBuild -v
```

Expected: FAIL — `KeyError: 'version'` or similar.

- [ ] **Step 3: Implement version/build in `memory_service/main.py`**

Add these imports at the top (after existing imports):

```python
import subprocess
from importlib.metadata import version as _pkg_version, PackageNotFoundError
```

Add these two module-level constants after the imports, before the `@asynccontextmanager`:

```python
def _get_build_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        return result.stdout.strip()[:7]
    except Exception:
        return "unknown"


try:
    _SERVICE_VERSION = _pkg_version("graph-memory-fabric")
except PackageNotFoundError:
    _SERVICE_VERSION = "unknown"

_BUILD_HASH = _get_build_hash()
```

Update `HealthResponse` and `health_check`:

```python
class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = _SERVICE_VERSION
    build: str = _BUILD_HASH


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_wp084_health_polish.py::TestHealthVersionBuild -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Smoke-test against live service**

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

Expected output (values will differ):
```json
{"status": "ok", "version": "0.1.0", "build": "6fde99f"}
```

- [ ] **Step 6: Commit**

```bash
git add memory_service/main.py tests/test_wp084_health_polish.py
git commit -m "WP-084: add version and build hash to /health response"
```

---

## Task 2: Return `strand_ids` in `POST /memory` response

**Files:**
- Modify: `memory_service/main.py` (lines 88–125)
- Modify: `memory_client/client.py` (lines 34–57)
- Modify: `mcp_server/server.py` (lines 33–63)

### What to build

`POST /memory` currently returns `{"memory_id": "...", "deduplicated": false}`.
After this task it returns:

```json
{"memory_id": "...", "deduplicated": false, "strand_ids": ["strand-core-health"]}
```

- For a new memory: `strand_ids` = the list from `req.strand_ids` (the request body). These are the strand IDs that were actually linked (unknown strand IDs are silently skipped by `add_memory` in `memory_repo.py`, so we echo the requested list — the caller already knew which ones they asked for).
- For a deduplicated memory (`deduplicated=True`): `strand_ids` = empty list `[]` (the existing memory keeps its own strand links; we don't re-query them here).

The `MemoryClient.add_memory()` return type changes from `str` (memory_id) to `dict` with keys `memory_id`, `deduplicated`, `strand_ids`. The MCP `memory_add` function currently returns `mid` (a string) — update it to return the full dict so callers can access `strand_ids`.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_wp084_health_polish.py`:

```python
# ---------------------------------------------------------------------------
# POST /memory — strand_ids in response
# ---------------------------------------------------------------------------

class TestAddMemoryStrandIdsResponse:
    def test_response_includes_strand_ids_field(self):
        from memory_service.main import app
        with TestClient(app) as c:
            resp = c.post("/memory", json={
                "fact": "test memory for strand_ids response",
                "type": "fact",
                "agent_id": "test-agent-wp084",
                "strand_ids": [],
            })
        assert resp.status_code == 200
        assert "strand_ids" in resp.json()

    def test_empty_strand_ids_returns_empty_list(self):
        from memory_service.main import app
        with TestClient(app) as c:
            resp = c.post("/memory", json={
                "fact": "test memory no strands",
                "type": "fact",
                "agent_id": "test-agent-wp084",
            })
        assert resp.status_code == 200
        assert resp.json()["strand_ids"] == []

    def test_strand_ids_echoed_in_response(self):
        from memory_service.main import app
        import uuid
        suffix = str(uuid.uuid4())
        with TestClient(app) as c:
            resp = c.post("/memory", json={
                "fact": f"test memory with strand {suffix}",
                "type": "fact",
                "agent_id": "test-agent-wp084",
                "strand_ids": ["strand-core-health"],
            })
        assert resp.status_code == 200
        assert resp.json()["strand_ids"] == ["strand-core-health"]

    def test_deduplicated_response_has_empty_strand_ids(self):
        """When a memory is deduplicated, strand_ids in response is []."""
        from memory_service.main import app
        from unittest.mock import patch, MagicMock
        existing_id = "existing-mem-id-001"
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

        with patch("memory_service.main.memory_repo") as mock_repo, \
             patch("memory_service.main.get_embedding", return_value=[0.1] * 384):
            mock_repo.find_duplicate_memory.return_value = existing_id
            mock_repo.reinforce_memory.return_value = None
            with TestClient(app) as c:
                original = app.state.driver
                app.state.driver = mock_driver
                try:
                    resp = c.post("/memory", json={
                        "fact": "duplicate memory test",
                        "type": "fact",
                        "agent_id": "test-agent-wp084",
                        "strand_ids": ["strand-core-health"],
                    })
                finally:
                    app.state.driver = original
        assert resp.status_code == 200
        data = resp.json()
        assert data["deduplicated"] is True
        assert data["strand_ids"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_wp084_health_polish.py::TestAddMemoryStrandIdsResponse -v
```

Expected: FAIL — `KeyError: 'strand_ids'`.

- [ ] **Step 3: Update `AddMemoryResponse` and handler in `memory_service/main.py`**

Replace (lines 88–90):
```python
class AddMemoryResponse(BaseModel):
    memory_id: str
    deduplicated: bool = False
```

With:
```python
class AddMemoryResponse(BaseModel):
    memory_id: str
    deduplicated: bool = False
    strand_ids: List[str] = []
```

Replace the handler return statements (lines 115 and 123):
```python
            if existing_id is not None:
                memory_repo.reinforce_memory(
                    session,
                    existing_id,
                    strength_increment=settings.explicit_strength_increment,
                    edge_increment=settings.edge_explicit_increment,
                    co_recalled_ids=[],
                    now_iso=now,
                    consolidated_decay_rate=settings.memory_consolidated_decay_rate,
                )
                return AddMemoryResponse(memory_id=existing_id, deduplicated=True)
            memory_id = str(uuid.uuid4())
            memory_repo.add_memory(
                session, req, memory_id, embedding, now,
                decay_rate=settings.memory_initial_decay_rate,
                initial_strength_factor=settings.initial_strength_factor,
                importance_floor_factor=settings.importance_floor_factor,
            )
            return AddMemoryResponse(memory_id=memory_id)
```

With:
```python
            if existing_id is not None:
                memory_repo.reinforce_memory(
                    session,
                    existing_id,
                    strength_increment=settings.explicit_strength_increment,
                    edge_increment=settings.edge_explicit_increment,
                    co_recalled_ids=[],
                    now_iso=now,
                    consolidated_decay_rate=settings.memory_consolidated_decay_rate,
                )
                return AddMemoryResponse(memory_id=existing_id, deduplicated=True, strand_ids=[])
            memory_id = str(uuid.uuid4())
            memory_repo.add_memory(
                session, req, memory_id, embedding, now,
                decay_rate=settings.memory_initial_decay_rate,
                initial_strength_factor=settings.initial_strength_factor,
                importance_floor_factor=settings.importance_floor_factor,
            )
            return AddMemoryResponse(memory_id=memory_id, strand_ids=req.strand_ids)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_wp084_health_polish.py::TestAddMemoryStrandIdsResponse -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Update `MemoryClient.add_memory` return type in `memory_client/client.py`**

Replace lines 34–57:
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
        project_id: str | None = None,
        person_ids: list[str] | None = None,
        strand_ids: list[str] | None = None,
        related_ids: list[str] | None = None,
    ) -> str:
        """POST /memory. Returns memory_id string."""
        body: dict = {
            "fact": fact,
            "type": type,
            "agent_id": agent_id,
            "tags": tags or [],
            "importance": importance,
            "person_ids": person_ids or [],
            "strand_ids": strand_ids or [],
        }
        if so_what is not None:
            body["so_what"] = so_what
        if cause_ids is not None:
            body["cause_ids"] = cause_ids
        if effect_ids is not None:
            body["effect_ids"] = effect_ids
        if project_id is not None:
            body["project_id"] = project_id
        if related_ids is not None:
            body["related_ids"] = related_ids
        response = self._http.post("/memory", json=body)
        response.raise_for_status()
        return response.json()["memory_id"]
```

With:
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
        project_id: str | None = None,
        person_ids: list[str] | None = None,
        strand_ids: list[str] | None = None,
        related_ids: list[str] | None = None,
    ) -> dict:
        """POST /memory. Returns dict with memory_id, deduplicated, and strand_ids."""
        body: dict = {
            "fact": fact,
            "type": type,
            "agent_id": agent_id,
            "tags": tags or [],
            "importance": importance,
            "person_ids": person_ids or [],
            "strand_ids": strand_ids or [],
        }
        if so_what is not None:
            body["so_what"] = so_what
        if cause_ids is not None:
            body["cause_ids"] = cause_ids
        if effect_ids is not None:
            body["effect_ids"] = effect_ids
        if project_id is not None:
            body["project_id"] = project_id
        if related_ids is not None:
            body["related_ids"] = related_ids
        response = self._http.post("/memory", json=body)
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 6: Update `memory_add` in `mcp_server/server.py`**

The MCP `memory_add` tool currently does `mid = client.add_memory(...)` and `return mid`.
Now `client.add_memory` returns a dict. Update to return it directly:

Replace (lines 51–63):
```python
    with MemoryClient(base_url=settings.api_base_url) as client:
        mid = client.add_memory(
            fact,
            type,
            agent_id,
            so_what=so_what,
            cause_ids=cause_ids,
            effect_ids=effect_ids,
            tags=tags,
            importance=importance,
            strand_ids=strand_ids,
        )
    return mid
```

With:
```python
    with MemoryClient(base_url=settings.api_base_url) as client:
        result = client.add_memory(
            fact,
            type,
            agent_id,
            so_what=so_what,
            cause_ids=cause_ids,
            effect_ids=effect_ids,
            tags=tags,
            importance=importance,
            strand_ids=strand_ids,
        )
    return str(result)
```

- [ ] **Step 7: Fix callers of `client.add_memory` in CLI**

The CLI in `memory_client/cli.py` calls `client.add_memory(...)` and uses the result.

```bash
grep -n "add_memory\|\.add_memory" /home/oliver/projects/graph-memory-fabric/memory_client/cli.py
```

Find every line that uses the return value and update it to extract `["memory_id"]`. For example if the current pattern is:

```python
memory_id = client.add_memory(...)
```

Change to:

```python
result = client.add_memory(...)
memory_id = result["memory_id"]
```

- [ ] **Step 8: Fix callers of `client.add_memory` in the test suite**

The test helper in `tests/test_wake_up_close_session.py` mocks `client.wake_up_split`. Search for any test mocking or calling `add_memory` that still expects a bare string return:

```bash
grep -rn "add_memory" /home/oliver/projects/graph-memory-fabric/tests/
```

Update any mock `return_value` from a bare string to a dict, e.g.:

```python
mock_client.add_memory.return_value = "mem-123"
# becomes:
mock_client.add_memory.return_value = {"memory_id": "mem-123", "deduplicated": False, "strand_ids": []}
```

- [ ] **Step 9: Run full test suite**

```bash
pytest tests/ -x -q 2>&1 | tail -20
```

Expected: all tests pass (fix any additional callers found during this run).

- [ ] **Step 10: Integration smoke-test**

```bash
curl -s -X POST http://localhost:8000/memory \
  -H "Content-Type: application/json" \
  -d '{"fact":"WP-084 smoke test","type":"fact","agent_id":"claude-code","strand_ids":["strand-core-health"]}' \
  | python3 -m json.tool
```

Expected:
```json
{
  "memory_id": "<uuid>",
  "deduplicated": false,
  "strand_ids": ["strand-core-health"]
}
```

- [ ] **Step 11: Commit**

```bash
git add memory_service/main.py memory_client/client.py mcp_server/server.py memory_client/cli.py tests/test_wp084_health_polish.py
git commit -m "WP-084: return strand_ids in POST /memory response; update client and MCP"
```

---

## Task 3: Add integration tests for `strand_ids` in response (live stack)

**Files:**
- Modify: `tests/test_add_memory.py`

These tests require the live Memgraph stack and use real strand IDs (seeded strands).

- [ ] **Step 1: Write failing integration tests**

Add to `tests/test_add_memory.py` (append to the `TestPostMemoryWithStrands` class or add a new class after it):

```python
@pytest.mark.integration
class TestPostMemoryStrandIdsInResponse:
    """Integration: strand_ids returned in POST /memory response."""

    def test_strand_ids_in_response_when_linked(self, client, test_driver):
        import uuid
        suffix = uuid.uuid4()
        seeded_strand_id = "strand-core-health"
        resp = client.post("/memory", json={
            "fact": f"memory for strand_ids response test {suffix}",
            "type": "fact",
            "agent_id": _AGENT_ID,
            "strand_ids": [seeded_strand_id],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "strand_ids" in data
        assert seeded_strand_id in data["strand_ids"]
        cleanup_nodes(test_driver, data["memory_id"])

    def test_strand_ids_empty_when_none_requested(self, client, test_driver):
        import uuid
        suffix = uuid.uuid4()
        resp = client.post("/memory", json={
            "fact": f"memory with no strands {suffix}",
            "type": "fact",
            "agent_id": _AGENT_ID,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["strand_ids"] == []
        cleanup_nodes(test_driver, data["memory_id"])
```

- [ ] **Step 2: Run integration tests**

```bash
pytest tests/test_add_memory.py::TestPostMemoryStrandIdsInResponse -v -m integration
```

Expected: both PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_add_memory.py
git commit -m "WP-084: integration tests for strand_ids in POST /memory response"
```

---

## Task 4: Document `### Relevant to today` suppression in `COMPANION.md`

**Files:**
- Modify: `memory_client/COMPANION.md`

### What to document

When the memory graph is small or sparse (e.g. fewer than ~50 memories, or a brand-new installation), the `### Relevant to today` section in `memory wake-up` output is suppressed entirely. This is expected behaviour — not an error. The section only appears when there are enough memories for topic-based semantic search to return meaningful results distinct from the core importance-ranked memories.

The documentation should:
1. Explain the suppression in the context of the wake-up output section of `COMPANION.md`
2. Give the concrete threshold/condition in plain terms
3. Confirm it is not an error and what the companion should do when it is absent

- [ ] **Step 1: Find the right location in COMPANION.md**

Open `memory_client/COMPANION.md` and find the `## Session start — memory wake-up` section (around line 85). The note should go after the table of flags and before the "Examples:" block, or appended after the examples in a `> **Note:**` callout.

- [ ] **Step 2: Add the documentation**

In `memory_client/COMPANION.md`, after the `**Examples:**` block and before the `Recommended pattern:` heading in the `## Session start — memory wake-up` section, insert:

```markdown
> **Note — `### Relevant to today` suppression:** On small or sparse graphs (roughly fewer than 50 memories, or any brand-new installation), the `### Relevant to today` section is omitted entirely from wake-up output. This is expected — topic-based semantic search only produces a distinct, useful result set once the graph has enough memories for meaningful recall. Its absence is not an error; proceed with the core memories that were returned. As the fabric grows, the section will appear automatically.
```

- [ ] **Step 3: Verify the file reads cleanly**

```bash
grep -A 5 "Relevant to today" /home/oliver/projects/graph-memory-fabric/memory_client/COMPANION.md
```

Expected: the note text appears in output.

- [ ] **Step 4: Commit**

```bash
git add memory_client/COMPANION.md
git commit -m "WP-084: document Relevant to today suppression in COMPANION.md"
```

---

## Task 5: Update BACKLOG and CHANGELOG; final verification

**Files:**
- Modify: `BACKLOG.md`
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: Run full test suite (unit + integration)**

```bash
pytest tests/ -q 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 2: Move WP-084 to Completed in BACKLOG.md**

Remove the WP-084 row from the Prioritised Backlog table. Add an entry to `docs/CHANGELOG.md`:

```markdown
## WP-084 — API health and response polish

**Completed:** 2026-04-02

- `GET /health` now returns `version` (from package metadata) and `build` (7-char git commit hash, or `"unknown"` if git unavailable)
- `POST /memory` response now includes `strand_ids: list[str]` — echoes the strand IDs that were linked (empty list for deduplicated memories)
- `MemoryClient.add_memory()` return type changed from `str` to `dict` with keys `memory_id`, `deduplicated`, `strand_ids`
- `mcp_server.memory_add` now returns `str(result)` (full dict stringified) so callers can see `strand_ids`
- `COMPANION.md` documents `### Relevant to today` suppression on small/sparse graphs

**Retrospective:** Three independent improvements batched correctly — combined effort was Low as predicted. The `MemoryClient.add_memory` return type change required updating all callers (CLI + mocks); these were few but worth tracking during implementation.
```

- [ ] **Step 3: Final commit**

```bash
git add BACKLOG.md docs/CHANGELOG.md
git commit -m "WP-084: update BACKLOG and CHANGELOG — mark complete"
```

---

## Self-Review

### Spec coverage

| Spec item | Covered by |
|-----------|-----------|
| Add `version`/build hash to `/health` | Task 1 |
| Return `strand_ids` in `add-memory` response | Task 2 + Task 3 |
| Document `### Relevant to today` suppression in `COMPANION.md` | Task 4 |

### Placeholder scan

None found — all steps contain exact code, commands, and expected output.

### Type consistency

- `AddMemoryResponse.strand_ids: List[str]` (Task 2 Step 3) matches test assertion `resp.json()["strand_ids"]` (Task 2 Step 1 and Task 3 Step 1) ✓
- `MemoryClient.add_memory` returns `dict` (Task 2 Step 5); MCP `memory_add` calls `client.add_memory(...)` and gets `dict` (Task 2 Step 6) ✓
- CLI callers updated to `result["memory_id"]` pattern (Task 2 Step 7) ✓
- `_SERVICE_VERSION: str` and `_BUILD_HASH: str` used in `HealthResponse` fields both typed `str` ✓
