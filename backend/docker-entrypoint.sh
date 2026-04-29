#!/bin/sh
# Backend container entrypoint:
#   1. Run pending Alembic migrations (idempotent).
#   2. Seed the source list from data/seed_sources.yaml (idempotent — updates by URL).
#   3. Hand off to uvicorn.
set -e

echo "▶ alembic upgrade head"
alembic upgrade head

echo "▶ hotpot seed-sources (idempotent)"
hotpot seed-sources --file data/seed_sources.yaml >/dev/null 2>&1 || true

echo "▶ uvicorn → 0.0.0.0:8000"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --proxy-headers \
    --forwarded-allow-ips='*'
