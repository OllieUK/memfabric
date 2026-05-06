#!/usr/bin/env python3
"""SessionStart hook — inject memory wake-up briefing into Claude Code context.

Claude Code captures stdout from SessionStart hooks and injects it as a
<system-reminder> preamble before the first user prompt. Output must be
plain text — no Rich markup, no ANSI codes.

Environment variables (all optional):
    API_BASE_URL            Memory service URL (default: http://localhost:8000)
    HOOK_WAKE_UP_CORE_LIMIT Max memories in the unstructured "core" section (default: 8).
                            The four structured profile sections (global Mara baseline,
                            global user baseline, project persona, project baseline) have
                            their own per-section limits set via WAKE_UP_* env vars in
                            .env — this variable only controls the core section.
    HOOK_WAKE_UP_TOPIC      Topic for scoped wake-up (default: unset = general).
                            Prefer leaving this unset and using startup.json project
                            context, which is resolved automatically by the client.

Registration in .claude/settings.json (or global ~/.claude/settings.json):
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
from hooks._filters import contains_injection

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
HOOK_WAKE_UP_CORE_LIMIT = int(os.environ.get("HOOK_WAKE_UP_CORE_LIMIT", os.environ.get("HOOK_WAKE_UP_LIMIT", "8")))
HOOK_WAKE_UP_TOPIC = os.environ.get("HOOK_WAKE_UP_TOPIC") or None

_FACT_MAX_LEN = 500
_OUTPUT_MAX_LEN = 6000


def _filter_memories(memories: list) -> tuple[list, int]:
    """Remove memories containing injection patterns; truncate long facts.

    Memories tagged 'untrusted' are dropped silently (not counted in dropped).
    Only injection-filtered memories count toward the dropped note.

    Returns (filtered_list, dropped_count).
    """
    filtered = []
    dropped = 0
    for mem in memories:
        # Drop untrusted memories silently — no dropped counter increment
        raw_tags = mem.get("tags")
        tags = raw_tags if isinstance(raw_tags, list) else []
        if "untrusted" in tags:
            continue
        fact = mem.get("fact", "") or ""
        so_what = mem.get("so_what", "") or ""
        if contains_injection(fact + " " + so_what):
            dropped += 1
            continue
        if len(fact) > _FACT_MAX_LEN:
            mem = dict(mem)
            mem["fact"] = fact[:_FACT_MAX_LEN] + "[…]"
            # text is derived from fact+so_what — rebuild it so rendering is consistent
            mem["text"] = mem["fact"] + (" " + so_what if so_what else "")
        filtered.append(mem)
    return filtered, dropped


def _apply_filters(result: dict) -> tuple[dict, int]:
    """Filter all memory lists in a wake_up_split result. Returns (new_result, total_dropped)."""
    total_dropped = 0
    new_result = {}
    for key, value in result.items():
        if isinstance(value, list):
            filtered, dropped = _filter_memories(value)
            new_result[key] = filtered
            total_dropped += dropped
        else:
            new_result[key] = value
    return new_result, total_dropped


def main() -> None:
    try:
        with MemoryClient(base_url=API_BASE_URL) as client:
            result = client.wake_up_split(
                limit=HOOK_WAKE_UP_CORE_LIMIT,
                topic=HOOK_WAKE_UP_TOPIC,
            )
    except (httpx.ConnectError, httpx.TimeoutException):
        print("Memory service unreachable — operating without context briefing.")
        return
    except httpx.HTTPStatusError as exc:
        print(f"Memory service error ({exc.response.status_code}) — operating without context briefing.")
        return
    except Exception as exc:
        print(f"session_start hook: unexpected error ({exc!r}) — operating without context briefing.", file=sys.stderr)
        return

    try:
        filtered_result, dropped = _apply_filters(result)
    except Exception as exc:
        print(f"session_start hook: filter error ({exc!r}) — using unfiltered output.", file=sys.stderr)
        filtered_result = result
        dropped = 0

    output = format_wake_up(filtered_result, topic=HOOK_WAKE_UP_TOPIC, plain=True)

    if len(output) > _OUTPUT_MAX_LEN:
        output = output[:_OUTPUT_MAX_LEN] + "\n[note: output truncated at 6000 chars]"

    if dropped:
        output += f"\n[note: {dropped} memories omitted by content filter]"

    print(output)


if __name__ == "__main__":
    main()
