from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.routes.items import _to_out
from app.core.db import get_db
from app.models.item import Item
from app.models.security_score import SecurityItemScore
from app.schemas.security import (
    SecurityBucketOut,
    SecurityItemList,
    SecurityItemOut,
    SecurityScoreBucketOut,
    SecurityScoreOut,
    SecuritySoftArticleOut,
    SecurityStatsOut,
)

router = APIRouter(prefix="/security", tags=["security"])

_SECTIONS = {
    "all",
    "exploited_now",
    "new_important_cves",
    "real_attack_cases",
    "technical_analysis",
    "vendor_advisories",
    "oss_package_vulnerabilities",
}


@router.get("/hot", response_model=list[SecurityItemOut])
def security_hot(
    db: Session = Depends(get_db),
    limit: int = Query(10, ge=1, le=50),
):
    rows = _load_scores(db, section="all")
    groups = [g for g in _group_scores(rows) if _hot_eligible(g)]
    groups.sort(key=_hot_sort_key, reverse=True)
    return [_group_to_out(g) for g in groups[:limit]]


@router.get("/items", response_model=SecurityItemList)
def security_items(
    db: Session = Depends(get_db),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    section: str = Query("all"),
    sort: str = Query("score_desc", pattern="^(score_desc|hot_desc|date_desc)$"),
):
    if section not in _SECTIONS:
        raise HTTPException(400, f"unknown security section: {section}")

    groups = _group_scores(_load_scores(db, section=section))
    if sort == "hot_desc":
        groups.sort(key=_hot_sort_key, reverse=True)
    elif sort == "date_desc":
        groups.sort(key=_date_sort_key, reverse=True)
    else:
        groups.sort(key=_score_sort_key, reverse=True)

    total = len(groups)
    page = groups[offset:offset + limit]
    return SecurityItemList(
        items=[_group_to_out(g) for g in page],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=SecurityStatsOut)
def security_stats(db: Session = Depends(get_db)):
    total = db.execute(select(func.count()).select_from(SecurityItemScore)).scalar_one()
    accepted = db.execute(
        select(func.count())
        .select_from(SecurityItemScore)
        .where(SecurityItemScore.accepted.is_(True))
    ).scalar_one()
    rejected = max(int(total) - int(accepted), 0)
    version = db.execute(
        select(SecurityItemScore.score_version)
        .order_by(SecurityItemScore.computed_at.desc())
        .limit(1)
    ).scalar_one_or_none() or "security-v1"

    reject_rows = db.execute(
        select(SecurityItemScore.reject_reason, func.count())
        .where(SecurityItemScore.accepted.is_(False))
        .group_by(SecurityItemScore.reject_reason)
        .order_by(func.count().desc(), SecurityItemScore.reject_reason)
    ).all()

    section_rows = db.execute(
        select(SecurityItemScore.section, func.count())
        .where(SecurityItemScore.accepted.is_(True))
        .group_by(SecurityItemScore.section)
        .order_by(func.count().desc(), SecurityItemScore.section)
    ).all()

    score_values = db.execute(select(SecurityItemScore.final_security_score)).scalars().all()
    buckets = _score_buckets([float(x or 0.0) for x in score_values])

    soft_rows = db.execute(
        select(SecurityItemScore)
        .join(SecurityItemScore.item)
        .options(
            selectinload(SecurityItemScore.item).selectinload(Item.tags),
            selectinload(SecurityItemScore.item).selectinload(Item.source),
        )
        .where(SecurityItemScore.accepted.is_(False))
        .where(SecurityItemScore.soft_article_score > 0)
        .order_by(
            SecurityItemScore.soft_article_score.desc(),
            SecurityItemScore.evidence_score.asc(),
            SecurityItemScore.final_security_score.asc(),
        )
        .limit(10)
    ).scalars().unique().all()

    return SecurityStatsOut(
        score_version=version,
        total_scored=int(total),
        accepted=int(accepted),
        rejected=rejected,
        accept_rate=round((int(accepted) / int(total)) if total else 0.0, 4),
        reject_reasons=[
            SecurityBucketOut(key=reason or "unknown", count=int(count))
            for reason, count in reject_rows
        ],
        sections=[
            SecurityBucketOut(key=section or "all", count=int(count))
            for section, count in section_rows
        ],
        score_distribution=buckets,
        soft_article_top=[
            SecuritySoftArticleOut(
                item=_to_out(row.item),
                reject_reason=row.reject_reason,
                soft_article_score=row.soft_article_score,
                evidence_score=row.evidence_score,
                final_security_score=row.final_security_score,
                badges=[str(x) for x in (row.badges or [])],
                why_ranked=[str(x) for x in (row.why_ranked or [])],
            )
            for row in soft_rows
        ],
    )


