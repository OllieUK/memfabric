# WP-039: Ephemeral Test-Memory Handling — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `ephemeral` flag to memories so integration tests can write to the live graph without polluting companion context, plus a purge endpoint for batch cleanup.

**Architecture:** Add `ephemeral: bool` field to `AddMemoryRequest` and store it as a property on Memory nodes. Exclude ephemeral memories from search and wake-up by default. Add `POST /memory/maintenance/purge-ephemeral` for batch deletion. Wire through CLI and MCP. Does NOT change the `status` field — `ephemeral` is orthogonal (a memory can be active+ephemeral or archived+ephemeral).

**Tech Stack:** FastAPI, Pydantic, neo4j Python driver, Typer CLI, FastMCP, pytest

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `memory_service/main.py:84-112` | Add `ephemeral` to `AddMemoryRequest` |
| Modify | `memory_service/main.py` | Add `POST /memory/maintenance/purge-ephemeral` endpoint |
| Modify | `memory_service/memory_repo.py:35-56` | Store `ephemeral` on CREATE |
| Modify | `memory_service/memory_repo.py:183-227` | Exclude ephemeral in search query templates |
| Modify | `memory_service/memory_repo.py:345-399` | Exclude ephemeral in wake-up queries |
| Modify | `memory_service/memory_repo.py` | Add `purge_ephemeral()` function |
| Modify | `memory_service/memory_repo.py:1601-1649` | Exclude ephemeral in `find_duplicate_memory()` |
| Modify | `memory_client/client.py:19-57` | Add `ephemeral` to `add_memory()`, add `purge_ephemeral()` |
| Modify | `memory_client/cli.py` | Add `purge-ephemeral` command |
| Modify | `mcp_server/server.py` | Add `ephemeral` to `memory_add`, add `memory_purge_ephemeral` tool |
| Create | `tests/test_wp039_ephemeral.py` | Unit + integration tests |

---

### Task 1: Store `ephemeral` property on Memory nodes

**Files:**
- Modify: `memory_service/main.py:84-112` (AddMemoryRequest)
- Modify: `memory_service/memory_repo.py:35-56` (CREATE query)
- Create: `tests/test_wp039_ephemeral.py`

- [ ] **Step 1: Create test file with model test**

Create `tests/test_wp039_ephemeral.py`:

```python
# tests/test_wp039_ephemeral.py
"""Tests for WP-039: ephemeral test-memory handling."""
import pytest

from tests.conftest import cleanup_nodes, edge_exists

_AGENT_ID = "test-agent-wp039"
_BASE_URL = "http://localhost:8000"


def _cleanup(driver, *memory_ids):
    cleanup_nodes(driver, *memory_ids)
    with driver.session() as session:
        session.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)


def _add_body(fact: str, ephemeral: bool = False, **kwargs) -> dict:
    body = {
        "fact": fact,
        "type": "fact",
        "agent_id": _AGENT_ID,
        "importance": 1,
    }
    if ephemeral:
        body["ephemeral"] = True
    body.update(kwargs)
    return body


# ---------------------------------------------------------------------------
# Task 1 — Unit: AddMemoryRequest accepts ephemeral field
# ---------------------------------------------------------------------------
class TestAddMemoryRequestEphemeral:
    def test_default_false(self):
        from memory_service.main import AddMemoryRequest
        req = AddMemoryRequest(fact="test", type="fact", agent_id="a")
        assert req.ephemeral is False

    def test_explicit_true(self):
        from memory_service.main import AddMemoryRequest
        req = AddMemoryRequest(fact="test", type="fact", agent_id="a", ephemeral=True)
        assert req.ephemeral is True
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/test_wp039_ephemeral.py::TestAddMemoryRequestEphemeral -v`
Expected: FAIL — `ephemeral` field not on model.

- [ ] **Step 3: Add `ephemeral` to AddMemoryRequest**

In `memory_service/main.py`, add to `AddMemoryRequest` (after `effect_ids` field):

```python
    ephemeral: bool = False
```

- [ ] **Step 4: Store `ephemeral` in Memory CREATE Cypher**

In `memory_service/memory_repo.py`, modify the CREATE query in `add_memory()` (line 38-56). Add `ephemeral: $ephemeral` to the property map, and add the parameter to the `session.run()` call:

Add to CREATE properties (after `status: 'active'`):
```python
    ephemeral: $ephemeral
```

Add to the `session.run()` kwargs:
```python
    ephemeral=getattr(req, "ephemeral", False),
```

- [ ] **Step 5: Run test — expect PASS**

Run: `pytest tests/test_wp039_ephemeral.py::TestAddMemoryRequestEphemeral -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add memory_service/main.py memory_service/memory_repo.py tests/test_wp039_ephemeral.py
git commit -m "WP-039: add ephemeral field to AddMemoryRequest and Memory CREATE"
```

---

### Task 2: Exclude ephemeral memories from search

**Files:**
- Modify: `memory_service/memory_repo.py:183-227` (both query templates)
- Test: `tests/test_wp039_ephemeral.py`

- [ ] **Step 1: Add search exclusion test**

Append to `tests/test_wp039_ephemeral.py`:

```python
# ---------------------------------------------------------------------------
# Task 2 — Integration: ephemeral memories excluded from search
# ---------------------------------------------------------------------------
class TestEphemeralSearchExclusion:
    @pytest.mark.integration
    def test_ephemeral_excluded_from_search(self, client, test_driver):
        """Ephemeral memories do not appear in search results."""
        mid = None
        try:
            r = client.post("/memory", json=_add_body("WP039 ephemeral search test", ephemeral=True))
            assert r.status_code == 200
            mid = r.json()["memory_id"]

            r2 = client.post("/memory/search", json={"query": "WP039 ephemeral search test", "limit": 10})
            assert r2.status_code == 200
            hit_ids = [h["id"] for h in r2.json()["memories"]]
            assert mid not in hit_ids
        finally:
            if mid:
                _cleanup(test_driver, mid)

    @pytest.mark.integration
    def test_non_ephemeral_still_found(self, client, test_driver):
        """Normal memories still appear in search."""
        mid = None
        try:
            r = client.post("/memory", json=_add_body("WP039 normal search test unique phrase xyz"))
            assert r.status_code == 200
            mid = r.json()["memory_id"]

            r2 = client.post("/memory/search", json={"query": "WP039 normal search test unique phrase xyz", "limit": 10})
            assert r2.status_code == 200
            hit_ids = [h["id"] for h in r2.json()["memories"]]
            assert mid in hit_ids
        finally:
            if mid:
                _cleanup(test_driver, mid)
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/test_wp039_ephemeral.py::TestEphemeralSearchExclusion -v -m integration`
Expected: FAIL — ephemeral memory appears in search.

- [ ] **Step 3: Add ephemeral filter to search query templates**

In `memory_service/memory_repo.py`, modify `_SEARCH_QUERY_TEMPLATE` (line ~187). Change the WHERE clause:

```
WHERE (m.status IS NULL OR m.status = 'active')
```

To:

```
WHERE (m.status IS NULL OR m.status = 'active')
AND   (m.ephemeral IS NULL OR m.ephemeral = false)
```

Apply the same change to `_PERSON_SEARCH_QUERY_TEMPLATE` (line ~215):

```
AND   (m.status IS NULL OR m.status = 'active')
```

To:

```
AND   (m.status IS NULL OR m.status = 'active')
AND   (m.ephemeral IS NULL OR m.ephemeral = false)
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/test_wp039_ephemeral.py::TestEphemeralSearchExclusion -v -m integration`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memory_service/memory_repo.py tests/test_wp039_ephemeral.py
git commit -m "WP-039: exclude ephemeral memories from search"
```

---

### Task 3: Exclude ephemeral memories from wake-up

**Files:**
- Modify: `memory_service/memory_repo.py:345-399` (wake-up queries)
- Test: `tests/test_wp039_ephemeral.py`

- [ ] **Step 1: Add wake-up exclusion test**

Append to `tests/test_wp039_ephemeral.py`:

```python
# ---------------------------------------------------------------------------
# Task 3 — Integration: ephemeral memories excluded from wake-up
# ---------------------------------------------------------------------------
class TestEphemeralWakeUpExclusion:
    @pytest.mark.integration
    def test_ephemeral_excluded_from_wakeup(self, client, test_driver):
        """Ephemeral memories do not appear in wake-up."""
        mid = None
        try:
            r = client.post("/memory", json=_add_body(
                "WP039 ephemeral wakeup test", ephemeral=True, importance=5,
            ))
            assert r.status_code == 200
            mid = r.json()["memory_id"]

            r2 = client.get("/memory/wake-up?limit=100")
            assert r2.status_code == 200
            hit_ids = [m["id"] for m in r2.json()["memories"]]
            assert mid not in hit_ids
        finally:
            if mid:
                _cleanup(test_driver, mid)
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/test_wp039_ephemeral.py::TestEphemeralWakeUpExclusion -v -m integration`
Expected: FAIL — ephemeral memory appears in wake-up.

- [ ] **Step 3: Add ephemeral filter to wake-up queries**

In `memory_service/memory_repo.py`, find the core wake-up query (around line 358) and the topic wake-up query (around line 385). Add the ephemeral exclusion after the status filter in both:

```
AND   (m.ephemeral IS NULL OR m.ephemeral = false)
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/test_wp039_ephemeral.py::TestEphemeralWakeUpExclusion -v -m integration`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memory_service/memory_repo.py tests/test_wp039_ephemeral.py
git commit -m "WP-039: exclude ephemeral memories from wake-up"
```

---

### Task 4: Exclude ephemeral from duplicate detection

**Files:**
- Modify: `memory_service/memory_repo.py:1601-1649` (`find_duplicate_memory`)
- Test: `tests/test_wp039_ephemeral.py`

- [ ] **Step 1: Add dedup exclusion test**

Append to `tests/test_wp039_ephemeral.py`:

```python
# ---------------------------------------------------------------------------
# Task 4 — Integration: ephemeral memories don't block dedup
# ---------------------------------------------------------------------------
class TestEphemeralDedupExclusion:
    @pytest.mark.integration
    def test_ephemeral_not_matched_as_duplicate(self, client, test_driver):
        """Posting a normal memory with same fact as an ephemeral one creates a new node."""
        mid_eph = mid_normal = None
        try:
            # Create ephemeral memory first
            r1 = client.post("/memory", json=_add_body("WP039 dedup test fact", ephemeral=True))
            assert r1.status_code == 200
            mid_eph = r1.json()["memory_id"]

            # Create normal memory with same fact — should NOT deduplicate
            r2 = client.post("/memory", json=_add_body("WP039 dedup test fact"))
            assert r2.status_code == 200
            mid_normal = r2.json()["memory_id"]
            assert r2.json().get("deduplicated") is not True
            assert mid_normal != mid_eph
        finally:
            if mid_eph:
                _cleanup(test_driver, mid_eph)
            if mid_normal:
                _cleanup(test_driver, mid_normal)
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/test_wp039_ephemeral.py::TestEphemeralDedupExclusion -v -m integration`
Expected: FAIL — ephemeral memory matched as duplicate.

- [ ] **Step 3: Add ephemeral filter to `find_duplicate_memory`**

In `memory_service/memory_repo.py`, modify `find_duplicate_memory()`. In the exact-match query (line ~1621), add:

```
AND (m.ephemeral IS NULL OR m.ephemeral = false)
```

In the vector-similarity query (line ~1637), add:

