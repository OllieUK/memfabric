# Operating Guide

## Stack start and stop

**Start:**
```bash
docker compose up -d
python3 -m uvicorn memory_service.main:app --reload
```
Or use `scripts/start-local-stack.sh` if it exists.

**Stop:**
```bash
docker compose down
```

Do NOT use `docker compose down -v` — the `-v` flag removes named volumes and wipes Memgraph data.

## PDF review runbook

Run this checklist before ingesting any PDF. It MUST be completed before calling any ingest script.

1. **Source confirmation** — Who sent the PDF? Is it from an allow-listed OneDrive subfolder? If the source is unknown or outside the allow-listed paths, treat as untrusted and do not ingest.

2. **Structural scan** — Run `pdfid.py` or `peepdf` to flag the following keys:
   - `/JS` — embedded JavaScript
   - `/JavaScript` — same
   - `/EmbeddedFile` — attached file payload
   - `/OpenAction` — auto-execute on open
   - `/Launch` — shell launch action

   Any hit on these keys → manual review required before ingesting. Do not proceed automatically.

3. **Layer scan** — Sample `pdfplumber page.extract_text()` output visually for hidden, misleading, or out-of-context content. Look for invisible text (white on white), very small fonts, or text positioned outside visible page bounds.

4. **Hash record** — Compute SHA-256:
   ```bash
   sha256sum path/to/file.pdf
   ```
   Record the hash in `data/frameworks/SOURCES.md` (for framework documents) or `data/threats/SOURCES.md` (for CTI). This creates an immutable provenance record.

5. **Only then:** Run `scripts/ingest_document.py` or `scripts/extract_cti_threats.py`.

## Subprocess orchestration

`scripts/ingest_all_threat_reports.py` uses `subprocess.run([sys.executable, ...])` with argv (not `shell=True`). This is intentional and must be preserved. The list form prevents shell injection — the script path and arguments are passed as distinct tokens, not interpolated into a shell string.

Any new ingest orchestrator that requires `shell=True` triggers a policy review before it may be merged.

## seed_strands.py escape hatch

`scripts/seed_strands.py` is deny-tier on Bash execution because it performs DETACH DELETE on Memory, Agent, and Project nodes — wiping most of the graph. To run it legitimately:

1. Temporarily remove the deny rule from `.claude/settings.json` (this will fire the ask-tier dialog for the settings file itself).
2. Set `ENABLE_SEED_STRANDS=1` as an environment variable — this is the confirmation token the script checks before proceeding.
3. Run the script.
4. Immediately restore the deny rule.

This two-step process (remove rule + set env var) means accidental execution requires two separate deliberate acts.

## Incident response: fabric poisoned

If you suspect injected or malicious content has entered Memgraph:

1. **Identify** the source memory or chunk via search:
   ```
   memory_search <suspect phrase>
   knowledge_search_chunks <suspect phrase>
   ```

2. **Archive or delete** the memory via:
   ```
   memory archive <memory_id>
   ```
   Or via MCP: `memory_archive` / `memory_delete`.

3. **If ingested via the knowledge layer:** Find and delete the chunk directly:
   ```cypher
   MATCH (c:Chunk) WHERE c.text CONTAINS 'suspicious text' DETACH DELETE c
   ```

4. **Run short-rest** to recompute edges after deletion:
   ```
   memory_short_rest
   ```

5. **If session_start has already delivered the injection:** The current session's system prompt is compromised. Treat all reasoning in this session as potentially influenced and start a fresh session.

## Deployment gates

The following gates MUST be completed before moving the service outside a single-machine localhost environment. They are not current WPs — they are pre-conditions for any non-localhost deployment.

| Gate | WP | What it does |
|---|---|---|
| Bearer-token API auth | WP-096 | Prevents unauthenticated access to the FastAPI service |
| Memgraph authentication | n/a | Set non-empty `memgraph_user`/`memgraph_password` in `.env` |
| FastAPI bind address | n/a | Change `api_host` default from `0.0.0.0` to `127.0.0.1` |
| Memgraph Docker port prefix | n/a | Add `127.0.0.1:` prefix to all Memgraph port mappings in `docker-compose.yml` |

Do not skip these when leaving the development machine.
