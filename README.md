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

- Python 3.11+
- Node 20+
- Docker (for Postgres / Redis / Qdrant)

---

## Bring up the dev stack

```bash
# 1. Copy env template and edit secrets (OPENAI_API_KEY, GMAIL_APP_PASSWORD)
cp .env.example .env

# 2. Start Postgres, Redis, Qdrant
docker compose up -d

# 3. Backend — install + migrate + seed sources
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
alembic upgrade head
hotpot seed-sources --file data/seed_sources.yaml

# 4. First ingest (synchronous; ~1-3 minutes for the seed list)
hotpot ingest-now

# 5. Run the API
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
# 6. Frontend
cd frontend
npm install
npm run dev      # opens http://localhost:5173
```

Open `http://localhost:5173` — you should see ingested items with summaries.

---

## CLI reference

```bash
hotpot seed-sources [--file PATH]    # idempotent; updates existing sources
hotpot ingest-now                     # pull every active source once, sync
hotpot ingest-source "arXiv cs.LG"    # pull a single source by name
hotpot list-sources                   # print source rows + health
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
