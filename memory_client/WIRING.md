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

3. CLI entry point on PATH — install from the repo root:
   ```bash
   pip install -e .
   ```

   > **Note:** This requires `pyproject.toml` at the repo root (WP-035). Until WP-035 is complete, invoke the CLI via `python -m memory_client.cli` instead of `memory`.

### Configuration

`.env` at the repo root:

```env
API_BASE_URL=http://localhost:8000   # memory service URL
AGENT_ID=claude-code                 # identifies which agent produced a memory
```

### Recommended CLAUDE.md additions

```markdown
## Memory protocol

At session start: run `memory wake-up` (or `python -m memory_client.cli wake-up`)
At session end: run `memory close-session` and act on it
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

| Integration path | How |
|-----------------|-----|
| Shell | Use the CLI directly (`memory wake-up`, `memory add-memory`, etc.) |
| HTTP | Call the REST API at `http://localhost:8000` (interactive docs at `/docs`) |
| Python | Import `MemoryClient` from `memory_client.client` |

For remote (non-localhost) access, see WP-010 in BACKLOG.md.
