# WP-129 — SessionStart Context Injection Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract wake-up formatting into a shared `formatting.py` module and write a `hooks/session_start.py` that auto-injects a memory briefing before every Claude Code session.

**Architecture:** Extract the CLI's `_render_section`/`wake_up` render logic into `memory_client/formatting.py` as `format_wake_up(result, topic, plain)`. The CLI imports and calls it unchanged. The hook script imports `MemoryClient` + `format_wake_up`, calls wake-up, and prints plain-text output to stdout — which Claude Code captures and injects as a `<system-reminder>` preamble. Register in `.claude/settings.json`.

**Tech Stack:** Python 3.10+, httpx, memory_client (editable install), Claude Code SessionStart hook

---

## Files

| File | Change |
|---|---|
| `memory_client/formatting.py` | **Create** — `format_wake_up()` extracted from cli.py |
| `memory_client/cli.py` | Modify — `wake_up` command delegates to `format_wake_up` |
| `hooks/session_start.py` | **Create** — thin hook script |
| `.claude/settings.json` | Modify — register SessionStart hook |
| `tests/test_wp129_session_start_hook.py` | **Create** — all tests |

---

## Task 1: Extract format_wake_up into memory_client/formatting.py

**Files:**
- Create: `memory_client/formatting.py`
- Modify: `memory_client/cli.py`

- [ ] **Step 1: Write unit tests for format_wake_up**

Create `tests/test_wp129_session_start_hook.py`:

```python
import pytest
import re
from memory_client.formatting import format_wake_up


# Minimal result fixture matching wake_up_split() output shape
def _make_result(
    memories=None,
    topic_memories=None,
    companion_anchors=None,
    conversant_anchors=None,
):
    return {
        "memories": memories or [],
        "topic_memories": topic_memories or [],
        "companion_anchors": companion_anchors,
        "conversant_anchors": conversant_anchors,
    }


def _make_mem(text="some fact", importance=3, type="fact", strand_id="strand-core"):
    return {
        "id": "abc",
        "text": text,
        "type": type,
        "importance": importance,
        "strand_id": strand_id,
        "created_at": "2026-04-10T10:00:00+00:00",
        "tags": [],
    }


# --- plain=True removes Rich markup ---

def test_format_wake_up_plain_no_rich_tags():
    result = _make_result(memories=[_make_mem()])
    output = format_wake_up(result, plain=True)
    # Rich markup tags match pattern [word] or [/word]
    assert not re.search(r'\[[a-zA-Z_ /]+\]', output), f"Rich tags found in: {output!r}"


def test_format_wake_up_rich_has_markup_tags():
    result = _make_result(memories=[_make_mem()])
    output = format_wake_up(result, plain=False)
    # Rich output should contain at least one markup tag
    assert re.search(r'\[[a-zA-Z_ /]+\]', output), "Expected Rich tags in non-plain output"


# --- Structure preservation ---

def test_format_wake_up_contains_heading():
    result = _make_result(memories=[_make_mem()])
    output = format_wake_up(result, plain=True)
    assert "Memory briefing" in output


def test_format_wake_up_topic_in_heading():
    result = _make_result(memories=[_make_mem()])
    output = format_wake_up(result, topic="graph-memory-fabric", plain=True)
    assert "graph-memory-fabric" in output


def test_format_wake_up_general_session_when_no_topic():
    result = _make_result(memories=[_make_mem()])
    output = format_wake_up(result, topic=None, plain=True)
    assert "general session" in output


def test_format_wake_up_strand_heading_present():
    result = _make_result(memories=[_make_mem(strand_id="strand-core-work")])
    output = format_wake_up(result, plain=True)
    assert "strand-core-work" in output


def test_format_wake_up_memory_text_present():
    result = _make_result(memories=[_make_mem(text="important fact about Memgraph")])
    output = format_wake_up(result, plain=True)
    assert "important fact about Memgraph" in output


# --- Section omission rules ---

def test_format_wake_up_no_topic_section_when_topic_memories_empty():
    result = _make_result(memories=[_make_mem()], topic_memories=[])
    output = format_wake_up(result, topic="some-topic", plain=True)
    assert "Relevant to today" not in output


def test_format_wake_up_topic_section_present_when_topic_and_memories():
    result = _make_result(
        memories=[_make_mem()],
        topic_memories=[_make_mem(text="topic-relevant memory")],
    )
    output = format_wake_up(result, topic="work", plain=True)
    assert "Relevant to today" in output
    assert "topic-relevant memory" in output


def test_format_wake_up_no_companion_section_when_none():
    result = _make_result(memories=[_make_mem()], companion_anchors=None)
    output = format_wake_up(result, plain=True)
    assert "Companion" not in output


def test_format_wake_up_companion_section_when_present():
    result = _make_result(
        memories=[_make_mem()],
        companion_anchors=[_make_mem(text="companion identity fact")],
    )
    output = format_wake_up(result, plain=True)
    assert "Companion" in output
    assert "companion identity fact" in output


def test_format_wake_up_no_conversant_section_when_none():
    result = _make_result(memories=[_make_mem()], conversant_anchors=None)
    output = format_wake_up(result, plain=True)
    assert "Conversant" not in output


def test_format_wake_up_empty_memories_non_empty_output():
    result = _make_result()
    output = format_wake_up(result, plain=True)
    assert len(output) > 0
    assert "Memory briefing" in output


# --- No-strand fallback ---

def test_format_wake_up_no_strand_shows_fallback_label():
    result = _make_result(memories=[_make_mem(strand_id=None)])
    output = format_wake_up(result, plain=True)
    assert "(no strand)" in output
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/test_wp129_session_start_hook.py -v
```

