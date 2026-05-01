"""Generic RSS / Atom adapter.

The Source.url field is the feed URL. extra may contain:
  - content_type: override the inferred content type (default "blog")
  - lab: pin a lab name on every item from this feed
  - max_results: cap entries per fetch (default 50)
  - max_age_days: skip dated entries older than this many days (default 365)
  - extract_full_text: fetch article pages when feed excerpts are short/missing
  - include_keywords: keep only entries matching one of these words (optional)
  - exclude_keywords: drop entries matching these words (optional)
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

import feedparser

from app.adapters.base import BaseAdapter
from app.models.item import ContentType
from app.schemas.item import RawItem
from app.services.extract import extract_article_text


class RssAdapter(BaseAdapter):
    def fetch(self) -> Iterable[RawItem]:
        with self._client() as client:
            resp = client.get(self.source.url)
            resp.raise_for_status()
            body = resp.text

        feed = feedparser.parse(body)
        extra = self.source.extra or {}
        max_results = int(extra.get("max_results", 50))
        max_age_days = int(extra.get("max_age_days", 365))
        extract_full_text = bool(extra.get("extract_full_text", False))
        include_keywords = _words(extra.get("include_keywords"))
        exclude_keywords = _words(extra.get("exclude_keywords"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        ctype_value = extra.get("content_type", "blog")
        try:
            content_type = ContentType(ctype_value)
        except ValueError:
            content_type = ContentType.blog
        lab = extra.get("lab") or self.source.lab

        emitted = 0
        for entry in feed.entries:
            link = entry.get("link") or entry.get("id")
            if not link:
                continue
            title = (entry.get("title") or "").strip()
            if not title:
                continue

            published_dt = _entry_datetime(entry)
            if published_dt is not None and published_dt < cutoff:
                continue
            authors = _entry_authors(entry)
            excerpt = _entry_excerpt(entry)
            if not _accept_entry(title, excerpt, include=include_keywords, exclude=exclude_keywords):
                continue
            if extract_full_text and (not excerpt or len(excerpt) < 280):
                full_text = _fetch_full_text(client, link)
                if full_text:
                    excerpt = full_text

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
            emitted += 1
            if emitted >= max_results:
                break


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


def _fetch_full_text(client, url: str) -> str | None:
    try:
        resp = client.get(url)
        if resp.status_code != 200:
            return None
    except Exception:
        return None
    return extract_article_text(resp.text, url=url, limit=3000)


def _words(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(x) for x in value if str(x)]
    return []


def _accept_entry(title: str, excerpt: str | None, *, include: list[str], exclude: list[str]) -> bool:
    haystack = f"{title}\n{excerpt or ''}".lower()
    has_cve = "cve-" in haystack
    if exclude and any(word.lower() in haystack for word in exclude) and not has_cve:
        return False
    if include and not any(word.lower() in haystack for word in include) and not has_cve:
        return False
    return True
