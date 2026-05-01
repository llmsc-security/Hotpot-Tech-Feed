"""Enrich an item with tags, summary, quality score, and optional commentary."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.db import session_scope
from app.core.logging import get_logger
from app.models.item import ContentType, Item, ItemTag
from app.services import embeddings, qdrant
from app.services.llm import commentary as llm_commentary
from app.services.llm import score_item_quality
from app.services.llm import summarize as llm_summarize
from app.services.llm import tag_item

log = get_logger(__name__)


def enrich_item(db: Session, item: Item) -> None:
    """Tag, summarize, score, optionally comment, and upsert embeddings if enabled."""
    # ---- Tagging ----
    existing_llm_tags = [t for t in item.tags if t.source == "llm"]
    if existing_llm_tags:
        tag_result = {"topics": [], "content_type": item.content_type.value, "tags": []}
    else:
        try:
            tag_result = tag_item(item.title, item.excerpt)
        except Exception as e:  # pragma: no cover
            log.warning("tag_item raised", err=str(e))
            tag_result = {"topics": ["Other"], "content_type": "other", "tags": []}

    # If the adapter didn't pin the content type strongly, trust the LLM.
    if item.content_type in (ContentType.other,) and tag_result.get("content_type"):
        try:
            item.content_type = ContentType(tag_result["content_type"])
        except ValueError:
            pass

    for topic in tag_result.get("topics", []):
        db.add(ItemTag(item_id=item.id, tag=f"topic:{topic}", confidence=1.0, source="llm"))
    for tag in tag_result.get("tags", []):
        db.add(ItemTag(item_id=item.id, tag=tag, confidence=0.9, source="llm"))

    # ---- Summary ----
    if settings.enrich_summary and item.excerpt and not item.summary:
        item.summary = llm_summarize(item.title, item.excerpt)

    # ---- Commentary (off by default until prompts are tuned) ----
    if settings.enrich_commentary and item.excerpt and not item.commentary:
        item.commentary = llm_commentary(
            item.title, item.excerpt, content_type=item.content_type.value
        )

    # ---- Quality score ----
    if not item.score or item.score <= 0:
        item.score = score_item_quality(
            item.title,
            item.excerpt,
            summary=item.summary,
            content_type=item.content_type.value,
            source_name=item.source.name if item.source else None,
            source_trust=item.source.trust_score if item.source else None,
        )

    # ---- Embeddings + Qdrant ----
    if embeddings.is_enabled():
        try:
            text = (item.title + "\n" + (item.excerpt or ""))[:1500]
            vec = embeddings.embed_text(text)
            if vec:
                qdrant.ensure_collection()
                qdrant.upsert_item(str(item.id), vec, item.published_at)
                item.embedding_id = str(item.id)
        except Exception as e:  # pragma: no cover
            log.warning("embedding upsert failed", item_id=str(item.id), err=str(e))

    item.enriched_at = datetime.now(timezone.utc)


@celery_app.task(name="app.tasks.enrich.enrich_item_id")
def enrich_item_id(item_id: str) -> bool:
    with session_scope() as db:
        item = db.get(Item, uuid.UUID(item_id))
        if not item:
            return False
        enrich_item(db, item)
        return True
