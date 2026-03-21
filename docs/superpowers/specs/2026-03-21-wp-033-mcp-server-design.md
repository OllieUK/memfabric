# WP-033: MCP Server Design
**Date:** 2026-03-21
**Status:** Draft
**Work package:** WP-033

---

## 1. Problem statement

The memory fabric is currently accessible only via the `memory` CLI (STDIO) or direct REST API calls. Claude Desktop and other MCP-capable clients (future: ChatGPT Desktop, remote agents) cannot access it without a custom integration per client. An MCP server wrapping the same REST API gives any MCP-capable client first-class access with no client-side code changes.

---

## 2. Scope

**In scope (WP-033):**
- New `mcp_server/` directory with a FastMCP-based server
- 5 MCP tools matching the spec (add, search, wake_up, list_strands, close_session)
- STDIO transport (Phase 1 — local Claude Code and Claude Desktop)
- Updated `WIRING.md`: Claude Desktop and Claude Code MCP sections (replacing placeholders)
- Updated `COMPANION.md`: MCP tools as preferred path when available, CLI as fallback
- Unit tests (mocked MemoryClient) and integration tests (live stack)
- `pyproject.toml` entry point: `memory-mcp`

**Out of scope (future WP):**
- Streamable HTTP / SSE transport for network/remote access
- Authentication beyond AGENT_ID env var
- ChatGPT Desktop integration (requires HTTP transport)
- `memory_client/` self-contained packaging (WP-035)

---

## 3. Approach

**FastMCP, STDIO transport, separate `mcp_server/` directory.**

FastMCP provides decorator-based tool definition, automatic JSON schema generation from type hints and docstrings, and built-in MCP Inspector support. Transport is STDIO for Phase 1: Claude Code and Claude Desktop both spawn the server as a subprocess — no network stack, <10ms latency per call, process isolation.

The server imports `MemoryClient` from `memory_client.client` — no HTTP logic is duplicated. It does not import from `memory_client.cli` (CLI formatting uses Rich markup and is terminal-only; MCP tools assemble plain-text strings independently).

Phase 2 (separate WP): add Streamable HTTP transport for network/remote access. FastMCP supports this with minimal code changes.

---

## 4. Directory structure

```
mcp_server/
  __init__.py
  server.py          # FastMCP app + all 5 tool definitions + main() entry point
  config.py          # Re-uses API_BASE_URL and AGENT_ID env vars (same as memory_client)
  requirements.txt   # fastmcp>=2.0 (only new dep for this module)
```

`pyproject.toml` gains one new entry point and `fastmcp` in the dependencies list:

```toml
[project]
dependencies = [
    "httpx",
    "typer",
    "rich",
    "pydantic-settings",
    "fastmcp>=2.0",
]

[project.scripts]
memory     = "memory_client.cli:app"
memory-mcp = "mcp_server.server:main"
```

> **Note:** `pyproject.toml` currently has no `dependencies` key. This WP adds it, which also resolves the `pip install -e .` prerequisite noted in `WIRING.md` (the WP-035 note in `WIRING.md` is removed as part of this WP). `sentence-transformers` is a `memory_service` dependency — it is not added here. `memory_client/requirements.txt` is unchanged — `fastmcp` is an MCP server dependency, not a `memory_client` dependency. `respx` (used in tests) remains in `memory_client/requirements.txt`; install it alongside `pip install -e .` by running `pip install -r memory_client/requirements.txt`.

`mcp_server/requirements.txt` lists only the additive dependency for this module:

```
fastmcp>=2.0
```

It is additive: it assumes `memory_client/requirements.txt` is already installed (which is guaranteed by `pyproject.toml` listing all shared deps). In an isolated environment, install from `pyproject.toml` via `pip install -e .`.

Run as: `memory-mcp` (after `pip install -e .`) or `python -m mcp_server.server`.

---

## 5. Tool definitions

