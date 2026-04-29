# Hotpot Tech Feed

A daily CS digest service. See [`PLAN.md`](./PLAN.md) for the architecture
plan and [`plan_project.md`](./plan_project.md) for the end-user pitch.

This README covers Phase 1.0 — the runnable foundation: arXiv + RSS ingestion,
URL + title-fuzzy dedup, optional embedding dedup, Qwen-powered summaries,
FastAPI, and a minimal React browse view.

---

## What's in here

```
feed_hotpot_tech/
├── PLAN.md                        full architecture + roadmap
├── plan_project.md                end-user-facing project overview
├── Hotpot_Tech_Feed_Intro.pptx    introduction deck
├── docker-compose.yml             Postgres + Redis + Qdrant
├── .env.example                   copy to .env, fill in secrets
├── backend/                       FastAPI + Celery + SQLAlchemy
│   ├── app/                       application code
│   ├── alembic/                   DB migrations
│   └── data/seed_sources.yaml     initial source list
└── frontend/                      Vite + React + Tailwind browse view
```

---

## Prerequisites

Target OS: **Ubuntu 22.04+** (also works on Debian / other modern Linux).

- Python 3.11+ (`apt install python3.11 python3.11-venv`)
- Node 20+ (NodeSource: <https://github.com/nodesource/distributions>)
- Docker + Compose v2 (`apt install docker.io docker-compose-v2`; add yourself to the `docker` group)

---

## One-shot bootstrap

A single command does setup + run:

```bash
git clone https://github.com/llmsc-security/Hotpot-Tech-Feed.git
cd Hotpot-Tech-Feed
cp .env.example .env                     # edit OPENAI_API_KEY and SMTP_PASSWORD
bash start.sh
```

`start.sh` is idempotent — re-run it any time. It will:

1. Verify Python / Node / Docker
2. Bring up Postgres + Redis + Qdrant via `docker compose`
3. Create the Python venv, install deps, run migrations, seed sources
4. Pull a first batch of items (skipped if `OPENAI_API_KEY` is still placeholder)
5. Install frontend deps
6. Start `uvicorn` (:8000) and Vite (:5173) in the background
7. Tail logs at `.run/backend.log` and `.run/frontend.log`

When it prints "is running", open `http://127.0.0.1:5173`.

Press Ctrl+C to stop both servers. `docker compose down` to stop the database stack.

---

## Manual bring-up (if you want each step explicit)

```bash
cp .env.example .env                     # edit secrets
docker compose up -d                     # Postgres, Redis, Qdrant

cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
alembic upgrade head
hotpot seed-sources --file data/seed_sources.yaml
hotpot ingest-now                        # 1-3 min for the seed list
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173`.

---

## CLI reference

```bash
hotpot seed-sources [--file PATH]         # idempotent; updates existing sources
hotpot ingest-now                          # one full sync pass over every active source
hotpot ingest-source "arXiv cs.LG"         # pull a single source by name
hotpot ingest-deep [--passes 3 --sleep 30] # multiple passes for aggressive bootstrap
hotpot enrich-all [--limit 1000]           # backfill summaries on items that lack one
hotpot list-sources                        # print source rows + health
hotpot preview-digest [--out PATH]         # render digest HTML locally (no email)
hotpot send-test-digest --to EMAIL         # render and send today's digest end-to-end
```

---

## Migration: snapshot on box A, restore on box B

For "crawl on a build box, deploy the data to the workstation" or just for backups.

### On the source box (where the data lives)

```bash
./scripts/snapshot.sh
# → data/snapshots/hotpot-<TIMESTAMP>.tar.gz
```

The tarball contains:

- `postgres.dump` — custom-format `pg_dump` of every table (sources, items, tags)
- `qdrant/<collection>.snapshot` — Qdrant collection snapshot (skipped if Qdrant isn't reachable; pass `--no-qdrant` to skip explicitly)
- `seed_sources.yaml` — the source list at snapshot time
- `manifest.json` — timestamp, host, item / source counts

### Transfer

```bash
scp data/snapshots/hotpot-*.tar.gz user@workstation:~/Hotpot-Tech-Feed/data/snapshots/
```

### On the target box

```bash
git clone https://github.com/llmsc-security/Hotpot-Tech-Feed.git
cd Hotpot-Tech-Feed
cp .env.example .env                  # edit secrets
docker compose up -d                  # Postgres + Redis + Qdrant

./scripts/restore.sh data/snapshots/hotpot-<TIMESTAMP>.tar.gz
```

The restore script:

1. Drops and recreates the database (5-second confirmation prompt before the destructive step)
2. Loads the dump with `pg_restore`
3. Uploads the Qdrant snapshot (if present) via the recovery API
4. Prints item / source counts so you can verify

If the Qdrant snapshot isn't in the tarball or upload fails, you can re-embed locally instead — that's a simple `EMBEDDINGS_ENABLED=true hotpot enrich-all --all` once the L40s are configured.

Then bring the app up normally:

```bash
bash start.sh
```

---

## Pipeline

```
[ adapter.fetch() ]
       │
       ▼
[ canonicalize_url() ]              ── strips UTM, normalizes host, drops arxiv version
       │
       ▼
[ find_dedup_target() ]
       ├── stage 1: canonical URL match
       ├── stage 2: title fuzzy match (rapidfuzz, 7-day window)
       └── stage 3: embedding cosine (bge-m3 + Qdrant; opt-in)
       │
       ▼ (no match)
[ persist Item ]
       │
       ▼
[ enrich_item() ]
       ├── tag_item()      → Qwen, returns {topics, content_type, tags}
       ├── summarize()     → Qwen, 1–2 sentence neutral summary
       └── (commentary)    → off until prompts are tuned (set ENRICH_COMMENTARY=true)
```

---

## Email (Resend via send.ai2wj.com)

`ai2wj.com` is verified at Resend with `send.ai2wj.com` carrying the
SPF / DKIM / return-path records, so digests go out as `digest@ai2wj.com`
with proper alignment. To send:

1. Create an API key in the Resend dashboard.
2. Put it in `.env` as `SMTP_PASSWORD`.
3. Test:

   ```bash
   hotpot preview-digest --out /tmp/digest.html   # open this in a browser
   hotpot send-test-digest --to you@example.com   # fires real SMTP
   ```

If `send-test-digest` returns `{"sent": true, ...}` and the email lands,
the pipeline is working.

---

## Turning on embedding dedup

Stage 3 of dedup uses `bge-m3` + Qdrant for cross-source similarity. Off by
default so the first run doesn't pull weights.

```bash
pip install -e ".[embeddings]"        # installs sentence-transformers + torch
# Edit .env
EMBEDDINGS_ENABLED=true
```

The first call will download `BAAI/bge-m3` (~2.3 GB). After that, the L40s
will batch-embed at thousands of items/second.

---

## Running periodic ingest under Celery

The synchronous `hotpot ingest-now` command is the easiest way to verify the
pipeline. For real periodic runs, start a worker + beat:

```bash
celery -A app.core.celery_app.celery_app worker -l info
celery -A app.core.celery_app.celery_app beat   -l info
```

Beat schedule (in `app/core/celery_app.py`):

| schedule          | task                          |
|-------------------|-------------------------------|
| every hour @ :15  | `ingest_kind("arxiv")`        |
| every 15 minutes  | `ingest_kind("rss")`          |

---

## What's missing in Phase 1.0 (and where it's coming)

- **Auth + accounts** → Phase 2 (email + password, Gmail SMTP for verify)
- **Per-user subscriptions + persona presets** → Phase 2
- **Daily email digest** → Phase 2 (per-user, with vote feedback links)
- **User-submitted source contributions + moderation** → Phase 3
- **WeChat / Xiaohongshu adapters + bilingual UI** → Phase 4
- **AI commentary turned on globally + better dedup tuning** → Phase 5

See `PLAN.md` §12 for the full phase plan.

---

## Troubleshooting

**"connection refused" on port 5432 / 6333 / 6379** — `docker compose up -d`
hasn't finished. `docker compose ps` should show all three healthy.

**Qwen calls 401 / connection error** — check `OPENAI_API_KEY` and
`OPENAI_BASE_URL` in `.env`. The backend silently falls back to "Other" tags
and skips summaries if the LLM fails, so the pipeline keeps moving — but
items will land without enrichment until the endpoint is reachable.

**arXiv returning empty** — arXiv occasionally rate-limits aggressive
clients. The seed list keeps the request count modest, but if you re-run
`ingest-now` repeatedly within a minute you'll get throttled. Wait a minute
and retry.

**Tailwind classes not applying** — run `npm install` in `frontend/`; the
PostCSS pipeline is what generates the utilities.
