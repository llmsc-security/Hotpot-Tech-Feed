"""Sitemap-driven HTML adapter.

For sites that don't ship RSS but do publish a sitemap.xml. The Source.url is
treated as a sitemap (or sitemapindex) URL. Source.extra may contain:

  - path_pattern   regex; only <loc> URLs matching this are kept (str)
  - max_results    cap on items returned per pass (default 30)
  - content_type   override (default "blog")
  - lab            pin a lab name on every item
  - max_age_days   only keep entries with lastmod within this window (default 365)

We follow one level of <sitemapindex> (capped at the first 3 child sitemaps to
keep the fetch budget bounded). Titles come from each page's <meta og:title>
or <title>; if neither is present we synthesize from the URL slug so the
downstream LLM enricher still has something to work with.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from html import unescape
from xml.etree import ElementTree as ET

from app.adapters.base import BaseAdapter
from app.core.logging import get_logger
from app.models.item import ContentType
from app.schemas.item import RawItem
from app.services.extract import extract_article_text

log = get_logger(__name__)

_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_OG_TITLE_RE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', re.I
)


class HtmlSitemapAdapter(BaseAdapter):
    def fetch(self) -> Iterable[RawItem]:
        extra = self.source.extra or {}
        max_results = int(extra.get("max_results", 30))
        max_age_days = int(extra.get("max_age_days", 365))
        pat = extra.get("path_pattern")
        path_re = re.compile(pat) if pat else None
        ctype_value = extra.get("content_type", "blog")
        try:
            content_type = ContentType(ctype_value)
        except ValueError:
            content_type = ContentType.blog
        lab = extra.get("lab") or self.source.lab
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        with self._client() as client:
            entries = list(_collect_sitemap(client, self.source.url, depth=0))
            entries = [(u, lm) for u, lm in entries if not path_re or path_re.search(u)]
            entries = [(u, lm) for u, lm in entries if lm is None or lm >= cutoff]
            entries.sort(key=lambda x: x[1] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            entries = entries[:max_results]

            for url, lastmod in entries:
                page = _fetch_page(client, url)
                title = _page_title(page) if page else None
                if _is_generic_title(title, source_name=self.source.name, lab=lab):
                    title = None
                title = title or _slug_title(url)
                if not title:
                    continue
                excerpt = extract_article_text(page, url=url, limit=3000) if page else None
                yield RawItem(
                    source_id=self.source.id,
                    url=url,
                    title=title,
                    published_at=lastmod,
                    language=self.source.language,
                    excerpt=excerpt,
                    content_type=content_type,
                    lab=lab,
                    extra={"sitemap": True},
                )


def _collect_sitemap(client, url: str, depth: int) -> Iterable[tuple[str, datetime | None]]:
    if depth > 1:
        return
    try:
        resp = client.get(url)
        resp.raise_for_status()
    except Exception as e:
        log.warning("sitemap fetch failed", url=url, err=str(e))
        return

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        log.warning("sitemap parse failed", url=url, err=str(e))
        return

    tag = root.tag.split("}", 1)[-1]
    if tag == "sitemapindex":
        children = root.findall("sm:sitemap/sm:loc", _NS)
        if not children:
            children = root.findall("sitemap/loc")
        for child in list(children)[:3]:
            if child.text:
                yield from _collect_sitemap(client, child.text.strip(), depth + 1)
    elif tag == "urlset":
        url_els = root.findall("sm:url", _NS)
        if not url_els:
            url_els = root.findall("url")
        for url_el in url_els:
            loc = url_el.find("sm:loc", _NS)
            if loc is None:
                loc = url_el.find("loc")
            if loc is None or not loc.text:
                continue
            lastmod_el = url_el.find("sm:lastmod", _NS)
            if lastmod_el is None:
                lastmod_el = url_el.find("lastmod")
            lastmod = _parse_date(lastmod_el.text) if lastmod_el is not None and lastmod_el.text else None
            yield loc.text.strip(), lastmod


def _parse_date(s: str) -> datetime | None:
    s = s.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s.replace("Z", "+0000"), fmt) if "%z" in fmt else datetime.strptime(s, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _fetch_page(client, url: str) -> str | None:
    try:
        resp = client.get(url)
        if resp.status_code != 200:
            return None
    except Exception:
        return None
    return resp.text


def _page_title(html: str | None) -> str | None:
    if not html:
        return None
    m = _OG_TITLE_RE.search(html)
    if m:
        return _strip_title_suffix(_clean(m.group(1)))
    m = _TITLE_RE.search(html)
    if m:
        return _strip_title_suffix(_clean(m.group(1)))
    return None


def _slug_title(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"[-_]+", " ", slug).strip()
    return slug.title() if slug else ""


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(s)).strip()[:300]


def _strip_title_suffix(title: str) -> str:
    for sep in (" | ", " - "):
        head, found, tail = title.rpartition(sep)
        if found and head and 2 <= len(tail) <= 32:
            return head.strip()
    return title


def _is_generic_title(title: str | None, *, source_name: str, lab: str | None) -> bool:
    if not title:
        return False
    normalized = _normalize_title(title)
    generic = {_normalize_title(source_name)}
    if lab:
        generic.add(_normalize_title(lab))
    return normalized in generic


def _normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())
