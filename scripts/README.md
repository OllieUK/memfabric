# scripts/

One-off operational scripts. Not part of the running service.

| Script | Purpose | When to run |
|--------|---------|-------------|
| `start-local-stack.sh` | Start Docker Compose services then launch the FastAPI service (with hot-reload). Sets offline embedding flags automatically. | Local development — replaces running `docker compose up` and `uvicorn` separately |
| `init_schema.py` | Create Memgraph constraints + vector index | Once after `docker compose up`, before first use (WP-002) |
| `smoke_test.py` | Insert a test Memory node and verify vector search works | After schema init, to confirm the stack is healthy (WP-002) |
| `seed_strands.py` | Wipe test Memory/Agent/Project nodes and seed Strand nodes from the Memory Web definition. Idempotent for strands (MERGE), destructive for other node types. | Once on a clean slate before first real use |
| `dump_db.py` | Dump all Memory nodes and RELATED_TO/LEADS_TO edges to a timestamped JSON snapshot | Before any destructive maintenance run (rollback mechanism) |
| `restore_db.py` | Restore Memory nodes and edges from a JSON snapshot (MERGE — does not clear DB first; drop Memory nodes manually before a clean restore) | After a failed maintenance run or to restore from backup |
| `migrate_fact_so_what.py` | Migrate Memory nodes from the legacy single `text` field to the `fact`/`so_what` split. Interactive JSON-lines protocol; supports `--dry-run` | One-time data migration (run against a dump backup first) |
| `migrate_person_nodes.py` | Wire ABOUT edges from existing Memory nodes to Person nodes. Interactive JSON-lines protocol; supports `--dry-run` and `--pre-created-persons` | One-time data migration (run against a dump backup first) |
| `migrate_reinforcement_defaults.py` | Backfill reinforcement properties (`strength`, `decay_rate`, etc.) on Memory nodes and RELATED_TO/LEADS_TO edges. Idempotent — skips already-set properties; supports `--dry-run` | One-time data migration after reinforcement model was introduced |

All scripts read config from `.env` via `pydantic-settings` — never hardcode hosts or ports.
