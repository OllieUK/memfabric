# WP-054: Maintenance Audit Trail and Startup Escalation Loop

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record every maintenance run (short-rest / long-rest) as a structured audit log entry on the System node, and escalate the wake-up maintenance warning from a passive text note to an actionable prompt that surfaces overdue status for *both* short-rest and long-rest.

**Architecture:** Maintenance audit entries are stored as a JSON-serialised list on the `System` node (`maintenance_log` property — append-only, capped at 100 entries). The `/memory/wake-up` response gains a `maintenance_status` field that replaces the single `maintenance_warning` string with a structured object carrying overdue booleans, days-since values, and a recommended action string. The MCP `memory_wake_up` tool is updated to surface overdue warnings prominently in its plain-text output.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, Neo4j Bolt driver (Memgraph), pytest, unittest.mock

---

## File Map

| File | Change |
|------|--------|
| `memory_service/memory_repo.py` | Add `append_maintenance_log()`, `get_maintenance_log()`. Extend `short_rest()` and `long_rest()` to call `append_maintenance_log()` after writing the System node. |
| `memory_service/main.py` | Replace `maintenance_warning: Optional[str]` on `WakeUpResponse` with `maintenance_status: MaintenanceStatus`. Update wake-up handler. Add `GET /memory/maintenance/log` endpoint. Add `MaintenanceStatus`, `MaintenanceLogResponse` Pydantic models. |
| `mcp_server/server.py` | Update `memory_wake_up()` to surface `maintenance_status` as prominent text lines. Add `memory_maintenance_log()` MCP tool. |
| `memory_client/client.py` | Add `maintenance_log()` method. Update `wake_up_split()` to return maintenance_status. |
| `tests/test_wp054_maintenance_audit.py` | All new unit + integration tests. |

---

## Task 1: Audit log helpers in `memory_repo.py`

**Files:**
- Modify: `memory_service/memory_repo.py`
- Test: `tests/test_wp054_maintenance_audit.py`

The `System` node gains a `maintenance_log` property: a JSON string encoding a list of entry objects. Each entry:
```python
{
    "operation": "short_rest" | "long_rest",
    "ran_at": "<ISO timestamp>",
    "dry_run": bool,
    "nodes_affected": int,   # nodes_decayed
    "edges_affected": int,   # edges_decayed
    "edges_discovered": int, # long_rest only, else 0
    "edges_pruned": int,     # long_rest only, else 0
}
```
Capped at 100 entries (oldest dropped when over limit).

- [ ] **Step 1.1: Write failing unit tests for `append_maintenance_log` and `get_maintenance_log`**

Create `tests/test_wp054_maintenance_audit.py`:

```python
# tests/test_wp054_maintenance_audit.py
"""WP-054: Maintenance audit trail and startup escalation loop."""
import json
import pytest
from unittest.mock import MagicMock, call
from memory_service import memory_repo


class TestAppendMaintenanceLog:
    def _make_session(self, existing_log=None):
        """Return a mock session whose run() returns existing_log JSON or None."""
        session = MagicMock()
        record = MagicMock()
        record.__getitem__ = lambda self, key: (
            json.dumps(existing_log) if existing_log is not None else None
        )
        session.run.return_value.single.return_value = record
        return session

    def test_appends_entry_to_empty_log(self):
        """First call creates a single-entry list."""
        session = self._make_session(existing_log=None)
        entry = {
            "operation": "short_rest",
            "ran_at": "2026-04-01T10:00:00+00:00",
            "dry_run": False,
            "nodes_affected": 5,
            "edges_affected": 2,
            "edges_discovered": 0,
            "edges_pruned": 0,
        }
        memory_repo.append_maintenance_log(session, entry)
        # Should call session.run twice: once to read, once to write
        assert session.run.call_count == 2
        write_call = session.run.call_args_list[1]
        # The written JSON should contain our entry
        written_json = write_call[1]["log_json"]
        parsed = json.loads(written_json)
        assert len(parsed) == 1
        assert parsed[0]["operation"] == "short_rest"
        assert parsed[0]["nodes_affected"] == 5

    def test_appends_entry_to_existing_log(self):
        """Subsequent calls append to existing list."""
        existing = [
            {
                "operation": "short_rest",
                "ran_at": "2026-03-01T00:00:00+00:00",
                "dry_run": False,
                "nodes_affected": 3,
                "edges_affected": 1,
                "edges_discovered": 0,
                "edges_pruned": 0,
            }
        ]
        session = self._make_session(existing_log=existing)
        new_entry = {
            "operation": "long_rest",
            "ran_at": "2026-04-01T10:00:00+00:00",
            "dry_run": False,
            "nodes_affected": 10,
            "edges_affected": 3,
            "edges_discovered": 2,
            "edges_pruned": 0,
        }
        memory_repo.append_maintenance_log(session, new_entry)
        write_call = session.run.call_args_list[1]
        parsed = json.loads(write_call[1]["log_json"])
        assert len(parsed) == 2
        assert parsed[-1]["operation"] == "long_rest"

    def test_caps_log_at_100_entries(self):
        """When log has 100 entries, oldest is dropped on append."""
        existing = [
            {
                "operation": "short_rest",
                "ran_at": f"2025-01-{i:02d}T00:00:00+00:00",
                "dry_run": False,
                "nodes_affected": i,
                "edges_affected": 0,
                "edges_discovered": 0,
                "edges_pruned": 0,
            }
            for i in range(1, 101)  # 100 entries
        ]
        session = self._make_session(existing_log=existing)
        new_entry = {
            "operation": "long_rest",
            "ran_at": "2026-04-01T10:00:00+00:00",
            "dry_run": False,
            "nodes_affected": 999,
            "edges_affected": 0,
            "edges_discovered": 0,
            "edges_pruned": 0,
        }
        memory_repo.append_maintenance_log(session, new_entry)
        write_call = session.run.call_args_list[1]
        parsed = json.loads(write_call[1]["log_json"])
        assert len(parsed) == 100
        # Oldest entry (nodes_affected=1) dropped; newest is long_rest
        assert parsed[-1]["nodes_affected"] == 999
        assert parsed[0]["nodes_affected"] == 2  # entry with i=2 is now first

    def test_skipped_when_dry_run(self):
        """append_maintenance_log is not called when dry_run=True."""
        # This is tested at the short_rest/long_rest level (Task 2)
        # Here just verify append_maintenance_log itself still writes dry_run entries
        # (the caller decides whether to call it)
        session = self._make_session(existing_log=None)
        entry = {
            "operation": "short_rest",
            "ran_at": "2026-04-01T10:00:00+00:00",
            "dry_run": True,
            "nodes_affected": 0,
            "edges_affected": 0,
            "edges_discovered": 0,
            "edges_pruned": 0,
        }
        memory_repo.append_maintenance_log(session, entry)
        assert session.run.call_count == 2  # still reads and writes


class TestGetMaintenanceLog:
    def test_returns_empty_list_when_no_log(self):
        """Returns [] when System node has no maintenance_log."""
        session = MagicMock()
        record = MagicMock()
        record.__getitem__ = lambda self, key: None
        session.run.return_value.single.return_value = record
        result = memory_repo.get_maintenance_log(session)
        assert result == []

    def test_returns_parsed_list(self):
        """Returns the parsed list from System node maintenance_log."""
        entries = [
            {
                "operation": "short_rest",
                "ran_at": "2026-04-01T10:00:00+00:00",
                "dry_run": False,
                "nodes_affected": 5,
                "edges_affected": 2,
                "edges_discovered": 0,
                "edges_pruned": 0,
            }
        ]
        session = MagicMock()
        record = MagicMock()
        record.__getitem__ = lambda self, key: json.dumps(entries)
        session.run.return_value.single.return_value = record
        result = memory_repo.get_maintenance_log(session)
        assert len(result) == 1
        assert result[0]["operation"] == "short_rest"
```

