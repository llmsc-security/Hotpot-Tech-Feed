# Content Quality Backfill Status

Last updated: 2026-05-01 17:20 +08

## Current Rule

- The LLM backend should be treated as a shared GPU pool.
- Do not exceed 8 concurrent quality-scoring workers total.
- Prefer one process with `--workers 8`, or two processes with `--workers 4`
  each. Do not dispatch four `--workers 4` jobs again.
- Resume with claim mode so multiple jobs do not process the same rows:

```bash
docker compose run --rm backend hotpot enrich-all --quality-only --claim --limit 700 --workers 4
```

## Current State

At the final DB check:

- canonical items: `5680`
- scored canonical items: `5680`
- zero-score canonical items: `0`
- average score over scored canonical items: `0.4465`

Always re-check the DB before starting more backfill:

```bash
docker compose exec -T backend python - <<'PY'
from sqlalchemy import func, select
from app.core.db import SessionLocal
from app.models.item import Item
with SessionLocal() as db:
    total = db.execute(select(func.count()).select_from(Item).where(Item.is_canonical.is_(True))).scalar_one()
    scored = db.execute(select(func.count()).select_from(Item).where(Item.is_canonical.is_(True), Item.score > 0)).scalar_one()
    zero = db.execute(select(func.count()).select_from(Item).where(Item.is_canonical.is_(True), Item.score <= 0)).scalar_one()
print({"total": total, "scored": scored, "zero": zero})
PY
```

## Backfill History

- Sequential `--limit 20`: processed `20`, ok `20`.
- Sequential `--limit 500`: processed `500`, ok `500`.
- Sequential `--limit 1000`: processed `1000`, ok `1000`.
- Parallel fixed batch `--limit 2000 --workers 8`: partially completed, then
  was stopped after it appeared stalled; DB had reached `3051` scored items.
- Four claim jobs with `--limit 800 --workers 4 --claim` were tried, but they
  used the broad missing-summary-or-score filter and mostly did not increase
  quality scores. This led to adding `--quality-only`.
- Four quality-only claim jobs were dispatched. This exceeded the requested
  pool size, so two were stopped. Two `--workers 4` jobs were left running,
  for 8 total workers.
- Final quality-only claim job ran with one `--workers 8` pool:
  - processed `324`
  - ok `324`
  - errors `0`
  - final zero-score canonical items: `0`

## Resume Guidance

If any quality-only claim jobs are still running, let them finish or stop extra
jobs until total workers are <= 8:

```bash
docker ps --filter name=hotpot-tech-feed-backend-run
```

After running jobs finish, check the DB count. The initial project-wide
backfill is complete as of 2026-05-01 17:20 +08. Only run another job if future
ingest creates new `score <= 0` rows.

If `zero > 0`, run one bounded job:

```bash
docker compose run --rm backend hotpot enrich-all --quality-only --claim --limit 1000 --workers 8
```

Do not rerun broad `hotpot enrich-all` without `--quality-only` for this
quality-score backfill; it can spend work on rows that already have scores.
