#!/usr/bin/env bash
# scripts/snapshot.sh — create a portable snapshot of Hotpot data.
#
# Produces a single tar.gz containing:
#   - postgres.dump        custom-format pg_dump of the items/sources DB
#   - qdrant/<col>.snap    optional Qdrant collection snapshot
#   - seed_sources.yaml    the source list at snapshot time
#   - manifest.json        timestamp, item count, version
#
# Usage:  ./scripts/snapshot.sh [--no-qdrant]
#
# The output goes to data/snapshots/hotpot-<TIMESTAMP>.tar.gz at the repo root.
# Transfer it to the workstation with scp / rsync and run scripts/restore.sh.

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

INCLUDE_QDRANT=true
for arg in "$@"; do
    case "$arg" in
        --no-qdrant) INCLUDE_QDRANT=false ;;
        *) err "unknown arg: $arg"; exit 1 ;;
    esac
done

TS=$(date -u +%Y%m%d-%H%M%SZ)
SNAP_NAME="hotpot-$TS"
WORK_DIR="$ROOT/data/snapshots/$SNAP_NAME"
TARBALL="$ROOT/data/snapshots/$SNAP_NAME.tar.gz"
mkdir -p "$WORK_DIR"

# ---------- Postgres ----------
log "Dumping Postgres ($POSTGRES_DB)"
docker compose exec -T postgres \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -Z 9 \
    > "$WORK_DIR/postgres.dump"
PG_BYTES=$(stat -c%s "$WORK_DIR/postgres.dump" 2>/dev/null || stat -f%z "$WORK_DIR/postgres.dump")
log "  postgres.dump  $(numfmt --to=iec --suffix=B "$PG_BYTES" 2>/dev/null || echo "$PG_BYTES bytes")"

# ---------- Qdrant ----------
if [ "$INCLUDE_QDRANT" = "true" ]; then
    if curl -fs "$QDRANT_URL/collections/$QDRANT_COLLECTION" >/dev/null 2>&1; then
        log "Snapshotting Qdrant collection $QDRANT_COLLECTION"
        mkdir -p "$WORK_DIR/qdrant"
        QSNAP=$(curl -s -X POST "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots" \
            | python3 -c "import sys, json; print(json.load(sys.stdin)['result']['name'])" 2>/dev/null || true)
        if [ -n "${QSNAP:-}" ]; then
            curl -fs "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/$QSNAP" \
                -o "$WORK_DIR/qdrant/$QDRANT_COLLECTION.snapshot"
            QBYTES=$(stat -c%s "$WORK_DIR/qdrant/$QDRANT_COLLECTION.snapshot" 2>/dev/null || stat -f%z "$WORK_DIR/qdrant/$QDRANT_COLLECTION.snapshot")
            log "  qdrant snapshot  $(numfmt --to=iec --suffix=B "$QBYTES" 2>/dev/null || echo "$QBYTES bytes")"
        else
            warn "Qdrant snapshot failed — continuing without embeddings (re-embed on the remote with: hotpot enrich-all --all)"
        fi
    else
        warn "Qdrant not reachable at $QDRANT_URL — skipping (use --no-qdrant to silence)"
    fi
fi

# ---------- Sources YAML + manifest ----------
cp backend/data/seed_sources.yaml "$WORK_DIR/seed_sources.yaml"

ITEM_COUNT=$(docker compose exec -T postgres \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT COUNT(*) FROM items;" 2>/dev/null | tr -d '[:space:]' || echo "?")
SOURCE_COUNT=$(docker compose exec -T postgres \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT COUNT(*) FROM sources;" 2>/dev/null | tr -d '[:space:]' || echo "?")

cat > "$WORK_DIR/manifest.json" <<JSON
{
  "snapshot_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "version": "0.1.0",
  "host": "$(hostname)",
  "qdrant_collection": "$QDRANT_COLLECTION",
  "qdrant_included": $INCLUDE_QDRANT,
  "items": ${ITEM_COUNT:-0},
  "sources": ${SOURCE_COUNT:-0}
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
echo "Transfer it to the workstation:"
echo "  scp $TARBALL  user@workstation:~/feed_hotpot_tech/data/snapshots/"
echo "Then on the workstation:"
echo "  ./scripts/restore.sh  data/snapshots/$SNAP_NAME.tar.gz"