Expected: `ModuleNotFoundError: No module named 'memory_client.formatting'`

- [ ] **Step 3: Create memory_client/formatting.py**

```python
"""Wake-up output formatting for CLI and hook consumers.

format_wake_up() is the single source of truth for rendering a wake_up_split()
result. The CLI uses it with plain=False (Rich markup). The SessionStart hook
uses it with plain=True (stripped plain text).
"""
import re
from itertools import groupby


def _format_timestamp(created_at: str | None) -> str | None:
    """Return a compact UTC label like '2026-04-10 10:00 UTC', or None."""
    if not created_at:
        return None
    try:
        # created_at is ISO 8601: '2026-04-10T10:00:00+00:00'
        dt = created_at[:16].replace("T", " ")
        return f"{dt} UTC"
    except Exception:
        return None


def _render_section(items: list, plain: bool) -> str:
    """Render a list of memory dicts as a strand-grouped text block."""
    if not items:
        if plain:
            return "  No memories found."
        return "  [dim]No memories found.[/dim]"

    lines = []
    sorted_items = sorted(items, key=lambda m: m.get("strand_id") or "(no strand)")
    for strand_id, group in groupby(sorted_items, key=lambda m: m.get("strand_id") or "(no strand)"):
        if plain:
            lines.append(f"{strand_id}")
        else:
            lines.append(f"[dim]{strand_id}[/dim]")
        for mem in group:
            imp = str(mem.get("importance") or "")
            timestamp = _format_timestamp(mem.get("created_at"))
            mem_type = mem.get("type", "")
            text = mem.get("text", "")
            if plain:
                ts_label = f" ({timestamp})" if timestamp else ""
                lines.append(f"  [{imp}] {mem_type}{ts_label} — {text}")
            else:
                ts_label = f" [dim]({timestamp})[/dim]" if timestamp else ""
                lines.append(f"  [{imp}] [bold]{mem_type}[/bold]{ts_label} — {text}")
    return "\n".join(lines)


def format_wake_up(
    result: dict,
    topic: str | None = None,
    plain: bool = False,
) -> str:
    """Format a wake_up_split() result dict as a readable briefing string.

    Args:
        result: Dict with keys 'memories', 'topic_memories', 'companion_anchors',
                'conversant_anchors' — as returned by MemoryClient.wake_up_split().
        topic: Optional topic string used in the heading and to gate the
               'Relevant to today' section.
        plain: If True, emit plain text (no Rich markup). Used by hooks.
               If False (default), emit Rich markup for CLI rendering.

    Returns:
        A multi-line string ready to print or inject.
    """
    topic_label = topic if topic else "general session"

    core = result.get("memories", [])
    topic_memories = result.get("topic_memories", [])
    companion_anchors = result.get("companion_anchors")
    conversant_anchors = result.get("conversant_anchors")

    lines = []

    if plain:
        lines.append(f"## Memory briefing — {topic_label}")
    else:
        lines.append(f"[bold]## Memory briefing — {topic_label}[/bold]")

    if plain:
        lines.append("\n### Core context")
    else:
        lines.append("\n[bold cyan]### Core context[/bold cyan]")
    lines.append(_render_section(core, plain=plain))

    if topic and topic_memories:
        if plain:
            lines.append("\n### Relevant to today")
        else:
            lines.append("\n[bold cyan]### Relevant to today[/bold cyan]")
        lines.append(_render_section(topic_memories, plain=plain))

    if companion_anchors is not None:
        if plain:
            lines.append("\n### Companion")
        else:
            lines.append("\n[bold cyan]### Companion[/bold cyan]")
        lines.append(_render_section(companion_anchors, plain=plain))

    if conversant_anchors is not None:
        if plain:
            lines.append("\n### Conversant")
        else:
            lines.append("\n[bold cyan]### Conversant[/bold cyan]")
        lines.append(_render_section(conversant_anchors, plain=plain))

    return "\n".join(lines)
```

