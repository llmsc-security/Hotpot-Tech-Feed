"""Generic RSS / Atom adapter.

The Source.url field is the feed URL. extra may contain:
  - content_type: override the inferred content type (default "blog")
  - lab: pin a lab name on every item from this feed
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

import feedparser

from app.adapters.base import BaseAdapter
from app.models.item import ContentType
from app.schemas.item import RawItem


class RssAdapter(BaseAdapter):
    def fetch(self) -> Iterable[RawItem]:
        with self._client() as client:
            resp = client.get(self.source.url)
            resp.raise_for_status()
            body = resp.text

        feed = feedparser.parse(body)
        ctype_value = self.source.extra.get("content_type", "blog")
        try:
            content_type = ContentType(ctype_value)
        except ValueError:
            content_type = ContentType.blog
        lab = self.source.extra.get("lab") or self.source.lab

        for entry in feed.entries:
            link = entry.get("link") or entry.get("id")
            if not link:
                continue
            title = (entry.get("title") or "").strip()
            if not title:
                continue

            published_dt = _entry_datetime(entry)
            authors = _entry_authors(entry)
            excerpt = _entry_excerpt(entry)

            yield RawItem(
                source_id=self.source.id,
                url=link,
                title=title,
                authors=authors,
                published_at=published_dt,
                language=self.source.language,
                excerpt=excerpt,
                content_type=content_type,
                lab=lab,
                extra={"feed_id": entry.get("id")},
            )


def _entry_datetime(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        struct = entry.get(key)
        if struct:
            return datetime(*struct[:6], tzinfo=timezone.utc)
    return None


def _entry_authors(entry) -> list[str]:
    authors = []
    if entry.get("author"):
        authors.append(entry["author"])
    for a in entry.get("authors", []) or []:
        name = a.get("name") if isinstance(a, dict) else None
        if name and name not in authors:
            authors.append(name)
    return authors


def _entry_excerpt(entry, limit: int = 1500) -> str | None:
    for key in ("summary", "description"):
        val = entry.get(key)
        if val:
            return _strip_tags(val)[:limit]
    content = entry.get("content")
    if content and isinstance(content, list) and content:
        return _strip_tags(content[0].get("value", ""))[:limit]
    return None


def _strip_tags(html: str) -> str:
    """Cheap HTML strip — we keep the raw HTML separately for re-parsing."""
    import re
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
