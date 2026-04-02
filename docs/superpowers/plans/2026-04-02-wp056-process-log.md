# WP-056: Process Log for Lifecycle and Maintenance Operations

**Date:** 2026-04-02
**Status:** Ready for implementation

## Summary

Add append-only operation logging for the four lifecycle operations — `update`, `merge`, `archive`, `restore` — storing entries on the `System` node in a new `operation_log` property, and expose them via `GET /memory/operation/log`, an MCP tool, and a client method.

## Design Decisions

**Separate property (`operation_log`) from `maintenance_log`.**
The two logs have different schemas: maintenance entries record bulk decay stats; operation entries record per-memory mutations with `memory_id` and operation-specific detail. Mixing them would require defensive field access on every reader and would pollute `MaintenanceLogEntry`. A second property on the same `System` node is the minimal change — no new node label, no schema migration, same read/write pattern.

**No `agent_id` in WP-056.**
The lifecycle endpoints do not currently accept `agent_id` in the request body and adding it is a separate scope concern. WP-056 logs what it can observe at the call site: operation, memory_id, ran_at, and op-specific outcome fields. `agent_id` can be added in a follow-up WP once the endpoint contract is settled.

**Log written in the handler, not in the repo function.**
`update_memory`, `archive_memory`, `restore_memory`, `merge_memory` are repo primitives that do not own the session lifecycle. The handler opens the session, calls the repo function, then appends the log entry — all within the same session block. This keeps the repo functions side-effect-free and mirrors the maintenance pattern (short_rest/long_rest call `append_maintenance_log` inside the same session they were passed).

**Cap at 200 entries** (separate constant `_OPERATION_LOG_CAP = 200`). Lifecycle ops are called more frequently than maintenance runs, so a higher cap is appropriate. The same read-append-write-cap pattern used for maintenance log is reused verbatim.

**Entry schema per operation:**

| operation | common fields | extra fields |
|-----------|---------------|--------------|
| `update` | `operation`, `memory_id`, `ran_at` | `fields_updated: list[str]` |
| `merge` | `operation`, `memory_id`, `ran_at` | `target_id: str` |
| `archive` | `operation`, `memory_id`, `ran_at` | — |
| `restore` | `operation`, `memory_id`, `ran_at` | — |

`fields_updated` for `update` is the set of keys passed in the patch body (before embedding recomputation), e.g. `["fact", "tags"]`. This is derivable from `patch_fields` before the repo call.

## Approach

### Step 1 — `memory_service/memory_repo.py`

Add two new functions alongside the existing maintenance log pair:

```python
_OPERATION_LOG_CAP = 200

def get_operation_log(session) -> list:
    # OPTIONAL MATCH (sys:System {id: "system"})
    # RETURN sys.operation_log AS operation_log
    # same null/parse-error handling as get_maintenance_log

def append_operation_log(session, entry: dict) -> None:
    # read, append, cap, write — identical pattern to append_maintenance_log
    # property name: operation_log
```

No changes to existing repo functions.

### Step 2 — `memory_service/main.py`

**New Pydantic models** (after `MaintenanceLogResponse`):

```python
class OperationLogEntry(BaseModel):
    operation: str
    memory_id: str
    ran_at: str
    # optional op-specific fields — use Optional so all entry types validate
    fields_updated: Optional[List[str]] = None
    target_id: Optional[str] = None

class OperationLogResponse(BaseModel):
    entries: List[OperationLogEntry]
```

**New endpoint** (after `GET /memory/maintenance/log`):

```python
@app.get("/memory/operation/log", response_model=OperationLogResponse)
async def operation_log(request: Request) -> OperationLogResponse:
    ...
```

**Handler changes** — add `append_operation_log` call inside the existing `with session` block, after the successful repo call, in each of the four lifecycle handlers:

- `PATCH /memory/{memory_id}` (`update_memory` handler): append entry with `fields_updated=list(req.model_dump(exclude_none=True).keys())`
- `POST /memory/{memory_id}/merge` (`merge_memory` handler): append entry with `target_id=req.target_id`
- `POST /memory/{memory_id}/archive` (`archive_memory` handler): append minimal entry
- `POST /memory/{memory_id}/restore` (`restore_memory` handler): append minimal entry

The `ran_at` timestamp is already computed in the `update` and `archive` handlers; for `merge` and `restore`, compute it locally in the handler before the `with session` block (same pattern as the others).

### Step 3 — `mcp_server/server.py`

Add new MCP tool after `memory_maintenance_log`:

```python
@mcp.tool
def memory_operation_log() -> str:
    """Return the lifecycle operation log as plain text (most recent first)."""
```

Format: one line per entry — `{ran_at}  {operation}  {memory_id}  [{extra}]`

### Step 4 — `memory_client/client.py`

Add method after `maintenance_log`:

```python
def operation_log(self) -> list[dict]:
    """GET /memory/operation/log. Returns list of operation entry dicts."""
    response = self._http.get("/memory/operation/log")
    response.raise_for_status()
    return response.json()["entries"]
```

## Affected Files

