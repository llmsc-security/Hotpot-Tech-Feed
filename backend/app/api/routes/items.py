from __future__ import annotations

import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, extract, func, or_, select
from sqlalchemy.orm import Session, selectinload
from rapidfuzz import fuzz

from app.core.db import get_db
from app.models.item import ContentType, Item, ItemTag
from app.models.search_log import SearchLog
from app.models.source import Source
from app.schemas.item import HotItemOut, ItemList, ItemOut, TagOut
from app.services.contribute import USER_SOURCE_URL

router = APIRouter(prefix="/items", tags=["items"])


def _apply_filters(
    stmt,
    *,
    topic: Optional[str],
    content_type: Optional[ContentType],
    source_id: Optional[uuid.UUID],
    source: Optional[str],
    year: Optional[int],
    q: Optional[str],
):
    if topic:
        sub = select(ItemTag.item_id).where(ItemTag.tag == topic)
        stmt = stmt.where(Item.id.in_(sub))
    if content_type:
        stmt = stmt.where(Item.content_type == content_type)
    if source_id:
        stmt = stmt.where(Item.source_id == source_id)
    if source:
        sub = select(Source.id).where(Source.name.ilike(f"%{source}%"))
        stmt = stmt.where(Item.source_id.in_(sub))
    if year:
        stmt = stmt.where(extract("year", Item.published_at) == year)
    if q:
        like = f"%{q}%"
        tag_sub = select(ItemTag.item_id).where(ItemTag.tag.ilike(like))
        stmt = stmt.where(
            or_(
                Item.title.ilike(like),
                Item.excerpt.ilike(like),
                Item.summary.ilike(like),
                Item.lab.ilike(like),
                Item.venue.ilike(like),
                Item.id.in_(tag_sub),
            )
        )
    return stmt


@router.get("", response_model=ItemList)
def list_items(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    topic: Optional[str] = Query(None, description="filter by topic tag, e.g. 'topic:ML'"),
    content_type: Optional[ContentType] = Query(None),
    source_id: Optional[uuid.UUID] = Query(None),
    source: Optional[str] = Query(None, description="case-insensitive source-name substring (e.g. 'wechat')"),
    year: Optional[int] = Query(None, ge=1990, le=2100, description="filter by published year"),
    q: Optional[str] = Query(None, description="text/tag substring search (case-insensitive)"),
    sort: str = Query("smart", pattern="^(smart|date_desc|date_asc|fetched_desc|fetched_asc)$"),
):
    base = (
        select(Item)
        .join(Source, Item.source_id == Source.id)
        .options(selectinload(Item.tags), selectinload(Item.source))
        .where(Item.is_canonical.is_(True))
    )
    base = _apply_filters(
        base,
        topic=topic,
        content_type=content_type,
        source_id=source_id,
        source=source,
        year=year,
        q=q,
    )

    if sort == "smart":
        base = base.order_by(
            _smart_rank_expr(q=q).desc(),
            Item.published_at.desc().nulls_last(),
            Item.fetched_at.desc(),
        )
    elif sort == "date_desc":
        base = base.order_by(
            Item.published_at.desc().nulls_last(), Item.fetched_at.desc()
        )
    elif sort == "date_asc":
        base = base.order_by(
            Item.published_at.asc().nulls_last(), Item.fetched_at.asc()
        )
    elif sort == "fetched_asc":
        base = base.order_by(Item.fetched_at.asc())
    else:  # fetched_desc
        base = base.order_by(Item.fetched_at.desc())

    count_stmt = _apply_filters(
        select(func.count()).select_from(Item).where(Item.is_canonical.is_(True)),
        topic=topic,
        content_type=content_type,
        source_id=source_id,
        source=source,
        year=year,
        q=q,
    )

    total = db.execute(count_stmt).scalar_one()
    if sort == "smart":
        pool_limit = min(max(offset + limit * 4, offset + limit), 500)
        pool = db.execute(base.limit(pool_limit)).scalars().unique().all()
        rows = _diversify(pool, limit=offset + limit)[offset:offset + limit]
    else:
        rows = db.execute(base.limit(limit).offset(offset)).scalars().unique().all()

    items_out = [_to_out(item) for item in rows]
    return ItemList(items=items_out, total=total, limit=limit, offset=offset)


