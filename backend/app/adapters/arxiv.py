"""arXiv adapter.

Each Source row of kind=arxiv represents one arXiv category (e.g. cs.LG).
The category goes in `Source.extra["category"]` (set by the seeder).

We pull recent submissions via the public Atom API:
    http://export.arxiv.org/api/query?search_query=cat:cs.LG&sortBy=submittedDate&sortOrder=descending

This is rate-limited; arXiv asks for ~1 req every 3 seconds. The seed list
caps total categories so a daily run stays well under the limit.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

import feedparser
from dateutil import parser as dateparser

from app.adapters.base import BaseAdapter
from app.models.item import ContentType
from app.schemas.item import RawItem

ARXIV_API = "http://export.arxiv.org/api/query"


class ArxivAdapter(BaseAdapter):
    def fetch(self) -> Iterable[RawItem]:
        category = self.source.extra.get("category")
        if not category:
            raise ValueError(
                f"arXiv source {self.source.name!r} missing extra.category (e.g. 'cs.LG')"
            )
        max_results = int(self.source.extra.get("max_results", 50))

        params = {
            "search_query": f"cat:{category}",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": str(max_results),
        }
        with self._client() as client:
            resp = client.get(ARXIV_API, params=params)
            resp.raise_for_status()
            body = resp.text

        feed = feedparser.parse(body)
        for entry in feed.entries:
            arxiv_id = entry.get("id", "").rsplit("/", 1)[-1]
            abs_url = entry.get("id") or f"https://arxiv.org/abs/{arxiv_id}"
            published = entry.get("published")
            try:
                published_dt = dateparser.parse(published) if published else None
            except (TypeError, ValueError):
                published_dt = None
            if published_dt and published_dt.tzinfo is None:
                published_dt = published_dt.replace(tzinfo=timezone.utc)

            authors = [a.get("name") for a in entry.get("authors", []) if a.get("name")]
            summary = (entry.get("summary") or "").strip().replace("\n", " ")

            yield RawItem(
                source_id=self.source.id,
                url=abs_url,
                title=(entry.get("title") or "").strip().replace("\n", " "),
                authors=authors,
                published_at=published_dt,
                language="en",
                excerpt=summary[:2000],
                content_type=ContentType.paper,
                venue="arXiv",
                extra={"arxiv_id": arxiv_id, "category": category},
            )
