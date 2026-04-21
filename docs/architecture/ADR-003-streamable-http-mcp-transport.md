# ADR-003: Replace stdio MCP transport with streamable HTTP

**Status:** Proposed  
**Date:** 2026-04-21  
**Deciders:** Oliver  
**WP:** WP-105 (to be added to BACKLOG)

---

## Context

The MemFabric MCP server (`mcp_server/server.py`) currently runs over stdio transport
exclusively. Clients — Claude Desktop, Claude Code, future harnesses — must each have
the `memory-mcp` executable installed locally and referenced by absolute path in their
config files.

This creates a hard dependency on local installation in every environment that wants to
use the MCP tools:

- **Claude Desktop (Windows):** `memory-mcp.exe` installed to Python 3.14 scripts dir,
  referenced by full path in `claude_desktop_config.json`.
- **Claude Code (WSL):** `memory-mcp` on `$PATH` (installed via pip in WSL),
  referenced via `.mcp.json` with `API_KEY=${MEMFABRIC_API_KEY}` env var expansion.
- **Any future harness:** Must repeat the install-and-configure cycle.

The 401 auth failures seen in Claude Code sessions arise from exactly this fragility —
`MEMFABRIC_API_KEY` is not reliably propagated into every shell environment where the
harness spawns the child process.

The MemFabric FastAPI service is already publicly accessible at
`https://memfabric.carr-it.net` via Cloudflare Tunnel, and bearer token auth (WP-096) is
already implemented. The MCP library (FastMCP ≥ 2.0) supports streamable HTTP transport
natively. The preconditions for URL-based MCP access already exist.

### Current architecture

```
Claude Code / Desktop
    │  stdio (spawn child process)
    ▼
memory-mcp  (mcp_server/server.py — local process)
    │  HTTP + Bearer token
    ▼
FastAPI service  (memory_service/)
    │  Bolt
    ▼
Memgraph
```

### Target architecture

```
Claude Code / Desktop / any harness
    │  HTTPS + Bearer token (MCP streamable HTTP)
    ▼
FastAPI service  (/mcp endpoint — same process)
    │  direct function calls (no HTTP round-trip)
    ▼
Memgraph
```

---

## Decision

Mount the FastMCP server as an ASGI sub-application inside the existing FastAPI service,
exposed at `/mcp`. This is **Option B** from the options considered below.

All MCP clients are reconfigured to use `url: https://memfabric.carr-it.net/mcp` with a
bearer token. No local install is required anywhere.

---

## Options Considered

### Option A — Separate streamable-HTTP process (minimal change)

Keep `mcp_server/server.py` as a standalone process; switch
`mcp.run(transport="stdio")` to `mcp.run(transport="streamable-http", ...)`. Deploy as a
second service alongside FastAPI; expose via the same Cloudflare Tunnel on a different
path or port.

| Dimension | Assessment |
|-----------|------------|
| Code change | Minimal — one-line transport swap + new docker-compose service |
| Deployment complexity | Medium — second service, second health check, second restart policy |
| Auth | FastMCP 2.x has built-in API key support for HTTP transport; configure independently of FastAPI's auth |
| Coupling | Low — MCP server remains an HTTP client of FastAPI, independent lifecycles |
| HTTP round-trip | Present — MCP server still calls FastAPI over HTTP for every tool call |
| Local install | Eliminated from client side; still present in server-side deployment |

**Pros:** Lowest risk, rollback is a one-line revert, process isolation preserved, independent scaling.  
**Cons:** Second service to operate; each MCP tool call still traverses an HTTP round-trip (MCP → FastAPI); two auth surfaces to keep in sync; Docker-compose grows.

---

### Option B — ASGI mount inside FastAPI (recommended)

Mount the FastMCP server directly inside the FastAPI app via
`app.mount("/mcp", fastmcp_app)`. The MCP tools call repo functions directly rather than
via HTTP. One process, one deployment, one TLS termination.

| Dimension | Assessment |
|-----------|------------|
| Code change | Medium — refactor MCP tools to call repo directly; wire ASGI mount; handle auth at mount boundary |
| Deployment complexity | Low — no new service; existing docker-compose unchanged |
| Auth | Requires explicit wiring: FastAPI's global `Depends(verify_api_key)` does NOT propagate to ASGI-mounted sub-applications. Must add auth via FastMCP's own API-key feature or a lightweight ASGI middleware at the mount point |
| Coupling | Medium — MCP tools now import from `memory_service.*` directly; shared process |
| HTTP round-trip | Eliminated — tool calls are in-process function calls |
| Local install | Eliminated everywhere |

**Pros:** Single process to operate; no internal HTTP round-trip; one auth surface; cleaner long-term architecture; `mcp_server/config.py` (`MCPSettings` / `API_BASE_URL` / `API_KEY`) becomes unnecessary.  
**Cons:** Auth at the ASGI mount boundary needs explicit care; MCP tools must be refactored to call repo functions directly (remove `MemoryClient` httpx calls); the `ENABLE_KNOWLEDGE_LAYER` flag exists in both `mcp_server/config.py` and `memory_service/config.py` — needs consolidation.

---

### Option C — Abandon FastMCP, use bare `mcp` SDK

Rewrite `mcp_server/server.py` using the official Anthropic `mcp` SDK's low-level server
classes; mount via ASGI. Not recommended — FastMCP 2.x wraps the SDK cleanly and
provides the ASGI integration out of the box. No value in bypassing it.

