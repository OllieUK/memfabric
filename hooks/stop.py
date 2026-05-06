#!/usr/bin/env python3
"""Stop hook — inject close-session scaffold before Claude ends its turn.

Claude Code captures stdout from Stop hooks and injects it as a <system-reminder>
visible to Claude before it stops generating. This gives Claude a final prompt to
run close-session and reinforce before the session ends.

The hook is intentionally lightweight: it checks whether the memory service is
reachable. If it is, it prints the close-session scaffold. If not, it exits
silently (service might be down; don't block the session).

Layered design — cooperates with the Mara baseline Stop hook:
    Two Stop hooks are intentionally registered. The Mara baseline hook
    (~/.claude/hooks/memory_management_wrapper.py stop) writes a single
    safety-net memory tagged "auto-capture" if the assistant's last message
    matches a heuristic keyword regex; it runs async and prints nothing.
    This project hook prints a four-question scaffold so Claude can write
    deliberate, well-typed memories tagged "deliberate". The two layer:
    safety net guarantees minimum coverage even if Claude rushes; scaffold
    raises quality when Claude engages. They do not collide because one
    writes silently and the other prints to stdout.

Environment variables (all optional):
    API_BASE_URL   Memory service URL (default: http://localhost:8000)

Registration in .claude/settings.json:
    "hooks": {
      "Stop": [
        {"command": "python3 /path/to/memfabric/hooks/stop.py"}
      ]
    }
"""
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import httpx

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

_SCAFFOLD = """\
--- Memory close-session reminder ---

Note: the Mara baseline Stop hook may have already auto-captured one heuristic
memory tagged `auto-capture` for this turn. Use this scaffold to add deliberate,
well-typed memories beyond that — or to overwrite the auto-capture with a
better-judged version. Tag scaffold-driven writes with `deliberate` so they can
be distinguished from the safety-net write. Do not duplicate.

Before ending this session, work through these four questions and write any
durable memories that surface. Call `memory_add` (MCP) or `memory add-memory` (CLI) for each.

1. DECISIONS — What choices were made that constrain future sessions?
   (type: decision, importance 4 if they limit future options, 3 otherwise)

2. INSIGHTS / OBSERVATIONS — What was learned about Oliver, the project, or the system?
   (type: insight or observation, importance 3 unless high blast-radius)

3. TODOS — What actions were committed to but not yet done?
   (type: todo, include explicit deadline in the fact text if one was stated)

4. FACTS — What context should a future session know that it can't derive itself?
   (type: fact, importance 3–4 for architectural or relationship facts)

After writing, reinforce 2–4 memories that genuinely shaped this session's decisions.
Do not reinforce everything — the signal has value only if it is selective.

Skip this scaffold only if: (a) nothing durable happened this session,
(b) close-session was already run earlier in this turn, or
(c) the Mara baseline safety-net auto-capture is sufficient on its own.
--- End of close-session reminder ---
"""


def main() -> None:
    try:
        response = httpx.get(f"{API_BASE_URL}/health", timeout=3.0)
        response.raise_for_status()
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
        # Service unreachable or unhealthy — don't print scaffold, exit silently.
        return
    except Exception:
        return

    print(_SCAFFOLD)


if __name__ == "__main__":
    main()
