"""Source adapter registry.

Add a new adapter by:
  1. Subclassing `BaseAdapter` and implementing `fetch()`.
  2. Registering the class in ADAPTERS below, keyed by `SourceKind`.
"""
from __future__ import annotations

from app.adapters.base import BaseAdapter
from app.adapters.arxiv import ArxivAdapter
from app.adapters.doonsec import DoonsecAdapter
from app.adapters.html import HtmlSitemapAdapter
from app.adapters.html_index import HtmlIndexAdapter
from app.adapters.rss import RssAdapter
from app.models.source import Source, SourceKind


ADAPTERS: dict[SourceKind, type[BaseAdapter]] = {
    SourceKind.arxiv: ArxivAdapter,
    SourceKind.rss: RssAdapter,
    SourceKind.html: HtmlSitemapAdapter,
}


def get_adapter(source: Source) -> BaseAdapter:
    if source.kind == SourceKind.rss and (source.extra or {}).get("adapter") == "doonsec":
        return DoonsecAdapter(source)
    if source.kind == SourceKind.html and (source.extra or {}).get("adapter") == "html_index":
        return HtmlIndexAdapter(source)
    cls = ADAPTERS.get(source.kind)
    if cls is None:
        raise ValueError(f"No adapter registered for source kind {source.kind!r}")
    return cls(source)
