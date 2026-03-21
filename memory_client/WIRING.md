# Wiring Instructions

How to connect a companion environment to the Graph Memory Fabric CLI.

---

## Claude Code (active)

The `memory` CLI is available in any Claude Code session opened in this repository.

### Prerequisites

1. Memory service running:
   ```bash
   docker compose up -d
   uvicorn memory_service.main:app --reload
   ```

2. Packages installed:
   ```bash
   pip install -r memory_client/requirements.txt
   ```

3. CLI entry point on PATH (one-time setup):
   ```bash
   pip install -e .   # requires WP-035; until then use python -m memory_client.cli
   ```

   Until WP-035 is complete, invoke via:
   ```bash
   python -m memory_client.cli wake-up
   python -m memory_client.cli add-memory --text "..." --type fact
   ```

### Configuration

`.env` at the repo root:

```env
API_BASE_URL=http://localhost:8000   # memory service URL
AGENT_ID=claude-code                 # identifies which agent produced a memory
```

### Hook: automatic session start

Add to `.claude/hooks` (once available) to auto-run wake-up at session open:

```json
{
  "event": "session_start",
  "command": "python -m memory_client.cli wake-up"
}
```

### Recommended CLAUDE.md additions

```markdown
## Memory protocol

At session start: run `python -m memory_client.cli wake-up`
At session end: run `python -m memory_client.cli close-session` and act on it
See memory_client/COMPANION.md for full protocol.
```

---

## Claude Desktop + MCP (planned — WP-033)

> Not yet implemented. This section will be completed when WP-033 delivers the MCP server.

The planned MCP server will expose these tools:

| Tool | Maps to |
|------|---------|
| `memory_wake_up` | `GET /memory/wake-up` |
| `memory_add` | `POST /memory` |
| `memory_search` | `POST /memory/search` |
| `memory_list_strands` | `GET /strands` |
| `memory_close_session` | local scaffold (no API) |

**Placeholder config** (Claude Desktop `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "graph-memory-fabric": {
      "command": "python",
      "args": ["-m", "memory_mcp.server"],
      "env": {
        "API_BASE_URL": "http://localhost:8000",
        "AGENT_ID": "claude-desktop"
      }
    }
  }
}
```

This config will be finalised in WP-033.

---

## Other environments

Any environment that can run a shell command or call HTTP endpoints can integrate:

- **Shell**: use the CLI directly (`memory wake-up`, `memory add-memory`, etc.)
- **HTTP**: call the REST API at `http://localhost:8000` directly (see FastAPI docs at `/docs`)
- **Python**: import `MemoryClient` from `memory_client.client`

For remote access (non-localhost), see WP-010 (Tailscale + TLS) in BACKLOG.md.