| File | Change |
|------|--------|
| `memory_service/memory_repo.py` | Add `_OPERATION_LOG_CAP`, `get_operation_log`, `append_operation_log` |
| `memory_service/main.py` | Add `OperationLogEntry`, `OperationLogResponse`, `GET /memory/operation/log`; add `append_operation_log` call in four lifecycle handlers |
| `mcp_server/server.py` | Add `memory_operation_log` MCP tool |
| `memory_client/client.py` | Add `operation_log()` method |
| `tests/test_wp056_process_log.py` | New test file |

## Cypher Patterns

No new Cypher queries are required. `get_operation_log` and `append_operation_log` use the same pattern as their maintenance counterparts, changing only the property name:

```cypher
-- read
OPTIONAL MATCH (sys:System {id: "system"})
RETURN sys.operation_log AS operation_log

-- write
MERGE (sys:System {id: "system"})
SET sys.operation_log = $log_json
```

No `DETACH DELETE` or `RETURN` after mutation — not applicable here.

## Test Plan

### Unit Tests — `tests/test_wp056_process_log.py`

All unit tests use `MagicMock` sessions and `pytest.MonkeyPatch`, following the WP-054 patterns exactly.

**`TestAppendOperationLog`**
- `test_appends_entry_to_empty_log` — first call creates a single-entry list; verifies `session.run` call count and written JSON
- `test_appends_entry_to_existing_log` — subsequent call appends; both entries present in written JSON
- `test_caps_log_at_200_entries` — log with 200 entries drops oldest on append; result is still 200

**`TestGetOperationLog`**
- `test_returns_empty_list_when_no_log` — `sys.operation_log` is None → returns `[]`
- `test_returns_parsed_list` — JSON on node → returns parsed list
- `test_returns_empty_on_corrupt_json` — malformed string → returns `[]` (error tolerance)

**`TestUpdateHandlerLogsEntry`**
- Monkeypatch `memory_repo.update_memory` and `memory_repo.append_operation_log`; call `PATCH /memory/{id}` via `TestClient`; verify `append_operation_log` was called with `operation="update"`, correct `memory_id`, and `fields_updated` containing the patched keys

**`TestMergeHandlerLogsEntry`**
- Same pattern; verify `operation="merge"`, `target_id` matches request

**`TestArchiveHandlerLogsEntry`**
- Verify `operation="archive"`, `memory_id` correct, no extra fields required

**`TestRestoreHandlerLogsEntry`**
- Verify `operation="restore"`, `memory_id` correct

**`TestOperationLogEndpoint`**
- `test_returns_entries` — mock `get_operation_log`; `GET /memory/operation/log` returns 200 with `entries` list
- `test_returns_empty` — mock returns `[]`; response is `{"entries": []}`

**`TestOperationLogClientMethod`**
- Mock HTTP response; `client.operation_log()` returns list of dicts from `entries` key

**`TestMcpOperationLogTool`**
- Mock `MemoryClient`; `memory_operation_log()` returns non-empty string with expected fields when entries present
- Returns "No operation log entries yet." when empty

### Integration Tests (require live Memgraph + FastAPI)

`@pytest.mark.integration` class `TestOperationLogIntegration` in the same test file.

All tests call the live service at `http://localhost:8000`.

- `test_update_creates_log_entry` — PATCH a known memory; GET `/memory/operation/log`; verify latest entry has `operation="update"` and correct `memory_id` and `fields_updated`
- `test_merge_creates_log_entry` — POST merge on two live memories; GET log; verify `operation="merge"`, `target_id` correct
- `test_archive_creates_log_entry` — POST archive; GET log; verify `operation="archive"`
- `test_restore_creates_log_entry` — POST restore on an archived memory; GET log; verify `operation="restore"`
- `test_log_endpoint_returns_200` — GET `/memory/operation/log` returns 200 and `entries` key present (smoke test, no prior op required)
- `test_failed_op_does_not_write_log_entry` — PATCH a non-existent memory_id; GET log; entry count unchanged (ValueError path must not log)

### Acceptance Criteria

1. `GET /memory/operation/log` returns HTTP 200 with `{"entries": [...]}` after any lifecycle operation is executed against the live service.
2. Each entry has `operation`, `memory_id`, `ran_at` fields. `update` entries have `fields_updated`; `merge` entries have `target_id`.
3. A failed operation (404 path — memory not found) does not append a log entry.
4. After 200+ operations the log is capped at 200 entries (oldest dropped).
5. `memory_operation_log()` MCP tool returns a human-readable plain-text summary of entries, most recent first.
6. `MemoryClient.operation_log()` returns a Python list of dicts matching the endpoint's `entries` array.

## Risks / Open Questions

- **Session scope for logging on failure:** The `update_memory` handler opens one session and calls `update_memory` then `append_operation_log` within it. If `append_operation_log` raises (e.g. Memgraph hiccup after a successful update), the log write fails silently. This is acceptable for a traceability log — the operation itself succeeded. No rollback complexity is warranted.
- **`merge` handler has no `now` variable today.** The `merge_memory` handler does not compute `now`. Step 2 adds `now = datetime.now(tz=timezone.utc).isoformat()` at the top of that handler, matching the `update` and `archive` handlers. This is a purely mechanical addition.
- **`restore` handler has no `now` variable today.** Same resolution — add `now` computation at the top of the `restore_memory` handler.
- **`agent_id` deferred.** Out of scope for WP-056. Tracking note: add to a future WP when lifecycle endpoints gain `agent_id` support.