- [ ] **Step 1.2: Run tests to confirm they fail**

```bash
cd /home/oliver/projects/graph-memory-fabric
pytest tests/test_wp054_maintenance_audit.py::TestAppendMaintenanceLog tests/test_wp054_maintenance_audit.py::TestGetMaintenanceLog -v
```
Expected: FAIL — `AttributeError: module 'memory_service.memory_repo' has no attribute 'append_maintenance_log'`

- [ ] **Step 1.3: Implement `append_maintenance_log` and `get_maintenance_log` in `memory_repo.py`**

Add after the `upsert_system_node` function (after line ~1100):

```python
_MAINTENANCE_LOG_CAP = 100


def get_maintenance_log(session) -> list:
    """Return the maintenance audit log from the System node.

    Returns a list of dicts (parsed from JSON). Empty list if not set.
    """
    result = session.run(
        """
        OPTIONAL MATCH (sys:System {id: "system"})
        RETURN sys.maintenance_log AS maintenance_log
        """
    )
    record = result.single()
    if record is None:
        return []
    raw = record["maintenance_log"]
    if raw is None:
        return []
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return []


def append_maintenance_log(session, entry: dict) -> None:
    """Append an audit entry to the System node maintenance_log (capped at 100).

    Reads current log, appends, caps, and writes back atomically within the
    same session. entry must be a JSON-serialisable dict.
    """
    import json as _json

    existing = get_maintenance_log(session)
    existing.append(entry)
    if len(existing) > _MAINTENANCE_LOG_CAP:
        existing = existing[-_MAINTENANCE_LOG_CAP:]
    log_json = _json.dumps(existing)
    session.run(
        """
        MERGE (sys:System {id: "system"})
        SET sys.maintenance_log = $log_json
        """,
        log_json=log_json,
    )
```

Also add `import json` at the top of `memory_repo.py` if not already present.

- [ ] **Step 1.4: Check if `json` is already imported in `memory_repo.py`**

```bash
cd /home/oliver/projects/graph-memory-fabric
head -20 memory_service/memory_repo.py
```

If `import json` is missing, add it to the imports section.

- [ ] **Step 1.5: Run tests to confirm they pass**

```bash
pytest tests/test_wp054_maintenance_audit.py::TestAppendMaintenanceLog tests/test_wp054_maintenance_audit.py::TestGetMaintenanceLog -v
```
Expected: PASS (all 5 tests)

- [ ] **Step 1.6: Commit**

```bash
git add memory_service/memory_repo.py tests/test_wp054_maintenance_audit.py
git commit -m "WP-054: add append_maintenance_log and get_maintenance_log"
```

---

## Task 2: Wire audit logging into `short_rest` and `long_rest`

**Files:**
- Modify: `memory_service/memory_repo.py` (short_rest and long_rest functions)
- Test: `tests/test_wp054_maintenance_audit.py`

Audit logging is only written on non-dry-run runs (same guard as the System timestamp write).

- [ ] **Step 2.1: Write failing tests**

Add this class to `tests/test_wp054_maintenance_audit.py`:

