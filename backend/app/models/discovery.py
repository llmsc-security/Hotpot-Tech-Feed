"""Source-discovery + source-quality models.

source_candidates  — domains we've spotted (via outbound links, user
                     contributions, GitHub trending, HN) but not yet
                     promoted to Source. Reviewable by the user.
source_quality_runs — weekly audit log of trust_score recomputation.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SourceCandidate(Base):
    __tablename__ = "source_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    sample_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    name_hint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    oa_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    mention_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    contributor_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    signal_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    llm_verdict: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    llm_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_llm_focused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    academic_depth: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    suggested_kind: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    suggested_rss_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    promoted_to_source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    source_signal: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


class SourceQualityRun(Base):
    __tablename__ = "source_quality_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ran_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ctr_30d: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    median_clicks_30d: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    item_count_30d: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    llm_noise_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    llm_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trust_score_before: Mapped[float] = mapped_column(Float, nullable=False)
    trust_score_after: Mapped[float] = mapped_column(Float, nullable=False)
    action_taken: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
