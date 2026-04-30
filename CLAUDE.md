# CLAUDE.md

Project guide for Claude Code agents. Read once, then keep `.claude/memory/`
loaded for the nuanced rules.

## What this is

A self-hosted CS-feed aggregator. Backend (FastAPI + Postgres + Redis +
Qdrant) ingests RSS / arXiv / HTML sources, classifies each item with a
self-hosted Qwen3.5 LLM, and serves a React SPA where the user searches in
plain English. An LLM agent translates the query into structured filters.

## Run / develop

```bash
bash start.sh                      # idempotent: builds, brings stack up on HOST_PORT
docker compose logs -f backend     # tail
docker compose run --rm backend hotpot ingest-now              # default cpu/2 workers
docker compose run --rm backend hotpot ingest-now --workers 16 # override
docker compose run --rm backend hotpot enrich-all              # backfill missing tags
```

The only host-facing port is `gateway` (nginx) on `${HOST_PORT}` (default 50002,
not 8080 — see `.env`). Everything else is on the internal docker network.

## Backup / migrate (data is load-bearing)

```bash
bash backup.sh                     # → backups/hotpot-<UTC-ts>.tar.gz (~2 MB)
bash restore.sh <archive.tar.gz>   # wipes DB → pg_restore → restarts → prints /api/stats
```

The named volumes (`hotpot_pg`, `hotpot_redis`, `hotpot_qdrant`) survive
`docker compose down`. `down -v` would delete them — never use it without
asking. Adding any new persistent state means extending both scripts.

## Layout

```
backend/                          FastAPI + CLI (one image, two entrypoints)
  app/main.py                     FastAPI app
  app/cli.py                      `hotpot` CLI (ingest-now, enrich-all, …)
  app/api/routes/                 items, sources, contribute, health
  app/services/llm.py             ALL LLM calls go through _chat() here
  app/services/contribute.py      User URL → fetch → classify → ingest
  app/services/dedup.py           3-stage: canonical → fuzzy title → embeddings
  app/tasks/ingest.py             ThreadPoolExecutor-based parallel ingest
  app/models/                     SQLAlchemy ORM (Item, Source, ItemTag, SearchLog)
  alembic/versions/               migrations — add a new file, don't edit old
frontend/                         React + Vite + TanStack Query + Tailwind
  src/pages/Browse.tsx            "Ask Hotpot" agent UI (no manual dropdowns)
  src/components/ContributeModal.tsx
  src/components/SourcesDrawer.tsx
deploy/                           gateway.Dockerfile, nginx.conf
docs/                             slides.pptx generator
.claude/memory/                   nuanced rules — read MEMORY.md first
```

## Hard rules (don't relearn the hard way)

1. **Every Qwen chat call must go through `app.services.llm._chat()`.** It
   passes `extra_body={"chat_template_kwargs":{"enable_thinking":False}}` —
   without it, Qwen3.5's thinking-mode output eats `max_tokens` and JSON
   tagging silently degrades to "Other" for everything. Don't call
   `client.chat.completions.create` directly.

2. **No manual dropdowns / rule-based filter UI in LLM-backed surfaces.** The
   user explicitly rejected hardcoded dropdowns: the agent owns the search
   surface; chips are the only knobs. New filters → extend the NL prompt and
   add a chip type, never a `<select>`. (See `.claude/memory/feedback_llm_as_agent.md`.)

3. **Ingest concurrency is capped at 32**, even though `cpu_count // 2`
   would suggest more — the host has 256 cores but the upstream LLM doesn't
   tolerate that. DB pool tracks workers (`max(20, ingest_workers + 8)`).

4. **AI-lab "blog" posts are `lab_announcement`**, not `blog`. The NL prompt
   carries explicit aliasing for OpenAI / DeepMind / Anthropic / Google
   Research / Meta AI / MS Research / NVIDIA / Apple / BAIR / SAIL.

5. **When in doubt about volumes, run `bash backup.sh` first.** Restoring
   from a 2 MB tarball is cheap; losing weeks of corpus + contributions is
   not.

## Build / verify after a change

```bash
docker compose build backend gateway   # rebuilds whichever changed
docker compose up -d                   # recreates only changed containers
curl -fsS http://127.0.0.1:50002/api/stats   # smoke test
```

UI changes need the gateway image rebuilt (frontend bundle is baked in).
Backend Python changes need `backend` rebuilt; alembic runs on container
start, so a new migration file is enough.

## Conventions

- Frontend never calls Postgres directly — only `/api/*`.
- Tags are stored as strings: `topic:ML`, plus free-form lowercase
  subfield tags from the LLM. `topic:` prefix is structural; lowercase
  freebies are LLM-suggested.
- `ContentType` enum: `paper | blog | news | lab_announcement | tutorial |
  oss_release | other`. Add new enum values via alembic migration.
- Errors meant for the user (wrong contribute URL, malformed query) return
  HTTP 422 with `{message, hint}`. The frontend renders both verbatim.
