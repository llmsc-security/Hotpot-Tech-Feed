from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.item import Item
from app.models.source import Source

router = APIRouter(tags=["meta"])


@router.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    items = db.execute(
        select(func.count()).select_from(Item).where(Item.is_canonical.is_(True))
    ).scalar_one()
    sources = db.execute(select(func.count()).select_from(Source)).scalar_one()
    return {"items": items, "sources": sources}
