"""Source adapter registry.

Add a new adapter by:
  1. Subclassing `BaseAdapter` and implementing `fetch()`.
  2. Registering the class in ADAPTERS below, keyed by `SourceKind`.
"""
from __future__ import annotations

from app.adapters.base import BaseAdapter
from app.adapters.arxiv import ArxivAdapter
from app.adapters.rss import RssAdapter
from app.models.source import Source, SourceKind


ADAPTERS: dict[SourceKind, type[BaseAdapter]] = {
    SourceKind.arxiv: ArxivAdapter,
    SourceKind.rss: RssAdapter,
}


def get_adapter(source: Source) -> BaseAdapter:
    cls = ADAPTERS.get(source.kind)
    if cls is None:
        raise ValueError(f"No adapter registered for source kind {source.kind!r}")
    return cls(source)