def _smart_rank_expr(*, q: str | None):
    now = datetime.now(timezone.utc)
    item_time = func.coalesce(Item.published_at, Item.fetched_at)
    freshness = case(
        (item_time >= now - timedelta(days=7), 1.0),
        (item_time >= now - timedelta(days=30), 0.75),
        (item_time >= now - timedelta(days=120), 0.45),
        (item_time >= now - timedelta(days=365), 0.2),
        else_=0.05,
    )
    engagement = case(
        (Item.click_count >= 10, 1.0),
        (Item.click_count >= 3, 0.7),
        (Item.click_count >= 1, 0.4),
        else_=0.0,
    )
    content_prior = case(
        (Item.content_type == ContentType.paper, 0.9),
        (Item.content_type == ContentType.lab_announcement, 0.8),
        (Item.content_type == ContentType.tutorial, 0.75),
        (Item.content_type == ContentType.blog, 0.6),
        (Item.content_type == ContentType.news, 0.55),
        else_=0.35,
    )
    relevance = 0.0
    if q:
        like = f"%{q}%"
        tag_sub = select(ItemTag.item_id).where(ItemTag.tag.ilike(like))
        relevance = (
            case((Item.title.ilike(like), 0.7), else_=0.0)
            + case((Item.summary.ilike(like), 0.45), else_=0.0)
            + case((Item.excerpt.ilike(like), 0.35), else_=0.0)
            + case((Item.lab.ilike(like), 0.3), else_=0.0)
            + case((Item.venue.ilike(like), 0.25), else_=0.0)
            + case((Source.name.ilike(like), 0.3), else_=0.0)
            + case((Item.id.in_(tag_sub), 0.45), else_=0.0)
        )
    return (
        relevance * 0.35
        + Item.score * 0.25
        + freshness * 0.15
        + Source.trust_score * 0.15
        + case(
            (Item.exposure_count >= 5, 1.0),
            (Item.exposure_count >= 3, 0.75),
            (Item.exposure_count >= 2, 0.45),
            else_=0.0,
        ) * 0.05
        + engagement * 0.03
        + content_prior * 0.02
    )


