from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.item import ContentType


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tag: str
    confidence: float
    source: str


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    source_name: Optional[str] = None
    canonical_url: str
    title: str
    authors: list[str] = Field(default_factory=list)
    published_at: Optional[datetime]
    fetched_at: datetime
    language: str
    excerpt: Optional[str]
    content_type: ContentType
    primary_category: Optional[str] = None
    lab: Optional[str]
    venue: Optional[str]
    summary: Optional[str]
    commentary: Optional[str]
    score: float
    click_count: int = 0
    exposure_count: int = 1
    exposure_sources: list[str] = Field(default_factory=list)
    tags: list[TagOut] = Field(default_factory=list)


class ItemList(BaseModel):
    items: list[ItemOut]
    total: int
    limit: int
    offset: int


class HotItemOut(BaseModel):
    item: ItemOut
    hot_score: float
    support_count: int
    source_count: int
    sources: list[str] = Field(default_factory=list)
    topic: str
    matched_titles: list[str] = Field(default_factory=list)


class RawItem(BaseModel):
    """What an adapter returns before normalization."""
    source_id: uuid.UUID
    url: str
    title: str
    authors: list[str] = Field(default_factory=list)
    published_at: Optional[datetime] = None
    language: str = "en"
    excerpt: Optional[str] = None
    raw_html: Optional[str] = None
    content_type: ContentType = ContentType.other
    lab: Optional[str] = None
    venue: Optional[str] = None
    extra: dict = Field(default_factory=dict)
