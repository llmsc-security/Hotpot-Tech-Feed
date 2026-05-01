"""Cron-polled HTML index adapter.

For sites that do not expose RSS/Atom or a useful sitemap but do have a blog,
news, or research listing page. A scheduled ingest pass polls the listing page,
extracts article links, fetches those pages, and lets the normal canonical URL
dedup layer decide what is new. In practice this makes an ordinary HTML index
behave like a feed.

Source.extra keys:
  - adapter: "html_index"       required by the registry dispatch
  - index_urls: [url, ...]      optional; defaults to Source.url
  - link_pattern: regex         keep only article URLs matching this pattern
  - exclude_link_pattern: regex drop URLs matching this pattern
  - same_domain: bool           default true
  - candidate_limit: int        max article links to fetch before filters
  - max_results: int            max RawItems to emit (default 30)
  - max_age_days: int           skip pages with parsed published dates older than this
  - content_type: enum value    default "blog"
  - lab: str                    pin lab/source label
  - include_keywords/exclude_keywords: title/excerpt filters
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit

from dateutil import parser as dateparser

from app.adapters.base import BaseAdapter
from app.models.item import ContentType
from app.schemas.item import RawItem
from app.services.extract import extract_article_text

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_OG_TITLE_RE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', re.I
)
_META_RE = re.compile(r"<meta\s+[^>]*>", re.I)
_ATTR_RE = re.compile(r'([A-Za-z_:.-]+)\s*=\s*["\']([^"\']*)["\']')
_TIME_RE = re.compile(r"<time[^>]+datetime=[\"']([^\"']+)[\"']", re.I)
_DATE_KEYS = {
    "article:published_time",
    "date",
    "dc.date",
    "dc:date",
    "datepublished",
    "publishdate",
    "pubdate",
    "published_time",
    "timestamp",
}
_AUTHOR_KEYS = {"author", "article:author", "dc.creator", "dc:creator"}


class HtmlIndexAdapter(BaseAdapter):
    def fetch(self) -> Iterable[RawItem]:
        extra = self.source.extra or {}
        max_results = int(extra.get("max_results", 30))
        candidate_limit = int(extra.get("candidate_limit", max_results * 3))
        max_age_days = int(extra.get("max_age_days", 365))
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        link_re = _compile_pattern(extra.get("link_pattern"))
        exclude_re = _compile_pattern(extra.get("exclude_link_pattern"))
        same_domain = bool(extra.get("same_domain", True))
        include_keywords = _words(extra.get("include_keywords"))
        exclude_keywords = _words(extra.get("exclude_keywords"))
        content_type = _content_type(extra.get("content_type", "blog"))
        lab = extra.get("lab") or self.source.lab
        index_urls = _index_urls(extra.get("index_urls"), self.source.url)

        emitted = 0
        seen: set[str] = set()
        with self._client() as client:
            candidates: list[tuple[str, str | None]] = []
            for index_url in index_urls:
                try:
                    response = client.get(index_url)
                    response.raise_for_status()
                except Exception:
                    continue
                for url, link_text in _extract_links(
                    response.text,
                    base_url=str(response.url),
                    same_domain=same_domain,
                    link_re=link_re,
                    exclude_re=exclude_re,
                ):
                    if url in seen:
                        continue
                    seen.add(url)
                    candidates.append((url, link_text))
                    if len(candidates) >= candidate_limit:
                        break
                if len(candidates) >= candidate_limit:
                    break

            for url, link_text in candidates:
                page = _fetch_page(client, url)
                if not page:
                    continue
                published_at = _page_date(page)
                if published_at is not None and published_at < cutoff:
                    continue
                title = _page_title(page) or _clean(link_text or "") or _slug_title(url)
                if not title:
                    continue
                excerpt = extract_article_text(page, url=url, limit=3000)
                if not _accept_entry(title, excerpt, include=include_keywords, exclude=exclude_keywords):
                    continue
                yield RawItem(
                    source_id=self.source.id,
                    url=url,
                    title=title[:300],
                    authors=_page_authors(page),
                    published_at=published_at,
                    language=self.source.language,
                    excerpt=excerpt,
                    content_type=content_type,
                    lab=lab,
                    extra={"adapter": "html_index", "index_polled": True},
                )
                emitted += 1
                if emitted >= max_results:
                    break


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            self.links.append((self._href, _clean(" ".join(self._text))))
            self._href = None
            self._text = []


def _extract_links(
    html: str,
    *,
    base_url: str,
    same_domain: bool,
    link_re: re.Pattern[str] | None,
    exclude_re: re.Pattern[str] | None,
) -> list[tuple[str, str | None]]:
    parser = _AnchorParser()
    parser.feed(html)
    base_host = urlsplit(base_url).netloc.lower()
    out: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for href, text in parser.links:
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urldefrag(urljoin(base_url, href))[0]
        if same_domain and urlsplit(url).netloc.lower() != base_host:
            continue
        if link_re and not link_re.search(url):
            continue
        if exclude_re and exclude_re.search(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append((url, text or None))
    return out


def _fetch_page(client, url: str) -> str | None:
    try:
        response = client.get(url)
        if response.status_code != 200:
            return None
    except Exception:
        return None
    ctype = response.headers.get("content-type", "").lower()
    if ctype and "html" not in ctype:
        return None
    return response.text


def _page_title(html: str) -> str | None:
    m = _OG_TITLE_RE.search(html)
    if m:
        return _strip_title_suffix(_clean(m.group(1)))
    m = _TITLE_RE.search(html)
    if m:
        return _strip_title_suffix(_clean(m.group(1)))
    return None


def _page_date(html: str) -> datetime | None:
    for attrs in _meta_attrs(html):
        key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
        if key in _DATE_KEYS and attrs.get("content"):
            dt = _parse_date(attrs["content"])
            if dt:
                return dt
    m = _TIME_RE.search(html)
    if m:
        return _parse_date(m.group(1))
    return None


def _page_authors(html: str) -> list[str]:
    authors: list[str] = []
    for attrs in _meta_attrs(html):
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        author = _clean(attrs.get("content", ""))
        if key in _AUTHOR_KEYS and author and author not in authors:
            authors.append(author)
    return authors[:5]


def _meta_attrs(html: str) -> Iterable[dict[str, str]]:
    for match in _META_RE.finditer(html):
        yield {k.lower(): v for k, v in _ATTR_RE.findall(match.group(0))}


def _parse_date(value: str) -> datetime | None:
    try:
        dt = dateparser.parse(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _content_type(value) -> ContentType:
    try:
        return ContentType(str(value))
    except ValueError:
        return ContentType.blog


def _compile_pattern(value) -> re.Pattern[str] | None:
    if not value:
        return None
    return re.compile(str(value))


def _index_urls(value, fallback: str) -> list[str]:
    if isinstance(value, list):
        urls = [str(x) for x in value if str(x)]
        return urls or [fallback]
    if isinstance(value, str) and value:
        return [value]
    return [fallback]


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


def _slug_title(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"[-_]+", " ", slug).strip()
    return slug.title() if slug else ""


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def _strip_title_suffix(title: str) -> str:
    for sep in (" | ", " - "):
        head, found, tail = title.rpartition(sep)
        if found and head and 2 <= len(tail) <= 32:
            return head.strip()
    return title
