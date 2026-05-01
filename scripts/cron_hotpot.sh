#!/usr/bin/env bash
# Locked host-cron wrapper for Hotpot one-shot jobs.
#
# Usage from crontab:
#   /path/to/Hotpot-Tech-Feed/scripts/cron_hotpot.sh ingest-html
#
# Environment knobs:
#   WORKERS=4          per-item LLM workers for ingest jobs
#   SOURCE_WORKERS=1   source-level workers for ingest-now

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JOB="${1:-ingest-now}"
LOG_DIR="${LOG_DIR:-$ROOT/logs}"
WORKERS="${WORKERS:-4}"
SOURCE_WORKERS="${SOURCE_WORKERS:-1}"

mkdir -p "$LOG_DIR"
cd "$ROOT"

LOCK="$LOG_DIR/${JOB}.lock"
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
    backup)
        bash backup.sh
        ;;
    *)
        printf 'unknown cron_hotpot job: %s\n' "$JOB" >&2
        exit 2
        ;;
esac

printf '[%s] done %s\n' "$(date -Is)" "$JOB"