| MCP Tool | HTTP call | Parameters | Return |
|---|---|---|---|
| `memory_add` | `POST /memory` | `text`, `type`, `strand_ids`, `tags`, `importance`, `agent_id` | `str` — created memory ID |
| `memory_search` | `POST /memory/search` | `query`, `tags`, `agent_ids`, `limit` | `list[dict]` — matching memories |
| `memory_wake_up` | `GET /memory/wake-up` | `topic` (optional), `limit` (default 20) | `str` — plain-text briefing (see Section 5.1) |
| `memory_list_strands` | `GET /strands` | none | `list[dict]` — strand records |
| `memory_close_session` | (no API call) | none | `str` — plain-text close-out scaffold (see Section 5.2) |

**Return type rationale:**
- `memory_wake_up` and `memory_close_session` return plain strings — the companion reads them and acts. Rich markup is stripped; MCP tools assemble their own plain-text variants.
- `memory_search` and `memory_list_strands` return structured dicts — the companion can reason over them programmatically.
- `memory_add` returns a plain string confirmation — the companion acknowledges and continues.

### Tool parameter detail

**`memory_add`:**
```python
@mcp.tool
def memory_add(
    text: str,
    type: str = "fact",
    strand_ids: list[str] | None = None,
    tags: list[str] | None = None,
    importance: int = 3,
    agent_id: str | None = None,
) -> str:
    """Add a memory to the fabric. Returns the created memory ID."""
```

Implementation note: `MemoryClient.add_memory` requires `agent_id` as a mandatory positional argument. The tool resolves `None` to `settings.agent_id` before calling the client:

```python
resolved_agent_id = agent_id or settings.agent_id
with MemoryClient(base_url=settings.api_base_url) as client:
    mid = client.add_memory(text, type, resolved_agent_id, ...)
return mid
```

A fresh `MemoryClient` context is opened per tool call (stateless, safe for concurrent MCP requests).

**`memory_search`:**
```python
@mcp.tool
def memory_search(
    query: str,
    tags: list[str] | None = None,
    agent_ids: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search the memory fabric by semantic similarity."""
```

**`memory_wake_up`:**
```python
@mcp.tool
def memory_wake_up(
    topic: str | None = None,
    limit: int = 20,
) -> str:
    """Return the session wake-up briefing as plain text. Read fully before responding to the user."""
```

**`memory_list_strands`:**
```python
@mcp.tool
def memory_list_strands() -> list[dict]:
    """Return all strands. Use strand IDs when calling memory_add."""
```

**`memory_close_session`:**
```python
@mcp.tool
def memory_close_session() -> str:
    """Return the session close-out scaffold as plain text. Work through it before ending the session."""
```

### 5.1 `memory_wake_up` plain-text format

The tool assembles its own plain-text briefing (not delegating to CLI formatting). Exact rules:

- Use `strand_id` (the raw ID field, e.g. `strand-identity`) as the group header — not the strand name.
- Two-space indent for memory lines.
- Blank line between strand groups.
- No Rich markup (`[bold]`, `[cyan]`, etc.).

Format:

```
## Memory briefing — {topic or "general session"}

### Core context

strand-identity
  [4] fact — The user's name is Oliver.

strand-work
  [3] decision — The user has decided to use FastMCP for the MCP server.

### Relevant to today

strand-projects
  [3] observation — The user is building the graph-memory-fabric MCP server today.
```

The "Relevant to today" section is **omitted entirely** when `topic` is `None` or when `topic_memories` is empty. This matches the CLI behaviour exactly.

**Assembly algorithm:** `wake_up_split(limit=limit, topic=topic)` returns `(core_memories, topic_memories)` — both are flat lists of memory dicts. To produce the grouped output:

1. Sort each list by `strand_id` (ascending, so groupby produces stable groups).
2. Use `itertools.groupby` on `strand_id` to emit one strand header per group.
3. Within each group, emit one memory line per memory in the group's order.
4. Memories without a `strand_id` are grouped under `"(no strand)"`.
5. No deduplication — a memory in both lists appears in both sections.

> **WP-028 compatibility note:** WP-028 (causal graph) will replace the `text` field on Memory nodes with `fact` + `so_what`. At that point, the briefing line format becomes `[{importance}] {type} — {fact}` (and optionally `→ {so_what}` on a continuation line). This is a follow-up change scoped to WP-028; WP-033 uses `text` as the current API field.

