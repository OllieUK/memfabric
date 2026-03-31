#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

docker compose up -d

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
