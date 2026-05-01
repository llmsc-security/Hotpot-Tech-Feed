from __future__ import annotations

import abc
from collections.abc import Iterable

import httpx

from app.core.config import settings
from app.models.source import Source
from app.schemas.item import RawItem


class BaseAdapter(abc.ABC):
    """All source adapters return an iterable of RawItem from `fetch()`."""

    def __init__(self, source: Source) -> None:
        self.source = source

    @abc.abstractmethod
    def fetch(self) -> Iterable[RawItem]:
        """Pull fresh items from the source. Implementations should be idempotent —
        the dedup pipeline downstream will collapse repeats."""
        raise NotImplementedError

    # ---- helpers ----
    def _client(self) -> httpx.Client:
        extra = self.source.extra or {}
        verify = bool(extra.get("verify_ssl", True))
        return httpx.Client(
            timeout=settings.http_timeout_s,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
            verify=verify,
        )
