from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.models.item import ContentType, Item, ItemTag
from app.models.search_log import SearchLog
from app.models.source import Source
from app.schemas.item import ItemList, ItemOut, TagOut

router = APIRouter(prefix="/items", tags=["items"])


def _apply_filters(
    stmt,
    *,
    topic: Optional[str],
    content_type: Optional[ContentType],
    source_id: Optional[uuid.UUID],
    source: Optional[str],
    year: Optional[int],
    q: Optional[str],
):
    if topic:
        sub = select(ItemTag.item_id).where(ItemTag.tag == topic)
        stmt = stmt.where(Item.id.in_(sub))
    if content_type:
        stmt = stmt.where(Item.content_type == content_type)
    if source_id:
        stmt = stmt.where(Item.source_id == source_id)
    if source:
        sub = select(Source.id).where(Source.name.ilike(f"%{source}%"))
        stmt = stmt.where(Item.source_id.in_(sub))
    if year:
        stmt = stmt.where(extract("year", Item.published_at) == year)
    if q:
        stmt = stmt.where(Item.title.ilike(f"%{q}%"))
    return stmt


@router.get("", response_model=ItemList)
def list_items(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    topic: Optional[str] = Query(None, description="filter by topic tag, e.g. 'topic:ML'"),
    content_type: Optional[ContentType] = Query(None),
    source_id: Optional[uuid.UUID] = Query(None),
    source: Optional[str] = Query(None, description="case-insensitive source-name substring (e.g. 'wechat')"),
    year: Optional[int] = Query(None, ge=1990, le=2100, description="filter by published year"),
    q: Optional[str] = Query(None, description="title substring search (case-insensitive)"),
    sort: str = Query("date_desc", pattern="^(date_desc|date_asc|fetched_desc|fetched_asc)$"),
):
    base = select(Item).options(selectinload(Item.tags), selectinload(Item.source)).where(
        Item.is_canonical.is_(True)
    )
    base = _apply_filters(
        base,
        topic=topic,
        content_type=content_type,
        source_id=source_id,
        source=source,
        year=year,
        q=q,
    )

    if sort == "date_desc":
        base = base.order_by(
            Item.published_at.desc().nulls_last(), Item.fetched_at.desc()
        )
    elif sort == "date_asc":
        base = base.order_by(
            Item.published_at.asc().nulls_last(), Item.fetched_at.asc()
        )
    elif sort == "fetched_asc":
        base = base.order_by(Item.fetched_at.asc())
    else:  # fetched_desc
        base = base.order_by(Item.fetched_at.desc())

    count_stmt = _apply_filters(
        select(func.count()).select_from(Item).where(Item.is_canonical.is_(True)),
        topic=topic,
        content_type=content_type,
        source_id=source_id,
        source=source,
        year=year,
        q=q,
    )

    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(base.limit(limit).offset(offset)).scalars().unique().all()

    items_out = [_to_out(item) for item in rows]
    return ItemList(items=items_out, total=total, limit=limit, offset=offset)


@router.get("/years")
def list_years(db: Session = Depends(get_db)):
    """Distinct years present in the corpus, with item counts. Useful for the year-filter chips."""
    rows = db.execute(
        select(
            extract("year", Item.published_at).label("y"),
            func.count(),
        )
        .where(Item.is_canonical.is_(True))
        .where(Item.published_at.is_not(None))
        .group_by("y")
        .order_by("y")
    ).all()
    return [{"year": int(y), "count": int(c)} for (y, c) in rows]


class NLSearchIn(BaseModel):
    query: str
    record: bool = True  # honored after the user has accepted the consent banner


@router.post("/nl-search")
def nl_search(payload: NLSearchIn = Body(...), db: Session = Depends(get_db)):
    """Translate a natural-language query into structured filters via the LLM.

    Returns {topic?, content_type?, source?, year?, q?, sort?}. The frontend
    applies these as filter chips. Every query is recorded in `search_logs`
    so we can study how people search and improve the prompt over time.
    """
    from app.services.llm import nl_filter

    raw = (payload.query or "").strip()
    if not raw:
        raise HTTPException(400, "query is empty")
    if len(raw) > 500:
        raise HTTPException(400, "query too long (>500 chars)")
    current_year = datetime.now(timezone.utc).year
    parsed = nl_filter(raw, current_year=current_year)

    if payload.record:
        try:
            db.add(SearchLog(query=raw, parsed_filters=parsed))
            db.commit()
        except Exception:
            db.rollback()  # logging is best-effort — never fail the user's query

    return parsed


@router.get("/recent-searches")
def recent_searches(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    """Most recent distinct NL queries — for the input's recall dropdown."""
    rows = db.execute(
        select(SearchLog.query, func.max(SearchLog.created_at).label("ts"))
        .group_by(SearchLog.query)
        .order_by(func.max(SearchLog.created_at).desc())
        .limit(limit)
    ).all()
    return [{"query": q, "last_used_at": ts.isoformat()} for (q, ts) in rows]


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