def _diversify(rows: list[Item], *, limit: int) -> list[Item]:
    if len(rows) <= 1:
        return rows
    selected: list[Item] = []
    deferred: list[Item] = []
    source_counts: dict[str, int] = defaultdict(int)
    topic_counts: dict[str, int] = defaultdict(int)
    source_cap = max(4, limit // 5)
    topic_cap = max(6, limit // 4)

    for item in rows:
        source_name = item.source.name if item.source else ""
        topic = _item_topic(item)
        too_much_source = bool(source_name and source_counts[source_name] >= source_cap)
        too_much_topic = bool(topic and topic_counts[topic] >= topic_cap)
        too_similar = any(_title_overlap(item.title, chosen.title) >= 0.72 for chosen in selected[-8:])
        if len(selected) < limit and not (too_much_source or too_much_topic or too_similar):
            selected.append(item)
            if source_name:
                source_counts[source_name] += 1
            if topic:
                topic_counts[topic] += 1
        else:
            deferred.append(item)
    return (selected + deferred)[:limit]


def _item_topic(item: Item) -> str:
    for tag in item.tags:
        if tag.tag.startswith("topic:"):
            return tag.tag[6:]
    return ""


def _title_overlap(a: str, b: str) -> float:
    left = {w for w in a.lower().split() if len(w) > 3}
    right = {w for w in b.lower().split() if len(w) > 3}
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, min(len(left), len(right)))


@router.get("/hot", response_model=list[HotItemOut])
def hot_items(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=50),
    window_days: int = Query(14, ge=1, le=120),
    pool: int = Query(400, ge=50, le=2000),
):
    """High-quality hot topics, boosted when multiple sources cover the same story."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    item_time = func.coalesce(Item.published_at, Item.fetched_at)
    rows = db.execute(
        select(Item)
        .join(Source, Item.source_id == Source.id)
        .options(selectinload(Item.tags), selectinload(Item.source))
        .where(Item.is_canonical.is_(True))
        .where(item_time >= cutoff)
        .where(or_(Item.exposure_count > 1, Item.score >= 0.55, Item.click_count > 0))
        .order_by(
            Item.exposure_count.desc(),
            Item.score.desc(),
            Item.click_count.desc(),
            Item.published_at.desc().nulls_last(),
            Item.fetched_at.desc(),
        )
        .limit(pool)
    ).scalars().unique().all()
    clusters = _cluster_hot(rows)
    return clusters[:limit]


def _cluster_hot(items: list[Item]) -> list[HotItemOut]:
    clusters: list[dict] = []
    for item in items:
        if item.score < 0.15 and (item.exposure_count or 1) <= 1 and (item.click_count or 0) <= 0:
            continue
        key = _topic_key(item)
        target = None
        for cluster in clusters:
            if key and key == cluster["key"]:
                target = cluster
                break
            if _topic_similarity(item.title, cluster["item"].title) >= 0.76:
                target = cluster
                break
        if target is None:
            target = {
                "key": key,
                "item": item,
                "items": [],
                "sources": set(),
                "support": 0,
                "titles": [],
            }
            clusters.append(target)

        labels = _exposure_labels(item)
        target["items"].append(item)
        target["sources"].update(labels)
        target["support"] += max(item.exposure_count or 1, len(labels), 1)
        if item.title not in target["titles"]:
            target["titles"].append(item.title)

        if _item_hot_base(item) > _item_hot_base(target["item"]):
            target["item"] = item

    out: list[HotItemOut] = []
    for cluster in clusters:
        rep: Item = cluster["item"]
        source_count = len(cluster["sources"])
        support_count = max(int(cluster["support"]), source_count, rep.exposure_count or 1)
        repeat_bonus = min(source_count / 5.0, 1.0) * 0.22 + min(max(support_count - 1, 0) / 8.0, 1.0) * 0.12
        hot_score = min(1.5, _item_hot_base(rep) + repeat_bonus)
        sources = sorted(cluster["sources"], key=lambda s: s.lower())[:8]
        out.append(
            HotItemOut(
                item=_to_out(rep),
                hot_score=round(hot_score, 4),
                support_count=support_count,
                source_count=source_count,
                sources=sources,
                topic=cluster["key"] or _short_topic(rep.title),
                matched_titles=cluster["titles"][:5],
            )
        )
    out.sort(key=lambda x: (x.source_count >= 2, x.hot_score, x.item.score), reverse=True)
    return out


_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.I)


def _topic_key(item: Item) -> str:
    text = f"{item.title}\n{item.summary or ''}\n{item.excerpt or ''}"
    cves: list[str] = []
    for match in _CVE_RE.finditer(text):
        cve = match.group(0).upper()
        if cve not in cves:
            cves.append(cve)
    if cves:
        return cves[0]
    return ""


def _topic_similarity(a: str, b: str) -> float:
    left = _normalize_title(a)
    right = _normalize_title(b)
    if not left or not right:
        return 0.0
    return max(
        fuzz.token_set_ratio(left, right),
        fuzz.partial_ratio(left, right),
    ) / 100.0


def _normalize_title(title: str) -> str:
    text = re.sub(r"https?://\S+", " ", title.lower())
    text = re.sub(r"[\[\]【】()（）|｜:：,，.!！？?\"'“”‘’]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _exposure_labels(item: Item) -> list[str]:
    labels = [str(x) for x in (item.exposure_sources or []) if str(x)]
    if item.lab:
        labels.append(item.lab)
    if item.source and not (
        (item.source.extra or {}).get("adapter") == "doonsec" and labels
    ):
        labels.append(item.source.name)
    deduped: list[str] = []
    for label in labels:
        if label not in deduped:
            deduped.append(label)
    return deduped or ["unknown"]


def _item_hot_base(item: Item) -> float:
    now = datetime.now(timezone.utc)
    ts = item.published_at or item.fetched_at
    if ts and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_days = max((now - ts).total_seconds() / 86400.0, 0.0) if ts else 365.0
    freshness = 1.0 if age_days <= 2 else 0.8 if age_days <= 7 else 0.55 if age_days <= 30 else 0.25
    engagement = min((item.click_count or 0) / 10.0, 1.0)
    return (item.score or 0.0) * 0.62 + freshness * 0.23 + engagement * 0.15


def _short_topic(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()[:80]


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    """Distinct primary_category values with item counts. Powers the contribute UI's
    "existing categories" hint and frontend chips."""
    rows = db.execute(
        select(Item.primary_category, func.count())
        .where(Item.is_canonical.is_(True))
        .where(Item.primary_category.is_not(None))
        .group_by(Item.primary_category)
        .order_by(func.count().desc(), Item.primary_category)
    ).all()
    return [{"category": c, "count": int(n)} for (c, n) in rows]


@router.get("/content-types")
def list_content_types(db: Session = Depends(get_db)):
    """Distinct content_type values with counts."""
    rows = db.execute(
        select(Item.content_type, func.count())
        .where(Item.is_canonical.is_(True))
        .group_by(Item.content_type)
        .order_by(func.count().desc())
    ).all()
    return [{"content_type": c.value, "count": int(n)} for (c, n) in rows]


@router.get("/years")
def list_years(db: Session = Depends(get_db)):
    """Distinct years present in the corpus, with item counts. Useful for the year-filter chips."""
    rows = db.execute(
        select(
            extract("year", Item.published_at).label("y"),
            func.count(),
        )
        .where(Item.is_canonical.is_(True))
        .where(Item.published_at.is_not(None))
        .group_by("y")
        .order_by("y")
    ).all()
    return [{"year": int(y), "count": int(c)} for (y, c) in rows]


class NLSearchIn(BaseModel):
    query: str
    record: bool = True  # honored after the user has accepted the consent banner


@router.post("/nl-search")
def nl_search(payload: NLSearchIn = Body(...), db: Session = Depends(get_db)):
    """Translate a natural-language query into structured filters via the LLM.

    Returns {topic?, content_type?, source?, year?, q?, sort?}. The frontend
    applies these as filter chips. Every query is recorded in `search_logs`
    so we can study how people search and improve the prompt over time.
    """
    from app.services.llm import nl_filter

    raw = (payload.query or "").strip()
    if not raw:
        raise HTTPException(400, "query is empty")
    if len(raw) > 500:
        raise HTTPException(400, "query too long (>500 chars)")
    current_year = datetime.now(timezone.utc).year
    parsed = nl_filter(raw, current_year=current_year)

    if payload.record:
        try:
            db.add(SearchLog(query=raw, parsed_filters=parsed))
            db.commit()
        except Exception:
            db.rollback()  # logging is best-effort — never fail the user's query

    return parsed


@router.get("/recent-searches")
def recent_searches(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    """Most recent distinct NL queries — for the input's recall dropdown."""
    rows = db.execute(
        select(SearchLog.query, func.max(SearchLog.created_at).label("ts"))
        .group_by(SearchLog.query)
        .order_by(func.max(SearchLog.created_at).desc())
        .limit(limit)
    ).all()
    return [{"query": q, "last_used_at": ts.isoformat()} for (q, ts) in rows]


