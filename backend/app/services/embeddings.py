"""Embeddings via local sentence-transformers (bge-m3 by default).

Loaded lazily so importing this module is cheap if embeddings_enabled=False.
The L40s on the workstation will run bge-m3 fast in batch.
"""
from __future__ import annotations

from typing import Sequence

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_model = None


def is_enabled() -> bool:
    return settings.embeddings_enabled


def _ensure_model():
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "sentence-transformers not installed; install the 'embeddings' extra "
            "or set embeddings_enabled=false to skip the embedding stage of dedup."
        ) from e
    log.info("loading embedding model", model=settings.embeddings_model)
    _model = SentenceTransformer(settings.embeddings_model)
    return _model


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    if not is_enabled():
        return []
    model = _ensure_model()
    vecs = model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vecs]


def embed_text(text: str) -> list[float] | None:
    if not is_enabled():
        return None
    out = embed_texts([text])
    return out[0] if out else None
