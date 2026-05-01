#!/usr/bin/env bash
# Locked host-cron wrapper for Hotpot one-shot jobs.
#
# Usage from crontab:
#   /path/to/Hotpot-Tech-Feed/scripts/cron_hotpot.sh ingest-html
#
# Environment knobs:
#   WORKERS=4          per-item LLM workers for ingest jobs
#   SOURCE_WORKERS=1   source-level workers for ingest-now
#   SECURITY_LIMIT=5000       max items for score-security
#   SECURITY_RECENT_DAYS=120  recent window for score-security

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JOB="${1:-ingest-now}"
LOG_DIR="${LOG_DIR:-$ROOT/logs}"
WORKERS="${WORKERS:-4}"
SOURCE_WORKERS="${SOURCE_WORKERS:-1}"
SECURITY_LIMIT="${SECURITY_LIMIT:-5000}"
SECURITY_RECENT_DAYS="${SECURITY_RECENT_DAYS:-120}"

mkdir -p "$LOG_DIR"
cd "$ROOT"

INGEST_JOB=0
case "$JOB" in
    ingest-now|ingest-html|ingest-rss|ingest-arxiv|ingest-empty)
        INGEST_JOB=1
        ;;
esac

if [[ "$INGEST_JOB" == "1" ]]; then
    # Keep compatibility with older running wrappers that held ingest-now.lock.
    exec 8>"$LOG_DIR/ingest-now.lock"
    if ! flock -n 8; then
        printf '[%s] skipped %s: previous ingest run still active\n' "$(date -Is)" "$JOB"
        exit 0
    fi
    LOCK="$LOG_DIR/ingest.lock"
else
    LOCK="$LOG_DIR/${JOB}.lock"
fi

exec 9>"$LOCK"
if ! flock -n 9; then
    printf '[%s] skipped %s: previous run still active\n' "$(date -Is)" "$JOB"
    exit 0
fi

printf '[%s] start %s\n' "$(date -Is)" "$JOB"

case "$JOB" in
    ingest-now)
        docker compose run --rm backend hotpot ingest-now \
            --workers "$WORKERS" \
            --source-workers "$SOURCE_WORKERS"
        ;;
    ingest-html)
        docker compose run --rm backend hotpot ingest-kind html --workers "$WORKERS"
        ;;
    ingest-rss)
        docker compose run --rm backend hotpot ingest-kind rss --workers "$WORKERS"
        ;;
    ingest-arxiv)
        docker compose run --rm backend hotpot ingest-kind arxiv --workers "$WORKERS"
        ;;
    ingest-empty)
        docker compose run --rm backend hotpot ingest-empty
        ;;
    health-check-sources)
        docker compose run --rm backend hotpot health-check-sources
        ;;
    score-sources)
        docker compose run --rm backend hotpot score-sources
        ;;
    score-security)
        docker compose run --rm backend hotpot score-security \
            --limit "$SECURITY_LIMIT" \
            --recent-days "$SECURITY_RECENT_DAYS"
        ;;
    backup)
        bash backup.sh
        ;;
    *)
        printf 'unknown cron_hotpot job: %s\n' "$JOB" >&2
        exit 2
        ;;
esac

printf '[%s] done %s\n' "$(date -Is)" "$JOB"
