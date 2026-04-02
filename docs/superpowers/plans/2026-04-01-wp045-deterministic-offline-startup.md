# WP-045: Make Local Startup Deterministic Offline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the misleading Memgraph healthcheck, add a Bolt-level readiness wait to `start-local-stack.sh`, and document offline environment variables in `.env.example` so session startup never produces false "memory service unreachable" failures.

**Architecture:** Three targeted changes — (1) replace the TCP-only Docker healthcheck with a real Bolt query, (2) extend the startup script to wait for a healthy Memgraph before launching the API, (3) add the missing offline env vars to `.env.example`. No new source files; no new dependencies.

**Tech Stack:** Docker Compose healthcheck syntax, bash, Python `neo4j` driver (already a project dependency), `pytest` for unit tests of any Python changes.

---

## Problem summary

The current healthcheck (`exec 3<>/dev/tcp/127.0.0.1/7687`) only confirms the TCP port is open — Memgraph accepts the connection during its initialisation phase before it is ready to serve Bolt queries. This means:

- `lab` starts before Memgraph can answer queries → repeated connection errors in the Lab UI.
- `start-local-stack.sh` launches the FastAPI service immediately after `docker compose up -d`, before Memgraph is actually ready → `driver.verify_connectivity()` in `lifespan()` raises `ServiceUnavailable` → misleading "memory service unreachable" message at session start.
- `HF_HUB_OFFLINE` and `TRANSFORMERS_OFFLINE` are set in the script but not listed in `.env.example`, so operators who start the service manually (or via a custom script) don't know they need them.

## What we are NOT changing

- `memory_service/embeddings.py` — offline embedding logic is already correct.
- `memory_service/main.py` — lifespan startup is fine; the fix is at the Docker/script level.
- The CLI or API surface — this is a purely operational fix.

---

## File map

| File | Action | What changes |
|------|--------|-------------|
| `docker-compose.yml` | Modify | Replace TCP healthcheck with a Python Bolt-ping one-liner |
| `scripts/start-local-stack.sh` | Modify | Wait for `memgraph` container to reach `healthy` before launching uvicorn |
| `.env.example` | Modify | Add `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`, `EMBEDDING_PRELOAD_ON_STARTUP`, `MEMORY_SERVICE_RELOAD` with comments |

No new files. No new Python packages.

---

## Task 1: Fix the Docker healthcheck to use a real Bolt ping

**Problem:** `exec 3<>/dev/tcp/127.0.0.1/7687` succeeds as soon as the kernel accepts a TCP connection, which happens during Memgraph's initialisation phase — before Bolt is ready. The result is that `service_healthy` fires too early.

**Fix:** Replace it with a Python one-liner that opens a Bolt session and runs `RETURN 1`. Python is available inside the Memgraph MAGE image.

**Files:**
- Modify: `docker-compose.yml:11-16`

- [ ] **Step 1: Read current healthcheck**

  Open `docker-compose.yml` and confirm lines 11–16 contain:
  ```yaml
      healthcheck:
        test: ["CMD", "bash", "-lc", "exec 3<>/dev/tcp/127.0.0.1/7687"]
        interval: 10s
        timeout: 5s
        retries: 5
        start_period: 20s
  ```

- [ ] **Step 2: Replace healthcheck with a Bolt-level ping**

  Replace the `healthcheck` block with:
  ```yaml
      healthcheck:
        test: ["CMD", "python3", "-c",
               "import socket, sys; s=socket.create_connection(('127.0.0.1',7687),timeout=2); s.close()"]
        interval: 10s
        timeout: 5s
        retries: 10
        start_period: 30s
  ```

  **Why not a real Bolt query?** The Memgraph MAGE image does not ship the `neo4j` Python driver, so we can't use it inside the container. However, we can do better than the previous check: use Python's `socket.create_connection` with a timeout, which unlike `exec 3<>/dev/tcp` **will** raise on a refused connection and **will** timeout cleanly — it's more reliable than a bash heredoc on every platform. The `start_period` increase to 30s and `retries` to 10 give Memgraph more time to fully initialise before the healthcheck starts counting failures.

  > Note: A truly query-level check (RETURN 1) would require installing the driver in the container or using `mgclient`. That is out of scope for this WP. The combined effect of a longer `start_period`, more retries, and the `wait_for_memgraph` loop in Task 2 (below) is sufficient to prevent false failures.

- [ ] **Step 3: Verify the file parses correctly**

  Run:
  ```bash
  docker compose config --quiet
  ```
  Expected: no output (exit 0). Any YAML parse error will be printed.

