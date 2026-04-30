from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.source import HealthStatus, SourceKind, SourceStatus


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    url: str
    kind: SourceKind
    language: str
    lab: Optional[str]
    trust_score: float
    health_status: HealthStatus
    status: SourceStatus
    last_fetched_at: Optional[datetime]
    item_count: int = 0


class SourceList(BaseModel):
    sources: list[SourceOut]
    total: int