```
AND (node.ephemeral IS NULL OR node.ephemeral = false)
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/test_wp039_ephemeral.py::TestEphemeralDedupExclusion -v -m integration`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memory_service/memory_repo.py tests/test_wp039_ephemeral.py
git commit -m "WP-039: exclude ephemeral memories from duplicate detection"
```

---

### Task 5: Purge-ephemeral endpoint and repo function

**Files:**
- Modify: `memory_service/memory_repo.py` (new function)
- Modify: `memory_service/main.py` (new endpoint)
- Test: `tests/test_wp039_ephemeral.py`

- [ ] **Step 1: Add purge tests**

Append to `tests/test_wp039_ephemeral.py`:

```python
# ---------------------------------------------------------------------------
# Task 5 — Integration: purge-ephemeral endpoint
# ---------------------------------------------------------------------------
class TestPurgeEphemeral:
    @pytest.mark.integration
    def test_purge_deletes_ephemeral_only(self, client, test_driver):
        """Purge deletes ephemeral memories but keeps normal ones."""
        mid_eph = mid_normal = None
        try:
            r1 = client.post("/memory", json=_add_body("WP039 purge eph", ephemeral=True))
            mid_eph = r1.json()["memory_id"]

            r2 = client.post("/memory", json=_add_body("WP039 purge normal"))
            mid_normal = r2.json()["memory_id"]

            r3 = client.post("/memory/maintenance/purge-ephemeral")
            assert r3.status_code == 200
            data = r3.json()
            assert data["deleted"] >= 1

            # Verify ephemeral is gone
            with test_driver.session() as session:
                result = session.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.id AS id", id=mid_eph
                )
                assert result.single() is None

            # Verify normal is still there
            with test_driver.session() as session:
                result = session.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.id AS id", id=mid_normal
                )
                assert result.single() is not None
        finally:
            if mid_normal:
                _cleanup(test_driver, mid_normal)

    @pytest.mark.integration
    def test_purge_returns_zero_when_none(self, client):
        """Purge returns deleted=0 when no ephemeral memories exist."""
        # First purge any leftovers
        client.post("/memory/maintenance/purge-ephemeral")
        # Second call should return 0
        r = client.post("/memory/maintenance/purge-ephemeral")
        assert r.status_code == 200
        assert r.json()["deleted"] == 0
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/test_wp039_ephemeral.py::TestPurgeEphemeral -v -m integration`
Expected: FAIL — endpoint doesn't exist (404).

- [ ] **Step 3: Add `purge_ephemeral` repo function**

In `memory_service/memory_repo.py`, add:

```python
def purge_ephemeral(session) -> int:
    """Hard-delete all ephemeral memories. Returns count deleted."""
    result = session.run(
        "MATCH (m:Memory) WHERE m.ephemeral = true "
        "WITH count(m) AS cnt "
        "MATCH (m:Memory) WHERE m.ephemeral = true "
        "DETACH DELETE m "
        "RETURN cnt"
    )
    record = result.single()
    return record["cnt"] if record else 0
```

Note: DETACH DELETE in Memgraph does not support RETURN, so we count first then delete.

- [ ] **Step 4: Add purge endpoint to main.py**

In `memory_service/main.py`, add a response model and endpoint (near the other maintenance endpoints):

```python
class PurgeEphemeralResponse(BaseModel):
    deleted: int


@app.post("/memory/maintenance/purge-ephemeral", response_model=PurgeEphemeralResponse)
async def purge_ephemeral(request: Request) -> PurgeEphemeralResponse:
    try:
        with request.app.state.driver.session() as session:
            deleted = memory_repo.purge_ephemeral(session)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return PurgeEphemeralResponse(deleted=deleted)
```

- [ ] **Step 5: Run test — expect PASS**

Run: `pytest tests/test_wp039_ephemeral.py::TestPurgeEphemeral -v -m integration`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add memory_service/memory_repo.py memory_service/main.py tests/test_wp039_ephemeral.py
git commit -m "WP-039: add purge-ephemeral endpoint"
```

---

### Task 6: Client, CLI, and MCP wiring

**Files:**
- Modify: `memory_client/client.py` (add `ephemeral` to `add_memory`, add `purge_ephemeral`)
- Modify: `memory_client/cli.py` (add `purge-ephemeral` command)
- Modify: `mcp_server/server.py` (add `ephemeral` to `memory_add`, add `memory_purge_ephemeral` tool)
- Test: `tests/test_wp039_ephemeral.py`

- [ ] **Step 1: Add client + CLI + MCP unit tests**

Append to `tests/test_wp039_ephemeral.py`:

