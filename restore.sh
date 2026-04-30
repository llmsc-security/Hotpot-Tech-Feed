#!/usr/bin/env bash
# Hotpot Tech Feed — restore from an archive produced by backup.sh.
#
# Replaces the contents of the running Postgres database (and optionally the
# Qdrant volume) with the snapshot. Existing data is wiped first — the
# archive is the source of truth. Source rows from data/seed_sources.yaml
# will be re-merged on the next start (idempotent).
#
# Usage:   bash restore.sh <archive.tar.gz>
# Example: bash restore.sh backups/hotpot-20260430-001500Z.tar.gz

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

ARCHIVE="${1:-}"
if [ -z "$ARCHIVE" ] || [ ! -f "$ARCHIVE" ]; then
    echo "Usage: bash restore.sh <archive.tar.gz>" >&2
    exit 2
fi
ARCHIVE="$(cd "$(dirname "$ARCHIVE")" && pwd)/$(basename "$ARCHIVE")"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; X='\033[0m'
log()  { printf "${G}▶${X} %s\n" "$*"; }
warn() { printf "${Y}!${X} %s\n" "$*"; }
err()  { printf "${R}✗${X} %s\n" "$*" >&2; }

read_env() {
    { grep -E "^$1=" .env 2>/dev/null || true; } | tail -n 1 | cut -d= -f2- \
        | sed 's/^"\(.*\)"$/\1/' | sed "s/^'\(.*\)'$/\1/"
}
PGUSER="$(read_env POSTGRES_USER)"; PGUSER="${PGUSER:-hotpot}"
PGDB="$(read_env POSTGRES_DB)";     PGDB="${PGDB:-hotpot}"

log "Unpacking $ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"

if [ -f "$WORK/manifest.json" ]; then
    log "Manifest:"
    sed 's/^/    /' "$WORK/manifest.json"
fi

if [ ! -f "$WORK/postgres.dump" ]; then
    err "Archive is missing postgres.dump — bad backup?"
    exit 1
fi

# Stack must be up; need backend stopped so it doesn't write while we restore,
# but postgres needs to be running.
if ! docker compose ps postgres --format '{{.State}}' 2>/dev/null | grep -q running; then
    err "hotpot-postgres is not running. Bring the stack up first: bash start.sh"
    exit 1
fi

log "Stopping backend + worker so they don't write during restore"
docker compose stop backend worker 2>/dev/null || true

log "Wiping current Postgres database"
docker compose exec -T postgres \
    psql -U "$PGUSER" -d postgres -v ON_ERROR_STOP=1 \
    -c "DROP DATABASE IF EXISTS \"$PGDB\";" \
    -c "CREATE DATABASE \"$PGDB\" OWNER \"$PGUSER\";"

log "Restoring Postgres dump (this may take a minute on large corpora)"
docker compose exec -T postgres \
    pg_restore -U "$PGUSER" -d "$PGDB" --no-owner --no-acl \
    < "$WORK/postgres.dump"

if [ -f "$WORK/qdrant.tar.gz" ]; then
    log "Restoring Qdrant volume from snapshot"
    docker compose stop qdrant 2>/dev/null || true
    docker run --rm \
        -v hotpot-tech-feed_hotpot_qdrant:/data \
        -v "$WORK":/in \
        alpine:3.19 \
        sh -c "rm -rf /data/* /data/..?* /data/.[!.]* 2>/dev/null; tar -xzf /in/qdrant.tar.gz -C /data"
    docker compose start qdrant
else
    warn "No qdrant.tar.gz in archive — skipping (only matters if EMBEDDINGS_ENABLED=true)."
fi

log "Restarting backend + worker"
docker compose start backend worker 2>/dev/null || docker compose start backend

# Wait for the backend to come back up before we report.
HOST_PORT="$(read_env HOST_PORT)"; HOST_PORT="${HOST_PORT:-8080}"
printf "  Waiting for gateway on :%s " "$HOST_PORT"
for i in $(seq 1 60); do
    if curl -fs "http://127.0.0.1:${HOST_PORT}/healthz" >/dev/null 2>&1; then
        printf " ${G}up${X}\n"; break
    fi
    printf "."; sleep 2
done

log "Restore complete. Stats from the live API:"
curl -fs "http://127.0.0.1:${HOST_PORT}/api/stats" 2>/dev/null || warn "could not reach /api/stats — check 'docker compose logs backend'"
echo