```python
class TestShortRestLogsAuditEntry:
    def _run_short_rest(self, dry_run=False):
        """Run short_rest with a mocked session that returns no nodes (empty graph)."""
        session = MagicMock()
        # node query returns empty
        session.run.return_value.__iter__ = lambda s: iter([])
        session.run.return_value = MagicMock()
        session.run.return_value.__iter__ = lambda s: iter([])
        session.run.return_value.single.return_value = MagicMock(
            **{"__getitem__": lambda self, k: None}
        )

        # We need a smarter mock: first call (node fetch) returns [], subsequent calls vary
        call_results = []
        node_result = MagicMock()
        node_result.__iter__ = lambda s: iter([])
        call_results.append(node_result)  # node query

        # For append_maintenance_log: read returns None (no existing log)
        read_result = MagicMock()
        read_record = MagicMock()
        read_record.__getitem__ = lambda self, k: None
        read_result.single.return_value = read_record
        call_results.append(read_result)  # upsert_system_node (no return needed)
        call_results.append(MagicMock())  # append read
        call_results.append(MagicMock())  # append write

        session.run.side_effect = call_results

        return memory_repo.short_rest(
            session,
            now_iso="2026-04-01T10:00:00+00:00",
            recency_days=7,
            min_strength=0.0,
            edge_modulation_factor=0.5,
            edge_modulation_cap=10.0,
            dry_run=dry_run,
        )

    def test_audit_log_written_on_real_run(self):
        """short_rest writes an audit entry when dry_run=False."""
        with pytest.MonkeyPatch.context() as mp:
            logged = []
            mp.setattr(
                memory_repo,
                "append_maintenance_log",
                lambda session, entry: logged.append(entry),
            )
            memory_repo.short_rest(
                MagicMock(run=MagicMock(return_value=MagicMock(
                    __iter__=lambda s: iter([]),
                    single=MagicMock(return_value=None),
                ))),
                now_iso="2026-04-01T10:00:00+00:00",
                recency_days=7,
                min_strength=0.0,
                edge_modulation_factor=0.5,
                edge_modulation_cap=10.0,
                dry_run=False,
            )
        assert len(logged) == 1
        assert logged[0]["operation"] == "short_rest"
        assert logged[0]["dry_run"] is False
        assert "ran_at" in logged[0]
        assert "nodes_affected" in logged[0]
        assert "edges_affected" in logged[0]

    def test_audit_log_not_written_on_dry_run(self):
        """short_rest does NOT write an audit entry when dry_run=True."""
        with pytest.MonkeyPatch.context() as mp:
            logged = []
            mp.setattr(
                memory_repo,
                "append_maintenance_log",
                lambda session, entry: logged.append(entry),
            )
            memory_repo.short_rest(
                MagicMock(run=MagicMock(return_value=MagicMock(
                    __iter__=lambda s: iter([]),
                    single=MagicMock(return_value=None),
                ))),
                now_iso="2026-04-01T10:00:00+00:00",
                recency_days=7,
                min_strength=0.0,
                edge_modulation_factor=0.5,
                edge_modulation_cap=10.0,
                dry_run=True,
            )
        assert len(logged) == 0


class TestLongRestLogsAuditEntry:
    def test_audit_log_written_on_real_run(self):
        """long_rest writes an audit entry when dry_run=False."""
        with pytest.MonkeyPatch.context() as mp:
            logged = []
            mp.setattr(
                memory_repo,
                "append_maintenance_log",
                lambda session, entry: logged.append(entry),
            )
            # Mock decay_pass to return minimal result
            mp.setattr(
                memory_repo,
                "decay_pass",
                lambda *a, **kw: {"nodes_updated": 2, "edges_updated": 1},
            )
            session = MagicMock()
            session.run.return_value.__iter__ = lambda s: iter([])  # strong_nodes
            session.run.return_value.single.return_value = None
            memory_repo.long_rest(
                session,
                now_iso="2026-04-01T10:00:00+00:00",
                min_strength=0.0,
                edge_modulation_factor=0.5,
                edge_modulation_cap=10.0,
                rediscovery_strength_threshold=0.3,
                edge_hard_prune_floor=0.01,
                edge_hard_prune_min_days=90,
                edge_decay_rate=0.005,
                dry_run=False,
                prune=False,
            )
        assert len(logged) == 1
        assert logged[0]["operation"] == "long_rest"
        assert logged[0]["dry_run"] is False
        assert "edges_discovered" in logged[0]
        assert "edges_pruned" in logged[0]

    def test_audit_log_not_written_on_dry_run(self):
        """long_rest does NOT write an audit entry when dry_run=True."""
        with pytest.MonkeyPatch.context() as mp:
            logged = []
            mp.setattr(
                memory_repo,
                "append_maintenance_log",
                lambda session, entry: logged.append(entry),
            )
            mp.setattr(
                memory_repo,
                "decay_pass",
                lambda *a, **kw: {"nodes_updated": 0, "edges_updated": 0},
            )
            session = MagicMock()
            session.run.return_value.__iter__ = lambda s: iter([])
            session.run.return_value.single.return_value = None
            memory_repo.long_rest(
                session,
                now_iso="2026-04-01T10:00:00+00:00",
                min_strength=0.0,
                edge_modulation_factor=0.5,
                edge_modulation_cap=10.0,
                rediscovery_strength_threshold=0.3,
                edge_hard_prune_floor=0.01,
                edge_hard_prune_min_days=90,
                edge_decay_rate=0.005,
                dry_run=True,
                prune=False,
            )
        assert len(logged) == 0
```

- [ ] **Step 2.2: Run tests to confirm they fail**

```bash
pytest tests/test_wp054_maintenance_audit.py::TestShortRestLogsAuditEntry tests/test_wp054_maintenance_audit.py::TestLongRestLogsAuditEntry -v
```
Expected: FAIL

- [ ] **Step 2.3: Update `short_rest` in `memory_repo.py` to call `append_maintenance_log`**

Find the block in `short_rest` (around line 1222):
```python
    if not dry_run:
        upsert_system_node(session, last_short_rest_at=now_iso)

    return {
        "nodes_decayed": len(node_updates),
        "edges_decayed": len(edge_updates),
        "dry_run": dry_run,
    }
```

Replace with:
```python
    if not dry_run:
        upsert_system_node(session, last_short_rest_at=now_iso)
        append_maintenance_log(session, {
            "operation": "short_rest",
            "ran_at": now_iso,
            "dry_run": False,
            "nodes_affected": len(node_updates),
            "edges_affected": len(edge_updates),
            "edges_discovered": 0,
            "edges_pruned": 0,
        })

    return {
        "nodes_decayed": len(node_updates),
        "edges_decayed": len(edge_updates),
        "dry_run": dry_run,
    }
```

- [ ] **Step 2.4: Update `long_rest` in `memory_repo.py` to call `append_maintenance_log`**

Find the System node update near the end of `long_rest` (search for `upsert_system_node(session, last_long_rest_at`):
```python
    if not dry_run:
        upsert_system_node(session, last_long_rest_at=now_iso)

    return {
        ...
    }
```

