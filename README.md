# Graph-Memory Fabric

Local-first, model-agnostic long-term memory with graph-cloud visualisation for multiple agents.

Memories are stored as graph nodes with vector embeddings in [Memgraph](https://memgraph.com). A FastAPI service exposes HTTP endpoints for storing and searching memories. Memgraph Lab provides a live graph-cloud visualisation at `http://localhost:3000`. In v1 the only LLM is your IDE session (Claude Code); the runtime makes no external API calls.

---

## Prerequisites

- Docker Desktop with WSL2 backend
- Python 3.11+
- WSL2 (Ubuntu 22.04 recommended)

---

## Setup

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env if you need non-default values (host, port, credentials, embedding model)
```

### 2. Start Memgraph + Lab

```bash
docker compose up -d
```

Verify:
- Memgraph Lab UI: http://localhost:3000 (connect to `localhost:7687`)
- Bolt port: `localhost:7687`

### 3. Install Python dependencies

```bash
pip install -r memory_service/requirements.txt
```

### 4. Run the Memory API service

```bash
uvicorn memory_service.main:app --reload
```

---

## Verify

```bash
# Health check
curl http://localhost:8000/health
# → {"status":"ok"}

# Interactive API docs
open http://localhost:8000/docs
```

---

## Current status

| Work Package | Status |
|---|---|
| WP-001: Project framework + scaffold | ✅ Complete |
| WP-002: Memgraph schema + vector index | Backlog |
| WP-003: Local embeddings module | Backlog |
| WP-004–006: Wire API endpoints | Backlog |
| WP-007: Python client + CLI | Backlog |

See [BACKLOG.md](BACKLOG.md) for the full prioritised backlog.

---

## Working norms

See [CLAUDE.md](CLAUDE.md) for operating instructions, Definition of Done, naming conventions, and configuration guidelines.

---

## Stopping services

```bash
docker compose down        # stop containers, keep volumes
docker compose down -v     # stop and delete all data volumes
```
