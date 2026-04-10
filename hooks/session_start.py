#!/usr/bin/env python3
"""SessionStart hook — inject memory wake-up briefing into Claude Code context.

Claude Code captures stdout from SessionStart hooks and injects it as a
<system-reminder> preamble before the first user prompt. Output must be
plain text — no Rich markup, no ANSI codes.

Environment variables (all optional):
    API_BASE_URL         Memory service URL (default: http://localhost:8000)
    HOOK_WAKE_UP_LIMIT   Max memories to fetch (default: 8)
    HOOK_WAKE_UP_TOPIC   Topic for scoped wake-up (default: unset = general)

Registration in .claude/settings.json:
    "hooks": {
      "SessionStart": [
        {"command": "python3 /home/oliver/projects/graph-memory-fabric/hooks/session_start.py"}
      ]
    }
"""
import os
import sys

# Ensure the project root is on the path so memory_client is importable
# even when the hook is invoked from a different working directory.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import httpx
from memory_client.client import MemoryClient
from memory_client.formatting import format_wake_up

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
HOOK_WAKE_UP_LIMIT = int(os.environ.get("HOOK_WAKE_UP_LIMIT", "8"))
HOOK_WAKE_UP_TOPIC = os.environ.get("HOOK_WAKE_UP_TOPIC") or None


def main() -> None:
    try:
        with MemoryClient(base_url=API_BASE_URL) as client:
            result = client.wake_up_split(
                limit=HOOK_WAKE_UP_LIMIT,
                topic=HOOK_WAKE_UP_TOPIC,
            )
    except (httpx.ConnectError, httpx.TimeoutException):
        print("Memory service unreachable — operating without context briefing.")
        return
    except httpx.HTTPStatusError as exc:
        print(f"Memory service error ({exc.response.status_code}) — operating without context briefing.")
        return

    output = format_wake_up(result, topic=HOOK_WAKE_UP_TOPIC, plain=True)
    print(output)


if __name__ == "__main__":
    main()