Replace with:
```python
    if not dry_run:
        upsert_system_node(session, last_long_rest_at=now_iso)
        append_maintenance_log(session, {
            "operation": "long_rest",
            "ran_at": now_iso,
            "dry_run": False,
            "nodes_affected": nodes_decayed,
            "edges_affected": edges_decayed,
            "edges_discovered": edges_discovered,
            "edges_pruned": edges_pruned,
        })

    return {
        "nodes_decayed": nodes_decayed,
        "edges_decayed": edges_decayed,
        "edges_discovered": edges_discovered,
        "edges_pruned": edges_pruned,
        "dry_run": dry_run,
    }
```

- [ ] **Step 2.5: Run tests to confirm they pass**

```bash
pytest tests/test_wp054_maintenance_audit.py::TestShortRestLogsAuditEntry tests/test_wp054_maintenance_audit.py::TestLongRestLogsAuditEntry -v
```
Expected: PASS

- [ ] **Step 2.6: Run full WP-040 test suite to check for regressions**

```bash
pytest tests/test_wp040_maintenance.py -v
```
Expected: All pass (excluding any pre-existing flaky test)

- [ ] **Step 2.7: Commit**

```bash
git add memory_service/memory_repo.py tests/test_wp054_maintenance_audit.py
git commit -m "WP-054: wire audit logging into short_rest and long_rest"
```

---

## Task 3: `GET /memory/maintenance/log` endpoint

**Files:**
- Modify: `memory_service/main.py`
- Test: `tests/test_wp054_maintenance_audit.py`

- [ ] **Step 3.1: Write the failing unit test**

Add to `tests/test_wp054_maintenance_audit.py`:

```python
class TestMaintenanceLogEndpoint:
    def test_maintenance_log_endpoint_returns_entries(self):
        """GET /memory/maintenance/log returns list of audit entries."""
        from fastapi.testclient import TestClient
        from unittest.mock import patch, MagicMock
        from memory_service.main import app

        entries = [
            {
                "operation": "short_rest",
                "ran_at": "2026-04-01T10:00:00+00:00",
                "dry_run": False,
                "nodes_affected": 5,
                "edges_affected": 2,
                "edges_discovered": 0,
                "edges_pruned": 0,
            }
        ]
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = lambda s: mock_session
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        app.state.driver = mock_driver

        with patch("memory_service.main.memory_repo.get_maintenance_log", return_value=entries):
            with TestClient(app) as client:
                response = client.get("/memory/maintenance/log")
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert len(data["entries"]) == 1
        assert data["entries"][0]["operation"] == "short_rest"

    def test_maintenance_log_endpoint_empty(self):
        """GET /memory/maintenance/log returns empty list when no log exists."""
        from fastapi.testclient import TestClient
        from unittest.mock import patch, MagicMock
        from memory_service.main import app

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = lambda s: mock_session
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        app.state.driver = mock_driver

        with patch("memory_service.main.memory_repo.get_maintenance_log", return_value=[]):
            with TestClient(app) as client:
                response = client.get("/memory/maintenance/log")
        assert response.status_code == 200
        assert response.json() == {"entries": []}
```

- [ ] **Step 3.2: Run tests to confirm they fail**

```bash
pytest tests/test_wp054_maintenance_audit.py::TestMaintenanceLogEndpoint -v
```
Expected: FAIL — 404 Not Found

- [ ] **Step 3.3: Add `MaintenanceLogEntry`, `MaintenanceLogResponse` models and endpoint to `main.py`**

Find the `MaintenanceStatsResponse` block in `main.py` (around line 428) and add after it (before the `UpdateMemoryRequest` class):

```python
class MaintenanceLogEntry(BaseModel):
    operation: str
    ran_at: str
    dry_run: bool
    nodes_affected: int
    edges_affected: int
    edges_discovered: int
    edges_pruned: int


class MaintenanceLogResponse(BaseModel):
    entries: List[MaintenanceLogEntry]


@app.get("/memory/maintenance/log", response_model=MaintenanceLogResponse)
async def maintenance_log(request: Request) -> MaintenanceLogResponse:
    try:
        with request.app.state.driver.session() as session:
            entries = memory_repo.get_maintenance_log(session)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return MaintenanceLogResponse(entries=[MaintenanceLogEntry(**e) for e in entries])
```

- [ ] **Step 3.4: Run tests to confirm they pass**

```bash
pytest tests/test_wp054_maintenance_audit.py::TestMaintenanceLogEndpoint -v
```
Expected: PASS

- [ ] **Step 3.5: Commit**

```bash
git add memory_service/main.py tests/test_wp054_maintenance_audit.py
git commit -m "WP-054: add GET /memory/maintenance/log endpoint"
```

---

## Task 4: Structured `maintenance_status` on wake-up response

**Files:**
- Modify: `memory_service/main.py`
- Test: `tests/test_wp054_maintenance_audit.py`

Replace the single `maintenance_warning: Optional[str]` field on `WakeUpResponse` with a `maintenance_status: MaintenanceStatus` field. `MaintenanceStatus` carries structured overdue info for *both* short-rest and long-rest, plus a recommended action string.

`MaintenanceStatus` model:
```python
class MaintenanceStatus(BaseModel):
    short_rest_overdue: bool
    long_rest_overdue: bool
    short_rest_days_ago: Optional[float] = None   # None if never run
    long_rest_days_ago: Optional[float] = None    # None if never run
    recommended_action: Optional[str] = None      # human-readable, or None if all fine
```

`recommended_action` values (in priority order, first match wins):
- Long-rest never run: `"long-rest has never run — run `memory long-rest` before this session"`
- Short-rest never run: `"short-rest has never run — run `memory short-rest`"`
- Both overdue: `"both short-rest and long-rest are overdue — run `memory long-rest` (covers both)"`
- Only long-rest overdue: `"long-rest is overdue ({N:.0f}d) — run `memory long-rest`"`
- Only short-rest overdue: `"short-rest is overdue ({N:.0f}d) — run `memory short-rest`"`
- Neither overdue: `None`

**Note:** The old `maintenance_warning` field is removed. Any consumer of the HTTP API that reads `maintenance_warning` must migrate to `maintenance_status`. The memory client's `wake_up_split` is updated in Task 6.

- [ ] **Step 4.1: Write the failing unit test**

Add to `tests/test_wp054_maintenance_audit.py`:

