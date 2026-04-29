"""Three-stage dedup.

Stage 1 — canonical URL match (cheapest, exact).
Stage 2 — title fuzzy match within a recency window.
Stage 3 — embedding cosine similarity (only when embeddings_enabled).

The function `find_dedup_target(...)` returns the existing Item the new
candidate should be collapsed into, or None if it's genuinely new.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.item import Item
from app.schemas.item import RawItem
from app.services import embeddings, qdrant
from app.services.canonicalize import canonicalize_url

log = get_logger(__name__)


def find_dedup_target(db: Session, raw: RawItem, canonical: str) -> Optional[Item]:
    # Stage 1 — exact canonical URL match
    hit = db.execute(
        select(Item).where(Item.canonical_url == canonical)
    ).scalar_one_or_none()
    if hit:
        return hit

    # Stage 2 — fuzzy title within window
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.dedup_window_days)
    candidates = db.execute(
        select(Item).where(
            (Item.fetched_at >= cutoff) | (Item.published_at >= cutoff)
        )
    ).scalars().all()
    norm_new = _norm_title(raw.title)
    best: tuple[Item, float] | None = None
    for c in candidates:
        ratio = fuzz.token_set_ratio(norm_new, _norm_title(c.title)) / 100.0
        if best is None or ratio > best[1]:
            best = (c, ratio)
    if best and best[1] >= settings.dedup_title_threshold:
        return best[0]

    # Stage 3 — embedding similarity (optional)
    if embeddings.is_enabled():
        try:
            vec = embeddings.embed_text(_compose_for_embedding(raw))
            if vec:
                hits = qdrant.find_similar(
                    vec,
                    threshold=settings.dedup_embedding_threshold,
                    window_days=settings.dedup_window_days,
                    limit=3,
                )
                if hits:
                    item_id, _score = hits[0]
                    return db.get(Item, item_id)
        except Exception as e:  # pragma: no cover
            log.warning("embedding dedup failed; falling through", err=str(e))

    return None


def _norm_title(t: str) -> str:
    return " ".join(t.lower().split())


def _compose_for_embedding(raw: RawItem) -> str:
    head = raw.title.strip()
    if raw.excerpt:
        head = f"{head}\n{raw.excerpt[:500].strip()}"
    return head


__all__ = ["find_dedup_target", "canonicalize_url"]
