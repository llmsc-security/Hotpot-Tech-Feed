"""Source-discovery API: list candidates, promote ✓, reject ✗."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.discovery import SourceCandidate
from app.services.discovery import promote_candidate, reject_candidate

router = APIRouter(prefix="/discovery", tags=["discovery"])


class CandidateOut(BaseModel):
    id: str
    domain: str
    sample_url: str
    name_hint: Optional[str]
    language: Optional[str]
    mention_count: int
    contributor_count: int
    signal_score: float
    llm_verdict: Optional[str]
    llm_rationale: Optional[str]
    is_llm_focused: bool
    academic_depth: Optional[str]
    suggested_kind: Optional[str]
    status: str
    source_signal: Optional[str]


def _to_out(c: SourceCandidate) -> CandidateOut:
    return CandidateOut(
        id=str(c.id),
        domain=c.domain,
        sample_url=c.sample_url,
        name_hint=c.name_hint,
        language=c.language,
        mention_count=c.mention_count,
        contributor_count=c.contributor_count,
        signal_score=c.signal_score,
        llm_verdict=c.llm_verdict,
        llm_rationale=c.llm_rationale,
        is_llm_focused=c.is_llm_focused,
        academic_depth=c.academic_depth,
        suggested_kind=c.suggested_kind,
        status=c.status,
        source_signal=c.source_signal,
    )


@router.get("/candidates")
def list_candidates(
    db: Session = Depends(get_db),
    status: str = Query("pending", pattern="^(pending|promoted|rejected)$"),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """Discovery queue. Sorted by signal_score, LLM-focused first.

    Frontend uses this to render the SourcesDrawer "Discovery (N)" section.
    """
    rows = db.execute(
        select(SourceCandidate)
        .where(SourceCandidate.status == status)
        .order_by(
            SourceCandidate.is_llm_focused.desc(),
            SourceCandidate.signal_score.desc(),
        )
        .limit(limit)
    ).scalars().all()
    total = db.execute(
        select(SourceCandidate).where(SourceCandidate.status == status)
    ).scalars().all()
    return {
        "candidates": [_to_out(c) for c in rows],
        "total": len(total),
    }


class PromoteIn(BaseModel):
    kind: Optional[str] = Field(None, pattern="^(rss|html|arxiv|github)$")


@router.post("/candidates/{candidate_id}/promote")
def promote(
    candidate_id: uuid.UUID,
    payload: PromoteIn = Body(default_factory=PromoteIn),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        src = promote_candidate(db, candidate_id, kind=payload.kind)
    except Exception as e:
        raise HTTPException(422, detail={"message": str(e)})
    return {
        "ok": True,
        "source_id": str(src.id),
        "name": src.name,
        "url": src.url,
    }


@router.post("/candidates/{candidate_id}/reject")
def reject(candidate_id: uuid.UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    reject_candidate(db, candidate_id)
    return {"ok": True}
