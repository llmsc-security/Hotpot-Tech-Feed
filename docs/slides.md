---
marp: true
theme: default
paginate: true
backgroundColor: "#fff"
color: "#1f2937"
style: |
  section {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    padding: 56px 64px;
  }
  h1 { color: #1f1f1f; }
  h2 { color: #b91c1c; border-bottom: 2px solid #fbbf24; padding-bottom: 6px; }
  h3 { color: #374151; }
  code { background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 90%; }
  pre code { background: #0f172a; color: #e2e8f0; }
  table { font-size: 0.85em; }
  .small { font-size: 0.75em; color: #6b7280; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 32px; }
---

<!-- _class: lead -->

# 🌶️ Hotpot Tech Feed
### A daily CS digest, driven by an LLM agent

A self-hosted feed reader that ingests papers, blogs, and lab announcements,
classifies them with **Qwen3.5**, and lets you query the corpus in plain English.

<br>

**Stack** &nbsp;·&nbsp; FastAPI · Postgres · Redis · Qdrant · React · nginx · Qwen3.5
**Repo** &nbsp;·&nbsp; `github.com/llmsc-security/Hotpot-Tech-Feed`

---

## 1 · System architecture

<div class="two-col">

**One host port. One container per concern.**

- `nginx` (50002) is the only thing exposed; serves the React SPA and reverse-proxies `/api/*` to the backend over an internal docker network.
- `FastAPI` runs the REST API + the CLI (`hotpot ingest-now`, `enrich-all`, …).
- `Postgres 16` holds items, sources, tags, contributions; named volume → durable.
- `Redis` is the Celery broker (idle until you turn the worker on).
- `Qdrant` stores embeddings (off by default; flip `EMBEDDINGS_ENABLED=true` to enable semantic dedup).

```
              ┌────────┐
host :50002 → │ nginx  │ ─┐
              └────────┘  │  internal network
                          │
              ┌────────┐  ├→ Postgres
              │FastAPI │ ─┤
              │ + CLI  │  ├→ Redis
              └────────┘  │
                          └→ Qdrant
```

</div>

---

## 2 · LLM-driven search agent

The user types in plain English. Qwen3.5 returns structured filters; the UI applies them as removable chips.

```
"openai 2026 blog posts, newest first"
        │
        ▼   POST /api/items/nl-search    (extra_body: enable_thinking=false)
        │
{
  "content_type": "lab_announcement",   ← AI-lab posts ≠ "blog"
  "source":       "openai",
  "year":         2026,
  "sort":         "date_desc"
}
```

- **Few-shot prompt** with taxonomy hints (e.g. "OpenAI / DeepMind / Meta AI ⇒ `lab_announcement`, not `blog`").
- **Defensive parsing**: strips `</think>` blocks, falls back to plain title-substring search if the LLM emits all-null JSON.
- **No hardcoded UI dropdowns** — the agent owns the search surface; chips are the only knobs.

---

## 3 · Parallel ingest pipeline

47 sources × ~85 items × 1 LLM call/item is wall-clock bound on the LLM endpoint, not CPU. Solution: thread-per-item.

```python
def ingest_source(db, source, workers=settings.ingest_workers):
    raw_items = adapter.fetch()         # one HTTP per source
    new_ids   = persist_and_dedup(db, raw_items)
    db.commit()                         # publish before fan-out
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(_enrich_one, new_ids))   # one session per worker
```

| Knob | Default | Purpose |
| --- | --- | --- |
| `ingest_workers` | `min(32, cpu//2)` | per-item LLM enrichment |
| `ingest_source_workers` | 1 | source-level fan-out |
| DB `pool_size` | `max(20, workers+8)` | one session per worker, no contention |

**Result**: `3,889 fetched · 3,516 new · 373 dup · 7 errors` end-to-end in **~7 minutes** on a 256-core host capped to 32 LLM threads.

---

## 4 · Contribute & dedup

Anyone can paste a URL. Qwen reads it, the system classifies and dedups, and the item lands in the feed under a built-in **"User contributions"** source.

<div class="two-col">

**Pipeline**

1. Validate URL (scheme + host).
2. Fetch HTML with the project User-Agent + 20s timeout.
3. Pick the longer/more-specific of `<title>` vs `og:title` (≥ 2 words, > 5 chars — kills false dedup matches like bare "Archive").
4. **Three-stage dedup**:
   ① canonical-URL exact match
   ② title `token_set_ratio ≥ 0.90` within 7-day window
   ③ embedding cosine ≥ 0.92 (when enabled)
5. LLM classifies → topics + content_type + tags.
6. Insert as `Item` row.

**Failure UX**

```json
422 {
  "detail": {
    "message": "Server returned HTTP 404.",
    "hint":    "We need a publicly accessible HTML
                page — not a paywalled URL."
  }
}
```

The modal renders `message` + `hint` inline so the user knows how to fix the input — no opaque 500s.

</div>

---

## 5 · Tutorial — Deploy in one shot

**Prereqs**: Docker 20+ with the compose-v2 plugin.

```bash
git clone https://github.com/llmsc-security/Hotpot-Tech-Feed.git
cd Hotpot-Tech-Feed
cp .env.example .env                 # edit OPENAI_API_KEY, HOST_PORT (default 50002)
bash start.sh                        # builds images, brings up the stack
```

`start.sh` is idempotent: it rebuilds, brings everything up on an internal docker network, waits for `/healthz`, and prints the URLs.

```
  Hotpot Tech Feed is running.

  Open in browser →  http://127.0.0.1:50002
  API docs        →  http://127.0.0.1:50002/docs
  Health          →  http://127.0.0.1:50002/healthz
```

**First-time backfill**:
```bash
docker compose run --rm backend hotpot ingest-now            # default cpu/2 workers
docker compose run --rm backend hotpot ingest-now --workers 16   # override
```

---

## 6 · Tutorial — Migrate to another PC

Volumes are machine-local. The `backup.sh` / `restore.sh` pair turns the live state into a single ~2 MB archive that drops cleanly into any new host.

**Backup (old PC)**
```bash
bash backup.sh
# → backups/hotpot-20260430-044721Z.tar.gz
#   contains: postgres.dump (pg_dump -Fc), qdrant.tar.gz, env.backup, manifest.json
```

**Restore (new PC)**
```bash
git clone https://github.com/llmsc-security/Hotpot-Tech-Feed.git
cd Hotpot-Tech-Feed
bash start.sh                              # empty stack, all defaults
scp old-host:.../hotpot-*.tar.gz .
bash restore.sh hotpot-20260430-044721Z.tar.gz
# stops backend → drops & recreates DB → pg_restore → restarts → prints /api/stats
```

**No data loss**. Postgres dump is logical (cross-version safe); Qdrant snapshot is the raw volume tarball.

---

<!-- _class: lead -->

## Try it

```
http://127.0.0.1:50002
```

**Ask Hotpot** &nbsp;·&nbsp; *"ML papers from arxiv this year, newest first"*
**Contribute** &nbsp;·&nbsp; paste any blog post URL
**Corpus** &nbsp;·&nbsp; click the counter → drawer of all 47 sources

<br>

<span class="small">feed.ai2wj.com — daily CS digest · powered by Qwen3.5, a free self-hosted LLM</span>
