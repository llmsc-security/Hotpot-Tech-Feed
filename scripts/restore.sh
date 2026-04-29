#!/usr/bin/env bash
# scripts/restore.sh — apply a Hotpot snapshot on a fresh Ubuntu deploy.
#
# Usage:  ./scripts/restore.sh data/snapshots/hotpot-<TS>.tar.gz
#
# Idempotent in the sense that re-running with the same snapshot produces the
# same end state, but DESTRUCTIVE: it drops the existing database and recreates
# it from the dump. There's a 5-second confirmation prompt before the drop.
#
# Prerequisites on the target box:
#   - Repo cloned, .env populated
#   - docker compose up -d  (Postgres + Redis + Qdrant running)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; X='\033[0m'
log()  { printf "${G}▶${X} %s\n" "$*"; }
warn() { printf "${Y}!${X} %s\n" "$*"; }
err()  { printf "${R}✗${X} %s\n" "$*" >&2; }

[ "$#" -ge 1 ] || { err "usage: $0 <snapshot.tar.gz>"; exit 1; }
TAR="$1"
[ -f "$TAR" ] || { err "snapshot not found: $TAR"; exit 1; }

[ -f .env ] || { err ".env not found — cp .env.example .env and edit secrets first"; exit 1; }
# shellcheck disable=SC1091
set -a; source .env; set +a

# Verify docker-compose stack is up
if ! docker compose ps postgres 2>/dev/null | grep -qE "Up|running|healthy"; then
    err "Postgres container is not running"
    err "Start the stack first:  docker compose up -d"
    exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

log "Extracting $TAR"
tar -xzf "$TAR" -C "$WORK"
SNAP_DIR=$(find "$WORK" -maxdepth 1 -mindepth 1 -type d | head -n 1)
[ -d "$SNAP_DIR" ] || { err "tarball didn't contain a snapshot directory"; exit 1; }

# Show manifest if present
if [ -f "$SNAP_DIR/manifest.json" ]; then
    log "Snapshot manifest:"
    sed 's/^/    /' "$SNAP_DIR/manifest.json"
fi

# Confirm before destructive restore
warn "This will DROP and recreate database '$POSTGRES_DB' on $(hostname)."
warn "Press Ctrl+C within 5 seconds to abort…"
sleep 5

# ---------- Postgres restore ----------
log "Recreating database $POSTGRES_DB"
docker compose exec -T postgres dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"
docker compose exec -T postgres createdb -U "$POSTGRES_USER" "$POSTGRES_DB"

log "Loading dump"
docker compose exec -T postgres \
    pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl --clean --if-exists \
    < "$SNAP_DIR/postgres.dump" 2>&1 | grep -vE '^(pg_restore: warning|pg_restore: dropping|pg_restore: creating)' || true

# Show what got restored
ITEMS=$(docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT COUNT(*) FROM items;" 2>/dev/null | tr -d '[:space:]' || echo "?")
SOURCES=$(docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT COUNT(*) FROM sources;" 2>/dev/null | tr -d '[:space:]' || echo "?")
log "Postgres restored — $ITEMS items, $SOURCES sources"

# ---------- Qdrant restore (optional) ----------
if [ -d "$SNAP_DIR/qdrant" ]; then
    SNAP_FILE=$(find "$SNAP_DIR/qdrant" -maxdepth 1 -type f | head -n 1)
    if [ -n "${SNAP_FILE:-}" ]; then
        log "Uploading Qdrant snapshot $(basename "$SNAP_FILE")"
        if curl -fs -X POST \
            "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/upload?priority=snapshot" \
            -F "snapshot=@$SNAP_FILE" >/dev/null; then
            log "Qdrant snapshot recovered"
        else
            warn "Qdrant upload failed — falling back to re-embed"
            warn "Run on this host:  EMBEDDINGS_ENABLED=true hotpot enrich-all --all"
        fi
    fi
else
    warn "Snapshot has no Qdrant data — re-embed locally if you need similarity dedup:"
    warn "  EMBEDDINGS_ENABLED=true hotpot enrich-all --all"
fi

log "Restore complete"
echo
echo "Verify with:"
echo "  source backend/.venv/bin/activate"
echo "  hotpot list-sources | head -5"
echo "  curl -s http://127.0.0.1:8000/items?limit=3 | jq '.items[].title'"
