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

MVP complete. The memory service, CLI, and companion integration package are all working.

See [BACKLOG.md](BACKLOG.md) for the full prioritised backlog and completed work packages.

---

## Using the CLI

```bash
# Session start — load memory briefing
memory wake-up
memory wake-up --topic "what I'm working on today"

# Store a memory
memory add-memory "TEXT" --type fact --strand-id <strand-id> --importance 3

# Search
memory search-memory "QUERY" [--tag TAG] [--limit N]

# Session end — review and store what was learned
memory close-session

# List available strands
memory list-strands
```

For the full companion session protocol, see [memory_client/COMPANION.md](memory_client/COMPANION.md).

---

## Working norms

See [CLAUDE.md](CLAUDE.md) for operating instructions, Definition of Done, naming conventions, and configuration guidelines.

---

## Stopping services

```bash
docker compose down        # stop containers, keep volumes
docker compose down -v     # stop and delete all data volumes
```