---

## Trade-off Analysis

The choice between A and B is operational complexity vs. architectural cleanliness.

Option A can ship faster and carries less refactor risk, but it perpetuates the
`mcp_server/` directory as a long-lived separate service that duplicates the config
surface and requires an internal HTTP client. Every tool call pays an extra round-trip.

Option B requires a one-time refactor of the 27 MCP tool implementations (from
`httpx`-based `MemoryClient` calls to direct repo function calls), and careful auth wiring
at the mount boundary. But once done, the architecture is simpler: one service, one auth
surface, no internal HTTP.

Given that MemFabric is a single-operator service (not multi-tenant SaaS), the operational
simplicity of Option B outweighs the short-term refactor cost. The auth boundary problem
is well-understood and solvable with FastMCP's native API-key parameter.

**Option B is chosen.**

---

## Implementation Notes

### Auth at the ASGI mount boundary

FastMCP's `FastMCP(name=..., dependencies=[...])` accepts a list of FastAPI-style
dependencies. Pass `verify_api_key` as a dependency there:

```python
from mcp_server.auth import verify_api_key  # or memory_service.auth

mcp = FastMCP("MemFabric", dependencies=[Depends(verify_api_key)])
```

This keeps the same auth logic (bearer token or `X-Api-Key` header, same key store)
without adding `/mcp` to `_OPEN_PATHS` or duplicating the token check.

Alternatively, FastMCP's built-in `api_key` parameter can be used — but sharing the
FastAPI auth dependency is preferable so key rotation happens in one place.

### Tool refactor pattern

Each of the 27 tools currently calls `MemoryClient` via httpx. After refactoring, each
tool opens a Memgraph session directly:

```python
# Before (via HTTP client)
async def memory_search(...):
    results = await client.search(query, ...)

# After (direct repo call)
async def memory_search(...):
    with get_driver().session() as session:
        results = memory_repo.search_memories(session, ...)
```

The `mcp_server/config.py` `MCPSettings` class (with `api_base_url`, `api_key`) can be
removed entirely once all tools are ported.

### ENABLE_KNOWLEDGE_LAYER consolidation

The knowledge-tool registration gate in `mcp_server/server.py` currently reads from
`mcp_server/config.py`'s `settings.enable_knowledge_layer`. After the merge, it should
read from `memory_service/config.py`'s `settings.enable_knowledge_layer` directly —
single source of truth.

### Client config changes

**Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "memory": {
      "type": "http",
      "url": "https://memfabric.carr-it.net/mcp",
      "headers": {
        "Authorization": "Bearer <api_key>"
      }
    }
  }
}
```

**Claude Code** (`.mcp.json` in project root):

```json
{
  "mcpServers": {
    "memory": {
      "type": "http",
      "url": "https://memfabric.carr-it.net/mcp",
      "headers": {
        "Authorization": "Bearer ${MEMFABRIC_API_KEY}"
      }
    }
  }
}
```

Env var expansion in headers still works in Claude Code's `.mcp.json` — but the key
benefit is that even if `MEMFABRIC_API_KEY` is unset, the error is a clean 401, not a
failure to spawn the subprocess at all.

The `memory-mcp` entrypoint and `mcp_server/server.py` stdio path can be kept as an
**offline/localhost fallback** — useful when the tunnel is down or in air-gapped
environments — but is no longer the primary path.

---

## Consequences

**Easier after this decision:**
- Any harness (Claude Desktop, Claude Code, VS Code extension, custom script) connects
  with a URL + token; no install step
- Auth failures surface as clean HTTP 401s, not cryptic subprocess spawn errors
- One service to monitor, restart, and upgrade
- In-process tool calls are faster than the current HTTP round-trip chain

**Harder after this decision:**
- 27 MCP tool implementations need porting from `MemoryClient` to direct repo calls
  (mechanical but non-trivial; good candidate for a parallel agent sweep)
- Auth at the FastMCP ASGI mount boundary requires explicit configuration; it does not
  inherit FastAPI's global dependency automatically
- `mcp_server/` directory either shrinks to a fallback-only stub or is removed; the
  removal adds some deployment churn if any external scripts reference `memory-mcp`

**Review triggers:**
- Multi-tenant requirement (the shared auth surface would need per-tenant key scoping)
- Need to run MCP server independently of the FastAPI service (e.g. separate scaling)
- FastMCP ASGI integration proves incompatible with a future FastAPI version upgrade

---

## Action Items

1. [ ] Add WP-105 to BACKLOG.md: *Streamable HTTP MCP transport (ADR-003)*
2. [ ] Refactor 27 MCP tools in `mcp_server/server.py` to call repo functions directly (remove `MemoryClient` / httpx dependency)
3. [ ] Mount `FastMCP` instance as ASGI sub-app at `/mcp` in `memory_service/main.py`
4. [ ] Wire `verify_api_key` as a FastMCP dependency at mount time
5. [ ] Consolidate `ENABLE_KNOWLEDGE_LAYER` to single `memory_service/config.py` source
6. [ ] Update `claude_desktop_config.json` to URL-based entry
7. [ ] Update `.mcp.json` to URL-based entry
8. [ ] Keep `memory-mcp` stdio entrypoint as offline fallback (do not delete)
9. [ ] Remove `mcp_server/config.py` `MCPSettings` (API_BASE_URL, API_KEY — no longer needed)
10. [ ] Update deployment docs / `cit-home-stackdeploy` if any references to the MCP child process exist