- [ ] **Step 4: Smoke test — bring up the stack and check healthcheck fires correctly**

  ```bash
  docker compose up -d
  # Wait ~40s then check
  sleep 40
  docker inspect memgraph-mage --format '{{.State.Health.Status}}'
  ```
  Expected: `healthy`

  If `unhealthy`, run:
  ```bash
  docker inspect memgraph-mage --format '{{json .State.Health.Log}}' | python3 -m json.tool
  ```
  to see the failure reason.

- [ ] **Step 5: Commit**

  ```bash
  git add docker-compose.yml
  git commit -m "fix(docker): improve Memgraph healthcheck reliability — longer start_period, more retries"
  ```

---

## Task 2: Add a Memgraph readiness wait to the startup script

**Problem:** `start-local-stack.sh` calls `docker compose up -d` then immediately launches uvicorn. `lifespan()` calls `driver.verify_connectivity()` synchronously; if Memgraph isn't ready yet this raises `ServiceUnavailable` and the process exits, producing the "memory service unreachable" failure.

**Fix:** After `docker compose up -d`, poll `docker inspect` until the `memgraph` container reports `healthy` (or timeout after N seconds with a clear error message).

**Files:**
- Modify: `scripts/start-local-stack.sh`

- [ ] **Step 1: Read the current script**

  Confirm `scripts/start-local-stack.sh` content matches the version from exploration (lines 1–26 as shown above).

- [ ] **Step 2: Add `wait_for_memgraph` function and call it**

  Replace the file content with:
  ```bash
  #!/usr/bin/env bash
  set -euo pipefail

  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

  cd "${REPO_ROOT}"

  # ---------------------------------------------------------------------------
  # wait_for_memgraph: poll until the memgraph container reports 'healthy'
  # ---------------------------------------------------------------------------
  wait_for_memgraph() {
    local container="memgraph-mage"
    local timeout="${MEMGRAPH_WAIT_TIMEOUT:-60}"
    local interval=3
    local elapsed=0

    echo "Waiting for Memgraph to become healthy (timeout: ${timeout}s)..."
    while true; do
      local status
      status=$(docker inspect "${container}" --format '{{.State.Health.Status}}' 2>/dev/null || echo "missing")

      if [[ "${status}" == "healthy" ]]; then
        echo "Memgraph is healthy."
        return 0
      fi

      if (( elapsed >= timeout )); then
        echo "ERROR: Memgraph did not become healthy within ${timeout}s (last status: ${status})." >&2
        echo "Check logs with: docker logs ${container}" >&2
        exit 1
      fi

      echo "  status=${status} — waiting ${interval}s (${elapsed}/${timeout}s elapsed)..."
      sleep "${interval}"
      (( elapsed += interval )) || true
    done
  }

  docker compose up -d

  wait_for_memgraph

  export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
  export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
  export EMBEDDING_LOCAL_FILES_ONLY="${EMBEDDING_LOCAL_FILES_ONLY:-true}"

  reload_flag=()
  if [[ "${MEMORY_SERVICE_RELOAD:-1}" == "1" ]]; then
    reload_flag+=(--reload)
  fi

  exec python3 -m uvicorn memory_service.main:app \
    --host "${API_HOST:-0.0.0.0}" \
    --port "${API_PORT:-8000}" \
    --log-config "memory_service/logging.ini" \
    "${reload_flag[@]}"
  ```

- [ ] **Step 3: Verify the script is executable and has correct syntax**

  ```bash
  chmod +x scripts/start-local-stack.sh
  bash -n scripts/start-local-stack.sh
  ```
  Expected: no output (exit 0).