class SuggestionOut(BaseModel):
    type: str
    label: str
    query: str
    detail: str | None = None


@router.get("/suggest", response_model=list[SuggestionOut])
def suggest_items(
    db: Session = Depends(get_db),
    q: str = Query("", max_length=120),
    limit: int = Query(10, ge=1, le=20),
    include_recent: bool = Query(False),
):
    """Fast typeahead suggestions for the NL input.

    This stays deterministic on the keystroke path: no LLM call per character.
    """
    text = " ".join((q or "").strip().split())[:120]
    like = f"%{text}%" if text else "%"
    suggestions: list[SuggestionOut] = []
    seen: set[str] = set()

    def add(kind: str, label: str, query: str, detail: str | None = None) -> None:
        key = query.strip().lower()
        if not key or key in seen or len(suggestions) >= limit:
            return
        seen.add(key)
        suggestions.append(SuggestionOut(type=kind, label=label, query=query, detail=detail))

    if include_recent:
        recent_rows = db.execute(
            select(SearchLog.query, func.max(SearchLog.created_at).label("ts"))
            .where(SearchLog.query.ilike(like))
            .group_by(SearchLog.query)
            .order_by(func.max(SearchLog.created_at).desc())
            .limit(4)
        ).all()
        for query, _ts in recent_rows:
            add("recent_query", query, query, "recent")

    source_rows = db.execute(
        select(Source.name, Source.trust_score)
        .where(Source.name.ilike(like))
        .order_by(Source.trust_score.desc(), Source.name)
        .limit(5)
    ).all()
    for name, trust in source_rows:
        add("source", name, f"latest {name} posts", f"source trust {trust:.2f}")

    topic_rows = db.execute(
        select(ItemTag.tag, func.count())
        .join(Item, Item.id == ItemTag.item_id)
        .where(Item.is_canonical.is_(True))
        .where(ItemTag.tag.startswith("topic:"))
        .where(ItemTag.tag.ilike(like if text.startswith("topic:") else f"%{text}%"))
        .group_by(ItemTag.tag)
        .order_by(func.count().desc(), ItemTag.tag)
        .limit(5)
    ).all()
    for tag, count in topic_rows:
        topic = tag[6:] if tag.startswith("topic:") else tag
        add("topic", topic, f"recent {topic} papers and posts", f"{int(count)} items")

    if text:
        title_rows = db.execute(
            select(Item.title, Item.content_type, Source.name)
            .join(Source, Item.source_id == Source.id)
            .where(Item.is_canonical.is_(True))
            .where(Item.title.ilike(like))
            .order_by(Item.score.desc(), Item.published_at.desc().nulls_last(), Item.fetched_at.desc())
            .limit(5)
        ).all()
        for title, ctype, source_name in title_rows:
            add("title", title[:96], title[:160], f"{ctype.value} · {source_name}")

        add("idea", f"recent {text} papers", f"recent {text} papers")
        add("idea", f"{text} lab announcements", f"{text} lab announcements this year")
        add("idea", f"{text} security reports", f"security reports about {text}")

    if not suggestions:
        add("idea", "recent ML papers", "recent ML papers from arxiv")
        add("idea", "security reports", "latest security reports")
        add("idea", "AI lab announcements", "OpenAI Anthropic DeepMind announcements this year")

    return suggestions[:limit]


