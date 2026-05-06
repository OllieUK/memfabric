#!/usr/bin/env python3
"""PostToolUse hook — capture semantic milestones as memory observations.

Claude Code invokes this after every tool call, passing a JSON payload on stdin.
Only landmark events that have meaningful cross-session value are captured:

  pytest runs    — pass/fail count extracted from output; stores test health signal
  git commit     — commit hash + message captured as a decision record

Write, Edit, WebFetch, and generic Bash commands are intentionally NOT captured.
File-level provenance (which files were touched) belongs in deliberate memory writes
via files_modified/files_read fields — not in standalone hook observations.

Must always exit 0 — a non-zero exit blocks the primary session.

Environment variables (all optional):
    API_BASE_URL   Memory service URL (default: http://localhost:8000)
    AGENT_ID       Agent identifier (default: claude-code)
"""
import json
import os
import re
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import httpx
from memory_client.client import MemoryClient
from hooks._filters import redact_secrets

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
AGENT_ID = os.environ.get("AGENT_ID", "claude-code")
STRAND_ID = "strand-session-activity"


def parse_payload(raw: str) -> dict | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _cmd(payload: dict) -> str:
    return (payload.get("tool_input") or {}).get("command", "").strip()


def _output(payload: dict) -> str:
    return ((payload.get("tool_response") or {}).get("result") or "").strip()


def _is_pytest(cmd: str) -> bool:
    return bool(re.match(r"^(python3?\s+-m\s+)?pytest\b", cmd))


def _is_git_commit(cmd: str) -> bool:
    return bool(re.match(r"^git\s+commit\b", cmd))


def is_substantive(payload: dict) -> bool:
    """Return True only for semantic milestone events worth persisting."""
    if payload.get("tool_name") != "Bash":
        return False
    cmd = _cmd(payload)
    return _is_pytest(cmd) or _is_git_commit(cmd)


def _parse_pytest_fact(cmd: str, output: str) -> tuple[str, int]:
    """Return (fact_string, importance) for a pytest result."""
    # Extract summary line: "5 passed, 2 failed in 1.23s" or "10 passed in 0.5s"
    summary = re.search(
        r"(\d+ passed(?:, \d+ failed)?(?:, \d+ error(?:s)?)?(?:, \d+ warning(?:s)?)?)\s+in\s+[\d.]+s",
        output,
    )
    if summary:
        result_str = summary.group(1)
        failed = re.search(r"(\d+) failed", result_str)
        importance = 3 if failed else 2
        fact = f"pytest: {result_str}"
    else:
        # Fallback: truncate raw output
        first_line = output.split("\n")[0][:120] if output else "no output"
        fact = f"pytest run: {first_line}"
        importance = 2
    return fact, importance


def _parse_git_commit_fact(output: str) -> tuple[str, int]:
    """Return (fact_string, importance) for a git commit result."""
    # Extract: [branch abc1234] Commit message
    match = re.search(r"\[(\S+)\s+([a-f0-9]+)\]\s+(.+)", output)
    if match:
        branch, sha, message = match.group(1), match.group(2), match.group(3).strip()
        fact = f"git commit {sha[:8]} on {branch}: {message[:120]}"
    else:
        first_line = output.split("\n")[0][:120] if output else "no output"
        fact = f"git commit: {first_line}"
    return fact, 2


def build_memory_params(payload: dict) -> dict | None:
    cmd = _cmd(payload)
    output = _output(payload)

    if _is_pytest(cmd):
        fact, importance = _parse_pytest_fact(cmd, output)
        return {"fact": fact, "importance": importance, "type": "observation"}

    if _is_git_commit(cmd):
        fact, importance = _parse_git_commit_fact(output)
        return {"fact": fact, "importance": importance, "type": "decision"}

    return None


def main() -> None:
    raw = sys.stdin.read()
    payload = parse_payload(raw)
    if payload is None:
        return
    if not is_substantive(payload):
        return
    params = build_memory_params(payload)
    if params is None:
        return

    fact = params["fact"]
    mem_type = params.get("type", "observation")
    importance = params.get("importance", 2)

    try:
        fact, _ = redact_secrets(fact)
    except Exception as exc:
        print(f"post_tool_use hook: filter error ({exc!r}) — proceeding with unfiltered add.", file=sys.stderr)

    try:
        with MemoryClient(base_url=API_BASE_URL) as client:
            client.add_memory(
                fact=fact,
                type=mem_type,
                agent_id=AGENT_ID,
                importance=importance,
                strand_ids=[STRAND_ID],
                tags=["hook", "post-tool-use"],
            )
    except (httpx.ConnectError, httpx.TimeoutException):
        print("post_tool_use hook: memory service unreachable — skipping capture.", file=sys.stderr)
    except httpx.HTTPStatusError as exc:
        print(f"post_tool_use hook: HTTP {exc.response.status_code} — skipping capture.", file=sys.stderr)
    except Exception as exc:
        print(f"post_tool_use hook: unexpected error ({exc!r}) — skipping capture.", file=sys.stderr)


if __name__ == "__main__":
    main()
