#!/usr/bin/env bash
# Hotpot Tech Feed — one-shot bootstrap + run.
#
# Target: Ubuntu 22.04+ (also works on Debian / other modern Linux).
# Idempotent: re-running is safe. It will:
#   1. Check Python 3.11+ / Node 20+ / Docker are installed
#   2. Copy .env.example → .env if missing
#   3. Bring up Postgres + Redis + Qdrant via docker compose
#   4. Set up the backend Python venv, install deps, migrate, seed
#   5. Pull the first batch of items (skipped if OPENAI_API_KEY is placeholder)
#   6. Install the frontend npm deps
#   7. Start uvicorn (:8000) and the Vite dev server (:5173) in the background
#   8. Tail logs, wait for Ctrl+C to stop everything
#
# Run from the repo root:  bash start.sh
#                          (or: chmod +x start.sh && ./start.sh)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# ---------- pretty output ----------
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[0;34m'; X='\033[0m'
log()  { printf "${G}▶${X} %s\n" "$*"; }
warn() { printf "${Y}!${X} %s\n" "$*"; }
err()  { printf "${R}✗${X} %s\n" "$*" >&2; }
hr()   { printf "${B}%s${X}\n" "──────────────────────────────────────────────"; }

# ---------- prerequisites ----------
hr
log "Checking prerequisites"
command -v python3 >/dev/null || { err "python3 not found — apt install python3.11 python3.11-venv"; exit 1; }
command -v node    >/dev/null || { err "node not found — install Node 20+ (https://github.com/nodesource/distributions)"; exit 1; }
command -v docker  >/dev/null || { err "docker not found — apt install docker.io docker-compose-v2  (or follow Docker's official Ubuntu guide)"; exit 1; }
docker info >/dev/null 2>&1   || { err "docker is installed but not running / no permission — try:  sudo systemctl start docker  &  sudo usermod -aG docker \$USER  then re-login"; exit 1; }

PYV=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
PYMAJ=$(python3 -c 'import sys; print(sys.version_info[0])')
PYMIN=$(python3 -c 'import sys; print(sys.version_info[1])')
if [ "$PYMAJ" -lt 3 ] || { [ "$PYMAJ" -eq 3 ] && [ "$PYMIN" -lt 11 ]; }; then
    err "python3 is $PYV — need 3.11+. On Ubuntu 22.04 try: sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.11 python3.11-venv"
    exit 1
fi
log "python3: $PYV   node: $(node --version)   docker: $(docker --version | awk '{print $3}' | sed 's/,$//')"

# ---------- .env ----------
if [ ! -f .env ]; then
    cp .env.example .env
    warn ".env created from .env.example — edit it to set OPENAI_API_KEY and SMTP_PASSWORD"
else
    log ".env already exists"
fi

# ---------- docker compose ----------
hr
log "Starting Postgres + Redis + Qdrant"
docker compose up -d
printf "  Waiting for Postgres "
for i in $(seq 1 60); do
    if docker compose exec -T postgres pg_isready -U hotpot >/dev/null 2>&1; then
        printf " ${G}ready${X}\n"; break
    fi
    printf "."; sleep 1
    if [ "$i" -eq 60 ]; then printf " ${R}timeout${X}\n"; err "Postgres didn't come up"; exit 1; fi
done

# ---------- backend setup ----------
hr
log "Setting up backend"
cd "$ROOT/backend"
if [ ! -d .venv ]; then
    log "Creating Python venv (.venv)"
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -e .

log "Running database migrations"
alembic upgrade head

log "Seeding sources"
hotpot seed-sources --file data/seed_sources.yaml >/dev/null

# ---------- ingest (skip cleanly if LLM key not set) ----------
if grep -qE '^OPENAI_API_KEY=(re_)?(replace_me|placeholder|sk-placeholder)' "$ROOT/.env" || \
   ! grep -q '^OPENAI_API_KEY=' "$ROOT/.env"; then
    warn "OPENAI_API_KEY is still a placeholder — skipping initial ingest."
    warn "Items will appear once you set a real key and run: hotpot ingest-now"
else
    log "Running first ingest (1–3 min for the seed list)"
    hotpot ingest-now || warn "Ingest had errors — items may be partial."
fi

# ---------- frontend deps ----------
hr
log "Installing frontend npm packages"
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
    npm install --silent --no-audit --no-fund
else
    log "node_modules already present (use 'rm -rf frontend/node_modules' to force reinstall)"
fi

# ---------- start both servers ----------
hr
log "Starting backend (uvicorn :8000) and frontend (vite :5173)"

mkdir -p "$ROOT/.run"
BACKEND_LOG="$ROOT/.run/backend.log"
FRONTEND_LOG="$ROOT/.run/frontend.log"
: > "$BACKEND_LOG"
: > "$FRONTEND_LOG"

cd "$ROOT/backend"
# shellcheck disable=SC1091
source .venv/bin/activate
nohup uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info \
    > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

cd "$ROOT/frontend"
nohup npm run dev -- --host 127.0.0.1 --port 5173 \
    > "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

cleanup() {
    printf "\n"
    log "Stopping servers (backend pid=$BACKEND_PID, frontend pid=$FRONTEND_PID)"
    kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
    log "Stopped. Postgres / Redis / Qdrant still running — stop with: docker compose down"
    exit 0
}
trap cleanup INT TERM

# Wait for backend to answer /healthz
printf "  Waiting for backend "
for i in $(seq 1 60); do
    if curl -fs http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
        printf " ${G}up${X}\n"; break
    fi
    printf "."; sleep 1
    if [ "$i" -eq 60 ]; then
        printf " ${R}timeout${X}\n"
        err "Backend didn't become healthy. See $BACKEND_LOG"
        cleanup
    fi
done

# Wait for frontend
printf "  Waiting for frontend "
for i in $(seq 1 60); do
    if curl -fs http://127.0.0.1:5173 >/dev/null 2>&1; then
        printf " ${G}up${X}\n"; break
    fi
    printf "."; sleep 1
    if [ "$i" -eq 60 ]; then
        printf " ${R}timeout${X}\n"
        err "Frontend didn't become healthy. See $FRONTEND_LOG"
        cleanup
    fi
done

# ---------- summary ----------
hr
cat <<EOF

  ${G}Hotpot Tech Feed is running.${X}

  ${B}Open in browser →${X}  http://127.0.0.1:5173
  API docs           →  http://127.0.0.1:8000/docs
  Health check       →  http://127.0.0.1:8000/healthz

  Logs:
    backend:   tail -f .run/backend.log
    frontend:  tail -f .run/frontend.log

  Useful commands (in another terminal, with .venv activated):
    hotpot ingest-now              re-pull every source
    hotpot preview-digest          render today's digest to digest_preview.html
    hotpot send-test-digest --to=you@example.com   real SMTP send

  Press Ctrl+C to stop both servers.
EOF
hr

# Open browser if a desktop is available (no-op on headless servers)
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open http://127.0.0.1:5173 >/dev/null 2>&1 &
fi

# Block until either server exits or user hits Ctrl+C
wait "$BACKEND_PID" "$FRONTEND_PID"
