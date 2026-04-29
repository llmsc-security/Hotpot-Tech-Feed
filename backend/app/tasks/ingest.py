"""Ingest pipeline: fetch from a source, normalize, dedup, persist.

Usable both from Celery (via @celery_app.task) and synchronously from the CLI.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters import get_adapter
from app.core.celery_app import celery_app
from app.core.db import session_scope
from app.core.logging import get_logger
from app.models.item import Item
from app.models.source import HealthStatus, Source, SourceKind, SourceStatus
from app.schemas.item import RawItem
from app.services import dedup
from app.services.canonicalize import canonicalize_url
from app.tasks.enrich import enrich_item

log = get_logger(__name__)


def ingest_source(db: Session, source: Source) -> dict:
    """Pull a single source. Returns counts: {fetched, new, dup, errors}."""
    adapter = get_adapter(source)
    counts = {"fetched": 0, "new": 0, "dup": 0, "errors": 0}
    try:
        raw_items: list[RawItem] = list(adapter.fetch())
    except Exception as e:
        log.warning("fetch failed", source=source.name, err=str(e))
        source.failure_streak += 1
        if source.failure_streak >= 5:
            source.health_status = HealthStatus.broken
        else:
            source.health_status = HealthStatus.degraded
        counts["errors"] = 1
        return counts

    counts["fetched"] = len(raw_items)
    source.failure_streak = 0
    source.health_status = HealthStatus.ok
    source.last_fetched_at = datetime.now(timezone.utc)

    for raw in raw_items:
        canonical = canonicalize_url(raw.url)
        try:
            target = dedup.find_dedup_target(db, raw, canonical)
        except Exception as e:  # pragma: no cover
            log.warning("dedup failed", url=canonical, err=str(e))
            target = None

        if target is not None:
            # Same content, different URL: collapse into the existing dedup group.
            if target.dedup_group_id is None:
                target.dedup_group_id = uuid.uuid4()
            counts["dup"] += 1
            continue

        item = Item(
            source_id=source.id,
            canonical_url=canonical,
            title=raw.title[:1024],
            authors=raw.authors,
            published_at=raw.published_at,
            language=raw.language,
            excerpt=raw.excerpt,
            content_type=raw.content_type,
            lab=raw.lab,
            venue=raw.venue,
            is_canonical=True,
        )
        db.add(item)
        db.flush()
        counts["new"] += 1
        try:
            enrich_item(db, item)
        except Exception as e:  # pragma: no cover — enrichment is best-effort
            log.warning("enrichment failed", item_id=str(item.id), err=str(e))

    return counts


# ---------- Celery entry points ----------

@celery_app.task(name="app.tasks.ingest.ingest_source_id")
def ingest_source_id(source_id: str) -> dict:
    with session_scope() as db:
        source = db.get(Source, uuid.UUID(source_id))
        if not source or source.status == SourceStatus.paused:
            return {"skipped": True}
        return ingest_source(db, source)


@celery_app.task(name="app.tasks.ingest.ingest_kind")
def ingest_kind(kind: str) -> dict:
    """Fetch every active source of a given kind."""
    aggregate = {"sources": 0, "fetched": 0, "new": 0, "dup": 0, "errors": 0}
    with session_scope() as db:
        sources = db.execute(
            select(Source).where(
                Source.kind == SourceKind(kind),
                Source.status != SourceStatus.paused,
            )
        ).scalars().all()
        for s in sources:
            counts = ingest_source(db, s)
            aggregate["sources"] += 1
            for k in ("fetched", "new", "dup", "errors"):
                aggregate[k] += counts.get(k, 0)
    return aggregate


def ingest_all_sync() -> dict:
    """Synchronous full run — what the CLI calls."""
    aggregate = {"sources": 0, "fetched": 0, "new": 0, "dup": 0, "errors": 0}
    with session_scope() as db:
        sources = db.execute(
            select(Source).where(Source.status != SourceStatus.paused)
        ).scalars().all()
        for s in sources:
            log.info("ingesting", source=s.name, kind=s.kind.value)
            counts = ingest_source(db, s)
            aggregate["sources"] += 1
            for k in ("fetched", "new", "dup", "errors"):
                aggregate[k] += counts.get(k, 0)
    return aggregate
