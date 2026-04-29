"""Source = anywhere we can pull items from (an RSS feed, an arXiv category, etc.)."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class SourceKind(str, enum.Enum):
    arxiv = "arxiv"
    rss = "rss"
    html = "html"
    github = "github"


class SourceStatus(str, enum.Enum):
    active = "active"
    probation = "probation"
    paused = "paused"


class HealthStatus(str, enum.Enum):
    ok = "ok"
    degraded = "degraded"
    broken = "broken"
    unknown = "unknown"


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    kind: Mapped[SourceKind] = mapped_column(Enum(SourceKind, name="source_kind"), nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    lab: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    trust_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    health_status: Mapped[HealthStatus] = mapped_column(
        Enum(HealthStatus, name="health_status"), default=HealthStatus.unknown, nullable=False
    )
    status: Mapped[SourceStatus] = mapped_column(
        Enum(SourceStatus, name="source_status"), default=SourceStatus.active, nullable=False
    )
    failure_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    last_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    items = relationship("Item", back_populates="source", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Source {self.kind.value}:{self.name}>"
