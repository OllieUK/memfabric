# WP-039: Ephemeral test-memory handling — TTL, tagging, cleanup

**Date:** 2026-04-09
**Status:** Ready for implementation

---

## Summary

Add an `ephemeral: bool` property to Memory nodes so that test-generated memories
are excluded from normal retrieval and can be hard-deleted in bulk via a single
maintenance endpoint. This stops integration test runs from polluting the live
companion graph.

---

## Approach

Implementation proceeds in strict dependency order: data model → repo → API →
client → CLI → MCP → test updates. Each step is self-contained so parallel
agents can be used for CLI and MCP once the client method exists.

### Step 1 — Data model: `AddMemoryRequest`

In `memory_service/main.py`, add to `AddMemoryRequest`:

```python
ephemeral: bool = False
```

No validator changes required; the field is optional with a safe default.

### Step 2 — Repo layer: `add_memory` Cypher

In `memory_service/memory_repo.py`, add `ephemeral: $ephemeral` to the `CREATE
(m:Memory {...})` block in `add_memory`. Pass `ephemeral=req.ephemeral` in the
`session.run(...)` call.

Note: `req.ephemeral` is a bool. Memgraph stores Python bools natively. No
type-casting required.

### Step 3 — Repo layer: `purge_ephemeral_memories`

Add a new function:

```python
def purge_ephemeral_memories(session) -> int:
    """Hard-delete all ephemeral Memory nodes. Returns count deleted.

    Uses the DETACH DELETE gotcha pattern: count first, delete second.
    DETACH DELETE does not support RETURN, so the count is fetched in a
    separate query before deletion.
    """
    count_result = session.run(
        "MATCH (m:Memory) WHERE m.ephemeral = true RETURN count(m) AS n"
    )
    count = count_result.single()["n"]
    if count > 0:
        session.run(
            "MATCH (m:Memory) WHERE m.ephemeral = true DETACH DELETE m"
        )
    return count
```

This is a single-query batch delete, not a loop over `delete_memory`. It is
more efficient than calling `delete_memory` in a loop and avoids the overhead
of individual existence checks for each node. The pattern mirrors
`_cleanup_by_tag` in `conftest.py`.

### Step 4 — Repo layer: exclude ephemeral from `search_memories`

Add `AND (m.ephemeral IS NULL OR m.ephemeral = false)` to `_SEARCH_QUERY_TEMPLATE`
(after the `status` filter) and to `_PERSON_SEARCH_QUERY_TEMPLATE` (same
position). Both templates already have a `status` guard — ephemeral goes on the
same line/block.

Note: the `fetch_associated` and `find_near_duplicates` functions already filter
`ephemeral`. No changes needed there.

### Step 5 — Repo layer: exclude ephemeral from `wake_up`

In `wake_up`, the core query and the topic vector-search query both need:

```cypher
AND (m.ephemeral IS NULL OR m.ephemeral = false)
```

added to their `WHERE` clause after the `status` guard.

### Step 6 — API layer: `add_memory` handler

No handler change required. `AddMemoryRequest.ephemeral` is passed through to
`memory_repo.add_memory` as part of `req`. The repo reads `req.ephemeral` from
the request object.

### Step 7 — API layer: `purge_ephemeral` endpoint

Add to `memory_service/main.py`:

```python
class PurgeEphemeralResponse(BaseModel):
    deleted: int

@app.post("/memory/maintenance/purge-ephemeral", response_model=PurgeEphemeralResponse)
async def purge_ephemeral(request: Request) -> PurgeEphemeralResponse:
    try:
        with request.app.state.driver.session() as session:
            deleted = memory_repo.purge_ephemeral_memories(session)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return PurgeEphemeralResponse(deleted=deleted)
```

Route follows the same `/memory/maintenance/...` prefix as `short-rest`,
`long-rest`, `decay`, `stats`, and `log`.

### Step 8 — Client layer: `MemoryClient.add_memory` + `purge_ephemeral`

In `memory_client/client.py`:

- Add `ephemeral: bool = False` kwarg to `add_memory`. Add
  `body["ephemeral"] = ephemeral` unconditionally (the server default is also
  `false` but explicit is clearer and avoids silent drift if the server default
  changes).

- Add new method:

```python
def purge_ephemeral(self) -> dict:
    """POST /memory/maintenance/purge-ephemeral. Returns {"deleted": int}."""
    response = self._http.post("/memory/maintenance/purge-ephemeral")
    response.raise_for_status()
    return response.json()
```

### Step 9 — CLI: `memory purge-ephemeral`

Add to `memory_client/cli.py`:

```python
@app.command("purge-ephemeral")
def purge_ephemeral() -> None:
    """Hard-delete all ephemeral memories from the graph."""
    try:
        with _make_client() as client:
            result = client.purge_ephemeral()
        console.print(f"Deleted {result['deleted']} ephemeral memories.")
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)
```

Pattern exactly mirrors other maintenance CLI commands (e.g. `purge-ephemeral`
has no options, just like `list-strands`).

### Step 10 — MCP: `memory_purge_ephemeral`

Add to `mcp_server/server.py`:

```python
@mcp.tool
def memory_purge_ephemeral() -> str:
    """Hard-delete all ephemeral memories from the graph.

    Ephemeral memories are test artefacts created with ephemeral=true.
    Returns a plain-text summary of the count deleted.
    """
    with MemoryClient(base_url=settings.api_base_url) as client:
        result = client.purge_ephemeral()
    return f"Purged {result['deleted']} ephemeral memories."
```

### Step 11 — Update the module docstring in `mcp_server/server.py`

Add `memory_purge_ephemeral` to the tool list in the module docstring.

### Step 12 — Update integration tests

For every integration test that calls `POST /memory` (directly or via the
client), add `"ephemeral": True` (or `ephemeral=True` when using the client).
This requires a coordinated sweep across all integration test files. See Test
Plan for the specific files.

The `cleanup_nodes` fixture in `conftest.py` does not need to change — it
remains the safety net for tests that pre-date this WP or for non-ephemeral
test data.

The session-scoped `_cleanup_by_tag` autouse can stay as an additional safety
net, but should no longer be the primary mechanism for test cleanup after this WP.

---

## Affected Files

| File | Change |
|------|--------|
| `memory_service/main.py` | Add `ephemeral: bool = False` to `AddMemoryRequest`; add `PurgeEphemeralResponse` model; add `POST /memory/maintenance/purge-ephemeral` handler |
| `memory_service/memory_repo.py` | Add `ephemeral: $ephemeral` to `add_memory` Cypher CREATE; add `purge_ephemeral_memories(session) -> int`; add ephemeral filter to `_SEARCH_QUERY_TEMPLATE`, `_PERSON_SEARCH_QUERY_TEMPLATE`, and `wake_up` queries |
| `memory_client/client.py` | Add `ephemeral: bool = False` kwarg to `add_memory`; add `purge_ephemeral() -> dict` method |
| `memory_client/cli.py` | Add `purge-ephemeral` command |
| `mcp_server/server.py` | Add `memory_purge_ephemeral` tool; update module docstring |
| `tests/test_wp039_ephemeral.py` | New test file (unit + integration) |
| All `tests/test_*.py` files with integration tests | Add `ephemeral=True` to test memory writes |

---

## Cypher Patterns

### CREATE with ephemeral flag (in `add_memory`)

```cypher
CREATE (m:Memory {
    id: $id,
    ...existing fields...,
    ephemeral: $ephemeral,
    status: 'active'
})
```

Parameter: `ephemeral` — Python bool, passed as-is.

### Ephemeral filter in search templates

```cypher
WHERE (m.status IS NULL OR m.status = 'active')
  AND (m.ephemeral IS NULL OR m.ephemeral = false)
  AND ($tags IS NULL OR ANY(t IN m.tags WHERE t IN $tags))
  ...
```

The `IS NULL` guard is required because existing nodes written before this WP
do not have the `ephemeral` property. This is the same pattern used in
`find_near_duplicates` and `fetch_associated` which already exclude ephemeral
nodes.

### Purge — count then delete (Memgraph gotcha: DETACH DELETE has no RETURN)

```cypher
-- Query 1: count
MATCH (m:Memory) WHERE m.ephemeral = true RETURN count(m) AS n

-- Query 2: delete (no RETURN clause)
MATCH (m:Memory) WHERE m.ephemeral = true DETACH DELETE m
```

No `IS NULL` guard on the purge side — we only delete nodes explicitly flagged
`ephemeral = true`. Nodes without the property are left untouched.

### Wake-up core query (modified)

```cypher
MATCH (m:Memory)
WHERE (m.status IS NULL OR m.status = 'active')
  AND (m.ephemeral IS NULL OR m.ephemeral = false)
OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
...
```

### Wake-up topic vector-search query (modified)

```cypher
CALL vector_search.search("mem_embedding_idx", $limit, $query_vec)
YIELD node AS m, distance
WITH m, distance
WHERE (m.status IS NULL OR m.status = 'active')
  AND (m.ephemeral IS NULL OR m.ephemeral = false)
...
```

---

## Test Plan

### Unit Tests (`tests/test_wp039_ephemeral.py`)

**U1: `purge_ephemeral_memories` — returns 0 when no ephemeral nodes**

```
mock_session.run returns count=0
assert purge_ephemeral_memories(mock_session) == 0
assert second run (DELETE) is NOT called
```

