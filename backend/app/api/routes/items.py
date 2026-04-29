from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.models.item import ContentType, Item, ItemTag
from app.models.source import Source
from app.schemas.item import ItemList, ItemOut, TagOut

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=ItemList)
def list_items(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    topic: Optional[str] = Query(None, description="filter by topic tag, e.g. 'topic:ML'"),
    content_type: Optional[ContentType] = Query(None),
    source_id: Optional[uuid.UUID] = Query(None),
    q: Optional[str] = Query(None, description="title substring search (case-insensitive)"),
):
    stmt = (
        select(Item)
        .options(selectinload(Item.tags), selectinload(Item.source))
        .where(Item.is_canonical.is_(True))
        .order_by(Item.fetched_at.desc())
    )
    count_stmt = select(func.count()).select_from(Item).where(Item.is_canonical.is_(True))

    if topic:
        sub = select(ItemTag.item_id).where(ItemTag.tag == topic)
        stmt = stmt.where(Item.id.in_(sub))
        count_stmt = count_stmt.where(Item.id.in_(sub))
    if content_type:
        stmt = stmt.where(Item.content_type == content_type)
        count_stmt = count_stmt.where(Item.content_type == content_type)
    if source_id:
        stmt = stmt.where(Item.source_id == source_id)
        count_stmt = count_stmt.where(Item.source_id == source_id)
    if q:
        stmt = stmt.where(Item.title.ilike(f"%{q}%"))
        count_stmt = count_stmt.where(Item.title.ilike(f"%{q}%"))

    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(stmt.limit(limit).offset(offset)).scalars().unique().all()

    items_out = [_to_out(item) for item in rows]
    return ItemList(items=items_out, total=total, limit=limit, offset=offset)


@router.get("/{item_id}", response_model=ItemOut)
def get_item(item_id: uuid.UUID, db: Session = Depends(get_db)):
    item = db.execute(
        select(Item)
        .options(selectinload(Item.tags), selectinload(Item.source))
        .where(Item.id == item_id)
    ).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "item not found")
    return _to_out(item)


def _to_out(item: Item) -> ItemOut:
    return ItemOut(
        id=item.id,
        source_id=item.source_id,
        source_name=item.source.name if item.source else None,
        canonical_url=item.canonical_url,
        title=item.title,
        authors=item.authors or [],
        published_at=item.published_at,
        fetched_at=item.fetched_at,
        language=item.language,
        excerpt=item.excerpt,
        content_type=item.content_type,
        lab=item.lab,
        venue=item.venue,
        summary=item.summary,
        commentary=item.commentary,
        score=item.score,
        tags=[TagOut(tag=t.tag, confidence=t.confidence, source=t.source) for t in item.tags],
    )
