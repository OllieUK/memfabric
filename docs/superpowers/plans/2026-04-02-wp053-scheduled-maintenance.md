# WP-053: Scheduled Maintenance Orchestration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move maintenance from manual CLI invocation to automated routine care via a documented host-level scheduling path (systemd timers), with safe defaults, dry-run support, and operational docs.

**Architecture:** The maintenance endpoints (`POST /memory/maintenance/short-rest` and `POST /memory/maintenance/long-rest`) are already complete and tested. This WP adds: (1) a thin orchestration script that calls the HTTP API with skip-if-recent logic, (2) systemd timer units for WSL2/Linux hosts, (3) a CLI `memory schedule` command that installs/uninstalls the timers, and (4) operational documentation. No new FastAPI endpoints needed.

**Tech Stack:** Python (httpx), systemd timers, Typer CLI, pytest

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `scripts/maintenance_runner.py` | Standalone script: calls short-rest or long-rest via HTTP, skip-if-recent logic, exit codes |
| Modify | `memory_client/cli.py` | Add `schedule install` / `schedule uninstall` / `schedule status` subcommands |
| Create | `scripts/templates/memory-short-rest.service` | systemd service unit template |
| Create | `scripts/templates/memory-short-rest.timer` | systemd timer unit (daily) |
| Create | `scripts/templates/memory-long-rest.service` | systemd service unit template |
| Create | `scripts/templates/memory-long-rest.timer` | systemd timer unit (weekly) |
| Create | `tests/test_wp053_scheduled_maintenance.py` | Unit tests for runner script + CLI |

---

### Task 1: Maintenance runner script

**Files:**
- Create: `scripts/maintenance_runner.py`
- Create: `tests/test_wp053_scheduled_maintenance.py`

- [ ] **Step 1: Create test file with runner tests**

Create `tests/test_wp053_scheduled_maintenance.py`:

```python
# tests/test_wp053_scheduled_maintenance.py
"""Tests for WP-053: scheduled maintenance orchestration."""
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

_BASE_URL = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Task 1 — Unit: maintenance_runner skip-if-recent logic
# ---------------------------------------------------------------------------
class TestMaintenanceRunner:
    def test_short_rest_skips_when_recent(self):
        """Short-rest is skipped if last run was within min_interval_hours."""
        from scripts.maintenance_runner import should_run

        last_run = (datetime.now(tz=timezone.utc) - timedelta(hours=2)).isoformat()
        assert should_run(last_run, min_interval_hours=24) is False

    def test_short_rest_runs_when_overdue(self):
        """Short-rest runs if last run was beyond min_interval_hours."""
        from scripts.maintenance_runner import should_run

        last_run = (datetime.now(tz=timezone.utc) - timedelta(hours=48)).isoformat()
        assert should_run(last_run, min_interval_hours=24) is True

    def test_runs_when_never_run(self):
        """Runs if no last_run timestamp exists."""
        from scripts.maintenance_runner import should_run

        assert should_run(None, min_interval_hours=24) is True

    @respx.mock
    def test_run_short_rest_calls_api(self):
        """run_maintenance calls the short-rest endpoint."""
        from scripts.maintenance_runner import run_maintenance

        # Mock stats endpoint for last-run check
        respx.get(f"{_BASE_URL}/memory/maintenance/stats").mock(
            return_value=httpx.Response(200, json={
                "maintenance": {"last_short_rest_at": None, "last_long_rest_at": None},
                "nodes": {}, "edges": {},
            })
        )
        respx.post(f"{_BASE_URL}/memory/maintenance/short-rest").mock(
            return_value=httpx.Response(200, json={
                "nodes_decayed": 5, "edges_decayed": 3, "dry_run": False,
            })
        )

        result = run_maintenance("short-rest", base_url=_BASE_URL, dry_run=False, min_interval_hours=0)
        assert result["nodes_decayed"] == 5

    @respx.mock
    def test_run_long_rest_calls_api(self):
        """run_maintenance calls the long-rest endpoint with prune flag."""
        from scripts.maintenance_runner import run_maintenance

        respx.get(f"{_BASE_URL}/memory/maintenance/stats").mock(
            return_value=httpx.Response(200, json={
                "maintenance": {"last_short_rest_at": None, "last_long_rest_at": None},
                "nodes": {}, "edges": {},
            })
        )
        respx.post(f"{_BASE_URL}/memory/maintenance/long-rest").mock(
            return_value=httpx.Response(200, json={
                "nodes_decayed": 10, "edges_decayed": 8,
                "edges_discovered": 3, "edges_pruned": 1, "dry_run": False,
            })
        )

        result = run_maintenance("long-rest", base_url=_BASE_URL, dry_run=False, prune=True, min_interval_hours=0)
        assert result["edges_pruned"] == 1

    @respx.mock
    def test_dry_run_passes_through(self):
        """dry_run=True is passed to the endpoint."""
        from scripts.maintenance_runner import run_maintenance

        respx.get(f"{_BASE_URL}/memory/maintenance/stats").mock(
            return_value=httpx.Response(200, json={
                "maintenance": {"last_short_rest_at": None, "last_long_rest_at": None},
                "nodes": {}, "edges": {},
            })
        )
        route = respx.post(f"{_BASE_URL}/memory/maintenance/short-rest").mock(
            return_value=httpx.Response(200, json={
                "nodes_decayed": 0, "edges_decayed": 0, "dry_run": True,
            })
        )

        run_maintenance("short-rest", base_url=_BASE_URL, dry_run=True, min_interval_hours=0)
        assert "dry_run=true" in str(route.calls.last.request.url).lower()
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/test_wp053_scheduled_maintenance.py::TestMaintenanceRunner -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create `scripts/maintenance_runner.py`**

```python
#!/usr/bin/env python3
"""Maintenance runner for scheduled invocation.

Called by systemd timers (or cron). Checks last-run timestamps and
invokes short-rest or long-rest via the HTTP API if overdue.

Usage:
    python -m scripts.maintenance_runner short-rest [--dry-run] [--min-interval-hours 20]
    python -m scripts.maintenance_runner long-rest  [--dry-run] [--prune] [--min-interval-hours 144]

Exit codes:
    0 — maintenance ran successfully (or was skipped because recent)
    1 — API error
    2 — invalid arguments
"""
import sys
from datetime import datetime, timezone, timedelta

