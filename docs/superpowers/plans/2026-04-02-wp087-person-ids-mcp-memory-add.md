# WP-087: Expose `person_ids` in MCP `memory_add` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `person_ids` parameter to the MCP `memory_add` tool so memories can be linked to people at creation time via the MCP surface.

**Architecture:** One-parameter addition to the MCP wrapper function in `mcp_server/server.py`. The HTTP API (`POST /memory`) and Python client (`MemoryClient.add_memory`) already support `person_ids` — only the MCP tool signature is missing it. Identical pattern to WP-052 which added `person_ids` to `memory_update`.

**Tech Stack:** FastMCP, pytest, unittest.mock

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `mcp_server/server.py:32-63` | Add `person_ids` param to `memory_add` tool + pass to client |
| Modify | `tests/test_wp033_mcp_server.py` | Add unit test (mock) + integration test (live stack) |

---

### Task 1: Unit test — MCP `memory_add` passes `person_ids`

**Files:**
- Test: `tests/test_wp033_mcp_server.py`

- [ ] **Step 1: Add unit test**

Append to `tests/test_wp033_mcp_server.py` (after existing WP-052 tests, following the `test_u8_memory_update_passes_person_ids` pattern):

```python
# ---------------------------------------------------------------------------
# U9: memory_add passes person_ids to client (WP-087)
# ---------------------------------------------------------------------------
def test_u9_memory_add_passes_person_ids():
    from mcp_server.server import memory_add

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.add_memory.return_value = {"memory_id": "uuid-new"}

    with patch("mcp_server.server.MemoryClient", return_value=mock_client):
        result = memory_add(
            fact="Test memory with persons",
            agent_id="test-agent",
            person_ids=["person-alice", "person-bob"],
        )

    mock_client.add_memory.assert_called_once_with(
        "Test memory with persons",
        "fact",
        "test-agent",
        so_what=None,
        cause_ids=None,
        effect_ids=None,
        tags=None,
        importance=3,
        strand_ids=None,
        person_ids=["person-alice", "person-bob"],
    )
    assert result["memory_id"] == "uuid-new"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wp033_mcp_server.py::test_u9_memory_add_passes_person_ids -v`
Expected: FAIL — `memory_add()` got an unexpected keyword argument `person_ids`.

---

### Task 2: Implementation — add `person_ids` to MCP `memory_add`

**Files:**
- Modify: `mcp_server/server.py:32-63`

- [ ] **Step 1: Add `person_ids` parameter and pass it through**

In `mcp_server/server.py`, modify the `memory_add` function:

Change the signature (lines 32-42) from:

```python
@mcp.tool
def memory_add(
    fact: str,
    agent_id: str,
    type: str = "fact",
    strand_ids: list[str] | None = None,
    tags: list[str] | None = None,
    importance: int = 3,
    so_what: str | None = None,
    cause_ids: list[str] | None = None,
    effect_ids: list[str] | None = None,
) -> dict:
```

To:

```python
@mcp.tool
def memory_add(
    fact: str,
    agent_id: str,
    type: str = "fact",
    strand_ids: list[str] | None = None,
    tags: list[str] | None = None,
    importance: int = 3,
    so_what: str | None = None,
    cause_ids: list[str] | None = None,
    effect_ids: list[str] | None = None,
    person_ids: list[str] | None = None,
) -> dict:
```

Change the client call (lines 51-62) from:

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
```

To:

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
            person_ids=person_ids,
        )
```

- [ ] **Step 2: Run unit test to verify it passes**

Run: `pytest tests/test_wp033_mcp_server.py::test_u9_memory_add_passes_person_ids -v`
Expected: PASS

- [ ] **Step 3: Run all existing MCP unit tests for regressions**

Run: `pytest tests/test_wp033_mcp_server.py -v -k "not integration"`
Expected: All existing unit tests still PASS.

- [ ] **Step 4: Commit**

```bash
git add mcp_server/server.py tests/test_wp033_mcp_server.py
git commit -m "WP-087: expose person_ids in MCP memory_add"
```

---

### Task 3: Integration test — live stack verification

**Files:**
- Test: `tests/test_wp033_mcp_server.py`

- [ ] **Step 1: Add integration test**

Append to `tests/test_wp033_mcp_server.py` (after existing integration tests, following the `test_i6_memory_update_person_ids_replaces_about_edges` pattern):

```python
# ---------------------------------------------------------------------------
# I7: memory_add with person_ids creates ABOUT edges on live stack (WP-087)
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_i7_memory_add_person_ids_creates_about_edges(test_driver):
    """person_ids passed via MCP memory_add creates ABOUT->Person edges on the live stack."""
    from mcp_server.server import memory_add
    from tests.conftest import cleanup_nodes, edge_exists

    memory_id = None
    try:
        raw = memory_add(
            fact="WP-087 integration: memory with person_ids via MCP",
            type="fact",
            agent_id="test-agent-wp087",
            importance=1,
            person_ids=["person-wp087-a", "person-wp087-b"],
        )
        memory_id = raw["memory_id"]
        assert isinstance(memory_id, str) and len(memory_id) == 36

        # Verify ABOUT edges to both persons
        assert edge_exists(test_driver, memory_id, "ABOUT", "person-wp087-a")
        assert edge_exists(test_driver, memory_id, "ABOUT", "person-wp087-b")
    finally:
        if memory_id:
            cleanup_nodes(test_driver, memory_id)
        # Clean up Person nodes
        with test_driver.session() as session:
            session.run("MATCH (p:Person {id: $id}) DETACH DELETE p", id="person-wp087-a")
            session.run("MATCH (p:Person {id: $id}) DETACH DELETE p", id="person-wp087-b")
        # Clean up Agent node
        with test_driver.session() as session:
            session.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id="test-agent-wp087")
```

- [ ] **Step 2: Run integration test against live stack**

Run: `pytest tests/test_wp033_mcp_server.py::test_i7_memory_add_person_ids_creates_about_edges -v`
Expected: PASS. Requires Memgraph + FastAPI to be running.

- [ ] **Step 3: Run full MCP test suite**

Run: `pytest tests/test_wp033_mcp_server.py -v`
Expected: All tests PASS (unit + integration).

- [ ] **Step 4: Commit**

```bash
git add tests/test_wp033_mcp_server.py
git commit -m "WP-087: add integration test for person_ids in MCP memory_add"
```

---

### Task 4: Finalise — BACKLOG update and /simplify

- [ ] **Step 1: Move WP-087 to Completed in BACKLOG.md**

Remove WP-087 from the priority table and add to Completed section.

- [ ] **Step 2: Run `/simplify`**

Review all changed code for quality. This is a tiny change — /simplify should confirm it's clean.

- [ ] **Step 3: Final commit**

```bash
git add BACKLOG.md
git commit -m "WP-087: update BACKLOG — mark complete"
```
