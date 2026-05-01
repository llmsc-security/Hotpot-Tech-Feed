from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.item import Item
from app.models.source import Source
from app.schemas.source import SourceList, SourceOut

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=SourceList)
def list_sources(
    db: Session = Depends(get_db),
    category: Optional[str] = Query(
        None,
        description="Restrict to sources that have ≥1 canonical item with this primary_category.",
    ),
):
    counts_q = (
        select(Item.source_id, func.count(Item.id).label("n"))
        .where(Item.is_canonical.is_(True))
    )
    if category:
        counts_q = counts_q.where(Item.primary_category == category)
    counts_subq = counts_q.group_by(Item.source_id).subquery()

    base = (
        select(Source, func.coalesce(counts_subq.c.n, 0).label("item_count"))
        .outerjoin(counts_subq, counts_subq.c.source_id == Source.id)
    )
    if category:
        base = base.where(counts_subq.c.n > 0)

    rows = db.execute(
        base.order_by(func.coalesce(counts_subq.c.n, 0).desc(), Source.name)
    ).all()

    total = len(rows) if category else db.execute(
        select(func.count()).select_from(Source)
    ).scalar_one()

    out: list[SourceOut] = []
    for src, count in rows:
        s = SourceOut.model_validate(src)
        s.item_count = int(count or 0)
        out.append(s)
    return SourceList(sources=out, total=total)
