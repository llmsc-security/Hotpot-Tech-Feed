"""User contribution: accept a URL, fetch + clean it via LLM, ingest as an Item.

Errors are surfaced as structured `ContributeError` so the API layer can return
helpful guidance to the user (rather than a generic 500).
"""
from __future__ import annotations

import html as _html
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.item import ContentType, Item, ItemTag
from app.models.source import HealthStatus, Source, SourceKind, SourceStatus
from app.schemas.item import RawItem
from app.services import dedup
from app.services.canonicalize import canonicalize_url
from app.services.llm import tag_item

log = get_logger(__name__)

USER_SOURCE_NAME = "User contributions"
USER_SOURCE_URL = "user-contributions://hotpot"

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_OG_TITLE_RE = re.compile(
    r'<meta\s+[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', re.I
)
_DESC_RE = re.compile(
    r'<meta\s+[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', re.I
)
_OG_DESC_RE = re.compile(
    r'<meta\s+[^>]*property=["\']og:description["\'][^>]*content=["\']([^"\']+)["\']', re.I
)


class ContributeError(Exception):
    """User-facing failure with a hint about how to fix it."""

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.hint = hint


def _extract(html: str, regexes: list[re.Pattern[str]]) -> str | None:
    for rx in regexes:
        m = rx.search(html)
        if m:
            text = _html.unescape(m.group(1)).strip()
            if text:
                return text
    return None


def _best_title(html: str) -> str | None:
    """Prefer whichever of <title> / og:title is longer and meaningful.

    A bare og:title like "Archive" matches any other title containing the
    word "archive" via fuzzy dedup — bad. Pick the one that carries more
    signal, and reject everything ≤ 2 words / ≤ 5 chars.
    """
    candidates: list[str] = []
    for rx in (_TITLE_RE, _OG_TITLE_RE):
        m = rx.search(html)
        if m:
            t = _html.unescape(m.group(1)).strip()
            t = re.sub(r"\s+", " ", t)
            if t:
                candidates.append(t)
    candidates = [c for c in candidates if len(c) > 5 and len(c.split()) >= 2]
    if not candidates:
        return None
    candidates.sort(key=len, reverse=True)
    return candidates[0]


def _strip_tags(html: str) -> str:
    s = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    s = re.sub(r"<style[^>]*>.*?</style>", " ", s, flags=re.I | re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return _html.unescape(re.sub(r"\s+", " ", s)).strip()


def _validate_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ContributeError(
            "Empty URL.",
            "Paste a full URL like https://example.com/some-article.",
        )
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise ContributeError(
            "That doesn't look like a URL.",
            "It should start with http:// or https:// and include a domain.",
        )
    return url


def _fetch(url: str) -> str:
    headers = {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }
    try:
        with httpx.Client(
            timeout=settings.http_timeout_s,
            follow_redirects=True,
            headers=headers,
        ) as client:
            r = client.get(url)
    except httpx.TimeoutException as e:
        raise ContributeError(
            f"Timed out fetching the URL ({settings.http_timeout_s:.0f}s).",
            "Try a faster source, or check the URL is reachable from this server.",
        ) from e
    except httpx.HTTPError as e:
        raise ContributeError(
            f"Couldn't connect: {e}.",
            "Confirm the URL is publicly reachable (no login wall, no private intranet).",
        ) from e

    if r.status_code >= 400:
        raise ContributeError(
            f"Server returned HTTP {r.status_code}.",
            "We need a publicly accessible HTML page — not a paywalled or login-gated URL.",
        )

    ctype = r.headers.get("content-type", "").lower()
    if "html" not in ctype and "xml" not in ctype:
        raise ContributeError(
            f"That URL returned {ctype or 'unknown'} content, not HTML.",
            "Submit the URL of an article page (HTML), not a PDF/image/feed binary.",
        )

    return r.text


def _get_or_create_user_source(db: Session) -> Source:
    src = db.execute(
        select(Source).where(Source.url == USER_SOURCE_URL)
    ).scalar_one_or_none()
    if src is not None:
        return src
    src = Source(
        name=USER_SOURCE_NAME,
        url=USER_SOURCE_URL,
        kind=SourceKind.html,
        language="en",
        trust_score=0.4,  # user-submitted, slightly lower trust
        health_status=HealthStatus.ok,
        status=SourceStatus.active,
        extra={"user_contributed": True},
    )
    db.add(src)
    db.flush()
    return src


def contribute_url(db: Session, url: str) -> dict:
    """Validate, fetch, classify, dedup, and persist a user-submitted URL.

    Returns a dict with keys:
      ok (bool), item_id, title, content_type, topics, tags, duplicate (bool)
    Raises ContributeError on any user-correctable failure.
    """
    url = _validate_url(url)
    html_text = _fetch(url)

    title = _extract(html_text, [_OG_TITLE_RE, _TITLE_RE])
    if not title:
        raise ContributeError(
            "We couldn't find a <title> on the page.",
            "Make sure the URL points to an article page (it should have a clear page title), not a homepage or app shell.",
        )
    title = title[:1024]

    excerpt = _extract(html_text, [_OG_DESC_RE, _DESC_RE])
    if not excerpt:
        # Fall back to first ~800 chars of stripped body
        body = _strip_tags(html_text)[:1500]
        excerpt = body if len(body) > 80 else None

    src = _get_or_create_user_source(db)
    canonical = canonicalize_url(url)
    raw = RawItem(
        source_id=src.id,
        url=canonical,
        title=title,
        authors=[],
        published_at=None,
        language="en",
        excerpt=excerpt,
        content_type=ContentType.other,
    )

    existing = dedup.find_dedup_target(db, raw, canonical)
    if existing is not None:
        return {
            "ok": True,
            "duplicate": True,
            "item_id": str(existing.id),
            "title": existing.title,
            "content_type": existing.content_type.value,
            "topics": [t.tag.removeprefix("topic:") for t in existing.tags if t.tag.startswith("topic:")],
            "tags": [t.tag for t in existing.tags if not t.tag.startswith("topic:")],
        }

    # Classify with the LLM
    tag_result = tag_item(title, excerpt)
    topics = tag_result.get("topics") or ["Other"]
    tags = tag_result.get("tags") or []
    ctype_str = tag_result.get("content_type") or "other"
    try:
        ctype = ContentType(ctype_str)
    except ValueError:
        ctype = ContentType.other
    item = Item(
        source_id=src.id,
        canonical_url=canonical,
        title=title,
        authors=[],
        published_at=datetime.now(timezone.utc),
        language="en",
        excerpt=excerpt,
        content_type=ctype,
        is_canonical=True,
    )
    db.add(item)
    db.flush()
    for topic in topics:
        db.add(ItemTag(item_id=item.id, tag=f"topic:{topic}", confidence=1.0, source="llm"))
    for tag in tags:
        db.add(ItemTag(item_id=item.id, tag=str(tag).lower()[:32], confidence=0.9, source="llm"))
    db.add(ItemTag(item_id=item.id, tag="contrib:user", confidence=1.0, source="user"))

    log.info("user contribution accepted", url=canonical, item_id=str(item.id))

    return {
        "ok": True,
        "duplicate": False,
        "item_id": str(item.id),
        "title": title,
        "content_type": ctype.value,
        "topics": topics,
        "tags": tags,
    }
