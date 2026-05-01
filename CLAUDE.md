# CLAUDE.md

Project guide for Claude Code agents. Read once, then keep `.claude/memory/`
loaded for the nuanced rules.

## What this is

A self-hosted CS-feed aggregator. Backend (FastAPI + Postgres + Redis +
Qdrant) ingests RSS / arXiv / HTML-sitemap sources, classifies each item
with a self-hosted Qwen3.5 LLM, and serves a React SPA where the user
searches in plain English. An LLM agent translates the query into
structured filters. Corpus spans CS research, engineering blogs, AI-lab
announcements, and security/CVE/threat-intel feeds.

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
  app/adapters/                   arxiv, rss, html sitemap, html_index polling — registered in __init__.py
  app/services/llm.py             ALL LLM calls go through _chat() here
  app/services/contribute.py      User URL → fetch → classify → ingest
  app/services/dedup.py           3-stage: canonical → fuzzy title → embeddings
  app/tasks/ingest.py             ThreadPoolExecutor-based parallel ingest
  app/models/                     SQLAlchemy ORM (Item, Source, ItemTag, SearchLog)
  alembic/versions/               migrations — add a new file, don't edit old
  data/seed_sources.yaml          baked into the image; entrypoint reseeds on every start
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

6. **`backend/data/seed_sources.yaml` is baked into the backend image** and
   `seed_from_yaml()` matches existing rows by URL (not name). After editing
   the YAML you must `docker compose build backend && docker compose up -d
   backend`. If you change a `Source.url` in the DB without updating the
   YAML, the next container restart re-creates the old row as a duplicate.

7. **Adapter dispatch is by `kind` plus optional `extra.adapter`.** Kinds are
   `arxiv | rss | html | github`. Default `html` is sitemap-driven
   (`app/adapters/html.py`): URL is `sitemap.xml`/`sitemapindex`, optional
   `extra.path_pattern` scopes URLs. `extra.adapter: html_index` uses
   `app/adapters/html_index.py`: cron polls ordinary listing pages, extracts
   links with `link_pattern`, fetches each article, and dedup makes repeated
   polling behave like RSS. `github` has no adapter yet; do not seed
   `kind: github` until one is added.

8. **Validate any new RSS feed before adding to seed_sources.yaml.** A 200
   response is not enough — feedparser may return zero entries (comments
   feeds, login walls, JS-only pages, "Comments on:" stubs). Probe with
   `httpx.get(url)` then `feedparser.parse(r.text)` and only commit if
   `len(parsed.entries) > 0`. Many Chinese/media/lab sites need RSSHub or
   cookies and belong in `seed_candidates.yaml`, not `seed_sources.yaml`.

9. **For sites without RSS, prefer cron-polled `html_index` over ad hoc
   scraping.** Add a constrained `link_pattern`, cap `max_results` and
   `candidate_limit`, then schedule `scripts/cron_hotpot.sh ingest-html`.
   The DB's canonical URL uniqueness is the seen-set.

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
- `GET /api/sources?category=X` filters to sources with ≥1 canonical item
  whose `primary_category == X`, with per-category item counts. Powers the
  Categories card in `SourcesDrawer`.
