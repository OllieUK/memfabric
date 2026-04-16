# WP-126 Implementation Plan: PostToolUse Observer Hook

## Context

WP-126 adds zero-friction automatic memory capture via a Claude Code `PostToolUse` hook. After each tool call, the hook fires, detects substantive events (file writes, edits, significant bash commands, web fetches), and POSTs an `observation` memory to the memory service with `files_modified`/`files_read` provenance.

**Already done — no changes needed:**
- `observation` is already a valid `MemoryType` in `memory_service/main.py`
- `files_modified` and `files_read` are fully wired on Memory nodes (WP-127)
- `memory_client/client.py` `add_memory()` already accepts `files_modified` and `files_read`
- `POST /memory` already accepts these fields

**What this WP builds:**
1. `strand-session-activity` strand seeded into Memgraph
2. `hooks/post_tool_use.py` hook script
3. Hook registered in `.claude/settings.json`
4. Full test suite

---

## Task 1 — Seed `strand-session-activity`

**Files to change:** `scripts/seed_strands.py`

Add the following entry to the Companion Domain block in the `STRANDS` list (after `strand-companion-memory-macro`):

```python
{
    "id": "strand-session-activity",
    "name": "Session Activity",
    "description": "Automatic observations captured from Claude Code tool use: file writes, edits, significant bash commands, and web fetches. Low-importance ephemeral record of what was done during sessions.",
    "category": "Companion Domain",
},
```

**Important:** `seed_strands.py` wipes Memory/Agent/Project nodes before seeding. Since we must not wipe the live graph, the implementer must add the strand via a direct Cypher MERGE instead of running the full seed script:

```cypher
MERGE (s:Strand {id: "strand-session-activity"})
SET s.name = "Session Activity",
    s.description = "Automatic observations captured from Claude Code tool use: file writes, edits, significant bash commands, and web fetches. Low-importance ephemeral record of what was done during sessions.",
    s.category = "Companion Domain"
```

