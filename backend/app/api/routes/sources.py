from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.source import Source
from app.schemas.source import SourceList, SourceOut

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=SourceList)
def list_sources(db: Session = Depends(get_db)):
    rows = db.execute(select(Source).order_by(Source.name)).scalars().all()
    total = db.execute(select(func.count()).select_from(Source)).scalar_one()
    return SourceList(sources=[SourceOut.model_validate(r) for r in rows], total=total)