> **Note:** `_strip_rich` was removed during implementation. The `plain=True` path builds plain strings directly via conditional branching (`if plain: ... else: ...`), which is cleaner than post-hoc stripping and easier to test. The `import re` and `_strip_rich` definition shown above should be omitted.

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_wp129_session_start_hook.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add memory_client/formatting.py tests/test_wp129_session_start_hook.py
git commit -m "WP-129: add memory_client/formatting.py with format_wake_up()"
```

---

## Task 2: Update cli.py to use format_wake_up

**Files:**
- Modify: `memory_client/cli.py`

The goal is to replace the inline rendering logic in the `wake_up` command with a call to `format_wake_up`. The CLI output must be visually unchanged.

- [ ] **Step 1: Write a CLI rendering regression test**

Add to `tests/test_wp129_session_start_hook.py`:

```python
def test_format_wake_up_rich_output_matches_cli_structure():
    """Verify rich output contains the same structural elements as before refactor."""
    result = _make_result(
        memories=[_make_mem(text="core fact", strand_id="strand-work")],
        topic_memories=[_make_mem(text="topic fact", strand_id="strand-work")],
        companion_anchors=[_make_mem(text="companion fact", strand_id="strand-companion")],
    )
    output = format_wake_up(result, topic="work", plain=False)
    assert "## Memory briefing — work" in output
    assert "Core context" in output
    assert "Relevant to today" in output
    assert "Companion" in output
    assert "core fact" in output
    assert "topic fact" in output
    assert "companion fact" in output
```

- [ ] **Step 2: Run test — expect pass**

```bash
pytest tests/test_wp129_session_start_hook.py::test_format_wake_up_rich_output_matches_cli_structure -v
```

Expected: PASS (format_wake_up already handles rich mode).

- [ ] **Step 3: Update cli.py wake_up command**

In `memory_client/cli.py`, add import at the top:

```python
from memory_client.formatting import format_wake_up
```

Find the `wake_up` command function (~line 390). Replace everything from the `heading = ...` line through the final `if conversant_anchors:` block with:

```python
    core = result.get("memories", [])
    topic_memories = result.get("topic_memories", [])
    companion_anchors = result.get("companion_anchors")
    conversant_anchors = result.get("conversant_anchors")

    output = format_wake_up(
        {
            "memories": core,
            "topic_memories": topic_memories,
            "companion_anchors": companion_anchors,
            "conversant_anchors": conversant_anchors,
        },
        topic=topic,
        plain=False,
    )
    console.print(output)
