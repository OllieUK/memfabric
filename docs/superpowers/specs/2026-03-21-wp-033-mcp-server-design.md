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

The server imports `MemoryClient` from `memory_client.client` — no HTTP logic is duplicated. It does not import from `memory_client.cli` (CLI formatting is terminal-only).

Phase 2 (separate WP): add `--transport streamable-http` for network/remote access. FastMCP supports this with minimal code changes.

---

## 4. Directory structure

```
mcp_server/
  __init__.py
  server.py          # FastMCP app + all 5 tool definitions + main() entry point
  config.py          # Re-uses API_BASE_URL and AGENT_ID env vars (same as memory_client)
```

`pyproject.toml` gains one new entry point:
```toml
[project.scripts]
memory-mcp = "mcp_server.server:main"
```

Run as: `memory-mcp` (after `pip install -e .`) or `python -m mcp_server.server`.

---

## 5. Tool definitions

| MCP Tool | HTTP call | Parameters | Return |
|---|---|---|---|
| `memory_add` | `POST /memory` | `text`, `type`, `strand_ids`, `tags`, `importance`, `agent_id` | `str` — created memory ID |
| `memory_search` | `POST /memory/search` | `query`, `tags`, `agent_ids`, `limit` | `list[dict]` — matching memories |
| `memory_wake_up` | `GET /memory/wake-up` | `topic` (optional), `limit` (default 20) | `str` — briefing text (same format as CLI) |
| `memory_list_strands` | `GET /strands` | none | `list[dict]` — strand records |
| `memory_close_session` | (no API call) | none | `str` — close-out scaffold text verbatim |

**Return type rationale:**
- `memory_wake_up` and `memory_close_session` return plain strings — the companion reads them and acts. This mirrors CLI behaviour exactly; no new logic needed.
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
    agent_id: str | None = None,  # falls back to config.AGENT_ID
) -> str:
    """Add a memory to the fabric. Returns the created memory ID."""
```

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
    """Return the session wake-up briefing. Read fully before responding to the user."""
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
    """Return the session close-out scaffold. Work through it before ending the session."""
```

---

## 6. Configuration

`mcp_server/config.py` uses the same `pydantic-settings` pattern as `memory_client/config.py`:

```python
class MCPSettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    agent_id: str = "claude-code"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
```

Same env vars (`API_BASE_URL`, `AGENT_ID`) — no new config surface.

---

## 7. Wiring

### Claude Code (`.mcp.json` in companion project root)

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

### Claude Desktop (`claude_desktop_config.json`)

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

Both configs assume `memory-mcp` is on PATH via `pip install -e .` from the repo root. `WIRING.md` is updated with these sections, replacing the current placeholders. The `command` can also be written as an absolute path (`/path/to/venv/bin/memory-mcp`) for robustness when PATH is not inherited.

### COMPANION.md update

A short section is prepended to the protocol noting that when MCP tools are available (`memory_wake_up`, `memory_add`, etc.), they are the preferred integration path. The CLI commands remain documented as the fallback for CLI-only environments.

---

## 8. Dependencies

`fastmcp` is added to `memory_client/requirements.txt` (shared requirements file for the package) and to the project's install dependencies in `pyproject.toml`.

```
fastmcp>=2.0
```

No other new dependencies. `httpx` is already present via `memory_client`.

---

## 9. Testing

### Unit tests (`tests/test_wp033_mcp_server.py`)

Run with `pytest` (no live stack required). Mock `MemoryClient` via `unittest.mock.patch`.

| Test | Assertion |
|---|---|
| U1 — `memory_add` calls correct client method | `client.add_memory()` called with correct kwargs; return is UUID string |
| U2 — `memory_search` calls correct client method | `client.search_memory()` called; return is list |
| U3 — `memory_wake_up` returns briefing string | `client.wake_up_split()` called; return is non-empty string containing "Memory briefing" |
| U4 — `memory_list_strands` returns list of dicts | `client.list_strands()` called; return is list |
| U5 — `memory_close_session` returns scaffold text | No client call; return contains "Session close-out" |
| U6 — `memory_wake_up` with topic includes topic in string | `topic` param passed through; "Relevant to today" present in output |

### Integration tests (live stack required)

Tagged `@pytest.mark.integration`. Require Memgraph + FastAPI service running.

| Test | Assertion |
|---|---|
| I1 — `memory_list_strands` returns ≥1 strand | Response is non-empty list with `id` and `name` keys |
| I2 — `memory_add` creates memory | Returns UUID string; subsequent search finds it |
| I3 — `memory_search` returns results | Known query returns non-empty list |
| I4 — `memory_wake_up` returns non-empty briefing | Return string contains "Memory briefing" |
| I5 — `memory_close_session` returns scaffold | Return string contains "Session close-out" |

### Manual smoke test (pre-wiring validation)

Before configuring Claude Code or Claude Desktop, validate the server schema using MCP Inspector:

```bash
npx @modelcontextprotocol/inspector memory-mcp
```

Confirms: all 5 tools listed with correct schemas, each tool callable and returning expected output.

---

## 10. Acceptance criteria

- [ ] `memory-mcp` entry point installed and executable
- [ ] All 5 MCP tools present and callable via MCP Inspector
- [ ] All unit tests passing
- [ ] All integration tests passing against live stack
- [ ] `.mcp.json` wired in this repo; `memory_list_strands` returns 20 strands from Claude Code MCP session
- [ ] `WIRING.md` Claude Desktop and Claude Code MCP sections complete (no placeholders)
- [ ] `COMPANION.md` updated with MCP-preferred-path note

---

## 11. Future: HTTP transport (Phase 2)

When remote/network access is needed, the same FastMCP server adds:

```python
mcp.run(transport="streamable-http", host="0.0.0.0", port=8001)
```

`WIRING.md` gains a "Remote / Claude.ai" section at that point. Authentication, TLS, and firewall considerations are scoped to that WP. This design does not block or constrain Phase 2.
