# WP-052: Expose `person_ids` in MCP `memory_update` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `person_ids` parameter to the `memory_update` MCP tool so it has full parity with the HTTP PATCH endpoint and Python client.

**Architecture:** The MCP tool `memory_update` in `mcp_server/server.py` delegates to `MemoryClient.update_memory()` which already accepts `person_ids`. The fix is a one-line signature change — add `person_ids: list[str] | None = None` to the MCP tool's parameters and thread it through to the client call. Tests follow the existing unit+integration pattern in `tests/test_wp033_mcp_server.py`.

**Tech Stack:** Python 3.11, FastMCP (`@mcp.tool` decorator), pytest, unittest.mock

---

## File Map

| Action | File |
|--------|------|
| Modify | `mcp_server/server.py` — add `person_ids` param to `memory_update` |
| Modify | `tests/test_wp033_mcp_server.py` — add unit + integration tests for `person_ids` |

---

### Task 1: Add failing unit test for `person_ids` in `memory_update` MCP tool

**Files:**
- Modify: `tests/test_wp033_mcp_server.py`

- [ ] **Step 1.1: Append the new unit test to the test file**

Add this test after the last unit test (before the integration section, around line 122). Open `tests/test_wp033_mcp_server.py` and append before the `# Integration tests` comment block:

```python
# ---------------------------------------------------------------------------
# U8: memory_update passes person_ids through to the client
# ---------------------------------------------------------------------------
def test_u8_memory_update_passes_person_ids():
    from mcp_server.server import memory_update

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.update_memory.return_value = {
        "memory_id": "uuid-abc",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }

    with patch("mcp_server.server.MemoryClient", return_value=mock_client):
        result = memory_update(
            memory_id="uuid-abc",
            person_ids=["person-alice", "person-bob"],
        )

    mock_client.update_memory.assert_called_once_with(
        "uuid-abc",
        fact=None,
        so_what=None,
        tags=None,
        importance=None,
        person_ids=["person-alice", "person-bob"],
        strand_ids=None,
    )
    assert result["memory_id"] == "uuid-abc"
```

- [ ] **Step 1.2: Run the test to confirm it fails**

```bash
cd /home/oliver/projects/graph-memory-fabric && pytest tests/test_wp033_mcp_server.py::test_u8_memory_update_passes_person_ids -v
```

Expected: **FAIL** — `TypeError: memory_update() got an unexpected keyword argument 'person_ids'`

---

### Task 2: Add `person_ids` to the `memory_update` MCP tool

**Files:**
- Modify: `mcp_server/server.py`

Current `memory_update` definition (lines ~229-249):

```python
@mcp.tool
def memory_update(
    memory_id: str,
    fact: str | None = None,
    so_what: str | None = None,
    tags: list[str] | None = None,
    importance: int | None = None,
    strand_ids: list[str] | None = None,
) -> dict:
    """Update an existing active memory's content. Only include fields you want to change.
    fact/so_what changes trigger embedding recomputation. strand_ids is a full replacement.
    Returns {memory_id, updated_at}."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.update_memory(
            memory_id,
            fact=fact,
            so_what=so_what,
            tags=tags,
            importance=importance,
            strand_ids=strand_ids,
        )
```

- [ ] **Step 2.1: Replace the `memory_update` function with the updated version**

Replace the existing `memory_update` function body with:

```python
@mcp.tool
def memory_update(
    memory_id: str,
    fact: str | None = None,
    so_what: str | None = None,
    tags: list[str] | None = None,
    importance: int | None = None,
    person_ids: list[str] | None = None,
    strand_ids: list[str] | None = None,
) -> dict:
    """Update an existing active memory's content. Only include fields you want to change.
    fact/so_what changes trigger embedding recomputation. person_ids and strand_ids are full
    replacements (existing edges are removed and recreated). Returns {memory_id, updated_at}."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.update_memory(
            memory_id,
            fact=fact,
            so_what=so_what,
            tags=tags,
            importance=importance,
            person_ids=person_ids,
            strand_ids=strand_ids,
        )
```

- [ ] **Step 2.2: Run the unit test to confirm it passes**

```bash
cd /home/oliver/projects/graph-memory-fabric && pytest tests/test_wp033_mcp_server.py::test_u8_memory_update_passes_person_ids -v
```

Expected: **PASS**

- [ ] **Step 2.3: Run the full unit test suite to check for regressions**

```bash
cd /home/oliver/projects/graph-memory-fabric && pytest tests/test_wp033_mcp_server.py -v -k "not integration"
```

Expected: All tests **PASS** (U1–U8).

- [ ] **Step 2.4: Commit**

