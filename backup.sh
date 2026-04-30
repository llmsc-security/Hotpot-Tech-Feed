#!/usr/bin/env bash
# Hotpot Tech Feed — back up all user data to a single portable archive.
#
# Snapshots:
#   * Postgres (items, sources, tags, contributions, source health)
#       — logical pg_dump in custom format (version-tolerant, compressed)
#   * Qdrant   (embeddings, optional — only if EMBEDDINGS_ENABLED=true)
#       — raw volume tarball
#
# The archive is portable across machines as long as the new host runs the
# same docker-compose stack (Postgres 16, Qdrant 1.9). See restore.sh.
#
# Usage:   bash backup.sh [output_dir]
# Default: ./backups/hotpot-YYYYMMDD-HHMMSS.tar.gz

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

OUT_DIR="${1:-$ROOT/backups}"
mkdir -p "$OUT_DIR"

TS="$(date -u +%Y%m%d-%H%M%SZ)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; X='\033[0m'
log()  { printf "${G}▶${X} %s\n" "$*"; }
warn() { printf "${Y}!${X} %s\n" "$*"; }
err()  { printf "${R}✗${X} %s\n" "$*" >&2; }

# Read POSTGRES_USER / POSTGRES_DB from .env (fallback to defaults).
read_env() {
    { grep -E "^$1=" .env 2>/dev/null || true; } | tail -n 1 | cut -d= -f2- \
        | sed 's/^"\(.*\)"$/\1/' | sed "s/^'\(.*\)'$/\1/"
}
PGUSER="$(read_env POSTGRES_USER)"; PGUSER="${PGUSER:-hotpot}"
PGDB="$(read_env POSTGRES_DB)";     PGDB="${PGDB:-hotpot}"

if ! docker compose ps postgres --format '{{.State}}' 2>/dev/null | grep -q running; then
    err "hotpot-postgres is not running. Start the stack first: bash start.sh"
    exit 1
fi

log "Dumping Postgres (db=$PGDB user=$PGUSER) → postgres.dump"
docker compose exec -T postgres \
    pg_dump -U "$PGUSER" -d "$PGDB" -Fc --no-owner --no-acl \
    > "$WORK/postgres.dump"

# Qdrant: only worth grabbing if it actually has data.
if docker volume inspect hotpot-tech-feed_hotpot_qdrant >/dev/null 2>&1; then
    log "Snapshotting Qdrant volume → qdrant.tar.gz"
    docker run --rm \
        -v hotpot-tech-feed_hotpot_qdrant:/data:ro \
        -v "$WORK":/out \
        alpine:3.19 \
        sh -c "cd /data && tar -czf /out/qdrant.tar.gz ."
else
    warn "Qdrant volume not found — skipping (fine if EMBEDDINGS_ENABLED=false)."
fi

# Also stash a copy of .env so the new machine has the same secrets.
if [ -f .env ]; then
    cp .env "$WORK/env.backup"
fi

# Manifest with versions + tooling for restore-time sanity checks.
cat > "$WORK/manifest.json" <<EOF
{
  "created_at":      "$TS",
  "host":            "$(hostname)",
  "compose_project": "hotpot-tech-feed",
  "postgres_user":   "$PGUSER",
  "postgres_db":     "$PGDB",
  "tool_versions": {
    "docker":  "$(docker --version | awk '{print $3}' | sed 's/,$//')",
    "compose": "$(docker compose version --short)"
  }
}
EOF

ARCHIVE="$OUT_DIR/hotpot-$TS.tar.gz"
log "Packing archive → $ARCHIVE"
( cd "$WORK" && tar -czf "$ARCHIVE" . )

SIZE="$(du -h "$ARCHIVE" | cut -f1)"
log "Done. ${SIZE} archive at:"
echo "  $ARCHIVE"
echo
echo "To restore on another PC:"
echo "  1) clone the repo and copy this archive there"
echo "     (any folder name works — compose project name is locked to hotpot-tech-feed)"
echo "  2) bash start.sh        (creates an empty stack; uses local .env if present)"
echo "  3) bash restore.sh $(basename "$ARCHIVE")"
echo "     (also auto-recovers .env from the archive if you don't have one locally)"