**U2: `purge_ephemeral_memories` — counts first, deletes second, no RETURN on DELETE**

```
mock_session.run side_effect: [count_result(3), delete_result]
assert purge_ephemeral_memories(mock_session) == 3
assert run called twice
assert second call query contains "DETACH DELETE"
assert second call query does NOT contain "RETURN"
```

**U3: `AddMemoryRequest` default — `ephemeral` defaults to `false`**

```python
req = AddMemoryRequest(fact="x", type="fact", agent_id="test")
assert req.ephemeral is False
```

**U4: `AddMemoryRequest` — `ephemeral=True` accepted**

```python
req = AddMemoryRequest(fact="x", type="fact", agent_id="test", ephemeral=True)
assert req.ephemeral is True
```

**U5: FastAPI handler `POST /memory` passes `ephemeral=True` into repo**

```
Patch memory_repo.add_memory, memory_repo.find_duplicate_memory
POST /memory with {"ephemeral": true, ...}
Assert add_memory was called with req.ephemeral == True
```

**U6: `POST /memory/maintenance/purge-ephemeral` handler returns `{"deleted": N}`**

```
Patch memory_repo.purge_ephemeral_memories to return 7
POST /memory/maintenance/purge-ephemeral
Assert response.status_code == 200
Assert response.json() == {"deleted": 7}
```

**U7: `MemoryClient.purge_ephemeral` sends POST and returns dict**

```
httpx.MockTransport returning {"deleted": 4}
client.purge_ephemeral()
Assert result == {"deleted": 4}
```

**U8: `MemoryClient.add_memory` sends ephemeral=True in body**

```
httpx.MockTransport that captures request body
client.add_memory(..., ephemeral=True)
Assert request_body["ephemeral"] is True
```

**U9: CLI `purge-ephemeral` prints count and exits 0**

```
Patch _make_client, mock client.purge_ephemeral returns {"deleted": 5}
runner.invoke(cli_app, ["purge-ephemeral"])
assert result.exit_code == 0
assert "5" in result.output
```

**U10: CLI `purge-ephemeral` exits 1 on HTTP error**

```
mock client.purge_ephemeral raises HTTPStatusError
runner.invoke(cli_app, ["purge-ephemeral"])
assert result.exit_code == 1
```

**U11: `_SEARCH_QUERY_TEMPLATE` excludes ephemeral**

```python
assert "m.ephemeral" in memory_repo._SEARCH_QUERY_TEMPLATE
```

**U12: `_PERSON_SEARCH_QUERY_TEMPLATE` excludes ephemeral**

```python
assert "m.ephemeral" in memory_repo._PERSON_SEARCH_QUERY_TEMPLATE
```

---

### Integration Tests (require live Memgraph + FastAPI)

Mark all with `@pytest.mark.integration`.

**I1: `POST /memory` with `ephemeral: true` stores node with `ephemeral=true`**

```
POST /memory {"fact": "...", "ephemeral": true, "tags": [TEST_TAG], ...}
assert 200
Directly query Memgraph: MATCH (m:Memory {id: $id}) RETURN m.ephemeral
assert m.ephemeral == True
Cleanup: cleanup_nodes or auto via DETACH DELETE ephemeral
```

**I2: Ephemeral memory excluded from `POST /memory/search`**

```
Create ephemeral memory with a distinctive fact string
Create non-ephemeral memory with same distinctive string
Search for the string
Assert non-ephemeral memory appears in results
Assert ephemeral memory does NOT appear in results
Cleanup: purge-ephemeral (or cleanup_nodes)
```

**I3: Ephemeral memory excluded from `GET /memory/wake-up`**

```
Create ephemeral memory with importance=5 (highest possible, most likely to appear)
GET /memory/wake-up
Assert ephemeral memory id is NOT in response.memories
Cleanup: purge-ephemeral
```

**I4: `POST /memory/maintenance/purge-ephemeral` deletes all ephemeral memories and returns count**

```
Create 3 ephemeral memories (tags=[TEST_TAG])
Create 1 non-ephemeral memory (tags=[TEST_TAG])
POST /memory/maintenance/purge-ephemeral
Assert response.json()["deleted"] == 3
Verify all 3 ephemeral nodes absent from DB
Verify non-ephemeral node still present
Cleanup: cleanup_nodes(non_ephemeral_id)
```

**I5: `POST /memory/maintenance/purge-ephemeral` with no ephemeral nodes returns 0**

```
(Run after I4 already purged, or ensure clean state)
POST /memory/maintenance/purge-ephemeral
Assert response.json()["deleted"] == 0
```

**I6: CLI `memory purge-ephemeral` against live service**