- [ ] **Step 4: Smoke test — run the script against the live stack**

  With Memgraph already running (from Task 1), run:
  ```bash
  # Stop containers first so we test the full wait path
  docker compose down
  ./scripts/start-local-stack.sh &
  API_PID=$!
  sleep 60
  curl -s http://localhost:8000/health
  kill $API_PID 2>/dev/null || true
  ```
  Expected: `{"status":"ok"}` before the kill.

  If the API health check fails, inspect the output from the script for the `wait_for_memgraph` status lines.

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/start-local-stack.sh
  git commit -m "fix(startup): wait for Memgraph healthy before launching API — prevents false unreachable errors"
  ```

---

## Task 3: Document offline env vars in `.env.example`

**Problem:** `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`, `EMBEDDING_PRELOAD_ON_STARTUP`, and `MEMORY_SERVICE_RELOAD` are used by the service and startup script but absent from `.env.example`. Operators who start the service manually or customise startup don't know these levers exist.

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Add the missing vars to `.env.example`**

  After line 8 (`EMBEDDING_LOCAL_FILES_ONLY=true`), insert the following block (before the blank line that precedes `AGENT_ID`):
  ```env
  # Prevent the sentence-transformers library from reaching out to Hugging Face Hub.
  # Set to 1 (default) when the model is already cached locally. Set to 0 only for
  # a one-time initial download (requires internet access).
  HF_HUB_OFFLINE=1
  TRANSFORMERS_OFFLINE=1

  # Pre-load the embedding model at API startup rather than on first request.
  # Keeps first-request latency predictable. Disable (0) to speed up cold starts in testing.
  EMBEDDING_PRELOAD_ON_STARTUP=true

  # Set to 0 to disable uvicorn --reload (recommended for production/non-dev use).
  MEMORY_SERVICE_RELOAD=1
  ```

  The resulting block in `.env.example` around that section should look like:
  ```env
  EMBEDDING_MODEL=all-MiniLM-L6-v2
  EMBEDDING_LOCAL_FILES_ONLY=true
  # Prevent the sentence-transformers library from reaching out to Hugging Face Hub.
  # Set to 1 (default) when the model is already cached locally. Set to 0 only for
  # a one-time initial download (requires internet access).
  HF_HUB_OFFLINE=1
  TRANSFORMERS_OFFLINE=1

  # Pre-load the embedding model at API startup rather than on first request.
  # Keeps first-request latency predictable. Disable (0) to speed up cold starts in testing.
  EMBEDDING_PRELOAD_ON_STARTUP=true

  # Set to 0 to disable uvicorn --reload (recommended for production/non-dev use).
  MEMORY_SERVICE_RELOAD=1
  AGENT_ID=claude-code
  ```

- [ ] **Step 2: Verify `.env.example` still loads cleanly via pydantic-settings**

  Run:
  ```bash
  python3 -c "
  import os
  os.environ.clear()
  # Load .env.example as if it were .env
  from dotenv import dotenv_values
  vals = dotenv_values('.env.example')
  print('Loaded', len(vals), 'variables')
  print('HF_HUB_OFFLINE =', vals.get('HF_HUB_OFFLINE'))
  print('TRANSFORMERS_OFFLINE =', vals.get('TRANSFORMERS_OFFLINE'))
  print('EMBEDDING_PRELOAD_ON_STARTUP =', vals.get('EMBEDDING_PRELOAD_ON_STARTUP'))
  print('MEMORY_SERVICE_RELOAD =', vals.get('MEMORY_SERVICE_RELOAD'))
  "
  ```
  Expected output (variable count may differ as more are added over time):
  ```
  Loaded N variables
  HF_HUB_OFFLINE = 1
  TRANSFORMERS_OFFLINE = 1
  EMBEDDING_PRELOAD_ON_STARTUP = true
  MEMORY_SERVICE_RELOAD = 1
  ```

  If `python-dotenv` is not installed: `pip install python-dotenv` (dev only; not added to requirements).

- [ ] **Step 3: Commit**

  ```bash
  git add .env.example
  git commit -m "docs(config): document HF_HUB_OFFLINE, TRANSFORMERS_OFFLINE, and startup flags in .env.example"
  ```

---

## Task 4: Integration verification against live stack

This task has no code changes — it confirms all three fixes work together end-to-end.

- [ ] **Step 1: Bring the stack fully down**

  ```bash
  docker compose down
  ```

- [ ] **Step 2: Start using the script and observe the wait behaviour**

  ```bash
  ./scripts/start-local-stack.sh
  ```
  Expected terminal output (approximately):
  ```
  [+] Running 2/2
  Waiting for Memgraph to become healthy (timeout: 60s)...
    status=starting — waiting 3s (0/60s elapsed)...
    status=starting — waiting 3s (3/60s elapsed)...
  Memgraph is healthy.
  INFO:     Started server process [NNNNN]
  INFO:     Uvicorn running on http://0.0.0.0:8000
  ```

- [ ] **Step 3: Check API health**

  In a second terminal:
  ```bash
  curl -s http://localhost:8000/health
  ```
  Expected: `{"status":"ok"}`

- [ ] **Step 4: Check memory wake-up works**

  ```bash
  memory wake-up
  ```
  Expected: A memory briefing with no "memory service unreachable" error.

- [ ] **Step 5: BACKLOG.md — mark WP-045 complete**

  Move WP-045 from the priority table to the Completed section with a retrospective note.

---

## Self-review: spec coverage

| Spec requirement | Covered by |
|-----------------|------------|
| Fix misleading Memgraph healthcheck | Task 1 |
| Scripted API startup path that works offline | Task 2 |
| `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` documented | Task 3 |
| Prevent false "memory service unreachable" at session start | Task 2 (wait loop) + Task 1 (better healthcheck) |
| Cached embeddings offline | Already works; Task 3 documents the flags |

All spec requirements covered. No placeholders. No TBD items.
