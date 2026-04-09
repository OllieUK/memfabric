# WP-118: `DELETE /memory/{id}` hard-delete endpoint

**Date:** 2026-04-09
**Status:** Ready for implementation

## Summary

Add a hard-delete path that permanently removes a Memory node and all its edges
from the graph via `DETACH DELETE`. The operation is exposed as
`DELETE /memory/{id}` (HTTP 204), a CLI command `memory delete <id>`, and an
MCP tool `memory_delete`. This unblocks WP-039 (purge-ephemeral) and eliminates
the current requirement for operators to bypass the API entirely.

## Approach

### Step 1 — `memory_repo.delete_memory(session, memory_id)`

Add to `memory_service/memory_repo.py`, following the same two-query pattern
used in `archive_memory` and `restore_memory`:

1. **Existence check (MATCH + RETURN):** Run a separate query that MATCHes the
   node and returns its id. If `result.single()` is `None`, raise
   `ValueError(f"Memory {memory_id!r} not found")`.
2. **Delete (DETACH DELETE — no RETURN):** Run a second query that MATCHes the
   same node and issues `DETACH DELETE`. Per the Memgraph gotcha documented in
   CLAUDE.md, `DETACH DELETE` does not support a `RETURN` clause — the node
   count is captured in step 1 and the delete runs unconditionally in step 2.

No status filter: a hard-delete should succeed regardless of whether the memory
is active, archived, or merged. The archive/restore pattern filters by status
because it enforces state-machine transitions; delete does not need that
constraint.

### Step 2 — `DELETE /memory/{memory_id}` in `main.py`

Add after the `restore_memory` route (around line 924) and before the
`reinforce_memory` route:

- No request body, no response model (HTTP 204 = `Response(status_code=204)`).
- Call `memory_repo.delete_memory(session, memory_id)` inside the standard
  `with request.app.state.driver.session() as session:` block.
- Call `memory_repo.append_operation_log(session, {...})` **in the same
  session** immediately after delete (the log is stored on the `System` node,
  not the deleted `Memory` node, so this is safe).
- Map `ValueError` → 404, `ServiceUnavailable` → 503.
- Return `Response(status_code=204)` on success.

The operation log entry shape mirrors the archive/restore entries:
```python
{
    "operation": "delete",
    "memory_id": memory_id,
    "ran_at": now,
}
```

### Step 3 — `MemoryClient.delete_memory(memory_id)` in `memory_client/client.py`

Add after `restore_memory`:

```python
def delete_memory(self, memory_id: str) -> None:
    """DELETE /memory/{id}. Returns None on 204."""
    response = self._http.delete(f"/memory/{memory_id}")
    response.raise_for_status()
```

Returns `None` (204 has no body). `raise_for_status()` raises
`httpx.HTTPStatusError` on 404.

### Step 4 — CLI `memory delete <id>` in `memory_client/cli.py`

Add after the `restore-memory` command, before `find-duplicates`:

```python
@app.command("delete")
def delete_memory(
    memory_id: str = typer.Argument(..., help="Memory UUID to permanently delete"),
) -> None:
    """Permanently delete a memory and all its edges (irreversible)."""
```

- On success: print `Deleted {memory_id[:8]}`.
- On `HTTPStatusError`: print the status and body to stderr, exit 1.
- On `ConnectError`: print connection error, exit 1.

No confirmation prompt is included in scope (the caller is the API or a script;
interactive prompts add complexity without clear value here).

### Step 5 — MCP tool `memory_delete` in `mcp_server/server.py`

Add after `memory_restore`, before `memory_merge`:

```python
@mcp.tool
def memory_delete(memory_id: str) -> str:
    """Permanently delete a memory and all its edges from the graph.

    This is irreversible — use memory_archive if you want a reversible path.
    Returns a plain-text confirmation string.
    """
    with MemoryClient(base_url=settings.api_base_url) as client:
        client.delete_memory(memory_id)
    return f"Deleted memory {memory_id}"
```

Also update the module-level docstring at the top of `mcp_server/server.py` to
include `memory_delete` in the tool list.

## Affected Files

| File | Change |
|------|--------|
| `memory_service/memory_repo.py` | Add `delete_memory(session, memory_id)` function |
| `memory_service/main.py` | Add `DELETE /memory/{memory_id}` route |
| `memory_client/client.py` | Add `delete_memory(memory_id)` method |
| `memory_client/cli.py` | Add `delete` CLI command |
| `mcp_server/server.py` | Add `memory_delete` tool; update module docstring |
| `tests/test_wp118_hard_delete.py` | New test file (unit + integration) |

## Cypher Patterns

### Existence check (query 1)
```cypher
MATCH (m:Memory {id: $id})
RETURN m.id AS id
```
Parameters: `id` (str, the memory UUID)

If `result.single()` is `None` → raise `ValueError(f"Memory {memory_id!r} not found")`.