### 5.2 `memory_close_session` plain-text format

The tool returns this fixed string (no timestamp — timestamps are CLI cosmetics):

```
## Session close-out

Review this session and answer the following before ending:

1. What decisions were made? (store as type: decision)
   → memory_add(text="...", type="decision", strand_ids=["<strand-id>"])

2. What was learned or observed about the user? (store as type: insight or observation)
   → memory_add(text="...", type="insight", strand_ids=["<strand-id>"])

3. What actions were committed to? (store as type: todo)
   → memory_add(text="...", type="todo", strand_ids=["<strand-id>"])

4. What context should a future session know that isn't already in the fabric?
   → memory_add(text="...", type="fact", strand_ids=["<strand-id>"])

Run memory_list_strands() if strand IDs are uncertain.
Do not end the session without calling memory_add at least once if any of the above apply.
```

Note: The scaffold uses MCP tool call syntax (`memory_add(...)`) rather than CLI command syntax (`memory add-memory --text ...`), as this is the preferred integration path when MCP is available.

---

## 6. `main()` entry point

```python
def main() -> None:
    mcp.run(transport="stdio")
```

`mcp` is a `FastMCP` instance created at module level:

```python
mcp = FastMCP("graph-memory-fabric")
```

No CLI argument parsing. Transport is always STDIO. The MCP client (Claude Code, Claude Desktop) spawns the process and communicates via stdin/stdout.

---

## 7. Configuration

`mcp_server/config.py` uses the same `pydantic-settings` pattern as `memory_client/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class MCPSettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    agent_id: str = "claude-code"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = MCPSettings()
```

Same env vars (`API_BASE_URL`, `AGENT_ID`) — no new config surface.

---

## 8. Wiring

### Claude Code — `.mcp.json` at the graph-memory-fabric repo root

```json
{
  "mcpServers": {
    "memory": {
      "command": "memory-mcp",
      "env": {
        "API_BASE_URL": "http://localhost:8000",
        "AGENT_ID": "claude-code"
      }
    }
  }
}
```

This file is created at `/home/oliver/projects/graph-memory-fabric/.mcp.json`. Claude Code auto-discovers `.mcp.json` in the project root (supported from Claude Code v1.x onwards; verify with `claude --version` if the server does not appear).

### Claude Desktop — `claude_desktop_config.json`

```json
{
  "mcpServers": {
    "memory": {
      "command": "memory-mcp",
      "env": {
        "API_BASE_URL": "http://localhost:8000",
        "AGENT_ID": "claude-desktop"
      }
    }
  }
}
```

> **Note:** The existing `WIRING.md` placeholder uses the server key `"graph-memory-fabric"`. This WP renames it to `"memory"` for brevity and consistency with the Claude Code config. Update any existing Desktop config accordingly.

Both configs assume `memory-mcp` is on PATH via `pip install -e .` from the repo root (this WP establishes the working `pyproject.toml` that makes this install work). If `memory-mcp` is not on PATH (e.g. Claude Desktop running outside the venv), use an absolute path and fallback args instead:

```json
{
  "mcpServers": {
    "memory": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "API_BASE_URL": "http://localhost:8000",
        "AGENT_ID": "claude-desktop"
      }
    }
  }
}
```

`WIRING.md` documents both forms (entry point and python -m fallback).

### WIRING.md update

File: `memory_client/WIRING.md`. The two placeholder sections ("Claude Desktop + MCP (planned — WP-033)" and the Claude.ai placeholder) are replaced with the above configs plus install steps. The existing "Claude Code (active)" section gains a new subsection for MCP wiring alongside the existing CLI wiring.

### COMPANION.md update

File: `memory_client/COMPANION.md`.

A short preamble is prepended:

> **MCP integration (preferred):** When running in a Claude Desktop or MCP-enabled Claude Code session, use the MCP tools (`memory_wake_up`, `memory_add`, `memory_search`, `memory_list_strands`, `memory_close_session`) directly. They are the preferred path. The CLI commands below remain valid as a fallback for CLI-only environments.

---

## 9. Testing