```python
class TestMaintenanceStatus:
    def _compute_status(self, last_short=None, last_long=None, now_iso="2026-04-01T10:00:00+00:00", short_recency=1, long_recency=1):
        """Call the helper being tested."""
        from memory_service.main import _compute_maintenance_status
        return _compute_maintenance_status(
            last_short_rest_at=last_short,
            last_long_rest_at=last_long,
            now_iso=now_iso,
            short_rest_recency_days=short_recency,
            long_rest_recency_days=long_recency,
        )

    def test_both_never_run(self):
        status = self._compute_status()
        assert status["long_rest_overdue"] is True
        assert status["short_rest_overdue"] is True
        assert status["long_rest_days_ago"] is None
        assert status["short_rest_days_ago"] is None
        assert "long-rest has never run" in status["recommended_action"]

    def test_long_rest_overdue_short_rest_ok(self):
        # short ran 0.5 days ago (within 1-day recency), long ran 3 days ago (overdue)
        from datetime import datetime, timezone, timedelta
        now = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
        short_ts = (now - timedelta(hours=12)).isoformat()
        long_ts = (now - timedelta(days=3)).isoformat()
        status = self._compute_status(last_short=short_ts, last_long=long_ts)
        assert status["long_rest_overdue"] is True
        assert status["short_rest_overdue"] is False
        assert "long-rest is overdue" in status["recommended_action"]

    def test_short_rest_overdue_long_rest_ok(self):
        from datetime import datetime, timezone, timedelta
        now = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
        short_ts = (now - timedelta(days=3)).isoformat()
        long_ts = (now - timedelta(hours=6)).isoformat()
        status = self._compute_status(last_short=short_ts, last_long=long_ts)
        assert status["short_rest_overdue"] is True
        assert status["long_rest_overdue"] is False
        assert "short-rest is overdue" in status["recommended_action"]

    def test_both_overdue(self):
        from datetime import datetime, timezone, timedelta
        now = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
        short_ts = (now - timedelta(days=3)).isoformat()
        long_ts = (now - timedelta(days=3)).isoformat()
        status = self._compute_status(last_short=short_ts, last_long=long_ts)
        assert status["short_rest_overdue"] is True
        assert status["long_rest_overdue"] is True
        assert "both short-rest and long-rest are overdue" in status["recommended_action"]

    def test_neither_overdue(self):
        from datetime import datetime, timezone, timedelta
        now = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
        short_ts = (now - timedelta(hours=6)).isoformat()
        long_ts = (now - timedelta(hours=6)).isoformat()
        status = self._compute_status(last_short=short_ts, last_long=long_ts)
        assert status["short_rest_overdue"] is False
        assert status["long_rest_overdue"] is False
        assert status["recommended_action"] is None

    def test_wake_up_response_includes_maintenance_status(self):
        """WakeUpResponse has maintenance_status field (not maintenance_warning)."""
        from fastapi.testclient import TestClient
        from unittest.mock import patch, MagicMock
        from memory_service.main import app

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = lambda s: mock_session
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        app.state.driver = mock_driver

        with patch("memory_service.main.memory_repo.wake_up", return_value={"core": [], "topic": []}):
            with patch("memory_service.main.memory_repo.get_system_timestamps", return_value={"last_short_rest_at": None, "last_long_rest_at": None}):
                with TestClient(app) as client:
                    response = client.get("/memory/wake-up")
        assert response.status_code == 200
        data = response.json()
        assert "maintenance_status" in data
        assert "maintenance_warning" not in data
        ms = data["maintenance_status"]
        assert "short_rest_overdue" in ms
        assert "long_rest_overdue" in ms
        assert "recommended_action" in ms
```

- [ ] **Step 4.2: Run tests to confirm they fail**

```bash
pytest tests/test_wp054_maintenance_audit.py::TestMaintenanceStatus -v
```
Expected: FAIL — `ImportError: cannot import name '_compute_maintenance_status'` and schema mismatches

- [ ] **Step 4.3: Add `MaintenanceStatus` model and `_compute_maintenance_status` helper to `main.py`**

Add after the `WakeUpMemoryItem` class (around line 190, before `WakeUpResponse`):

```python
class MaintenanceStatus(BaseModel):
    short_rest_overdue: bool
    long_rest_overdue: bool
    short_rest_days_ago: Optional[float] = None
    long_rest_days_ago: Optional[float] = None
    recommended_action: Optional[str] = None


def _compute_maintenance_status(
    last_short_rest_at: Optional[str],
    last_long_rest_at: Optional[str],
    now_iso: str,
    short_rest_recency_days: int,
    long_rest_recency_days: int,
) -> dict:
    """Compute structured maintenance status for the wake-up response."""
    now = memory_repo._parse_iso(now_iso)

    def _days_since(ts: Optional[str]) -> Optional[float]:
        if ts is None:
            return None
        try:
            return (now - memory_repo._parse_iso(ts)).total_seconds() / 86400.0
        except (ValueError, TypeError):
            return None

    short_days = _days_since(last_short_rest_at)
    long_days = _days_since(last_long_rest_at)

    short_overdue = short_days is None or short_days > short_rest_recency_days
    long_overdue = long_days is None or long_days > long_rest_recency_days

    if last_long_rest_at is None:
        action = "long-rest has never run — run `memory long-rest` before this session"
    elif last_short_rest_at is None:
        action = "short-rest has never run — run `memory short-rest`"
    elif short_overdue and long_overdue:
        action = "both short-rest and long-rest are overdue — run `memory long-rest` (covers both)"
    elif long_overdue:
        action = f"long-rest is overdue ({long_days:.0f}d) — run `memory long-rest`"
    elif short_overdue:
        action = f"short-rest is overdue ({short_days:.0f}d) — run `memory short-rest`"
    else:
        action = None

    return {
        "short_rest_overdue": short_overdue,
        "long_rest_overdue": long_overdue,
        "short_rest_days_ago": round(short_days, 1) if short_days is not None else None,
        "long_rest_days_ago": round(long_days, 1) if long_days is not None else None,
        "recommended_action": action,
    }
```

- [ ] **Step 4.4: Update `WakeUpResponse` to use `MaintenanceStatus`**