Run this directly against Memgraph (bolt://localhost:7687, no auth).

**Acceptance:** The strand node exists in Memgraph and is returned by `GET /memory/strands`.

---

## Task 2 — Implement `hooks/post_tool_use.py`

**Files to create:** `hooks/post_tool_use.py`

Follow `hooks/session_start.py` exactly for structure: sys.path manipulation, env-var config at module level, MemoryClient as context manager, `try/except httpx.*`, `if __name__ == "__main__": main()`.

### Module docstring and imports

```python
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
```

### Three pure functions (testable in isolation)

```python
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
```

### main()

```python
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
```

Key constraints:
- Errors go to `sys.stderr` only — stdout is injected into Claude Code context
- Always exits 0 (Python default; broad except ensures nothing propagates)
- Pure functions must be importable without triggering stdin read

**Acceptance:** `python3 hooks/post_tool_use.py` with a JSON payload piped to stdin posts an observation to the live service.

---

## Task 3 — Write unit tests

**Files to create:** `tests/test_wp126_post_tool_use_hook.py`

Follow `tests/test_wp129_session_start_hook.py` exactly for test structure and mocking patterns.

### Fixture payloads (module-level constants)

```python
WRITE_PAYLOAD = {
    "tool_name": "Write",
    "tool_input": {"file_path": "/tmp/test_file.py", "content": "x = 1"},
    "tool_response": {"type": "result", "result": "File written successfully"},
    "session_id": "test-session",
}

EDIT_PAYLOAD = {
    "tool_name": "Edit",
    "tool_input": {"file_path": "/tmp/test_file.py", "old_string": "x = 1", "new_string": "x = 2"},
    "tool_response": {"type": "result", "result": "Edit applied"},
    "session_id": "test-session",
}

BASH_PAYLOAD_SUBSTANTIVE = {
    "tool_name": "Bash",
    "tool_input": {"command": "pytest tests/ -x", "description": "Run tests"},
    "tool_response": {"type": "result", "result": "=== 42 passed in 3.1s ==="},
    "session_id": "test-session",
}

BASH_PAYLOAD_EMPTY = {
    "tool_name": "Bash",
    "tool_input": {"command": "cd /tmp", "description": ""},
    "tool_response": {"type": "result", "result": ""},
    "session_id": "test-session",
}

WEBFETCH_PAYLOAD = {
    "tool_name": "WebFetch",
    "tool_input": {"url": "https://memgraph.com/docs"},
    "tool_response": {"type": "result", "result": "...page content..."},
    "session_id": "test-session",
}

READ_PAYLOAD = {
    "tool_name": "Read",
    "tool_input": {"file_path": "/tmp/test_file.py"},
    "tool_response": {"type": "result", "result": "x = 1"},
    "session_id": "test-session",
}
```

### Required tests

**Group A — parse_payload:**
- `test_parse_payload_valid_json` — returns dict
- `test_parse_payload_empty_string` — returns None
- `test_parse_payload_whitespace_only` — returns None
- `test_parse_payload_invalid_json` — returns None

**Group B — is_substantive:**
- `test_is_substantive_write_true`
- `test_is_substantive_edit_true`
- `test_is_substantive_bash_long_output_true`
- `test_is_substantive_bash_empty_output_false`
- `test_is_substantive_bash_short_output_false` (result="ok" — 2 chars, below threshold)
- `test_is_substantive_bash_whitespace_output_false`
- `test_is_substantive_webfetch_with_url_true`
- `test_is_substantive_webfetch_without_url_false`
- `test_is_substantive_read_false`
- `test_is_substantive_unknown_tool_false`

**Group C — build_memory_params:**
- `test_build_params_write` — fact="Wrote file: /tmp/test_file.py", files_modified=["/tmp/test_file.py"], files_read=[]
- `test_build_params_edit` — fact="Edited file: ...", files_modified=[path], files_read=[]
- `test_build_params_bash_short_command` — full command in fact
- `test_build_params_bash_long_command_truncated` — command >120 chars truncated with "…"
- `test_build_params_webfetch` — fact contains URL, empty file lists
- `test_build_params_unknown_tool_returns_none`

**Group D — main() (mock MemoryClient via `patch("hooks.post_tool_use.MemoryClient")`):**
- `test_main_write_calls_add_memory` — type=observation, files_modified set
- `test_main_edit_calls_add_memory`
- `test_main_bash_substantive_calls_add_memory`
- `test_main_bash_empty_skips_add_memory` — assert NOT called
- `test_main_webfetch_calls_add_memory`
- `test_main_read_tool_skips`
- `test_main_empty_stdin_skips`
- `test_main_invalid_json_skips`
- `test_main_importance_is_2`
- `test_main_strand_is_session_activity`
- `test_main_tags_include_hook`
- `test_main_connect_error_exits_cleanly` — no exception propagated
- `test_main_timeout_error_exits_cleanly`
- `test_main_http_status_error_exits_cleanly`
- `test_main_unexpected_error_exits_cleanly`
- `test_main_agent_id_from_env` — monkeypatch AGENT_ID env var
- `test_main_agent_id_default_claude_code`
- `test_main_error_goes_to_stderr_not_stdout`

Mocking stdin in main() tests: patch `sys.stdin` with `unittest.mock.MagicMock(read=lambda: json.dumps(WRITE_PAYLOAD))`.

**Acceptance:** `pytest tests/test_wp126_post_tool_use_hook.py -v` passes all unit tests without the live service.

---

## Task 4 — Register hook in `.claude/settings.json`

**File to change:** `/home/oliver/projects/graph-memory-fabric/.claude/settings.json`

Add `PostToolUse` to the existing `hooks` object. The nested structure must match the `SessionStart` entry exactly:

```json
"PostToolUse": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "python3 /home/oliver/projects/graph-memory-fabric/hooks/post_tool_use.py"
      }
    ]
  }
]
```

Verify JSON is valid after editing.

**Acceptance:** `python3 -c "import json; json.load(open('.claude/settings.json'))"` exits 0.

---

## Task 5 — Integration tests and acceptance verification

**Files to create:** integration test block in `tests/test_wp126_post_tool_use_hook.py`

All integration tests marked `@pytest.mark.integration`. Use `tags=["test", "hook", "post-tool-use"]` on all test memories. Archive created memories in fixture teardown.

**Required integration tests:**
- `test_integration_write_observation_stored` — run main() with mocked stdin (Write payload) against live service; assert memory with type=observation, files_modified=[path] retrievable via `GET /memory/by-file?path=...&role=modified`
- `test_integration_observation_has_strand` — stored memory is retrievable via search with strand_ids=["strand-session-activity"] filter (or verify IN_STRAND edge via direct Bolt query)
- `test_integration_bash_observation_stored` — substantive Bash payload stores memory
- `test_integration_empty_bash_not_stored` — empty-output Bash payload stores nothing (count before/after)
- `test_integration_service_unreachable_exits_cleanly` — wrong port → no exception
- `test_integration_dedup_repeated_write` — two identical Write payloads → second returns deduplicated=True

Run: `pytest tests/test_wp126_post_tool_use_hook.py -v -m integration`

**Manual acceptance check:**
1. In a live Claude Code session (hook registered), ask Claude to write a trivial file to `/tmp/wp126_test.txt`
2. Query `GET /memory/by-file?path=/tmp/wp126_test.txt&role=modified`
3. Confirm observation memory present with correct fields

---

## Pitfalls

1. **strand-session-activity must be seeded before integration tests** — strand linking uses MATCH, not MERGE; unknown strand_ids are silently skipped (CLAUDE.md Cypher gotchas)
2. **stdout vs stderr** — hook errors go to stderr only; stdout gets injected into Claude Code context
3. **settings.json nested format** — the live file uses `{"hooks": [{"type": "command", ...}]}` nesting, not the simpler format shown in some docs
4. **File paths in payloads may be relative** — store as-is; the service does string matching
5. **stdin read deferred to main()** — pure functions must be importable without reading stdin
