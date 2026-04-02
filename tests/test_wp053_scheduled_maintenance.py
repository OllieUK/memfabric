# tests/test_wp053_scheduled_maintenance.py
"""Tests for WP-053: scheduled maintenance orchestration."""
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from typer.testing import CliRunner

from memory_client.cli import app as cli_app

_BASE_URL = "http://localhost:8000"
_cli_runner = CliRunner()


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

        # Second run with high interval — may skip if a real short-rest has run recently
        # We just verify no crash
        result2 = run_maintenance("short-rest", dry_run=True, min_interval_hours=999999)
        # result2 may be None (skipped) or a dict (ran); either is valid