Replace the existing `WakeUpResponse` class:
```python
class WakeUpResponse(BaseModel):
    memories: List[WakeUpMemoryItem]          # core (importance-ranked)
    topic_memories: List[WakeUpMemoryItem]    # topic-only; empty when no --topic
    maintenance_warning: Optional[str] = None
```

With:
```python
class WakeUpResponse(BaseModel):
    memories: List[WakeUpMemoryItem]          # core (importance-ranked)
    topic_memories: List[WakeUpMemoryItem]    # topic-only; empty when no --topic
    maintenance_status: MaintenanceStatus
```

- [ ] **Step 4.5: Update the wake-up handler to compute and return `maintenance_status`**

Replace the existing maintenance block (lines ~217–242) in the `wake_up` handler:

```python
    # Check maintenance staleness — best-effort, do not fail wake-up if this errors
    maintenance_status_data = {
        "short_rest_overdue": False,
        "long_rest_overdue": False,
        "short_rest_days_ago": None,
        "long_rest_days_ago": None,
        "recommended_action": None,
    }
    try:
        with request.app.state.driver.session() as maint_session:
            ts = memory_repo.get_system_timestamps(maint_session)
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        maintenance_status_data = _compute_maintenance_status(
            last_short_rest_at=ts.get("last_short_rest_at"),
            last_long_rest_at=ts.get("last_long_rest_at"),
            now_iso=now_iso,
            short_rest_recency_days=settings.short_rest_recency_days,
            long_rest_recency_days=settings.long_rest_recency_days,
        )
    except Exception:
        pass  # best-effort; never surface maintenance errors to wake-up

    return WakeUpResponse(
        memories=[WakeUpMemoryItem(**r) for r in result["core"]],
        topic_memories=[WakeUpMemoryItem(**r) for r in result["topic"]],
        maintenance_status=MaintenanceStatus(**maintenance_status_data),
    )
```

Note: Remove the `now_iso` variable defined before the maintenance block if it duplicates — check the handler for an existing `now_iso` assignment and consolidate.

- [ ] **Step 4.6: Run tests to confirm they pass**

```bash
pytest tests/test_wp054_maintenance_audit.py::TestMaintenanceStatus -v
```
Expected: PASS

- [ ] **Step 4.7: Commit**

```bash
git add memory_service/main.py tests/test_wp054_maintenance_audit.py
git commit -m "WP-054: add MaintenanceStatus to wake-up response"
```

---

## Task 5: Update `memory_client/client.py`

**Files:**
- Modify: `memory_client/client.py`
- Test: `tests/test_wp054_maintenance_audit.py`

- [ ] **Step 5.1: Write failing test**

Add to `tests/test_wp054_maintenance_audit.py`:

```python
class TestMemoryClientUpdates:
    def test_wake_up_split_returns_maintenance_status(self):
        """wake_up_split returns (core, topic, maintenance_status) tuple."""
        import httpx
        from unittest.mock import patch, MagicMock
        from memory_client.client import MemoryClient

        response_data = {
            "memories": [{"id": "abc", "fact": "test", "text": "test", "type": "fact", "importance": 3, "strength": 0.8, "tags": [], "created_at": None, "strand_id": None}],
            "topic_memories": [],
            "maintenance_status": {
                "short_rest_overdue": True,
                "long_rest_overdue": False,
                "short_rest_days_ago": 2.5,
                "long_rest_days_ago": 0.5,
                "recommended_action": "short-rest is overdue (2d) — run `memory short-rest`",
            },
        }
        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        with MemoryClient(base_url="http://localhost:8000") as client:
            with patch.object(client._http, "get", return_value=mock_response):
                core, topic, status = client.wake_up_split(limit=20)

        assert len(core) == 1
        assert topic == []
        assert status["short_rest_overdue"] is True
        assert status["recommended_action"] is not None

    def test_maintenance_log_client_method(self):
        """maintenance_log() returns list of audit entries."""
        import httpx
        from unittest.mock import patch, MagicMock
        from memory_client.client import MemoryClient

        response_data = {
            "entries": [
                {
                    "operation": "short_rest",
                    "ran_at": "2026-04-01T10:00:00+00:00",
                    "dry_run": False,
                    "nodes_affected": 5,
                    "edges_affected": 2,
                    "edges_discovered": 0,
                    "edges_pruned": 0,
                }
            ]
        }
        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        with MemoryClient(base_url="http://localhost:8000") as client:
            with patch.object(client._http, "get", return_value=mock_response):
                result = client.maintenance_log()

        assert len(result) == 1
        assert result[0]["operation"] == "short_rest"
```

- [ ] **Step 5.2: Run tests to confirm they fail**

```bash
pytest tests/test_wp054_maintenance_audit.py::TestMemoryClientUpdates -v
```
Expected: FAIL

- [ ] **Step 5.3: Update `wake_up_split` in `memory_client/client.py`**

The current return is `(data["memories"], data.get("topic_memories", []))`. Change it to also return `maintenance_status`:

```python
    def wake_up_split(
        self, *, limit: int = 20, topic: str | None = None
    ) -> tuple[list[dict], list[dict], dict]:
        """GET /memory/wake-up. Returns (core_memories, topic_memories, maintenance_status) tuple.

        core_memories: importance-ranked list (always populated if DB has memories)
        topic_memories: topic-only results (empty when no topic provided)
        maintenance_status: structured overdue info dict
        """
        params: dict = {"limit": limit}
        if topic is not None:
            params["topic"] = topic
        response = self._http.get("/memory/wake-up", params=params)
        response.raise_for_status()
        data = response.json()
        return data["memories"], data.get("topic_memories", []), data.get("maintenance_status", {})
```

- [ ] **Step 5.4: Add `maintenance_log` method to `memory_client/client.py`**

After the `maintenance_stats` method:

```python
    def maintenance_log(self) -> list[dict]:
        """GET /memory/maintenance/log. Returns list of audit entry dicts."""
        response = self._http.get("/memory/maintenance/log")
        response.raise_for_status()
        return response.json()["entries"]
```

- [ ] **Step 5.5: Run tests to confirm they pass**

