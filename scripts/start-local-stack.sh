#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

# ---------------------------------------------------------------------------
# Pre-flight: port 8000 must be free before compose tries to bind it.
# If a bare uvicorn process is still running, the api service will fail.
# ---------------------------------------------------------------------------
if lsof -Pi :8000 -sTCP:LISTEN -t > /dev/null 2>&1; then
  echo "ERROR: Port 8000 is already in use." >&2
  echo "Kill the bare uvicorn process first: fuser -k 8000/tcp" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Pre-flight: HuggingFace model cache must exist.
# An empty or missing bind-mount causes a crash-loop with no clear error.
# ---------------------------------------------------------------------------
HF_CACHE_PATH="${HF_CACHE_DIR:-/home/oliver/.cache/huggingface}"
if [[ ! -d "${HF_CACHE_PATH}/hub" ]]; then
  echo "ERROR: HuggingFace model cache not found at ${HF_CACHE_PATH}/hub" >&2
  echo "Expected models: all-MiniLM-L6-v2, paraphrase-multilingual-MiniLM-L12-v2" >&2
  exit 1
fi

docker compose up -d

# ---------------------------------------------------------------------------
# wait_for_api: poll until the memory API returns 200 on /health.
# The compose dependency chain handles Memgraph → API ordering internally.
# Docker Desktop port forwarding may have a 2–5s lag after compose up;
# initial connection-refused responses are normal and handled by retries.
# ---------------------------------------------------------------------------
wait_for_api() {
  local url="http://localhost:8000/health"
  local timeout="${API_WAIT_TIMEOUT:-180}"
  local interval=5
  local elapsed=0

  echo "Waiting for API to become healthy (timeout: ${timeout}s)..."
  while true; do
    if curl -sf "${url}" > /dev/null 2>&1; then
      echo "API is healthy."
      return 0
    fi

    if (( elapsed >= timeout )); then
      echo "ERROR: API did not become healthy within ${timeout}s." >&2
      echo "Check logs with: docker logs memory-api" >&2
      return 1
    fi

    echo "  API not ready — waiting ${interval}s (${elapsed}/${timeout}s elapsed)..."
    sleep "${interval}"
    (( elapsed += interval )) || true
  done
}

wait_for_api
