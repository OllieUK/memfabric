# Config surface

**Covers:** `.env`, `.claude/settings.json`, `.claude/settings.local.json`, `.mcp.json`, `docker-compose.yml`

**Native gate:** Edit rules on `.claude/settings*.json`, `.mcp.json`, `docker-compose.yml` fire ask-tier prompts. `.env` is deny-tier (Write/Edit blocked). For asked files, native dialog is the gate — no double-prompt.

## Proceed
- Read any config file for inspection
- Update `outputStyle`, `enabledPlugins`, or `additionalDirectories` in `settings.local.json`

## Report
- Add a new `allow` entry for a specific path or Bash form you've just used repeatedly

## Confirm (all of these fire the native ask dialog)
- Edit `.claude/settings.json` or `settings.local.json`
- Edit `.mcp.json` or `docker-compose.yml`
- Any change that adds a new MCP server or modifies existing `deny` rules

## Refuse
- Write or edit `.env` — native deny rule blocks this
- Add `defaultMode: "dontAsk"` back to `settings.local.json`
- Add `Bash(* | sh)`, `Bash(* | bash)`, or `Bash(eval *)` to any allow list

## Tightening Milestones
Files currently excluded from ask-tier (under active development — see `02-policy.md` for exit conditions):
`mcp_server/server.py`, `memory_service/main.py`, `memory_service/config.py`, `memory_service/knowledge_routes.py`

**Graduated (now ask-tier):** `hooks/_filters.py`, `hooks/session_start.py`, `hooks/post_tool_use.py` — 2026-04-11
