# scripts/

One-off operational scripts. Not part of the running service.

| Script | Purpose | When to run |
|--------|---------|-------------|
| `init_schema.py` | Create Memgraph constraints + vector index | Once after `docker compose up`, before first use (WP-002) |
| `smoke_test.py` | Insert a test Memory node and verify vector search works | After schema init, to confirm the stack is healthy (WP-002) |

Add new scripts here as work packages require them.
All scripts read config from `.env` via `pydantic-settings` — never hardcode hosts or ports.