```
Create 2 ephemeral memories
subprocess.run([sys.executable, "-m", "memory_client.cli", "purge-ephemeral"])
assert returncode == 0
assert "2" in stdout
```

---

### Acceptance Criteria

1. `POST /memory` with `"ephemeral": true` succeeds (200) and the node has
   `ephemeral=true` in Memgraph.

2. `POST /memory/search` with a query that would match an ephemeral memory
   returns no ephemeral hits in the `memories` list.

3. `GET /memory/wake-up` never surfaces ephemeral memories regardless of
   their `importance` value.

4. `POST /memory/maintenance/purge-ephemeral` deletes all ephemeral nodes and
   returns `{"deleted": N}` where N is exact.

5. `POST /memory/maintenance/purge-ephemeral` when there are no ephemeral
   nodes returns `{"deleted": 0}` and does not error.

6. `memory purge-ephemeral` CLI command prints the count and exits 0.

7. `memory_purge_ephemeral` MCP tool returns a plain-text summary string.

8. All existing integration tests that call `POST /memory` have been updated
   to pass `"ephemeral": true`, so that a `purge-ephemeral` after any test run
   removes all test artefacts.

9. A non-ephemeral memory written alongside ephemeral test memories survives
   a `purge-ephemeral` intact.

---

## Files to Update with `ephemeral=True` (integration test sweep)

The following test files contain `POST /memory` calls (directly via `client.post`
or via `MemoryClient.add_memory`) that write to the live graph. Each must be
updated to add `"ephemeral": True`.

Identified by searching for `client.post("/memory"` and `client.add_memory`:

- `tests/test_add_memory.py`
- `tests/test_search_memory.py`
- `tests/test_wake_up_close_session.py`
- `tests/test_wp022_neighbour_cap.py`
- `tests/test_wp029_reinforcement.py`
- `tests/test_wp037_person_nodes.py`
- `tests/test_wp038_lifecycle.py`
- `tests/test_wp040_maintenance.py`
- `tests/test_wp046_dedup.py`
- `tests/test_wp047_near_duplicates.py`
- `tests/test_wp048_two_speed_decay.py`
- `tests/test_wp053_scheduled_maintenance.py`
- `tests/test_wp054_maintenance_audit.py`
- `tests/test_wp056_process_log.py`
- `tests/test_wp078_project_nodes.py`
- `tests/test_wp084_health_polish.py`
- `tests/test_wp088_dedup_enforcement.py`
- `tests/test_wp093_agent_search.py`
- `tests/test_wp102_housekeeping.py`
- `tests/test_wp105_cross_framework_informs.py`
- `tests/test_wp111_attack_mitigations.py`
- `tests/test_wp112_sp800_53.py`
- `tests/test_wp118_hard_delete.py`

The implementer should grep for `client.post("/memory"` and `add_memory(` in
the tests directory to confirm this list is complete before starting the sweep.

---

## Implementation Order

1. `memory_service/memory_repo.py` — `add_memory` Cypher, search template
   filters, wake-up filters, `purge_ephemeral_memories`
2. `memory_service/main.py` — `AddMemoryRequest.ephemeral`, purge endpoint
3. `memory_client/client.py` — `add_memory` kwarg, `purge_ephemeral` method
4. `memory_client/cli.py` — `purge-ephemeral` command (parallel with step 5)
5. `mcp_server/server.py` — `memory_purge_ephemeral` tool (parallel with step 4)
6. `tests/test_wp039_ephemeral.py` — new unit + integration tests
7. Integration test sweep — add `ephemeral=True` to all existing test writes

---

## Risks / Open Questions

**Risk: existing Memory nodes without the `ephemeral` property**

The `IS NULL OR = false` guard handles this correctly in all filter positions.
Tested pattern is already used in `find_near_duplicates` and `fetch_associated`.
No migration needed.

**Risk: dedup path swallows `ephemeral` flag**

When `POST /memory` detects an exact duplicate it calls `reinforce_memory` on
the existing node and returns early — the `ephemeral` field from the request
is not applied to the existing node. This is correct behaviour: the existing
node may be a real (non-ephemeral) memory. The test must use a unique enough
fact string to avoid triggering dedup. Flag this in the test comments.

**Risk: purge removes memories needed by an in-flight test**

The purge endpoint is global — it deletes ALL ephemeral memories. If parallel
test sessions run concurrently against the same Memgraph instance, one session's
purge could delete another session's in-flight test nodes. This is acceptable
for the current single-user architecture (v1). Document in the endpoint docstring.

**Open question: should `ephemeral` be exposed in `GET /memory/wake-up` response?**

Not in scope for v1. The exclusion filter is what matters; the property does not
need to be surfaced in any response model for this WP.