```

Remove the now-unused `_render_section` private function from `cli.py` (it lives in `formatting.py` now).

Also remove the `groupby` import from `cli.py` if it was only used by `_render_section`. Check the import line at the top of `cli.py`:

```python
from itertools import groupby
```

Search the rest of `cli.py` for any other use of `groupby`. If none found, remove the import.

- [ ] **Step 4: Run full CLI-related tests**

```bash
pytest tests/test_wp129_session_start_hook.py -v
```

Expected: all PASS.

- [ ] **Step 5: Smoke test CLI manually**

```bash
python3 -m memory_client.cli wake-up --limit 3
```

Expected: output appears identical to before — strand headings, importance markers, memory text.

- [ ] **Step 6: Commit**

```bash
git add memory_client/cli.py tests/test_wp129_session_start_hook.py
git commit -m "WP-129: cli.py wake_up delegates to format_wake_up; remove duplicated render logic"
```

---

## Task 3: Create hooks/session_start.py

**Files:**
- Create: `hooks/session_start.py`

- [ ] **Step 1: Write tests for hook script behaviour**

Add to `tests/test_wp129_session_start_hook.py`:

```python
import subprocess
import sys
from unittest.mock import patch, MagicMock
import httpx


def test_hook_script_exits_zero_on_success(tmp_path, monkeypatch):
    """Hook prints briefing and exits 0 when service is reachable."""
    mock_result = {
        "memories": [_make_mem(text="session start test memory")],
        "topic_memories": [],
        "companion_anchors": None,
        "conversant_anchors": None,
        "maintenance_status": {
            "short_rest_overdue": False,
            "long_rest_overdue": False,
            "short_rest_days_ago": None,
            "long_rest_days_ago": None,
            "recommended_action": None,
        },
    }

    with patch("memory_client.client.MemoryClient.wake_up_split", return_value=mock_result):
        result = subprocess.run(
            [sys.executable, "hooks/session_start.py"],
            capture_output=True,
            text=True,
            cwd="/home/oliver/projects/graph-memory-fabric",
        )

    assert result.returncode == 0
    assert "Memory briefing" in result.stdout


def test_hook_script_exits_zero_on_connect_error():
    """Hook exits 0 with fallback notice when service is unreachable."""
    with patch(
        "memory_client.client.MemoryClient.wake_up_split",
        side_effect=httpx.ConnectError("refused"),
    ):
        result = subprocess.run(
            [sys.executable, "hooks/session_start.py"],
            capture_output=True,
            text=True,
            cwd="/home/oliver/projects/graph-memory-fabric",
            env={**__import__("os").environ, "API_BASE_URL": "http://localhost:19999"},
        )

    assert result.returncode == 0
    assert "unreachable" in result.stdout.lower() or "unreachable" in result.stderr.lower()


