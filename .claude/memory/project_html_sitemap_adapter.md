---
name: HtmlSitemapAdapter for sites without RSS
description: SourceKind.html is the sitemap-driven adapter; what it expects in `extra` and the ElementTree pitfall to avoid.
type: project
---

`SourceKind.html` is served by `app/adapters/html.py` (HtmlSitemapAdapter). The Source.url is treated as a sitemap.xml or sitemapindex; the adapter walks one level into a sitemapindex (capped at the first 3 children) and extracts each page's title via `<meta og:title>` then `<title>`, falling back to the URL slug.

`extra` keys: `path_pattern` (regex against `<loc>`), `max_results` (default 30), `max_age_days` (default 365), `content_type`, `lab`.

**Why:** Anthropic, Princeton PLI, ByteDance Seed, DeepSeek news, etc. don't publish RSS but do publish sitemaps; without this adapter their entries sat at item_count=0.

**How to apply:** When adding a source whose RSS endpoint is dead or missing, check `<host>/sitemap.xml` — if it returns urlset/sitemapindex, use `kind: html` with a `path_pattern` to scope to the blog/news section.

**Pitfall:** ElementTree's `Element.__bool__` returns False for childless elements, so chaining `find("sm:loc", _NS) or find("loc")` falls through on namespaced loc tags whose only content is text. Always use `if x is None:`, never `or`-chain Element results.
