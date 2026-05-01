"""Article text extraction helpers."""
from __future__ import annotations

from app.core.logging import get_logger

log = get_logger(__name__)


def extract_article_text(html: str, *, url: str | None = None, limit: int = 3000) -> str | None:
    """Extract main article text from HTML, returning a compact plain-text excerpt."""
    if not html:
        return None
    try:
        import trafilatura  # type: ignore
    except ImportError:
        log.warning("trafilatura unavailable; skipping article text extraction")
        return None

    try:
        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            deduplicate=True,
            favor_precision=True,
            output_format="txt",
        )
    except Exception as e:  # pragma: no cover
        log.warning("article text extraction failed", url=url, err=str(e))
        return None

    text = " ".join((text or "").split())
    return text[:limit] if text else None