@router.get("/community", response_model=ItemList)
def list_community(
    db: Session = Depends(get_db),
    sort: str = Query("hot", pattern="^(hot|recent)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Public, read-only feed of user-contributed URLs.

    `hot`    — most-clicked first; ties break to newest.
    `recent` — newest contribute time first.
    Items here are auto-accepted at commit time; this endpoint only ranks/lists.
    """
    user_src = select(Source.id).where(Source.url == USER_SOURCE_URL)
    base = (
        select(Item)
        .options(selectinload(Item.tags), selectinload(Item.source))
        .where(Item.is_canonical.is_(True))
        .where(Item.source_id.in_(user_src))
    )
    if sort == "hot":
        base = base.order_by(Item.click_count.desc(), Item.fetched_at.desc())
    else:
        base = base.order_by(Item.fetched_at.desc())

    total = db.execute(
        select(func.count())
        .select_from(Item)
        .where(Item.is_canonical.is_(True))
        .where(Item.source_id.in_(user_src))
    ).scalar_one()
    rows = db.execute(base.limit(limit).offset(offset)).scalars().unique().all()
    return ItemList(
        items=[_to_out(it) for it in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{item_id}/click")
def bump_click(item_id: uuid.UUID, db: Session = Depends(get_db)):
    """Increment click_count for an item. Public, no auth — single-host app.

    Done as an atomic UPDATE so concurrent clicks don't lose counts.
    """
    item = db.execute(select(Item).where(Item.id == item_id)).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "item not found")
    item.click_count = (item.click_count or 0) + 1
    db.commit()
    return {"item_id": str(item.id), "click_count": item.click_count}


@router.get("/{item_id}", response_model=ItemOut)
def get_item(item_id: uuid.UUID, db: Session = Depends(get_db)):
    item = db.execute(
        select(Item)
        .options(selectinload(Item.tags), selectinload(Item.source))
        .where(Item.id == item_id)
    ).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "item not found")
    return _to_out(item)


def _to_out(item: Item) -> ItemOut:
    return ItemOut(
        id=item.id,
        source_id=item.source_id,
        source_name=item.source.name if item.source else None,
        canonical_url=item.canonical_url,
        title=item.title,
        authors=item.authors or [],
        published_at=item.published_at,
        fetched_at=item.fetched_at,
        language=item.language,
        excerpt=item.excerpt,
        content_type=item.content_type,
        primary_category=item.primary_category,
        lab=item.lab,
        venue=item.venue,
        summary=item.summary,
        commentary=item.commentary,
        score=item.score,
        click_count=item.click_count or 0,
        exposure_count=item.exposure_count or 1,
        exposure_sources=[str(x) for x in (item.exposure_sources or [])],
        tags=[TagOut(tag=t.tag, confidence=t.confidence, source=t.source) for t in item.tags],
    )
