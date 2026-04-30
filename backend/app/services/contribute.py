"""User contribution: a two-stage flow.

  Stage 1 — classify_url(db, url)
        Validates + fetches the URL, picks the best title/excerpt, asks the
        LLM for ranked candidate categories, returns metadata for the user
        to review. Nothing is persisted yet.

  Stage 2 — commit_url(db, url, title, excerpt, category, ...)
        Persists the Item under the user-confirmed category.

The legacy single-shot `contribute_url` is kept as a convenience wrapper:
classify, then commit with the LLM's top candidate.
"""
from __future__ import annotations

import html as _html
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable
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


def _extract(html: str, regexes: Iterable[re.Pattern[str]]) -> str | None:
    for rx in regexes:
        m = rx.search(html)
        if m:
            text = _html.unescape(m.group(1)).strip()
            if text:
                return text
    return None


def _best_title(html: str) -> str | None:
    candidates: list[str] = []
    for rx in (_TITLE_RE, _OG_TITLE_RE):
        m = rx.search(html)
        if m:
            t = re.sub(r"\s+", " ", _html.unescape(m.group(1)).strip())
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
        trust_score=0.4,
        health_status=HealthStatus.ok,
        status=SourceStatus.active,
        extra={"user_contributed": True},
    )
    db.add(src)
    db.flush()
    return src


def _existing_to_dict(existing: Item) -> dict[str, Any]:
    return {
        "duplicate": True,
        "item_id": str(existing.id),
        "url": existing.canonical_url,
        "title": existing.title,
        "excerpt": existing.excerpt,
        "primary_category": existing.primary_category,
        "content_type": existing.content_type.value,
        "candidates": [],
        "tags": [t.tag for t in existing.tags if not t.tag.startswith("topic:")],
    }


# ---------- Stage 1: classify ----------

def classify_url(db: Session, url: str) -> dict[str, Any]:
    """Fetch + classify a URL. Returns metadata for the user to review.
    Does NOT persist anything new (but reports duplicates if found).
    """
    url = _validate_url(url)
    html_text = _fetch(url)

    title = _best_title(html_text)
    if not title:
        raise ContributeError(
            "We couldn't find a usable <title> on the page.",
            "Make sure the URL points to an article page (with a clear page title), not a homepage or app shell.",
        )
    title = title[:1024]

    excerpt = _extract(html_text, [_OG_DESC_RE, _DESC_RE])
    if not excerpt:
        body = _strip_tags(html_text)[:1500]
        excerpt = body if len(body) > 80 else None

    canonical = canonicalize_url(url)

    src = _get_or_create_user_source(db)
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
        return _existing_to_dict(existing)

    # Ask the LLM for ranked categories: 2 closed-vocab + 1 open free-form.
    tag_result = tag_item(title, excerpt)
    topics = [t for t in (tag_result.get("topics") or []) if t]
    if not topics:
        topics = ["Other"]
    open_topic = tag_result.get("open_topic")
    candidates = []
    for i, t in enumerate(topics[:3]):
        candidates.append({
            "category": t,
            "confidence": round(max(0.4, 1.0 - i * 0.15), 2),
            "open": bool(open_topic and t == open_topic),
        })

    return {
        "duplicate": False,
        "url": canonical,
        "title": title,
        "excerpt": excerpt,
        "candidates": candidates,
        "content_type": tag_result.get("content_type", "other"),
        "tags": [str(t).lower()[:32] for t in (tag_result.get("tags") or [])][:5],
    }


# ---------- Stage 2: commit ----------

def commit_url(
    db: Session,
    url: str,
    title: str,
    excerpt: str | None,
    category: str | None,
    candidates: list[dict[str, Any]] | None = None,
    content_type: str = "other",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Persist a classified URL using the user-confirmed category."""
    url = _validate_url(url)
    canonical = canonicalize_url(url)
    title = (title or "").strip()
    if not title or len(title) < 3:
        raise ContributeError(
            "Missing title.",
            "Re-run classification to refresh the title before committing.",
        )

    src = _get_or_create_user_source(db)

    # Re-check dedup at commit time — someone else might have inserted in between.
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
        return _existing_to_dict(existing)

    try:
        ctype = ContentType(content_type)
    except ValueError:
        ctype = ContentType.other

    primary = (category or "").strip()[:64] or None
    if primary is None and candidates:
        primary = candidates[0].get("category")

    item = Item(
        source_id=src.id,
        canonical_url=canonical,
        title=title[:1024],
        authors=[],
        published_at=datetime.now(timezone.utc),
        language="en",
        excerpt=excerpt,
        content_type=ctype,
        primary_category=primary,
        is_canonical=True,
    )
    db.add(item)
    db.flush()

    seen_topics: set[str] = set()
    for c in candidates or []:
        cat = (c.get("category") or "").strip()
        if not cat or cat in seen_topics:
            continue
        seen_topics.add(cat)
        db.add(ItemTag(
            item_id=item.id,
            tag=f"topic:{cat}"[:64],
            confidence=float(c.get("confidence") or 1.0),
            source="llm",
        ))
    if primary and primary not in seen_topics:
        # User typed a brand-new category that wasn't in the LLM's suggestions.
        db.add(ItemTag(
            item_id=item.id,
            tag=f"topic:{primary}"[:64],
            confidence=1.0,
            source="user",
        ))
    for t in tags or []:
        db.add(ItemTag(
            item_id=item.id,
            tag=str(t).lower()[:32],
            confidence=0.9,
            source="llm",
        ))
    db.add(ItemTag(item_id=item.id, tag="contrib:user", confidence=1.0, source="user"))

    log.info("user contribution committed",
             url=canonical, item_id=str(item.id), category=primary)

    return {
        "ok": True,
        "duplicate": False,
        "item_id": str(item.id),
        "url": canonical,
        "title": title,
        "primary_category": primary,
        "content_type": ctype.value,
    }


# ---------- Legacy convenience wrapper ----------

def contribute_url(db: Session, url: str) -> dict[str, Any]:
    """Single-shot: classify and commit with the LLM's top candidate."""
    classified = classify_url(db, url)
    if classified["duplicate"]:
        return {**classified, "ok": True}
    candidates = classified["candidates"]
    cat = candidates[0]["category"] if candidates else None
    return commit_url(
        db,
        url=classified["url"],
        title=classified["title"],
        excerpt=classified["excerpt"],
        category=cat,
        candidates=candidates,
        content_type=classified["content_type"],
        tags=classified["tags"],
    )
