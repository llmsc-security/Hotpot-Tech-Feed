from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.contribute import (
    ContributeError,
    classify_url,
    commit_url,
    contribute_url,
)

router = APIRouter(prefix="/contribute", tags=["contribute"])


class ContributeIn(BaseModel):
    url: str = Field(..., min_length=4, max_length=2048)


class CandidateIn(BaseModel):
    category: str = Field(..., min_length=1, max_length=64)
    confidence: float = 1.0


class CommitIn(BaseModel):
    url: str = Field(..., min_length=4, max_length=2048)
    title: str = Field(..., min_length=3, max_length=1024)
    excerpt: str | None = None
    category: str | None = Field(None, max_length=64)
    candidates: list[CandidateIn] = Field(default_factory=list)
    content_type: str = "other"
    tags: list[str] = Field(default_factory=list)


def _user_error(e: ContributeError) -> HTTPException:
    return HTTPException(
        status_code=422, detail={"message": str(e), "hint": e.hint}
    )


@router.post("")
def contribute(payload: ContributeIn = Body(...), db: Session = Depends(get_db)) -> Any:
    """Legacy single-shot endpoint: classify + commit with the top candidate."""
    try:
        return contribute_url(db, payload.url)
    except ContributeError as e:
        raise _user_error(e)


@router.post("/classify")
def classify(payload: ContributeIn = Body(...), db: Session = Depends(get_db)) -> Any:
    """Stage 1: fetch, extract, classify. Returns ranked candidates for review."""
    try:
        return classify_url(db, payload.url)
    except ContributeError as e:
        raise _user_error(e)


@router.post("/commit")
def commit(payload: CommitIn = Body(...), db: Session = Depends(get_db)) -> Any:
    """Stage 2: persist the classified item under the user-chosen category."""
    try:
        return commit_url(
            db,
            url=payload.url,
            title=payload.title,
            excerpt=payload.excerpt,
            category=payload.category,
            candidates=[c.model_dump() for c in payload.candidates],
            content_type=payload.content_type,
            tags=payload.tags,
        )
    except ContributeError as e:
        raise _user_error(e)
