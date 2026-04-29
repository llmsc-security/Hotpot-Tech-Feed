#!/usr/bin/env bash
# Hotpot Tech Feed — single-port deploy.
#
# Target: Ubuntu 22.04+ with Docker + Compose v2.
# Builds the gateway (frontend SPA + nginx) and backend images, brings up the
# full stack on an internal docker network, and exposes ONLY the gateway on
# the host at $HOST_PORT (default 8080).
#
# Idempotent: re-run any time. Pre-existing data volumes are preserved.
#
# Run:    bash start.sh
# Stop:   docker compose down

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[0;34m'; X='\033[0m'
log()  { printf "${G}▶${X} %s\n" "$*"; }
warn() { printf "${Y}!${X} %s\n" "$*"; }
err()  { printf "${R}✗${X} %s\n" "$*" >&2; }
hr()   { printf "${B}%s${X}\n" "──────────────────────────────────────────────"; }

# ---------- prerequisites ----------
hr
log "Checking prerequisites"
command -v docker >/dev/null || { err "docker not found — apt install docker.io docker-compose-v2"; exit 1; }
docker info >/dev/null 2>&1   || { err "docker installed but not running / no permission — try: sudo usermod -aG docker \$USER (then re-login)"; exit 1; }
if ! docker compose version >/dev/null 2>&1; then
    err "docker compose v2 not installed — apt install docker-compose-v2"
    exit 1
fi
log "docker: $(docker --version | awk '{print $3}' | sed 's/,$//')   compose: $(docker compose version --short)"

# ---------- .env ----------
if [ ! -f .env ]; then
    cp .env.example .env
    warn ".env created from .env.example — edit OPENAI_API_KEY, SMTP_PASSWORD, then re-run."
fi
# shellcheck disable=SC1091
set -a; source .env; set +a
HOST_PORT=${HOST_PORT:-8080}

# ---------- check host port not already taken ----------
if command -v ss >/dev/null && ss -ltn "( sport = :${HOST_PORT} )" 2>/dev/null | grep -q LISTEN; then
    err "Port ${HOST_PORT} is already in use on the host."
    err "Pick a free port and update HOST_PORT in .env, then re-run."
    exit 1
fi

# ---------- build + up ----------
hr
log "Building images (gateway + backend)"
docker compose build

log "Bringing up the stack"
docker compose up -d

# ---------- wait for gateway ----------
hr
printf "  Waiting for gateway on :%s " "$HOST_PORT"
for i in $(seq 1 60); do
    if curl -fs "http://127.0.0.1:${HOST_PORT}/healthz" >/dev/null 2>&1; then
        printf " ${G}up${X}\n"
        break
    fi
    printf "."; sleep 2
    if [ "$i" -eq 60 ]; then
        printf " ${R}timeout${X}\n"
        err "Gateway didn't become healthy. Check logs:"
        err "  docker compose logs gateway backend"
        exit 1
    fi
done

# ---------- summary ----------
hr
cat <<EOF

  ${G}Hotpot Tech Feed is running.${X}

  Open in browser →  ${B}http://127.0.0.1:${HOST_PORT}${X}
  API docs        →  http://127.0.0.1:${HOST_PORT}/docs
  Health          →  http://127.0.0.1:${HOST_PORT}/healthz

  Containers (internal network, no host ports):
    hotpot-postgres  hotpot-redis  hotpot-qdrant  hotpot-backend  hotpot-gateway

  CLI from inside the backend container:
    docker compose run --rm backend hotpot ingest-now
    docker compose run --rm backend hotpot ingest-deep --passes 5
    docker compose run --rm backend hotpot enrich-all --limit 2000
    docker compose run --rm backend hotpot send-test-digest --to you@example.com

  Logs:
    docker compose logs -f gateway backend

  Stop everything:
    docker compose down            # keeps data volumes
    docker compose down -v         # also wipes Postgres + Qdrant data
EOF
hr

if [ -z "${OPENAI_API_KEY:-}" ] || [ "$OPENAI_API_KEY" = "replace_me" ]; then
    warn "OPENAI_API_KEY is still a placeholder — items will ingest without summaries."
    warn "Set a real key in .env and:  docker compose run --rm backend hotpot enrich-all"
fi

if [ "${SMTP_PASSWORD:-re_replace_me}" = "re_replace_me" ]; then
    warn "SMTP_PASSWORD is still a placeholder — send-test-digest will fail until you set the Resend API key in .env."
fi
