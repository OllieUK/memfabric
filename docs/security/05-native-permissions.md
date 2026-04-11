# Native Permissions Rationale

## Design principle

The operating model is: broad allows for normal development work, ask-tier on genuine outliers that warrant a pause, deny on catastrophic or irreversible operations. The permission system is not a whitelist — it is a set of speed bumps at the edges of safe operation.

Developers should not feel friction during routine tasks (reading files, running tests, git operations, starting Docker). The ask-tier fires for things that are either irreversible, structurally significant, or represent potential injection consequences. Deny covers only the operations that should never happen without explicit manual intervention.

## Deny rules

| Rule | Rationale |
|---|---|
| `Write(.env)` / `Edit(.env)` | Contains (or will contain, WP-096) API keys; any LLM write to this file is likely an injection consequence |
| `Write(.env.*)` / `Edit(.env.*)` | Covers `.env.staging`, `.env.local`, etc. — same risk |
| `Bash(docker compose down -v*)` | Destroys Memgraph named volumes, wiping all graph data irreversibly |
| `Bash(docker-compose down -v*)` | Legacy CLI spelling; same risk |
| `Bash(docker volume rm *memgraph*)` | Direct volume deletion; same risk |
| `Bash(rm -rf .../data/*)` | Destroys all source data (frameworks, threats) under the project |
| `Bash(python3 .../seed_strands.py*)` | Wipes Memory/Agent/Project nodes; legitimate use requires `ENABLE_SEED_STRANDS=1` |
| `Bash(python .../seed_strands.py*)` | Same, alternate interpreter invocation |

## Ask rules

| Rule | Rationale |
|---|---|
| `Edit(.claude/settings.json)` | Modifying the permission system is a privileged, self-affecting operation |
| `Edit(.claude/settings.local.json)` | Same — user-level overrides |
| `Edit(.mcp.json)` | Adds or modifies MCP servers, extending Claude's tool surface |
| `Edit(docker-compose.yml)` | Port bindings and volume mounts affect network exposure and data persistence |
| `Edit(CLAUDE.md)` | Primary instruction file; changes affect every session |
| `Edit(scripts/seed_strands.py)` | See deny rationale — edit gate before the exec deny |
| `Edit(scripts/dump_db.py)` | Exfiltrates entire graph; modify with care |
| `Edit(scripts/restore_db.py)` | Overwrites entire graph |
| `Edit(scripts/init_schema.py)` | Alters graph schema; migration risk |
| `Edit(scripts/init_knowledge_schema.py)` | Same for knowledge layer schema |
| `Bash(sudo*)` | Privilege escalation gate |
| `Bash(pip install *)` | Arbitrary package installation; supply chain risk |
| `Bash(curl http*)` / `Bash(curl https*)` | General network egress; more-specific allows for localhost/127.0.0.1 take precedence |
| `Bash(docker compose down*)` | Stops the stack; ask before disrupting the running service |
| `Bash(docker volume *)` | Volume management; broad gate |

## Allow rules

The allow list is intentionally broad for development operations. The philosophy: if the deny list catches the catastrophes, and the ask list catches the outliers, then normal development should be friction-free.

`Bash(git *)` and `Bash(python3 *)` are intentionally broad — the deny list catches the catastrophic operations within those wildcards (e.g. `python3 .../seed_strands.py`). The allow rules express trust in the operator; the deny rules express absolute limits.

`Read(/home/oliver/**)` and `Read(/mnt/c/Users/olive/**)` allow broad file reading because Claude Code regularly needs to read source files, configs, and data across the project tree. This is not a security boundary — an LLM that can read arbitrary files is a design choice for an interactive coding assistant.

`Bash(curl http://127.0.0.1*)` and `Bash(curl http://localhost*)` are allow-listed as more specific forms within the ask-tier `curl http*`/`curl https*` rules. More specific rules take precedence, so localhost health checks and API smoke tests proceed without prompting.

## settings.local.json cleanup

The following entries were removed from `.claude/settings.local.json` in this WP:

| Removed entry | Reason |
|---|---|
| `"defaultMode": "dontAsk"` | Bypassed all ask-tier prompts globally; this negated the entire permission framework |
| `Bash(del "C:\\Users\\olive\\.claude\\...")` | Windows `del` command for old memory files; no longer relevant |
| `Bash(powershell.exe -Command "Remove-Item ...")` | Same — Windows memory file cleanup |
| `Bash(HF_HUB_OFFLINE=0 /bin/python3.10:*)` | Obsolete interpreter path; replaced by `python3` allow in project settings |
| `Bash(TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1 /bin/python3.10:*)` | Same |
| `Bash(/bin/python3.10:*)` | Same |

## Cross-reference to user-level invariants

Force-push, recursive `rm` outside the project tree, credential file reads (`~/.ssh/`, `~/.gnupg/`, etc.), and other global denies are handled by `~/.claude/settings.json`. Those rules are not duplicated here — project settings layer on top of user settings. Consult `~/.claude/settings.json` for the full set of user-level invariants.
