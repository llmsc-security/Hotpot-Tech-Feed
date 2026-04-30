# Database

Single Postgres 16 instance running inside the compose stack
(`hotpot-postgres`, internal docker network only — no host port).
Schema is owned by SQLAlchemy + Alembic, migrations live in
`backend/alembic/versions/`. The current head is **`0003_primary_category`**.

## Connecting

Credentials come from `.env`:
```
POSTGRES_USER=hotpot
POSTGRES_PASSWORD=hotpot
POSTGRES_DB=hotpot
```

Three ways to get a `psql` prompt — pick by what you want to do.

```bash
# 1. Quick shell — easiest, password not needed (peer auth inside the container)
docker compose exec postgres psql -U hotpot -d hotpot

# 2. Run a single query without entering the REPL
docker compose exec -T postgres psql -U hotpot -d hotpot -c \
  "SELECT primary_category, count(*) FROM items GROUP BY 1 ORDER BY 2 DESC;"

# 3. From outside the container (host psql client) — uses the .env password
PGPASSWORD="$(grep ^POSTGRES_PASSWORD= .env | cut -d= -f2-)" \
  psql -h 127.0.0.1 -p 5432 -U hotpot -d hotpot
#   ↑ requires that you've added a host port mapping for the postgres
#     service in docker-compose.yml — by default it's internal only.
```

For the dev-friendly daily case, just use **method 1**.

## Schema overview

```
sources ───< items >── item_tags
                     \
                      ── search_logs (independent)
```

### `sources`
Where each ingested item came from.

| column | type | notes |
| --- | --- | --- |
| `id` | uuid | PK |
| `name` | varchar(200) | display name |
| `url` | varchar(2048) | unique; for the built-in user-contribution source it's `user-contributions://hotpot` |
| `kind` | enum `source_kind` | `arxiv \| rss \| html \| github` |
| `language` | varchar(10) | default `en` |
| `lab` | varchar(200) | optional |
| `extra` | jsonb | adapter-specific config |
| `trust_score` | float | 0..1, used for ranking |
| `health_status` | enum | `ok \| degraded \| broken \| unknown` |
| `status` | enum | `active \| probation \| paused` |
| `failure_streak` | int | consecutive fetch failures |
| `last_fetched_at` | timestamptz | nullable |
| `created_at` | timestamptz | server default now() |

### `items` — **the core record**
Every item has the load-bearing meta **`title` · `canonical_url` · `excerpt` · `primary_category`**.

| column | type | notes |
| --- | --- | --- |
| `id` | uuid | PK |
| `source_id` | uuid → sources.id | FK; ON DELETE CASCADE |
| `canonical_url` | varchar(2048) | **unique** — primary dedup key |
| `title` | varchar(1024) | **required** |
| `authors` | jsonb | list of strings |
| `published_at` | timestamptz | nullable |
| `fetched_at` | timestamptz | server default now() |
| `language` | varchar(10) | |
| `excerpt` | text | the **content** snippet (og:description / meta description / first 1500 chars of stripped body) |
| `raw_html_path` | varchar(1024) | nullable |
| `content_type` | enum `content_type` | `paper \| blog \| news \| lab_announcement \| tutorial \| oss_release \| other` |
| `primary_category` | **varchar(64)** | **NEW** — the user-confirmed top-level category (e.g. `ML`, `Security`, `DevOps`). Indexed. |
| `lab` / `venue` | varchar(200) | optional |
| `dedup_group_id` | uuid | shared across items the dedup pipeline merged |
| `is_canonical` | bool | only canonical items appear in the feed |
| `embedding_id` | varchar(64) | Qdrant point id (only when embeddings enabled) |
| `summary` | text | LLM 1-2 sentence summary |
| `commentary` | text | LLM commentary (off by default) |
| `enriched_at` | timestamptz | when LLM tagging finished |
| `score` | float | ranking signal |

Indexes: `ix_items_published_at`, `ix_items_dedup_group`, `ix_items_primary_category`, FK on `source_id`.

### `item_tags`
Free-form structured tags, each `(item_id, tag)` is a row. `topic:<X>` rows are
the LLM's ranked category candidates (kept even after the user confirms a
`primary_category`); plain lowercase tags are subfield labels (`react`,
`transformer`, `usenix`, …); `contrib:user` marks user-submitted items.

### `search_logs`
Every NL query the user ran with consent. Columns: `id`, `query`,
`parsed_filters` (jsonb of what the LLM extracted), `client_hint`, `created_at`.

## Useful queries

```sql
-- Existing categories with counts
SELECT primary_category, count(*) AS n
FROM items
WHERE primary_category IS NOT NULL
GROUP BY primary_category
ORDER BY n DESC, primary_category;

-- Items contributed by users
SELECT i.title, i.canonical_url, i.primary_category, i.created_at
FROM items i JOIN sources s ON s.id = i.source_id
WHERE s.url = 'user-contributions://hotpot'
ORDER BY i.fetched_at DESC;

-- LLM-suggested topic tags vs. confirmed primary_category
SELECT i.id, i.primary_category,
       array_agg(t.tag ORDER BY t.confidence DESC) FILTER (WHERE t.tag LIKE 'topic:%') AS suggested
FROM items i LEFT JOIN item_tags t ON t.item_id = i.id
WHERE i.primary_category IS NOT NULL
GROUP BY i.id LIMIT 10;

-- Top NL queries this week
SELECT query, count(*) FROM search_logs
WHERE created_at > now() - interval '7 days'
GROUP BY 1 ORDER BY 2 DESC LIMIT 20;
```

## Backups

A pg_dump-based archive (covers everything above, including
`search_logs` and the user-contribution rows) is produced by
`bash backup.sh` at the repo root and restored with
`bash restore.sh <archive.tar.gz>`. See `restore.sh` for cross-PC
migration steps.