```bash
cd /home/oliver/projects/graph-memory-fabric && git add mcp_server/server.py tests/test_wp033_mcp_server.py && git commit -m "WP-052: expose person_ids in MCP memory_update tool"
```

---

### Task 3: Add integration test for `person_ids` in `memory_update` MCP tool

**Files:**
- Modify: `tests/test_wp033_mcp_server.py`

> **Requires live stack:** Memgraph + FastAPI service must be running. Start with `docker compose up -d` if not already up.

- [ ] **Step 3.1: Append the integration test to the test file**

Add this at the end of `tests/test_wp033_mcp_server.py`:

```python
@pytest.mark.integration
def test_i6_memory_update_person_ids_replaces_about_edges():
    """person_ids passed via MCP memory_update replaces ABOUT→Person edges on the live stack."""
    from mcp_server.server import memory_add, memory_update
    from mcp_server.config import settings
    from memory_client.client import MemoryClient

    # 1. Create a memory linked to person-wp052-a
    memory_id = memory_add(
        fact="WP-052 integration test memory for person_ids",
        type="fact",
        importance=1,
        person_ids=["person-wp052-a"],
    )
    assert isinstance(memory_id, str) and len(memory_id) == 36

    # 2. Use MCP memory_update to replace person link with person-wp052-b
    result = memory_update(
        memory_id=memory_id,
        person_ids=["person-wp052-b"],
    )
    assert result["memory_id"] == memory_id

    # 3. Verify via HTTP API that only person-wp052-b is linked
    with MemoryClient(base_url=settings.api_base_url) as client:
        results = client.search_memory(
            "WP-052 integration test memory for person_ids",
            person_ids=["person-wp052-b"],
            limit=5,
        )
    texts = [r.get("text", "") for r in results]
    assert any("WP-052 integration test memory for person_ids" in t for t in texts)

    # 4. Confirm old person link is gone
    with MemoryClient(base_url=settings.api_base_url) as client:
        old_results = client.search_memory(
            "WP-052 integration test memory for person_ids",
            person_ids=["person-wp052-a"],
            limit=5,
        )
    old_texts = [r.get("text", "") for r in old_results]
    assert not any("WP-052 integration test memory for person_ids" in t for t in old_texts)
```

- [ ] **Step 3.2: Run the integration test against the live stack**

```bash
cd /home/oliver/projects/graph-memory-fabric && pytest tests/test_wp033_mcp_server.py::test_i6_memory_update_person_ids_replaces_about_edges -v -m integration
```

Expected: **PASS** — memory found under new person, not found under old person.

- [ ] **Step 3.3: Run the full test file (unit + integration) to confirm no regressions**

```bash
cd /home/oliver/projects/graph-memory-fabric && pytest tests/test_wp033_mcp_server.py -v
```

Expected: All tests **PASS** (U1–U8, I1–I6).

- [ ] **Step 3.4: Commit**

```bash
cd /home/oliver/projects/graph-memory-fabric && git add tests/test_wp033_mcp_server.py && git commit -m "WP-052: add integration test for person_ids in MCP memory_update"
```

---

### Task 4: Update BACKLOG.md

**Files:**
- Modify: `BACKLOG.md`

- [ ] **Step 4.1: Move WP-052 row to the Completed section**

In `BACKLOG.md`:
1. Delete the WP-052 row from the priority table.
2. Add this entry to the Completed section (after the last completed WP entry):

```
| WP-052 | Expose `person_ids` in MCP `memory_update` | MCP tool now accepts `person_ids` with full parity to HTTP PATCH endpoint. Unit test U8 and integration test I6 added. One-line signature change; no new abstractions needed. |
```

- [ ] **Step 4.2: Add retrospective note to BACKLOG.md**

Append to the Retrospective Notes section (or create it if absent):

```
### WP-052
- **What went well:** Minimal change — single parameter addition to an existing tool; HTTP API, repo layer, and client already handled it correctly.
- **What to improve:** n/a — scope was intentionally narrow.
```

- [ ] **Step 4.3: Commit**

```bash
cd /home/oliver/projects/graph-memory-fabric && git add BACKLOG.md && git commit -m "WP-052: update BACKLOG — mark complete"
```

---

## Self-Review

**Spec coverage:**
- ✅ MCP `memory_update` tool exposes `person_ids` parameter
- ✅ MCP parity with HTTP PATCH endpoint (both now accept `person_ids`)
- ✅ MCP parity with Python client (`client.update_memory` already had `person_ids`)
- ✅ Unit test added alongside tool signature update
- ✅ Integration test added to verify ABOUT edge replacement on live stack

**Placeholder scan:** No TBD/TODO placeholders — all steps include actual code.

**Type consistency:** `list[str] | None` used consistently in server.py signature and test assertion. `person_ids` keyword name matches client method signature exactly.
