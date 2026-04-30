from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.contribute import ContributeError, contribute_url

router = APIRouter(prefix="/contribute", tags=["contribute"])


class ContributeIn(BaseModel):
    url: str = Field(..., min_length=4, max_length=2048)


@router.post("")
def contribute(payload: ContributeIn = Body(...), db: Session = Depends(get_db)):
    try:
        result = contribute_url(db, payload.url)
    except ContributeError as e:
        # 422 = correctable user input. Body carries a human hint.
        raise HTTPException(
            status_code=422,
            detail={"message": str(e), "hint": e.hint},
        )
    return result
