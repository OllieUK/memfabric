# Threat Model

## Adversary model

Windows host and WSL2 guest are a **single trust domain**. Network ports on `0.0.0.0` are not treated as external exposure within that trust domain. The framework does **not** protect against LAN attackers — that is a deployment concern addressed by WP-096 (bearer-token auth) and the deployment gates listed in `03-operating-guide.md`.

### Threats in scope

1. **Indirect prompt injection via ingested content** — malicious text embedded in PDFs, STIX bundles, or framework YAML that reaches the system prompt via the memory/knowledge retrieval pipeline.
2. **Supply chain** — tampered Python packages, framework data files, or STIX bundles substituted before ingestion.
3. **Catastrophic local mistakes** — irreversible Cypher operations (DETACH DELETE all nodes), volume wipes (`docker compose down -v`), or accidental `.env` edits that destroy keys or state.
4. **Data exhaust from the PostToolUse hook** — the hook captures tool outputs to memory; if the tool output contains sensitive data (credentials, PII from file reads), it persists in Memgraph.

### Threats out of scope (v1)

- LAN-adjacent attackers reaching Memgraph or the FastAPI service directly.
- Authenticated multi-user access control (deferred to WP-096).
- Operating-system-level privilege escalation.

## Canonical injection chain

```
PDF in /mnt/c/.../OneDrive/...
  → scripts/ingest_document.py
  → Chunk.text in Memgraph
  → knowledge_search_chunks (MCP)   OR   memory_wake_up
  → hooks/session_start.py
  → stdout
  → Claude Code <system-reminder>
  → next session's system prompt
```

Any node on this chain that passes untrusted text forward without sanitisation or trust-level tagging is an amplification point. The framework's primary defence is a PDF review runbook (see `03-operating-guide.md`) applied before any content enters Memgraph.

## Crown jewels

The following files require elevated caution. "Ask" means the native permission system fires a confirmation dialog; "deny" means the operation is blocked.

| File / path | Level | Notes |
|---|---|---|
| `.env` | **deny** Write/Edit | Contains (or will contain, WP-096) API keys and service credentials |
| `.claude/settings*.json` | ask | Modifying permissions rules is a privileged operation |
| `.mcp.json` | ask | Adding an MCP server extends Claude's tool surface |
| `docker-compose.yml` | ask | Port bindings and volume mounts affect network exposure |
| `CLAUDE.md` | ask | Primary instruction file read every session |
| `BACKLOG.md` | ask | Authoritative work queue; accidental edits lose priority context |
| `data/frameworks/**` | ask | Source-of-truth for ingested knowledge; tampering affects all downstream analysis |
| `data/threats/**` | ask | CTI source data; same risk as frameworks |
| `scripts/seed_strands.py` | ask on edit, **deny** on Bash exec | Wipes Memory/Agent/Project nodes; legitimate use requires `ENABLE_SEED_STRANDS=1` escape |
| `scripts/dump_db.py` | ask on edit | Exfiltrates entire graph |
| `scripts/restore_db.py` | ask on edit | Overwrites entire graph |
| `scripts/init_schema.py` | ask on edit | Alters graph schema |
| `scripts/init_knowledge_schema.py` | ask on edit | Alters knowledge layer schema |

## MCP inventory

**Local MCP: `memory`**
- Implementation: `mcp_server/server.py` via stdio transport
- Trust level: HIGH — local code, no network reach, runs in-process with the CLI
- Review cadence: each `mcp_server/` release

User-level MCPs (Gamma, Notion, etc.) are out of scope for this framework — they are governed by `~/.claude/` settings and not subject to project-level review here.

## Token footprint budget

| Layer | Target | When loaded |
|---|---|---|
| A fragment in CLAUDE.md | ≤ 80 tokens | every session |
| B ingest.md | ≤ 250 tokens | ingest skill activation |
| B config.md | ≤ 250 tokens | harness/config edit |
| C files | no ceiling | rarely (editing framework) |

Full framework reference: `docs/security/`. Per-surface sheets: `docs/security/layer-b/`.