### Hard delete (query 2)
```cypher
MATCH (m:Memory {id: $id})
DETACH DELETE m
```
Parameters: `id` (str, the memory UUID)

No RETURN clause — Memgraph does not support RETURN after DETACH DELETE.

## Test Plan

### Unit Tests (`tests/test_wp118_hard_delete.py`)

| # | Test | What it verifies |
|---|------|-----------------|
| U1 | `test_delete_memory_repo_raises_on_missing` | `memory_repo.delete_memory` raises `ValueError` when MATCH returns no row (mock session where `result.single()` returns `None`) |
| U2 | `test_delete_memory_repo_calls_detach_delete` | `memory_repo.delete_memory` issues `DETACH DELETE` query as second call when node exists (mock session) |
| U3 | `test_client_delete_memory_sends_delete_request` | `MemoryClient.delete_memory` issues `DELETE /memory/{id}` via respx mock, returns None on 204 |
| U4 | `test_client_delete_memory_raises_on_404` | `MemoryClient.delete_memory` raises `httpx.HTTPStatusError` when service returns 404 |
| U5 | `test_cli_delete_prints_confirmation` | `memory delete <id>` CLI command prints "Deleted" and exits 0 when service returns 204 (respx mock) |
| U6 | `test_cli_delete_prints_error_on_404` | CLI exits 1 and prints error when service returns 404 |
| U7 | `test_route_delete_returns_204_on_success` | FastAPI handler returns 204 when `memory_repo.delete_memory` succeeds (mock driver) |
| U8 | `test_route_delete_returns_404_on_missing` | FastAPI handler returns 404 when repo raises `ValueError` (mock driver) |

### Integration Tests (require live Memgraph + FastAPI — `@pytest.mark.integration`)

All integration tests use the `client` and `test_driver` fixtures from
`tests/conftest.py`. Test memories are created with `tags=["test"]` and cleaned
up in `finally` blocks.

| # | Test | What it verifies |
|---|------|-----------------|
| I1 | `test_delete_returns_204_and_node_is_gone` | POST /memory to create, DELETE /memory/{id}, verify 204, verify node absent via `get_memory_node` |
| I2 | `test_delete_removes_all_edges` | Create two memories with a RELATED_TO edge, DELETE one, verify no orphan edges via direct Cypher on `test_driver` |
| I3 | `test_delete_nonexistent_returns_404` | DELETE /memory/{uuid} for a UUID that never existed → 404 |
| I4 | `test_delete_appends_operation_log` | Create memory, DELETE it, GET /memory/operation/log, verify an entry with `operation=delete` and matching `memory_id` is present |
| I5 | `test_delete_archived_memory_succeeds` | Create memory, archive it, DELETE it → 204 and node gone (verify delete is status-agnostic) |
| I6 | `test_cli_delete_integration` | Run `memory delete <id>` via CLI runner against the live service; verify exit 0 and "Deleted" in output |

### Acceptance Criteria

1. `DELETE /memory/{id}` returns 204 and the node is no longer retrievable via
   any GET or search endpoint.
2. `DELETE /memory/{id}` on a non-existent ID returns 404 with a JSON detail
   message.
3. All edges attached to the deleted node are removed (`DETACH DELETE` is
   verified by the integration test checking orphan edges).
4. An operation log entry `{operation: "delete", memory_id: ..., ran_at: ...}`
   is appended on each successful delete.
5. `memory delete <id>` CLI command prints `Deleted <8-char prefix>` and exits
   0 on success; exits 1 on 404.
6. MCP `memory_delete` tool returns a confirmation string and propagates HTTP
   errors as exceptions.
7. No status filter on delete: memories in active, archived, and merged states
   are all successfully deleted.

## Risks / Open Questions

**R1 — Operation log session ordering.** `append_operation_log` runs in the
same session as the delete. After `DETACH DELETE m`, the session is still open
and the `System` node is unaffected — the log write is safe. Confirmed by
reading `append_operation_log` implementation (operates on `System {id:
"system"}`, not the deleted node).

**R2 — Two-query approach for DETACH DELETE.** The Memgraph gotcha means we
cannot use `DETACH DELETE m RETURN count(m)` to detect existence. The
two-query pattern (check then delete) introduces a TOCTOU window. This is
acceptable for v1: the service is single-writer per memory node, and the worst
case is a silent no-op if the node is deleted between the two queries. The
first query already throws for the normal 404 path.

**R3 — No confirmation prompt in CLI.** Accepted by design: the CLI is used
by scripts and automation, not interactive end-users. If an interactive guard
is needed later, add `--force / -y` as a follow-on.

**R4 — MCP tool name collision.** The existing tool list in `mcp_server/server.py`
docstring must be updated to include `memory_delete` — easy mechanical change,
no risk.

**R5 — WP-039 dependency.** WP-039 (ephemeral TTL / purge) lists WP-118 as a
dependency. This plan does not scope WP-039 work; only the atomic delete
primitive is delivered here.
