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

from memory_client.config import settings as _settings

_OPERATION_TS_KEYS = {
    "short-rest": "last_short_rest_at",
    "long-rest": "last_long_rest_at",
}


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
        ts_key = _OPERATION_TS_KEYS[operation]
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
