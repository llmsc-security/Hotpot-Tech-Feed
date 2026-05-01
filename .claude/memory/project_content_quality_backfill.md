# Content Quality Backfill Resume Rule

The item quality-score backfill is stateful and should not be restarted blindly.

Before starting more work, read:

- `docs/content_quality_backfill_status.md`

Then query the database for current zero-score canonical item count. Use the DB
as source of truth.

As of 2026-05-01 17:20 +08, the initial project-wide quality-score backfill was
complete: `5680/5680` canonical items scored, `0` zero-score canonical items.

For remaining quality-score backfill, use:

```bash
docker compose run --rm backend hotpot enrich-all --quality-only --claim --limit 1000 --workers 8
```

Constraints:

- Treat the LLM backend as a shared GPU pool.
- Do not exceed 8 concurrent quality-scoring workers total across all running
  containers.
- Prefer `--quality-only --claim`; do not rerun broad `enrich-all` for this
  task, because it can spend work on rows that already have scores.
- Check active run containers with:

```bash
docker ps --filter name=hotpot-tech-feed-backend-run
```
