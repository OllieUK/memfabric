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
      return 1
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
