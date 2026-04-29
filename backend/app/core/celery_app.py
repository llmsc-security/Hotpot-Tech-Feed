"""Celery app + beat schedule for periodic ingestion.

For Phase 1 we ship Celery wiring but the recommended path during dev is to
run `hotpot ingest-now` synchronously to verify the pipeline. Switch to
celery beat once you're ready to schedule daily runs.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "hotpot",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.ingest", "app.tasks.enrich"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=4,
)

celery_app.conf.beat_schedule = {
    "ingest-arxiv-hourly": {
        "task": "app.tasks.ingest.ingest_kind",
        "schedule": crontab(minute=15),
        "args": ("arxiv",),
    },
    "ingest-rss-15min": {
        "task": "app.tasks.ingest.ingest_kind",
        "schedule": crontab(minute="*/15"),
        "args": ("rss",),
    },
}
