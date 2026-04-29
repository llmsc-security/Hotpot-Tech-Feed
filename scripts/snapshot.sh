#!/usr/bin/env bash
# scripts/snapshot.sh — create a portable snapshot of Hotpot data.
#
# Produces a single tar.gz containing:
#   - postgres.dump        custom-format pg_dump of items / sources / tags
#   - seed_sources.yaml    the source list at snapshot time
#   - manifest.json        timestamp, item count, version
#
# Qdrant embeddings are NOT included (Qdrant has no host port now). On the
# remote box, re-embed with:
#     EMBEDDINGS_ENABLED=true docker compose run --rm backend hotpot enrich-all --all
#
# Usage:  ./scripts/snapshot.sh
# Output: data/snapshots/hotpot-<TIMESTAMP>.tar.gz

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; X='\033[0m'
log()  { printf "${G}▶${X} %s\n" "$*"; }
warn() { printf "${Y}!${X} %s\n" "$*"; }
err()  { printf "${R}✗${X} %s\n" "$*" >&2; }

[ -f .env ] || { err ".env not found — run start.sh once first"; exit 1; }
# shellcheck disable=SC1091
set -a; source .env; set +a

# Confirm postgres is up
if ! docker compose ps postgres 2>/dev/null | grep -qE "Up|running|healthy"; then
    err "postgres container is not running — start the stack first: bash start.sh"
    exit 1
fi

TS=$(date -u +%Y%m%d-%H%M%SZ)
SNAP_NAME="hotpot-$TS"
WORK_DIR="$ROOT/data/snapshots/$SNAP_NAME"
TARBALL="$ROOT/data/snapshots/$SNAP_NAME.tar.gz"
mkdir -p "$WORK_DIR"

# ---------- Postgres ----------
log "Dumping Postgres ($POSTGRES_DB) via docker compose exec"
docker compose exec -T postgres \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -Z 9 \
    > "$WORK_DIR/postgres.dump"
PG_BYTES=$(stat -c%s "$WORK_DIR/postgres.dump" 2>/dev/null || stat -f%z "$WORK_DIR/postgres.dump")
log "  postgres.dump   $(numfmt --to=iec --suffix=B "$PG_BYTES" 2>/dev/null || echo "$PG_BYTES bytes")"

# ---------- Sources YAML + manifest ----------
cp backend/data/seed_sources.yaml "$WORK_DIR/seed_sources.yaml"

ITEM_COUNT=$(docker compose exec -T postgres \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT COUNT(*) FROM items;" 2>/dev/null | tr -d '[:space:]' || echo "0")
SOURCE_COUNT=$(docker compose exec -T postgres \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT COUNT(*) FROM sources;" 2>/dev/null | tr -d '[:space:]' || echo "0")

cat > "$WORK_DIR/manifest.json" <<JSON
{
  "snapshot_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "version": "0.1.0",
  "host": "$(hostname)",
  "items": ${ITEM_COUNT:-0},
  "sources": ${SOURCE_COUNT:-0},
  "qdrant_included": false,
  "note": "Re-embed on restore: hotpot enrich-all --all (with EMBEDDINGS_ENABLED=true)"
}
JSON

# ---------- Tarball ----------
log "Packaging tarball"
tar -czf "$TARBALL" -C "$ROOT/data/snapshots" "$SNAP_NAME"
rm -rf "$WORK_DIR"

TBYTES=$(stat -c%s "$TARBALL" 2>/dev/null || stat -f%z "$TARBALL")
log "Snapshot ready"
echo
echo "  $TARBALL"
echo "  size:    $(numfmt --to=iec --suffix=B "$TBYTES" 2>/dev/null || echo "$TBYTES bytes")"
echo "  items:   $ITEM_COUNT"
echo "  sources: $SOURCE_COUNT"
echo
echo "Transfer to the remote box:"
echo "  scp $TARBALL  user@workstation:~/Hotpot-Tech-Feed/data/snapshots/"
echo "Then on the remote box:"
echo "  ./scripts/restore.sh  data/snapshots/$SNAP_NAME.tar.gz"
