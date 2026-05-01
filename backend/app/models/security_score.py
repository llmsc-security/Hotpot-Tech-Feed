"""Persisted security-specific scores for the /security projection."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class SecurityItemScore(Base):
    __tablename__ = "security_item_scores"
    __table_args__ = (
        Index("ix_security_scores_accepted_final_event", "accepted", "final_security_score", "event_time"),
        Index("ix_security_scores_accepted_hot", "accepted", "security_hot_score"),
        Index("ix_security_scores_section_final", "section", "accepted", "final_security_score"),
        Index("ix_security_scores_group_key", "group_key"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    reject_reason: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    score_version: Mapped[str] = mapped_column(String(32), default="security-v1", nullable=False)

    group_key: Mapped[str] = mapped_column(String(256), nullable=False)
    representative_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    section: Mapped[str] = mapped_column(String(64), default="all", nullable=False, index=True)
    event_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    security_relevance_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    evidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    exploitation_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    content_quality_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    impact_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    actionability_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source_authority_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    freshness_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    corroboration_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    soft_article_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    final_security_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    security_hot_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)

    badges: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    why_ranked: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    source_chain: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    features: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    item = relationship("Item")
