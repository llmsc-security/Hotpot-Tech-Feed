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

- Docker + Compose v2 (`apt install docker.io docker-compose-v2`; add yourself to the `docker` group)

That's it — Python and Node are inside the container images, you don't need them on the host.

---

## Architecture (host-port-wise)

Only **one** port reaches the host. Everything else is on the internal docker network and can't be hit from outside the project, so this stack coexists peacefully with anything else running on the workstation (other Postgres, other Redis, etc.).

```
   user
    │
    ▼ HOST_PORT (default 8080)
┌──────────────────────────────────────────────────────────────────┐
│  gateway (nginx)                                                 │
│   ├─ /            → built React SPA                              │
│   ├─ /api/*       → backend (uvicorn :8000)                      │
│   └─ /docs, /openapi.json                                        │
└──────────────────────────────────────────────────────────────────┘
                                │  (internal docker network)
                                ▼
        ┌─────────┐  ┌────────┐  ┌──────────┐  ┌─────────┐
        │ backend │──│postgres│  │  redis   │  │ qdrant  │
        └─────────┘  └────────┘  └──────────┘  └─────────┘
```

Ports 5432, 6379, 6333 are NOT exposed on the host.

---

## One-shot bootstrap

```bash
git clone https://github.com/llmsc-security/Hotpot-Tech-Feed.git
cd Hotpot-Tech-Feed
cp .env.example .env                     # edit OPENAI_API_KEY, SMTP_PASSWORD, HOST_PORT if 8080 is taken
bash start.sh
```

`start.sh` is idempotent — re-run it any time. It builds the images, brings up the stack, waits for the gateway to be healthy, and prints the URL.

When it prints **"is running"**, open `http://127.0.0.1:8080` (or whichever `HOST_PORT` you chose).

Stop everything with `docker compose down`. Add `-v` to also wipe data volumes.

---

## Running CLI commands (ingest, enrich, digest)

The `hotpot` CLI lives inside the backend container:

```bash
docker compose run --rm backend hotpot list-sources
docker compose run --rm backend hotpot ingest-now
docker compose run --rm backend hotpot ingest-deep --passes 5 --sleep 60
docker compose run --rm backend hotpot enrich-all --limit 2000
docker compose run --rm backend hotpot preview-digest --out /tmp/digest.html   # written inside the container
docker compose run --rm backend hotpot send-test-digest --to you@example.com
```

Or open a shell in the running container:

```bash
docker compose exec backend bash
hotpot list-sources
```

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

- `postgres.dump` — custom-format `pg_dump` of every table (sources, items, tags, summaries)
- `seed_sources.yaml` — the source list at snapshot time
- `manifest.json` — timestamp, host, item / source counts

Qdrant embeddings are NOT in the snapshot (Qdrant has no host port now, and embeddings can be regenerated quickly on the target box).

### Transfer

```bash
scp data/snapshots/hotpot-*.tar.gz user@workstation:~/Hotpot-Tech-Feed/data/snapshots/
```

### On the target box

```bash
git clone https://github.com/llmsc-security/Hotpot-Tech-Feed.git
cd Hotpot-Tech-Feed
cp .env.example .env                                # edit secrets
bash start.sh                                       # builds + starts the stack
./scripts/restore.sh data/snapshots/hotpot-<TS>.tar.gz   # loads the dump
```

The restore script:

1. Drops and recreates the database (5-second confirmation prompt before the destructive step)
2. Loads the dump with `pg_restore` via `docker compose exec postgres`
3. Prints item / source counts to verify

If you need similarity dedup, re-embed in place:

```bash
EMBEDDINGS_ENABLED=true docker compose run --rm backend hotpot enrich-all --all
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
