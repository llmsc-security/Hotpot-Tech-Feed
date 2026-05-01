---
name: Cron-polled HTML sources
description: For sites without usable RSS/Atom, use html_index plus host cron; canonical URL dedup is the seen-set.
type: project
---

`SourceKind.html` can opt into `app/adapters/html_index.py` with
`extra.adapter: html_index`. This is for ordinary blog/news listing pages that
are not RSS and are not useful sitemaps.

Required practice:

- Add a constrained `extra.link_pattern` that matches article URLs only.
- Add `extra.exclude_link_pattern` when category/tag pages share the same path.
- Cap both `extra.candidate_limit` and `extra.max_results`.
- Keep `max_age_days` bounded unless the source is intentionally archival.
- Run it from host cron with:

```bash
scripts/cron_hotpot.sh ingest-html
```

The cron job repeatedly polls the listing page; `items.canonical_url` uniqueness
and the dedup pipeline are the RSS-style seen-set. Do not add one-off scraper
logic for every site unless `html_index` cannot expose stable article URLs.
