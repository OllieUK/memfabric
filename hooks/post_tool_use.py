#!/usr/bin/env python3
"""PostToolUse hook — capture tool events as observation memories.

Claude Code invokes this after every tool call, passing a JSON payload on stdin.
Substantive events (Write, Edit, significant Bash, WebFetch) are stored as
observation memories in the memory service with files_modified/files_read provenance.

Must always exit 0 — a non-zero exit blocks the primary session.

Environment variables (all optional):
    API_BASE_URL   Memory service URL (default: http://localhost:8000)
    AGENT_ID       Agent identifier (default: claude-code)
"""
import json
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import httpx
from memory_client.client import MemoryClient

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
AGENT_ID = os.environ.get("AGENT_ID", "claude-code")
STRAND_ID = "strand-session-activity"
IMPORTANCE = 2
BASH_MIN_OUTPUT_LEN = 10
BASH_COMMAND_MAX_LEN = 120


def parse_payload(raw: str) -> dict | None:
    """Parse JSON from stdin. Returns None if empty or invalid."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def is_substantive(payload: dict) -> bool:
    """Return True if this tool event should generate an observation memory."""
    tool_name = payload.get("tool_name", "")
    if tool_name in ("Write", "Edit"):
        return True
    if tool_name == "Bash":
        result = (payload.get("tool_response") or {}).get("result", "")
        return isinstance(result, str) and len(result.strip()) >= BASH_MIN_OUTPUT_LEN
    if tool_name == "WebFetch":
        return bool((payload.get("tool_input") or {}).get("url"))
    return False


def build_memory_params(payload: dict) -> dict | None:
    """Build kwargs for MemoryClient.add_memory() from a tool payload.

    Returns None if tool type is unhandled.
    Returns dict with keys: fact, files_modified, files_read.
    """
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}

    if tool_name == "Write":
        path = tool_input.get("file_path", "")
        return {"fact": f"Wrote file: {path}", "files_modified": [path], "files_read": []}

    if tool_name == "Edit":
        path = tool_input.get("file_path", "")
        return {"fact": f"Edited file: {path}", "files_modified": [path], "files_read": []}

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if len(cmd) > BASH_COMMAND_MAX_LEN:
            cmd = cmd[:BASH_COMMAND_MAX_LEN] + "…"
        return {"fact": f"Ran bash command: {cmd}", "files_modified": [], "files_read": []}

    if tool_name == "WebFetch":
        url = tool_input.get("url", "")
        return {"fact": f"Fetched URL: {url}", "files_modified": [], "files_read": []}

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

    try:
        with MemoryClient(base_url=API_BASE_URL) as client:
            client.add_memory(
                fact=params["fact"],
                type="observation",
                agent_id=AGENT_ID,
                importance=IMPORTANCE,
                strand_ids=[STRAND_ID],
                files_modified=params["files_modified"],
                files_read=params["files_read"],
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
