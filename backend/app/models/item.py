"""Item = a single piece of content (paper, blog post, news article, ...)."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ContentType(str, enum.Enum):
    paper = "paper"
    blog = "blog"
    news = "news"
    lab_announcement = "lab_announcement"
    tutorial = "tutorial"
    oss_release = "oss_release"
    other = "other"


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        Index("ix_items_published_at", "published_at"),
        Index("ix_items_dedup_group", "dedup_group_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ---- core ----
    canonical_url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    authors: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_html_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # ---- classification ----
    content_type: Mapped[ContentType] = mapped_column(
        Enum(ContentType, name="content_type"), default=ContentType.other, nullable=False
    )
    primary_category: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    lab: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    venue: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # ---- dedup ----
    # Items in the same dedup_group are considered the same content from
    # different sources. The earliest-fetched item in the group is canonical.
    dedup_group_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_canonical: Mapped[bool] = mapped_column(default=True, nullable=False)
    embedding_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # ---- enrichment ----
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    commentary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enriched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ---- ranking signal ----
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    click_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False, index=True
    )
    exposure_count: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False, index=True
    )
    exposure_sources: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    # ---- relationships ----
    source = relationship("Source", back_populates="items")
    tags = relationship("ItemTag", back_populates="item", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Item {self.title[:60]!r}>"


class ItemTag(Base):
    __tablename__ = "item_tags"
    __table_args__ = (
        Index("ix_item_tags_tag", "tag"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="llm", nullable=False)  # llm | user

    item = relationship("Item", back_populates="tags")