def _load_scores(db: Session, *, section: str) -> list[SecurityItemScore]:
    stmt = (
        select(SecurityItemScore)
        .join(SecurityItemScore.item)
        .options(
            selectinload(SecurityItemScore.item).selectinload(Item.tags),
            selectinload(SecurityItemScore.item).selectinload(Item.source),
        )
        .where(SecurityItemScore.accepted.is_(True))
        .where(Item.is_canonical.is_(True))
    )
    if section != "all":
        stmt = stmt.where(SecurityItemScore.section == section)
    stmt = stmt.order_by(
        SecurityItemScore.final_security_score.desc(),
        SecurityItemScore.event_time.desc().nulls_last(),
        SecurityItemScore.group_key.asc(),
    )
    return db.execute(stmt).scalars().unique().all()


def _group_scores(rows: list[SecurityItemScore]) -> list[dict[str, Any]]:
    by_key: dict[str, list[SecurityItemScore]] = {}
    for row in rows:
        by_key.setdefault(row.group_key, []).append(row)

    now = datetime.now(timezone.utc)
    groups: list[dict[str, Any]] = []
    for group_key, scores in by_key.items():
        rep = max(scores, key=lambda s: (
            s.final_security_score or 0.0,
            s.source_authority_score or 0.0,
            _event_sort_value(s.event_time),
        ))
        labels = _dedupe(label for score in scores for label in _source_labels(score.item))
        matched_titles = _dedupe(score.item.title for score in scores if score.item)
        support_count = max(
            len(scores),
            len(labels),
            sum(max(score.item.exposure_count or 1, 1) for score in scores if score.item),
        )
        additional_authoritative_sources = max(0, len(labels) - 1)
        recent_sources = sum(
            1
            for score in scores
            if score.event_time and _ensure_tz(score.event_time) >= now - timedelta(days=7)
        )
        group_final = min(
            1.0,
            max(score.final_security_score or 0.0 for score in scores)
            + min(0.06, 0.015 * additional_authoritative_sources),
        )
        group_hot = min(
            1.0,
            max(score.security_hot_score or 0.0 for score in scores)
            + min(0.05, 0.0125 * max(0, recent_sources - 1)),
        )
        groups.append(
            {
                "group_key": group_key,
                "rep": rep,
                "scores": scores,
                "final": round(group_final, 4),
                "hot": round(group_hot, 4),
                "sources": labels,
                "source_count": max(1, len(labels)),
                "support_count": support_count,
                "matched_titles": matched_titles[:5],
            }
        )
    return groups


def _hot_eligible(group: dict[str, Any]) -> bool:
    rep: SecurityItemScore = group["rep"]
    features = rep.features or {}
    return bool(
        (rep.final_security_score >= 0.55 and rep.evidence_score >= 0.45)
        or features.get("cisa_kev_match")
        or rep.exploitation_score >= 0.85
    )


def _score_sort_key(group: dict[str, Any]) -> tuple:
    rep: SecurityItemScore = group["rep"]
    return (
        group["final"],
        _event_sort_value(rep.event_time),
        _reverse_alpha_key(group["group_key"]),
    )