```bash
pytest tests/test_wp054_maintenance_audit.py::TestMemoryClientUpdates -v
```
Expected: PASS

- [ ] **Step 5.6: Commit**

```bash
git add memory_client/client.py tests/test_wp054_maintenance_audit.py
git commit -m "WP-054: update memory client with maintenance_log and wake_up_split maintenance_status"
```

---

## Task 6: Update MCP `memory_wake_up` and add `memory_maintenance_log`

**Files:**
- Modify: `mcp_server/server.py`
- Test: `tests/test_wp054_maintenance_audit.py`

The MCP `memory_wake_up` must now surface `maintenance_status` as prominent lines at the top of the briefing when action is needed. The `memory_maintenance_log` tool lists recent runs.

- [ ] **Step 6.1: Write failing tests**

Add to `tests/test_wp054_maintenance_audit.py`:

```python
class TestMcpUpdates:
    def test_memory_wake_up_shows_maintenance_alert(self):
        """memory_wake_up includes a maintenance alert block when action is recommended."""
        from unittest.mock import MagicMock, patch

        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.wake_up_split.return_value = (
            [],  # core
            [],  # topic
            {
                "short_rest_overdue": True,
                "long_rest_overdue": True,
                "short_rest_days_ago": 3.0,
                "long_rest_days_ago": 3.0,
                "recommended_action": "both short-rest and long-rest are overdue — run `memory long-rest` (covers both)",
            },
        )

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            from mcp_server.server import memory_wake_up
            result = memory_wake_up()

        assert "MAINTENANCE" in result.upper() or "overdue" in result.lower()
        assert "long-rest" in result

    def test_memory_wake_up_no_alert_when_healthy(self):
        """memory_wake_up omits maintenance block when all is fine."""
        from unittest.mock import MagicMock, patch

        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.wake_up_split.return_value = (
            [],
            [],
            {
                "short_rest_overdue": False,
                "long_rest_overdue": False,
                "short_rest_days_ago": 0.5,
                "long_rest_days_ago": 0.5,
                "recommended_action": None,
            },
        )

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            from mcp_server.server import memory_wake_up
            result = memory_wake_up()

        # No maintenance section when all is fine
        assert "overdue" not in result.lower()

    def test_memory_maintenance_log_tool(self):
        """memory_maintenance_log returns formatted plain-text summary."""
        from unittest.mock import MagicMock, patch

        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.maintenance_log.return_value = [
            {
                "operation": "short_rest",
                "ran_at": "2026-04-01T10:00:00+00:00",
                "dry_run": False,
                "nodes_affected": 5,
                "edges_affected": 2,
                "edges_discovered": 0,
                "edges_pruned": 0,
            },
            {
                "operation": "long_rest",
                "ran_at": "2026-03-30T08:00:00+00:00",
                "dry_run": False,
                "nodes_affected": 20,
                "edges_affected": 10,
                "edges_discovered": 3,
                "edges_pruned": 1,
            },
        ]

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            from mcp_server.server import memory_maintenance_log
            result = memory_maintenance_log()

        assert "short_rest" in result or "short-rest" in result.lower()
        assert "long_rest" in result or "long-rest" in result.lower()
        assert "5" in result  # nodes_affected
        assert "20" in result
```

- [ ] **Step 6.2: Run tests to confirm they fail**

```bash
pytest tests/test_wp054_maintenance_audit.py::TestMcpUpdates -v
```
Expected: FAIL

- [ ] **Step 6.3: Update `memory_wake_up` in `mcp_server/server.py`**

Replace the current `memory_wake_up` function:

```python
@mcp.tool
def memory_wake_up(
    topic: str | None = None,
    limit: int = 20,
) -> str:
    """Return the session wake-up briefing as plain text. Read fully before responding to the user."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        core, topic_memories, maintenance_status = client.wake_up_split(limit=limit, topic=topic)

    lines = []

    # Maintenance alert — shown prominently at the top when action needed
    action = maintenance_status.get("recommended_action") if maintenance_status else None
    if action:
        lines += [
            "## ⚠ Maintenance required",
            "",
            f"  {action}",
            "",
        ]

    heading = f"## Memory briefing — {topic if topic else 'general session'}"
    lines += [heading, "", "### Core context", ""]
    lines.extend(_render_section(core))

    if topic and topic_memories:
        lines += ["", "### Relevant to today", ""]
        lines.extend(_render_section(topic_memories))

    return "\n".join(lines)
```

- [ ] **Step 6.4: Add `memory_maintenance_log` MCP tool to `mcp_server/server.py`**

Add after the `memory_maintenance_stats` tool:

```python
@mcp.tool
def memory_maintenance_log() -> str:
    """Return the maintenance audit log as plain text (most recent runs first)."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        entries = client.maintenance_log()

    if not entries:
        return "No maintenance runs recorded yet."

    lines = ["## Maintenance audit log", ""]
    for entry in reversed(entries):  # most recent first
        dr = " (dry-run)" if entry.get("dry_run") else ""
        op = entry.get("operation", "unknown").replace("_", "-")
        ran_at = entry.get("ran_at", "unknown")[:19].replace("T", " ")
        nodes = entry.get("nodes_affected", 0)
        edges = entry.get("edges_affected", 0)
        discovered = entry.get("edges_discovered", 0)
        pruned = entry.get("edges_pruned", 0)
        summary = f"{nodes} nodes, {edges} edges decayed"
        if discovered:
            summary += f", {discovered} edges discovered"
        if pruned:
            summary += f", {pruned} edges pruned"
        lines.append(f"  {ran_at}  {op}{dr}: {summary}")

    return "\n".join(lines)
```

- [ ] **Step 6.5: Run tests to confirm they pass**

```bash
pytest tests/test_wp054_maintenance_audit.py::TestMcpUpdates -v
```
Expected: PASS

- [ ] **Step 6.6: Run full WP-054 test suite**

```bash
pytest tests/test_wp054_maintenance_audit.py -v
```
Expected: All pass

- [ ] **Step 6.7: Commit**

```bash
git add mcp_server/server.py tests/test_wp054_maintenance_audit.py
git commit -m "WP-054: update MCP memory_wake_up escalation and add memory_maintenance_log tool"
```

