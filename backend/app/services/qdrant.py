"""Qdrant client wrapper for the items collection.

We store one point per canonical item, keyed by item.id (UUID string).
On dedup we query the collection with a fresh embedding and look for any hit
above the cosine threshold inside the recent-window filter.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_client: Optional[QdrantClient] = None


def client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=settings.qdrant_url)
    return _client


def ensure_collection() -> None:
    """Create the items collection if it doesn't exist. Safe to call repeatedly."""
    c = client()
    if c.collection_exists(settings.qdrant_collection):
        return
    c.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=qmodels.VectorParams(
            size=settings.embeddings_dim,
            distance=qmodels.Distance.COSINE,
        ),
    )
    log.info("created qdrant collection", name=settings.qdrant_collection)


def upsert_item(item_id: str, vector: list[float], published_at: datetime | None) -> None:
    c = client()
    payload = {"item_id": item_id}
    if published_at:
        payload["published_at_ts"] = int(published_at.timestamp())
    c.upsert(
        collection_name=settings.qdrant_collection,
        points=[qmodels.PointStruct(id=item_id, vector=vector, payload=payload)],
    )


def find_similar(
    vector: list[float],
    threshold: float,
    window_days: int,
    limit: int = 5,
) -> list[tuple[str, float]]:
    """Return [(item_id, score)] for points above `threshold` within the window."""
    c = client()
    cutoff_ts = int((datetime.now(timezone.utc) - timedelta(days=window_days)).timestamp())
    flt = qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="published_at_ts",
                range=qmodels.Range(gte=cutoff_ts),
            )
        ]
    )
    hits = c.search(
        collection_name=settings.qdrant_collection,
        query_vector=vector,
        limit=limit,
        score_threshold=threshold,
        query_filter=flt,
    )
    return [(str(h.id), float(h.score)) for h in hits]
