from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.item import ItemOut


class SecurityScoreOut(BaseModel):
    accepted: bool
    reject_reason: str | None = None
    score_version: str
    group_key: str
    section: str
    event_time: datetime | None = None

    security_relevance_score: float
    evidence_score: float
    exploitation_score: float
    content_quality_score: float
    impact_score: float
    actionability_score: float
    source_authority_score: float
    freshness_score: float
    corroboration_score: float
    soft_article_score: float
    final_security_score: float
    security_hot_score: float

    badges: list[str] = Field(default_factory=list)
    why_ranked: list[str] = Field(default_factory=list)
    source_chain: list[str] = Field(default_factory=list)


class SecurityItemOut(BaseModel):
    item: ItemOut
    security: SecurityScoreOut
    support_count: int = 1
    source_count: int = 1
    sources: list[str] = Field(default_factory=list)
    matched_titles: list[str] = Field(default_factory=list)


class SecurityItemList(BaseModel):
    items: list[SecurityItemOut]
    total: int
    limit: int
    offset: int


class SecurityBucketOut(BaseModel):
    key: str
    count: int


class SecurityScoreBucketOut(BaseModel):
    bucket: str
    min_score: float
    max_score: float
    count: int


class SecuritySoftArticleOut(BaseModel):
    item: ItemOut
    reject_reason: str | None = None
    soft_article_score: float
    evidence_score: float
    final_security_score: float
    badges: list[str] = Field(default_factory=list)
    why_ranked: list[str] = Field(default_factory=list)


class SecurityStatsOut(BaseModel):
    score_version: str
    total_scored: int
    accepted: int
    rejected: int
    accept_rate: float
    reject_reasons: list[SecurityBucketOut] = Field(default_factory=list)
    sections: list[SecurityBucketOut] = Field(default_factory=list)
    score_distribution: list[SecurityScoreBucketOut] = Field(default_factory=list)
    soft_article_top: list[SecuritySoftArticleOut] = Field(default_factory=list)