---

## Task 7: Integration tests against live stack

**Files:**
- Test: `tests/test_wp054_maintenance_audit.py`

These tests require the live Memgraph + FastAPI service running. Mark with `@pytest.mark.integration`.

- [ ] **Step 7.1: Write integration tests**

Add to `tests/test_wp054_maintenance_audit.py`:

```python
@pytest.mark.integration
class TestMaintenanceAuditIntegration:
    """Integration tests — require live Memgraph + FastAPI service (pytest -m integration)."""

    BASE_URL = "http://localhost:8000"

    def test_short_rest_creates_audit_entry(self):
        """Running short-rest adds an entry to the maintenance log."""
        import httpx

        # Get baseline log length
        r = httpx.get(f"{self.BASE_URL}/memory/maintenance/log")
        assert r.status_code == 200
        before = len(r.json()["entries"])

        # Run short-rest (not dry-run)
        r = httpx.post(f"{self.BASE_URL}/memory/maintenance/short-rest")
        assert r.status_code == 200

        # Log should have grown by 1
        r = httpx.get(f"{self.BASE_URL}/memory/maintenance/log")
        assert r.status_code == 200
        entries = r.json()["entries"]
        assert len(entries) == before + 1
        latest = entries[-1]
        assert latest["operation"] == "short_rest"
        assert latest["dry_run"] is False
        assert "ran_at" in latest

    def test_long_rest_creates_audit_entry(self):
        """Running long-rest adds an entry with edges_discovered field."""
        import httpx

        r = httpx.get(f"{self.BASE_URL}/memory/maintenance/log")
        before = len(r.json()["entries"])

        r = httpx.post(f"{self.BASE_URL}/memory/maintenance/long-rest")
        assert r.status_code == 200

        r = httpx.get(f"{self.BASE_URL}/memory/maintenance/log")
        entries = r.json()["entries"]
        assert len(entries) == before + 1
        latest = entries[-1]
        assert latest["operation"] == "long_rest"
        assert "edges_discovered" in latest
        assert "edges_pruned" in latest

    def test_dry_run_does_not_create_audit_entry(self):
        """dry_run=True must not write an audit entry."""
        import httpx

        r = httpx.get(f"{self.BASE_URL}/memory/maintenance/log")
        before = len(r.json()["entries"])

        r = httpx.post(f"{self.BASE_URL}/memory/maintenance/short-rest?dry_run=true")
        assert r.status_code == 200
        assert r.json()["dry_run"] is True

        r = httpx.get(f"{self.BASE_URL}/memory/maintenance/log")
        assert len(r.json()["entries"]) == before  # unchanged

    def test_wake_up_maintenance_status_structured(self):
        """GET /memory/wake-up returns maintenance_status (not maintenance_warning)."""
        import httpx

        r = httpx.get(f"{self.BASE_URL}/memory/wake-up")
        assert r.status_code == 200
        data = r.json()
        assert "maintenance_status" in data
        assert "maintenance_warning" not in data
        ms = data["maintenance_status"]
        assert "short_rest_overdue" in ms
        assert "long_rest_overdue" in ms
        assert "recommended_action" in ms
```

- [ ] **Step 7.2: Confirm live stack is running**

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```
Expected: `{"status": "ok"}` — if not, start the service with `uvicorn memory_service.main:app --reload` and ensure Memgraph is up.

- [ ] **Step 7.3: Run integration tests against live stack**

```bash
cd /home/oliver/projects/graph-memory-fabric
pytest tests/test_wp054_maintenance_audit.py -m integration -v
```
Expected: All 4 integration tests PASS

- [ ] **Step 7.4: Run full unit test suite (no live stack needed)**

```bash
pytest tests/test_wp054_maintenance_audit.py -m "not integration" -v
```
Expected: All unit tests PASS

- [ ] **Step 7.5: Run existing maintenance test suite to confirm no regressions**

```bash
pytest tests/test_wp040_maintenance.py -v
```
Expected: All pass (known flaky test `test_core_wake_up_prefers_stronger_reinforced_memory` excluded from regression consideration)

- [ ] **Step 7.6: Commit**

```bash
git add tests/test_wp054_maintenance_audit.py
git commit -m "WP-054: integration tests for audit trail and wake-up escalation"
```

---

## Task 8: Update BACKLOG.md

**Files:**
- Modify: `BACKLOG.md`

- [ ] **Step 8.1: Move WP-054 to Completed section in `BACKLOG.md`**

1. Remove the WP-054 row from the Currently In Progress or priority table.
2. Add to the Completed section:

```
| WP-054 | Maintenance audit trail and startup escalation loop | Completed 2026-04-01 | Audit entries on System node (maintenance_log); structured MaintenanceStatus on wake-up; memory_maintenance_log MCP tool. |
```

3. Add retrospective note after the completed entry:
```
**WP-054 retro:** Replacing the single string maintenance_warning with a structured MaintenanceStatus object was the right call — it lets the MCP surface a clear action rather than just a passive note. The JSON-on-System-node approach for the audit log keeps the schema minimal (no new node type), which fits v1 constraints well. Watch for: if maintenance_log grows unwieldy, consider a dedicated Operation node (WP-056 already planned for this).
```

- [ ] **Step 8.2: Final commit**

```bash
git add BACKLOG.md
git commit -m "WP-054: update BACKLOG — mark complete"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** Record maintenance runs ✓ (Tasks 1–2), startup escalation for both short-rest and long-rest ✓ (Task 4), optional auto-run path — deliberately deferred (out of scope for v1; WP-053 covers scheduled automation)
- [x] **No placeholders:** All code blocks are complete
- [x] **Type consistency:** `maintenance_status` used consistently; `wake_up_split` return type updated to 3-tuple; `maintenance_log()` client method returns `list[dict]`
- [x] **Dry-run guard:** Both short_rest and long_rest skip audit log on dry_run — tested in Tasks 2 and 7
- [x] **Backward compat:** `maintenance_warning` field removed from HTTP response — `wake_up_split` caller (MCP server) updated in same plan; no external consumers in v1
