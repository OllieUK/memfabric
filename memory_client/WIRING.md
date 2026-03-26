# Wiring Instructions

How to connect a companion environment to the Graph Memory Fabric.

---

## Claude Code (CLI)

### Prerequisites

1. Memory service running:
   ```bash
   ./scripts/start-local-stack.sh
   ```

2. Install the package (registers `memory` and `memory-mcp` entry points):
   ```bash
   pip install --user -e . --no-build-isolation
   pip install -r memory_client/requirements.txt
   ```

### Configuration

`.env` at the repo root:

```env
API_BASE_URL=http://localhost:8000   # memory service URL
AGENT_ID=claude-code                 # identifies which agent produced a memory
```

### Option A — MCP (recommended for Claude Code)

`.mcp.json` at the repo root is already configured. Claude Code auto-discovers it.

Verify: start a Claude Code session and run `/mcp` — `memory` should appear as a connected server.

### Option B — CLI fallback

Use the `memory` CLI directly in any shell or Claude Code bash tool call:

```bash
memory wake-up
memory add-memory --text "..." --type fact --strand-id <strand-id>
memory close-session
```

See `COMPANION.md` for the full session protocol.

### Recommended CLAUDE.md additions

```markdown
## Memory protocol

Read and follow `memory_client/COMPANION.md` at the start of every session.
MCP tools (`memory_wake_up`, `memory_add`, etc.) are preferred when available.
CLI fallback: `memory wake-up`, `memory add-memory`, `memory close-session`.
```

---

## Claude Desktop (MCP)

### Prerequisites

Same as Claude Code above — memory service must be running and package installed.

### Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

**Option A — entry point (preferred, requires PATH):**

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

**Option B — absolute path fallback (if `memory-mcp` not on Claude Desktop's PATH):**

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

Replace `/path/to/venv/bin/python` with the actual path from `which python3` in your active venv.

Restart Claude Desktop after editing. Verify: a hammer icon (🔨) should appear in the chat input area, listing `memory` tools.

---

## Other environments

| Integration path | How |
|-----------------|-----|
| Shell / Claude Code bash | Use the `memory` CLI directly |
| HTTP | Call the REST API at `http://localhost:8000` (interactive docs at `/docs`) |
| Python | Import `MemoryClient` from `memory_client.client` |

For remote (non-localhost) access, see WP-010 in BACKLOG.md (future: HTTP transport WP).