def test_hook_output_contains_no_rich_markup():
    """Hook output must be plain text — no Rich tags."""
    mock_result = {
        "memories": [_make_mem(text="plain text check")],
        "topic_memories": [],
        "companion_anchors": None,
        "conversant_anchors": None,
        "maintenance_status": {},
    }

    with patch("memory_client.client.MemoryClient.wake_up_split", return_value=mock_result):
        result = subprocess.run(
            [sys.executable, "hooks/session_start.py"],
            capture_output=True,
            text=True,
            cwd="/home/oliver/projects/graph-memory-fabric",
        )

    assert result.returncode == 0
    assert not re.search(r'\[[a-zA-Z_ /]+\]', result.stdout), (
        f"Rich tags found in hook output: {result.stdout!r}"
    )
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/test_wp129_session_start_hook.py -k "hook_script" -v
```

Expected: FAIL — `hooks/session_start.py` does not exist.

- [ ] **Step 3: Create hooks/session_start.py**

Create the file at project root:

```python
#!/usr/bin/env python3
"""SessionStart hook — inject memory wake-up briefing into Claude Code context.

Claude Code captures stdout from SessionStart hooks and injects it as a
<system-reminder> preamble before the first user prompt. Output must be
plain text — no Rich markup, no ANSI codes.

Environment variables (all optional):
    API_BASE_URL         Memory service URL (default: http://localhost:8000)
    HOOK_AGENT_ID        Agent ID for wake-up (default: claude-code)
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
```

- [ ] **Step 4: Make the script executable**

```bash
chmod +x /home/oliver/projects/graph-memory-fabric/hooks/session_start.py
```

- [ ] **Step 5: Run hook tests — expect pass**

```bash
pytest tests/test_wp129_session_start_hook.py -k "hook_script" -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add hooks/session_start.py tests/test_wp129_session_start_hook.py
git commit -m "WP-129: add hooks/session_start.py with graceful fallback"
```

---

## Task 4: Register hook in .claude/settings.json

**Files:**
- Modify: `.claude/settings.json`

- [ ] **Step 1: Add SessionStart hook registration**

In `/home/oliver/projects/graph-memory-fabric/.claude/settings.json`, add a `"hooks"` key at the top level (alongside `"permissions"`, `"enabledPlugins"`, etc.):

```json
"hooks": {
  "SessionStart": [
    {
      "hooks": [
        {"type": "command", "command": "python3 /home/oliver/projects/graph-memory-fabric/hooks/session_start.py"}
      ]
    }
  ]
}
```

The full updated file becomes (preserving existing keys):

```json
{
  "permissions": { ... },
  "enabledPlugins": { ... },
  "autoMode": { ... },
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {"type": "command", "command": "python3 /home/oliver/projects/graph-memory-fabric/hooks/session_start.py"}
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Validate JSON is well-formed**

```bash
python3 -c "import json; json.load(open('.claude/settings.json')); print('JSON valid')"
```

Expected: `JSON valid`

- [ ] **Step 3: Commit**

```bash
git add .claude/settings.json
git commit -m "WP-129: register SessionStart hook in .claude/settings.json"
```

---

## Task 5: Manual verification

- [ ] **Step 1: Verify hook runs correctly against live service**

```bash
python3 /home/oliver/projects/graph-memory-fabric/hooks/session_start.py
```

Expected: prints a memory briefing (plain text, no Rich tags, strand headings, memory facts).

- [ ] **Step 2: Verify graceful fallback when service is stopped**

Stop the service temporarily (or point to a bad port):

```bash
API_BASE_URL=http://localhost:19999 python3 /home/oliver/projects/graph-memory-fabric/hooks/session_start.py
```

Expected: prints `Memory service unreachable — operating without context briefing.` and exits 0.

- [ ] **Step 3: Run full test suite for regressions**

```bash
pytest tests/ -v -k "not integration" --tb=short 2>&1 | tail -20
```

Expected: no new failures.

- [ ] **Step 4: Run integration tests for WP-129 (only formatting — no live service tests needed)**

```bash
pytest tests/test_wp129_session_start_hook.py -v
```

Expected: all PASS.

---

## Task 6: Update BACKLOG.md

**Files:**
- Modify: `BACKLOG.md`

- [ ] **Step 1: Move WP-129 to Completed**

In `BACKLOG.md`:
1. Delete the WP-129 row from the priority table
2. Add to the Completed section:

```
### WP-129 — SessionStart context injection hook
Completed 2026-04-10. Extracted format_wake_up() from cli.py into memory_client/formatting.py (plain=True strips Rich markup for hook consumers). hooks/session_start.py calls wake_up_split + format_wake_up and prints plain text to stdout. Registered in .claude/settings.json. CLI output unchanged. All tests passing.
Retrospective: extracting the formatter first made the hook trivial (~35 lines). The plain=True flag was the key design decision — keeps one renderer for two consumers without branching logic.
```

- [ ] **Step 2: Commit**

```bash
git add BACKLOG.md
git commit -m "WP-129: complete — move to done in BACKLOG"
```
