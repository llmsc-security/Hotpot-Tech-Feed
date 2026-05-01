"""Doonsec WeChat security aggregator adapter.

Doonsec exposes a broad RSS feed, but its category JSON endpoint is cleaner for
this project: we can pull high-signal WeChat security categories such as
warning, reproduction, original, hot, and discussion while applying per-category
quality gates.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.adapters.base import BaseAdapter
from app.models.item import ContentType
from app.schemas.item import RawItem


_CN_TZ = timezone(timedelta(hours=8))
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
_POST_HEADERS = {
    "Accept": "application/json,*/*",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://wechat.doonsec.com",
    "Referer": "https://wechat.doonsec.com/news/",
    "User-Agent": _BROWSER_UA,
    "X-Requested-With": "XMLHttpRequest",
}


class DoonsecAdapter(BaseAdapter):
    def fetch(self) -> Iterable[RawItem]:
        extra = self.source.extra or {}
        categories = _categories(extra)
        max_results = int(extra.get("max_results", 100))
        max_age_days = int(extra.get("max_age_days", 60))
        cutoff = datetime.now(_CN_TZ) - timedelta(days=max_age_days)
        global_include = _words(extra.get("include_keywords"))
        global_exclude = _words(extra.get("exclude_keywords"))
        content_type = _content_type(extra.get("content_type", "news"))
        endpoint = _endpoint(self.source.url)
        emitted = 0
        seen: set[str] = set()

        with self._client() as client:
            # Warm a session cookie. Doonsec sometimes returns HTML or stalls on
            # direct AJAX POSTs from containerized clients without this first GET.
            try:
                client.get(
                    endpoint,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": _POST_HEADERS["Accept-Language"],
                        "Referer": "https://wechat.doonsec.com/",
                        "User-Agent": _BROWSER_UA,
                    },
                )
            except Exception:
                pass

            for cat in categories:
                cat_id = str(cat.get("id", "0"))
                cat_name = str(cat.get("name") or cat_id)
                cat_limit = int(cat.get("max_results", max_results))
                pages = int(cat.get("pages", 1))
                cat_emitted = 0
                include = _words(cat.get("include_keywords")) or global_include
                exclude = _words(cat.get("exclude_keywords")) or global_exclude

                for page in range(1, pages + 1):
                    response = client.post(
                        endpoint,
                        data={"page": page, "cat_id": cat_id},
                        headers=_POST_HEADERS,
                    )
                    response.raise_for_status()
                    try:
                        payload = response.json()
                    except ValueError:
                        break
                    rows = payload.get("data") or []
                    if not isinstance(rows, list) or not rows:
                        break

                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        published_at = _parse_dt(row.get("publish_time"))
                        if published_at is not None and published_at < cutoff:
                            continue
                        if not _accept(row, cat, include=include, exclude=exclude):
                            continue

                        link = row.get("short_url") or row.get("url")
                        title = (row.get("title") or "").strip()
                        if not link or not title or link in seen:
                            continue
                        seen.add(link)

                        account = (row.get("account") or row.get("source_account") or "").strip()
                        author = (row.get("author") or "").strip()
                        authors = [x for x in (account, author) if x]
                        cves = [
                            c.get("cve_name")
                            for c in (row.get("cves") or [])
                            if isinstance(c, dict) and c.get("cve_name")
                        ]
                        excerpt = _excerpt(row, cves=cves, category=cat_name)
                        yield RawItem(
                            source_id=self.source.id,
                            url=link,
                            title=title,
                            authors=authors,
                            published_at=published_at,
                            language=self.source.language,
                            excerpt=excerpt,
                            content_type=content_type,
                            lab=account or self.source.lab,
                            extra={
                                "adapter": "doonsec",
                                "category": cat_name,
                                "cat_id": cat_id,
                                "read_num": row.get("read_num"),
                                "quality": row.get("quality"),
                                "cves": cves,
                                "doonsec_id": row.get("id"),
                            },
                        )
                        emitted += 1
                        cat_emitted += 1
                        if emitted >= max_results or cat_emitted >= cat_limit:
                            break
                    if emitted >= max_results or cat_emitted >= cat_limit:
                        break
                if emitted >= max_results:
                    break


def _endpoint(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/news/", "", ""))


def _categories(extra: dict[str, Any]) -> list[dict[str, Any]]:
    configured = extra.get("categories")
    if isinstance(configured, list) and configured:
        return [c for c in configured if isinstance(c, dict)]
    return [
        {"id": -7, "name": "预警", "pages": 2, "max_results": 40, "min_quality": 0.05},
        {"id": -14, "name": "复现", "pages": 2, "max_results": 30, "min_quality": 0.35},
        {"id": -1, "name": "原创", "pages": 1, "max_results": 20, "min_quality": 0.25},
        {"id": -100, "name": "热点", "pages": 1, "max_results": 20, "min_quality": 0.15},
        {"id": -10, "name": "瓜田", "pages": 1, "max_results": 10, "min_read_num": 1500},
    ]


def _accept(row: dict[str, Any], cat: dict[str, Any], *, include: list[str], exclude: list[str]) -> bool:
    title = str(row.get("title") or "")
    digest = str(row.get("digest") or "")
    summary = str(row.get("summary") or "")
    haystack = f"{title}\n{digest}\n{summary}"
    cves = row.get("cves") or []
    has_cve = bool(cves)
    quality = _float(row.get("quality"))
    read_num = _int(row.get("read_num"))
    min_quality = _float(cat.get("min_quality"))
    min_read = _int(cat.get("min_read_num"))

    if exclude and any(word in haystack for word in exclude) and not has_cve and quality < 0.8:
        return False
    if include and not any(word in haystack for word in include) and not has_cve and quality < 0.8:
        return False
    if min_quality and quality < min_quality and not has_cve:
        return False
    if min_read and read_num < min_read and not has_cve and quality < 0.8:
        return False
    return True


def _excerpt(row: dict[str, Any], *, cves: list[str], category: str, limit: int = 2500) -> str | None:
    parts: list[str] = []
    summary = _clean(row.get("summary"))
    digest = _clean(row.get("digest"))
    article = _clean(row.get("article"))
    if summary:
        parts.append(summary)
    if digest and digest not in parts:
        parts.append(digest)
    if cves:
        parts.append("CVE: " + ", ".join(cves[:8]))
    keywords = row.get("keywords") or []
    if isinstance(keywords, list):
        labels = [
            str(k.get("keyword"))
            for k in keywords
            if isinstance(k, dict) and k.get("keyword")
        ]
        if labels:
            parts.append("Keywords: " + ", ".join(labels[:10]))
    if category:
        parts.append(f"Doonsec category: {category}")
    if not parts and article:
        parts.append(article)
    text = "\n".join(parts).strip()
    return text[:limit] if text else None


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=_CN_TZ)
        except ValueError:
            continue
    return None


def _content_type(value: Any) -> ContentType:
    try:
        return ContentType(str(value))
    except ValueError:
        return ContentType.news


def _words(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(x) for x in value if str(x)]
    return []


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