def _hot_sort_key(group: dict[str, Any]) -> tuple:
    rep: SecurityItemScore = group["rep"]
    return (
        group["hot"],
        group["final"],
        rep.exploitation_score or 0.0,
        rep.evidence_score or 0.0,
        _event_sort_value(rep.event_time),
        _reverse_alpha_key(group["group_key"]),
    )


def _date_sort_key(group: dict[str, Any]) -> tuple:
    rep: SecurityItemScore = group["rep"]
    return (
        _event_sort_value(rep.event_time),
        group["final"],
        rep.evidence_score or 0.0,
    )


def _group_to_out(group: dict[str, Any]) -> SecurityItemOut:
    rep: SecurityItemScore = group["rep"]
    score = _score_out(rep, final_score=group["final"], hot_score=group["hot"])
    score.source_chain = _dedupe(
        label for row in group["scores"] for label in (row.source_chain or [])
    )
    return SecurityItemOut(
        item=_to_out(rep.item),
        security=score,
        support_count=group["support_count"],
        source_count=group["source_count"],
        sources=group["sources"][:8],
        matched_titles=group["matched_titles"],
    )


def _score_out(
    row: SecurityItemScore,
    *,
    final_score: float | None = None,
    hot_score: float | None = None,
) -> SecurityScoreOut:
    return SecurityScoreOut(
        accepted=row.accepted,
        reject_reason=row.reject_reason,
        score_version=row.score_version,
        group_key=row.group_key,
        section=row.section,
        event_time=row.event_time,
        security_relevance_score=row.security_relevance_score,
        evidence_score=row.evidence_score,
        exploitation_score=row.exploitation_score,
        content_quality_score=row.content_quality_score,
        impact_score=row.impact_score,
        actionability_score=row.actionability_score,
        source_authority_score=row.source_authority_score,
        freshness_score=row.freshness_score,
        corroboration_score=row.corroboration_score,
        soft_article_score=row.soft_article_score,
        final_security_score=final_score if final_score is not None else row.final_security_score,
        security_hot_score=hot_score if hot_score is not None else row.security_hot_score,
        badges=[str(x) for x in (row.badges or [])],
        why_ranked=[str(x) for x in (row.why_ranked or [])],
        source_chain=[str(x) for x in (row.source_chain or [])],
    )


def _source_labels(item: Item) -> list[str]:
    labels = [str(x) for x in (item.exposure_sources or []) if str(x)]
    if item.lab:
        labels.append(item.lab)
    if item.source:
        labels.append(item.source.name)
    return _dedupe(labels) or ["unknown"]


def _dedupe(values) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        key = text.lower()
        if text and key not in seen:
            out.append(text)
            seen.add(key)
    return out


def _event_sort_value(value: datetime | None) -> float:
    if value is None:
        return 0.0
    return _ensure_tz(value).timestamp()


def _ensure_tz(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _reverse_alpha_key(value: str) -> tuple[int, ...]:
    return tuple(255 - ord(c) for c in value[:128])


def _score_buckets(values: list[float]) -> list[SecurityScoreBucketOut]:
    ranges = [
        ("0.00-0.20", 0.0, 0.2),
        ("0.20-0.40", 0.2, 0.4),
        ("0.40-0.60", 0.4, 0.6),
        ("0.60-0.80", 0.6, 0.8),
        ("0.80-1.00", 0.8, 1.0),
    ]
    out: list[SecurityScoreBucketOut] = []
    for label, lo, hi in ranges:
        if hi >= 1.0:
            count = sum(1 for value in values if lo <= value <= hi)
        else:
            count = sum(1 for value in values if lo <= value < hi)
        out.append(
            SecurityScoreBucketOut(
                bucket=label,
                min_score=lo,
                max_score=hi,
                count=count,
            )
        )
    return out