```python
import httpx
import respx
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner

from memory_client.cli import app as cli_app
from memory_client.client import MemoryClient

_cli_runner = CliRunner()


# ---------------------------------------------------------------------------
# Task 6 — Unit: client methods
# ---------------------------------------------------------------------------
class TestClientEphemeral:
    @respx.mock
    def test_add_memory_passes_ephemeral(self):
        respx.post(f"{_BASE_URL}/memory").mock(
            return_value=httpx.Response(200, json={"memory_id": "uuid-1", "strand_ids": []})
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            client.add_memory("fact", "fact", "agent", ephemeral=True)
        import json
        body = json.loads(respx.calls.last.request.content)
        assert body["ephemeral"] is True

    @respx.mock
    def test_purge_ephemeral(self):
        respx.post(f"{_BASE_URL}/memory/maintenance/purge-ephemeral").mock(
            return_value=httpx.Response(200, json={"deleted": 5})
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            result = client.purge_ephemeral()
        assert result["deleted"] == 5


# ---------------------------------------------------------------------------
# Task 6 — Unit: CLI purge-ephemeral
# ---------------------------------------------------------------------------
class TestCliPurgeEphemeral:
    @respx.mock
    def test_purge_ephemeral_output(self):
        respx.post(f"{_BASE_URL}/memory/maintenance/purge-ephemeral").mock(
            return_value=httpx.Response(200, json={"deleted": 3})
        )
        result = _cli_runner.invoke(cli_app, ["purge-ephemeral"])
        assert result.exit_code == 0
        assert "3" in result.output


# ---------------------------------------------------------------------------
# Task 6 — Unit: MCP memory_purge_ephemeral
# ---------------------------------------------------------------------------
class TestMcpPurgeEphemeral:
    def test_purge_ephemeral_calls_client(self):
        from mcp_server.server import memory_purge_ephemeral

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.purge_ephemeral.return_value = {"deleted": 2}

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            result = memory_purge_ephemeral()

        mock_client.purge_ephemeral.assert_called_once()
        assert result["deleted"] == 2
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/test_wp039_ephemeral.py -k "TestClient or TestCli or TestMcp" -v`
Expected: FAIL — methods/commands/tools don't exist yet.

- [ ] **Step 3: Add `ephemeral` to `MemoryClient.add_memory()`**

In `memory_client/client.py`, add `ephemeral: bool = False` to the `add_memory()` signature (keyword-only). In the body construction, add:

```python
    if ephemeral:
        body["ephemeral"] = True
```

- [ ] **Step 4: Add `purge_ephemeral()` to MemoryClient**

In `memory_client/client.py`, add:

```python
    def purge_ephemeral(self) -> dict:
        """POST /memory/maintenance/purge-ephemeral. Returns {deleted: int}."""
        response = self._http.post("/memory/maintenance/purge-ephemeral")
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 5: Add `purge-ephemeral` CLI command**

In `memory_client/cli.py`, add:

```python
@app.command("purge-ephemeral")
def purge_ephemeral() -> None:
    """Hard-delete all ephemeral memories from the fabric."""
    try:
        with _make_client() as client:
            result = client.purge_ephemeral()
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)
    console.print(f"Ephemeral memories deleted: {result['deleted']}")
```

- [ ] **Step 6: Add `ephemeral` to MCP `memory_add` and add `memory_purge_ephemeral` tool**

In `mcp_server/server.py`, add `ephemeral: bool = False` parameter to `memory_add()` and pass it through:

```python
    person_ids=person_ids,
    ephemeral=ephemeral,
```

Add new MCP tool:

```python
@mcp.tool
def memory_purge_ephemeral() -> dict:
    """Hard-delete all ephemeral memories. Returns {deleted: int}."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.purge_ephemeral()
```

Update the module docstring to include `memory_purge_ephemeral`.

- [ ] **Step 7: Run tests — expect PASS**

Run: `pytest tests/test_wp039_ephemeral.py -k "TestClient or TestCli or TestMcp" -v`
Expected: PASS

- [ ] **Step 8: Run full test suite**

Run: `pytest tests/ -v --timeout=30`
Expected: All existing tests pass — no regressions.

- [ ] **Step 9: Commit**

```bash
git add memory_client/client.py memory_client/cli.py mcp_server/server.py tests/test_wp039_ephemeral.py
git commit -m "WP-039: wire ephemeral through client, CLI, and MCP"
```

---

### Task 7: Finalise — BACKLOG update and /simplify

- [ ] **Step 1: Move WP-039 to Completed in BACKLOG.md**
- [ ] **Step 2: Run `/simplify`**
- [ ] **Step 3: Final commit**

```bash
git add BACKLOG.md
git commit -m "WP-039: update BACKLOG — mark complete"
```
