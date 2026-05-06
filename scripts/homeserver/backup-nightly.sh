#!/usr/bin/env bash
# backup-nightly.sh — daily Memgraph backup for the homeserver memfabric stack.
#
# Two complementary outputs per run, written to BACKUP_DIR:
#   dump_YYYY-MM-DD.json       — logical export via scripts/dump_db.py (Memory
#                                nodes + 15 edge types). Portable across
#                                Memgraph versions; restorable via
#                                scripts/restore_db.py after seed_strands.py.
#   volume_YYYY-MM-DD.tar.gz   — full tar of the memgraph_lib docker volume.
#                                Captures everything (Strand, Agent, Person,
#                                Project, Task, knowledge-layer nodes,
#                                indexes). Memgraph-version-tied; intended
#                                for in-place recovery.
#
# Files older than RETENTION_DAYS are pruned at the end of each run.
#
# Invoked by user cron at 02:30 UTC (just before Memgraph long-rest).
# Runs as oliver in the docker group; uses dcumf to route through the
# canonical compose project. Failures exit non-zero so cron mail or log
# scrapers see them.
#
# Install (manual, for now):
#   1. Copy this script to homeserver (or rely on the git checkout at
#      /opt/stacks/sources/graph-memory-fabric/scripts/homeserver/).
#   2. Ensure /opt/stacks/backups/memfabric/ exists, owned by the invoking
#      user, mode 0750.
#   3. Add a user crontab entry:
#        30 2 * * * /opt/stacks/sources/graph-memory-fabric/scripts/homeserver/backup-nightly.sh >> /opt/stacks/backups/memfabric/backup.log 2>&1
#
# Future hardening lives in WP-166 (off-host replication, restore-test
# discipline, dedicated stack-user, etc.).

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/stacks/backups/memfabric}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-memfabric}"
API_SERVICE="${API_SERVICE:-memfabric-api}"
VOLUME_NAME="${VOLUME_NAME:-${COMPOSE_PROJECT}_memgraph_lib}"

DATE_STAMP="$(date -u +%Y-%m-%d)"
JSON_OUT="$BACKUP_DIR/dump_${DATE_STAMP}.json"
TAR_OUT="$BACKUP_DIR/volume_${DATE_STAMP}.tar.gz"
LOCK_FILE="$BACKUP_DIR/.backup.lock"

mkdir -p "$BACKUP_DIR"

# Single-instance guard so two cron firings never overlap.
exec 9> "$LOCK_FILE"
if ! flock -n 9; then
    echo "[$(date -uIs)] another backup-nightly.sh is running; exiting" >&2
    exit 0
fi

echo "[$(date -uIs)] backup-nightly start (date=$DATE_STAMP)"

# 1. Logical export via dump_db.py running inside the api container.
#    The api container already has the venv and the right MEMGRAPH_HOST.
#    Mount BACKUP_DIR into the container and write the JSON there.
docker compose -p "$COMPOSE_PROJECT" exec -T \
    -e BACKUP_OUT="/backup/dump_${DATE_STAMP}.json" \
    "$API_SERVICE" \
    sh -c 'python3 /app/scripts/dump_db.py --output "$BACKUP_OUT"' \
    < /dev/null \
    > /dev/null 2>&1 || {
        # Fallback: dcumf exec without bind-mount. Run inside container,
        # then docker cp the file out.
        docker compose -p "$COMPOSE_PROJECT" exec -T "$API_SERVICE" \
            python3 /app/scripts/dump_db.py --output "/tmp/dump_${DATE_STAMP}.json"
        CONTAINER_ID=$(docker compose -p "$COMPOSE_PROJECT" ps -q "$API_SERVICE")
        docker cp "$CONTAINER_ID:/tmp/dump_${DATE_STAMP}.json" "$JSON_OUT"
        docker compose -p "$COMPOSE_PROJECT" exec -T "$API_SERVICE" \
            rm -f "/tmp/dump_${DATE_STAMP}.json"
    }

if [[ -f "$JSON_OUT" ]]; then
    JSON_SIZE=$(stat -c%s "$JSON_OUT" 2>/dev/null || stat -f%z "$JSON_OUT")
    echo "[$(date -uIs)] dump_db.py wrote $JSON_OUT ($JSON_SIZE bytes)"
else
    echo "[$(date -uIs)] WARNING: $JSON_OUT not produced" >&2
fi

# 2. Volume tarball. Hot copy of the live volume; Memgraph durability
#    (snapshot + WAL) makes this recoverable for emergency restore.
docker run --rm \
    -v "$VOLUME_NAME":/src:ro \
    -v "$BACKUP_DIR":/backup \
    alpine \
    tar czf "/backup/volume_${DATE_STAMP}.tar.gz" -C /src .

if [[ -f "$TAR_OUT" ]]; then
    TAR_SIZE=$(stat -c%s "$TAR_OUT" 2>/dev/null || stat -f%z "$TAR_OUT")
    echo "[$(date -uIs)] volume tar wrote $TAR_OUT ($TAR_SIZE bytes)"
else
    echo "[$(date -uIs)] WARNING: $TAR_OUT not produced" >&2
fi

# 3. Prune backups older than RETENTION_DAYS.
PRUNED=$(find "$BACKUP_DIR" \
    -maxdepth 1 \
    \( -name 'dump_*.json' -o -name 'volume_*.tar.gz' \) \
    -type f \
    -mtime "+$RETENTION_DAYS" \
    -print -delete 2>/dev/null | wc -l)
echo "[$(date -uIs)] pruned $PRUNED files older than $RETENTION_DAYS days"

echo "[$(date -uIs)] backup-nightly done"