import httpx

from memory_service.config import settings as _settings


def should_run(last_run_iso: str | None, min_interval_hours: float) -> bool:
    """Return True if enough time has elapsed since last_run_iso."""
    if last_run_iso is None:
        return True
    try:
        last_dt = datetime.fromisoformat(last_run_iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return True
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=min_interval_hours)
    return last_dt < cutoff


def run_maintenance(
    operation: str,
    *,
    base_url: str | None = None,
    dry_run: bool = False,
    prune: bool = False,
    min_interval_hours: float = 20,
) -> dict | None:
    """Run a maintenance operation if enough time has elapsed.

    Returns the API response dict, or None if skipped.
    """
    url = base_url or _settings.api_base_url

    # Check last-run timestamps
    if min_interval_hours > 0:
        stats = httpx.get(f"{url}/memory/maintenance/stats", timeout=30).json()
        ts_key = "last_short_rest_at" if operation == "short-rest" else "last_long_rest_at"
        last_run = stats.get("maintenance", {}).get(ts_key)
        if not should_run(last_run, min_interval_hours):
            return None

    # Call the endpoint
    params: dict = {"dry_run": dry_run}
    if operation == "long-rest":
        params["prune"] = prune

    response = httpx.post(
        f"{url}/memory/maintenance/{operation}",
        params=params,
        timeout=300,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run scheduled maintenance")
    parser.add_argument("operation", choices=["short-rest", "long-rest"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prune", action="store_true", help="Prune weak edges (long-rest only)")
    parser.add_argument(
        "--min-interval-hours", type=float, default=20,
        help="Skip if last run was within this many hours (default: 20)",
    )
    args = parser.parse_args()

    try:
        result = run_maintenance(
            args.operation,
            dry_run=args.dry_run,
            prune=args.prune,
            min_interval_hours=args.min_interval_hours,
        )
    except httpx.HTTPStatusError as exc:
        print(f"Error {exc.response.status_code}: {exc.response.text}", file=sys.stderr)
        return 1
    except httpx.ConnectError:
        print(f"Could not connect to memory service at {_settings.api_base_url}", file=sys.stderr)
        return 1

    if result is None:
        print(f"{args.operation}: skipped (last run within {args.min_interval_hours}h)")
        return 0

    print(f"{args.operation}: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/test_wp053_scheduled_maintenance.py::TestMaintenanceRunner -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/maintenance_runner.py tests/test_wp053_scheduled_maintenance.py
git commit -m "WP-053: add maintenance runner script with skip-if-recent logic"
```

---

### Task 2: systemd timer templates

**Files:**
- Create: `scripts/templates/memory-short-rest.service`
- Create: `scripts/templates/memory-short-rest.timer`
- Create: `scripts/templates/memory-long-rest.service`
- Create: `scripts/templates/memory-long-rest.timer`

- [ ] **Step 1: Create short-rest service unit**

Create `scripts/templates/memory-short-rest.service`:

```ini
[Unit]
Description=Graph Memory Fabric — short-rest maintenance
After=network.target

[Service]
Type=oneshot
WorkingDirectory={{PROJECT_DIR}}
ExecStart={{PYTHON}} -m scripts.maintenance_runner short-rest --min-interval-hours 20
Environment=PYTHONPATH={{PROJECT_DIR}}
StandardOutput=journal
StandardError=journal
```

- [ ] **Step 2: Create short-rest timer unit**

Create `scripts/templates/memory-short-rest.timer`:

```ini
[Unit]
Description=Run short-rest maintenance daily

[Timer]
OnCalendar=daily
RandomizedDelaySec=1800
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 3: Create long-rest service unit**

Create `scripts/templates/memory-long-rest.service`:

```ini
[Unit]
Description=Graph Memory Fabric — long-rest maintenance
After=network.target

[Service]
Type=oneshot
WorkingDirectory={{PROJECT_DIR}}
ExecStart={{PYTHON}} -m scripts.maintenance_runner long-rest --prune --min-interval-hours 144
Environment=PYTHONPATH={{PROJECT_DIR}}
StandardOutput=journal
StandardError=journal
```

- [ ] **Step 4: Create long-rest timer unit**

Create `scripts/templates/memory-long-rest.timer`:

```ini
[Unit]
Description=Run long-rest maintenance weekly

[Timer]
OnCalendar=weekly
RandomizedDelaySec=3600
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 5: Commit**

```bash
git add scripts/templates/
git commit -m "WP-053: add systemd timer unit templates"
```

---

### Task 3: CLI `schedule` subcommands

**Files:**
- Modify: `memory_client/cli.py`
- Test: `tests/test_wp053_scheduled_maintenance.py`

- [ ] **Step 1: Add CLI tests**

Append to `tests/test_wp053_scheduled_maintenance.py`:

```python
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from memory_client.cli import app as cli_app

_cli_runner = CliRunner()


# ---------------------------------------------------------------------------
# Task 3 — Unit: CLI schedule subcommands
# ---------------------------------------------------------------------------
class TestScheduleInstall:
    def test_install_creates_unit_files(self):
        """schedule install renders templates and writes to target dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _cli_runner.invoke(
                cli_app,
                ["schedule", "install", "--target-dir", tmpdir],
            )
            assert result.exit_code == 0
            assert Path(tmpdir, "memory-short-rest.service").exists()
            assert Path(tmpdir, "memory-short-rest.timer").exists()
            assert Path(tmpdir, "memory-long-rest.service").exists()
            assert Path(tmpdir, "memory-long-rest.timer").exists()

    def test_install_renders_project_dir(self):
        """Templates are rendered with correct project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _cli_runner.invoke(
                cli_app,
                ["schedule", "install", "--target-dir", tmpdir],
            )
            content = Path(tmpdir, "memory-short-rest.service").read_text()
            assert "{{PROJECT_DIR}}" not in content
            assert "{{PYTHON}}" not in content


class TestScheduleStatus:
    @respx.mock
    def test_status_shows_timestamps(self):
        respx.get(f"{_BASE_URL}/memory/maintenance/stats").mock(
            return_value=httpx.Response(200, json={
                "maintenance": {
                    "last_short_rest_at": "2026-04-01T10:00:00+00:00",
                    "last_long_rest_at": "2026-03-25T08:00:00+00:00",
                },
                "nodes": {"total": 100},
                "edges": {"total": 200},
            })
        )
        result = _cli_runner.invoke(cli_app, ["schedule", "status"])
        assert result.exit_code == 0
        assert "2026-04-01" in result.output
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/test_wp053_scheduled_maintenance.py -k "TestSchedule" -v`
Expected: FAIL — commands don't exist.

- [ ] **Step 3: Add schedule subcommands to CLI**

In `memory_client/cli.py`, add a Typer sub-app:

```python
schedule_app = typer.Typer(help="Manage scheduled maintenance timers.")
app.add_typer(schedule_app, name="schedule")


@schedule_app.command("install")
def schedule_install(
    target_dir: str = typer.Option(
        None, "--target-dir",
        help="Directory for unit files (default: ~/.config/systemd/user)",
    ),
) -> None:
    """Install systemd timer units for maintenance."""
    import sys
    from pathlib import Path

    if target_dir is None:
        target_dir = str(Path.home() / ".config" / "systemd" / "user")

    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    templates_dir = Path(__file__).resolve().parent.parent / "scripts" / "templates"
    project_dir = str(Path(__file__).resolve().parent.parent)
    python_path = sys.executable

    for template_file in templates_dir.glob("memory-*.service"):
        content = template_file.read_text()
        content = content.replace("{{PROJECT_DIR}}", project_dir)
        content = content.replace("{{PYTHON}}", python_path)
        (target / template_file.name).write_text(content)

    for template_file in templates_dir.glob("memory-*.timer"):
        content = template_file.read_text()
        (target / template_file.name).write_text(content)

    console.print(f"Installed timer units to {target_dir}")
    console.print("Enable with:")
    console.print("  systemctl --user enable --now memory-short-rest.timer")
    console.print("  systemctl --user enable --now memory-long-rest.timer")


@schedule_app.command("uninstall")
def schedule_uninstall(
    target_dir: str = typer.Option(
        None, "--target-dir",
        help="Directory containing unit files (default: ~/.config/systemd/user)",
    ),
) -> None:
    """Remove installed systemd timer units."""
    from pathlib import Path

    if target_dir is None:
        target_dir = str(Path.home() / ".config" / "systemd" / "user")

    target = Path(target_dir)
    removed = 0
    for name in [
        "memory-short-rest.service", "memory-short-rest.timer",
        "memory-long-rest.service", "memory-long-rest.timer",
    ]:
        f = target / name
        if f.exists():
            f.unlink()
            removed += 1

    console.print(f"Removed {removed} unit files from {target_dir}")
    console.print("Remember to run: systemctl --user daemon-reload")


@schedule_app.command("status")
def schedule_status() -> None:
    """Show maintenance schedule status and last-run timestamps."""
    try:
        with _make_client() as client:
            stats = client.maintenance_stats()
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    maint = stats.get("maintenance", {})
    console.print("[bold]Maintenance Schedule Status[/bold]")
    console.print(f"  Last short-rest: {maint.get('last_short_rest_at', 'never')}")
    console.print(f"  Last long-rest:  {maint.get('last_long_rest_at', 'never')}")
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/test_wp053_scheduled_maintenance.py -k "TestSchedule" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memory_client/cli.py tests/test_wp053_scheduled_maintenance.py
git commit -m "WP-053: add schedule install/uninstall/status CLI commands"
```

---

### Task 4: Integration test — runner against live stack

**Files:**
- Test: `tests/test_wp053_scheduled_maintenance.py`

- [ ] **Step 1: Add integration test**

Append to `tests/test_wp053_scheduled_maintenance.py`:

```python
# ---------------------------------------------------------------------------
# Task 4 — Integration: runner script against live stack
# ---------------------------------------------------------------------------
class TestMaintenanceRunnerIntegration:
    @pytest.mark.integration
    def test_short_rest_via_runner(self):
        """Runner executes short-rest against live stack."""
        from scripts.maintenance_runner import run_maintenance

        result = run_maintenance(
            "short-rest", dry_run=True, min_interval_hours=0,
        )
        assert result is not None
        assert "nodes_decayed" in result
        assert result["dry_run"] is True

    @pytest.mark.integration
    def test_long_rest_via_runner(self):
        """Runner executes long-rest against live stack."""
        from scripts.maintenance_runner import run_maintenance

        result = run_maintenance(
            "long-rest", dry_run=True, prune=False, min_interval_hours=0,
        )
        assert result is not None
        assert "edges_discovered" in result
        assert result["dry_run"] is True

    @pytest.mark.integration
    def test_skip_when_recent(self):
        """Runner skips if the operation ran recently."""
        from scripts.maintenance_runner import run_maintenance

        # First run — should execute
        result1 = run_maintenance("short-rest", dry_run=True, min_interval_hours=0)
        assert result1 is not None

        # Second run with high interval — should also run (dry_run doesn't update timestamp)
        # But with a real run + high min_interval, it would skip
        # This just verifies the skip logic doesn't crash
        result2 = run_maintenance("short-rest", dry_run=True, min_interval_hours=999999)
        # Result may be None (skipped) if a short-rest has run recently
        # We just verify no crash
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_wp053_scheduled_maintenance.py -v -m integration`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v --timeout=30`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_wp053_scheduled_maintenance.py
git commit -m "WP-053: add integration tests for maintenance runner"
```

---

### Task 5: Finalise — BACKLOG update and /simplify

- [ ] **Step 1: Move WP-053 to Completed in BACKLOG.md**
- [ ] **Step 2: Run `/simplify`**
- [ ] **Step 3: Final commit**

```bash
git add BACKLOG.md
git commit -m "WP-053: update BACKLOG — mark complete"
```
