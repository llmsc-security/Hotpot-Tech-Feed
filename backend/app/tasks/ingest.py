"""Ingest pipeline: fetch from a source, normalize, dedup, persist.

Usable both from Celery (via @celery_app.task) and synchronously from the CLI.

Parallelism: per-item enrichment (the LLM-bound bottleneck) runs in a thread
pool with one DB session per worker. Sources can also be fetched concurrently
in `ingest_all_sync_parallel` since each source uses its own session.
"""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters import get_adapter
from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.db import session_scope
from app.core.logging import get_logger
from app.models.item import Item
from app.models.source import HealthStatus, Source, SourceKind, SourceStatus
from app.schemas.item import RawItem
from app.services import dedup
from app.services.canonicalize import canonicalize_url
from app.services.contribute import USER_SOURCE_URL
from app.tasks.enrich import enrich_item

log = get_logger(__name__)


def _is_crawlable_source(source: Source | None) -> bool:
    return bool(
        source
        and source.status != SourceStatus.paused
        and source.url != USER_SOURCE_URL
    )


def _enrich_one(item_id: uuid.UUID) -> bool:
    """Re-open a fresh session and enrich a single item by id. Safe to call from a thread."""
    try:
        with session_scope() as db:
            item = db.get(Item, item_id)
            if item is None:
                return False
            enrich_item(db, item)
            return True
    except Exception as e:  # pragma: no cover — enrichment is best-effort
        log.warning("enrichment failed", item_id=str(item_id), err=str(e))
        return False


def ingest_source(db: Session, source: Source, workers: int | None = None) -> dict:
    """Pull a single source. Returns counts: {fetched, new, dup, errors}.

    Newly-inserted items are enriched in parallel via a thread pool (one DB
    session per worker). The caller's `db` session is committed before
    enrichment so workers can see the rows.
    """
    if workers is None:
        workers = settings.ingest_workers

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

    new_ids: list[uuid.UUID] = []
    for raw in raw_items:
        canonical = canonicalize_url(raw.url)
        try:
            target = dedup.find_dedup_target(db, raw, canonical)
        except Exception as e:  # pragma: no cover
            log.warning("dedup failed", url=canonical, err=str(e))
            target = None

        if target is not None:
            if target.dedup_group_id is None:
                target.dedup_group_id = uuid.uuid4()
            _record_exposure(target, source, raw)
            counts["dup"] += 1
            continue

        exposure_source = _exposure_source(source, raw)
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
            exposure_count=1,
            exposure_sources=[exposure_source] if exposure_source else [],
        )
        db.add(item)
        db.flush()
        counts["new"] += 1
        new_ids.append(item.id)

    # Commit so worker threads (each with their own session) see the new rows.
    db.commit()

    if not new_ids:
        return counts

    if workers and workers > 1 and len(new_ids) > 1:
        log.info("enriching", source=source.name, items=len(new_ids), workers=workers)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(_enrich_one, new_ids))
    else:
        for item_id in new_ids:
            _enrich_one(item_id)

    return counts


def _exposure_source(source: Source, raw: RawItem) -> str:
    """Name the entity that independently exposed the story.

    For normal feeds this is the Source row. For aggregators such as Doonsec,
    the WeChat account carried in the raw item is the useful exposure source.
    """
    if (source.extra or {}).get("adapter") == "doonsec":
        if raw.lab:
            return raw.lab
        if raw.authors:
            return str(raw.authors[0])
    return source.name


def _record_exposure(target: Item, source: Source, raw: RawItem) -> None:
    label = _exposure_source(source, raw)
    if not label:
        return
    sources = _known_exposure_sources(target)
    if label not in sources:
        sources.append(label)
    target.exposure_sources = sources[:20]
    target.exposure_count = max(target.exposure_count or 1, len(sources))


def _known_exposure_sources(target: Item) -> list[str]:
    labels = [str(x) for x in (target.exposure_sources or []) if str(x)]
    if target.lab:
        labels.append(target.lab)
    if target.source and not (
        (target.source.extra or {}).get("adapter") == "doonsec" and labels
    ):
        labels.append(target.source.name)

    deduped: list[str] = []
    for label in labels:
        if label not in deduped:
            deduped.append(label)
    return deduped


# ---------- Celery entry points ----------

@celery_app.task(name="app.tasks.ingest.ingest_source_id")
def ingest_source_id(source_id: str) -> dict:
    with session_scope() as db:
        source = db.get(Source, uuid.UUID(source_id))
        if not _is_crawlable_source(source):
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
                Source.url != USER_SOURCE_URL,
            )
        ).scalars().all()
        for s in sources:
            counts = ingest_source(db, s)
            aggregate["sources"] += 1
            for k in ("fetched", "new", "dup", "errors"):
                aggregate[k] += counts.get(k, 0)
    return aggregate


def _ingest_one_source_id(source_id: uuid.UUID, workers: int) -> dict:
    """Run a full ingest for one source in its own session. Thread-safe."""
    with session_scope() as db:
        source = db.get(Source, source_id)
        if not _is_crawlable_source(source):
            return {"fetched": 0, "new": 0, "dup": 0, "errors": 0}
        log.info("ingesting", source=source.name, kind=source.kind.value)
        return ingest_source(db, source, workers=workers)


def ingest_all_sync(workers: int | None = None, source_workers: int | None = None) -> dict:
    """Synchronous full run — what the CLI calls.

    Parallelism is two-level:
      * `source_workers` sources processed concurrently (each with its own session)
      * Inside each source, `workers` items enriched concurrently
    """
    if workers is None:
        workers = settings.ingest_workers
    if source_workers is None:
        source_workers = settings.ingest_source_workers

    aggregate = {"sources": 0, "fetched": 0, "new": 0, "dup": 0, "errors": 0}

    with session_scope() as db:
        source_ids = [
            sid for (sid,) in db.execute(
                select(Source.id).where(
                    Source.status != SourceStatus.paused,
                    Source.url != USER_SOURCE_URL,
                )
            ).all()
        ]

    if source_workers and source_workers > 1 and len(source_ids) > 1:
        with ThreadPoolExecutor(max_workers=source_workers) as ex:
            futs = [ex.submit(_ingest_one_source_id, sid, workers) for sid in source_ids]
            for fut in as_completed(futs):
                counts = fut.result()
                aggregate["sources"] += 1
                for k in ("fetched", "new", "dup", "errors"):
                    aggregate[k] += counts.get(k, 0)
    else:
        for sid in source_ids:
            counts = _ingest_one_source_id(sid, workers)
            aggregate["sources"] += 1
            for k in ("fetched", "new", "dup", "errors"):
                aggregate[k] += counts.get(k, 0)

    return aggregate