### Unit tests (`tests/test_wp033_mcp_server.py`)

Run with `pytest` (no live stack required). Each test instantiates the tool function directly, with `MemoryClient` patched via `unittest.mock.patch`.

The mock for `wake_up_split` returns `([{"strand_id": "strand-identity", "type": "fact", "text": "test memory", "importance": 4}], [])` by default. For U6, the mock returns a non-empty `topic_memories` list.

| Test | Setup | Assertion |
|---|---|---|
| U1 — `memory_add` resolves `agent_id` and calls client | Mock `add_memory` returns `"uuid-1234"` | `client.add_memory` called; `call_args.args[2] == settings.agent_id` (third positional arg); return is `"uuid-1234"` |
| U2 — `memory_search` calls client method | Mock `search_memory` returns `[{"id": "x"}]` | `client.search_memory` called with `query`; return is a list |
| U3 — `memory_wake_up` returns plain-text briefing | Mock `wake_up_split` returns one core memory | Return is `str`; contains `"## Memory briefing"`; contains the memory text; no Rich markup (`[bold]`, `[cyan]`) |
| U4 — `memory_list_strands` returns list of dicts | Mock `list_strands` returns `[{"id": "strand-x", "name": "X"}]` | `client.list_strands` called; return is a list with `id` key |
| U5 — `memory_close_session` returns scaffold text without client call | No mock needed | No client call made; return contains `"## Session close-out"` and `"memory_add("` |
| U6 — `memory_wake_up` with topic includes "Relevant to today" | Mock `wake_up_split` returns `(core, [{"strand_id": "s", "type": "fact", "text": "topic mem", "importance": 3}])` | Return contains `"### Relevant to today"` |
| U7 — `memory_wake_up` without topic omits "Relevant to today" | Mock `wake_up_split` returns `(core, [])` | Return does **not** contain `"Relevant to today"` |

### Integration tests (live stack required)

Tagged `@pytest.mark.integration`. Require Memgraph + FastAPI service running.

| Test | Assertion |
|---|---|
| I1 — `memory_list_strands` returns ≥1 strand | Response is non-empty list; first item has `id` and `name` keys |
| I2 — `memory_add` creates a memory | Returns a UUID string |
| I3 — `memory_search` returns results for text inserted by I2 | Query `"WP-033 integration test"` returns non-empty list; at least one result's `text` contains `"WP-033 integration test memory"` |
| I4 — `memory_wake_up` returns non-empty briefing | Return string contains `"## Memory briefing"`; length > 50 chars |
| I5 — `memory_close_session` returns scaffold | Return string contains `"## Session close-out"` |

For I2, the added memory text is `"WP-033 integration test memory"` with `type="fact"` and `importance=1`. The search query is `"WP-033 integration test"`.

### Manual smoke test (pre-wiring validation)

Before configuring Claude Code or Claude Desktop, validate the server schema using MCP Inspector:

```bash
npx @modelcontextprotocol/inspector memory-mcp
```

Confirms: all 5 tools listed with correct schemas, each tool callable and returning expected output.

---

## 10. Acceptance criteria

- [ ] `memory-mcp` entry point installed and on PATH (verify: `which memory-mcp` returns a path; validate via MCP Inspector smoke test below)
- [ ] All 5 MCP tools present and callable via MCP Inspector with correct schemas
- [ ] All unit tests passing (U1–U7)
- [ ] All integration tests passing against live stack (I1–I5)
- [ ] `.mcp.json` created at graph-memory-fabric repo root; Claude Code MCP session shows `memory_list_strands` returning 20 strands
- [ ] `WIRING.md` Claude Desktop and Claude Code MCP sections complete (no placeholder text remaining)
- [ ] `COMPANION.md` updated with MCP-preferred-path preamble

---

## 11. Future: HTTP transport (Phase 2)

When remote/network access is needed, `main()` is extended to accept a `--transport` flag:

```python
mcp.run(transport="streamable-http", host="0.0.0.0", port=8001)
```

`WIRING.md` gains a "Remote / Claude.ai" section at that point. Authentication, TLS, and firewall considerations are scoped to that WP. This design does not block or constrain Phase 2.
