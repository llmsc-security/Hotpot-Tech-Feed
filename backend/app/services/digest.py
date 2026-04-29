"""Digest builder.

Phase 2.0 — single shared digest. Phase 2.1 will add per-user filtering on
top by replacing the `pick_items` query with subscription-aware logic.

Render path:
  pick_items() -> list[Item] -> render_digest_html() -> (subject, html, text)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.item import ContentType, Item
from app.models.source import Source


# ---------- Selection ----------

_TYPE_LABEL = {
    ContentType.paper: "Paper",
    ContentType.blog: "Blog",
    ContentType.news: "News",
    ContentType.lab_announcement: "Lab",
    ContentType.tutorial: "Tutorial",
    ContentType.oss_release: "OSS",
    ContentType.other: "Other",
}


def pick_items(db: Session, *, hours: int = 24, limit: int = 25) -> list[Item]:
    """Pull recent canonical items, ranked by source trust × recency."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = db.execute(
        select(Item)
        .options(selectinload(Item.tags), selectinload(Item.source))
        .where(Item.is_canonical.is_(True))
        .where(Item.fetched_at >= cutoff)
        .order_by(Item.fetched_at.desc())
        .limit(limit * 4)  # oversample, then re-rank
    ).scalars().unique().all()

    # Rank: source trust score, then recency.
    rows.sort(
        key=lambda i: (
            i.source.trust_score if i.source else 0.5,
            (i.published_at or i.fetched_at).timestamp(),
        ),
        reverse=True,
    )
    return rows[:limit]


# ---------- Rendering ----------

@dataclass
class RenderedDigest:
    subject: str
    html: str
    text: str


def render_digest(items: Sequence[Item], *, recipient: str | None = None) -> RenderedDigest:
    """Render the final HTML + text digest for a given list of items."""
    today = datetime.now(timezone.utc).strftime("%A, %B %-d, %Y")
    subject = f"Hotpot — {today} ({len(items)} item{'s' if len(items) != 1 else ''})"

    html = _render_html(items, today)
    text = _render_text(items, today)
    return RenderedDigest(subject=subject, html=html, text=text)


def _render_html(items: Sequence[Item], date_label: str) -> str:
    blocks = []
    for item in items:
        topic = next((t.tag[6:] for t in item.tags if t.tag.startswith("topic:")), None)
        type_label = _TYPE_LABEL.get(item.content_type, "Item")
        source_name = item.source.name if item.source else ""
        date_str = (item.published_at or item.fetched_at).strftime("%b %-d")

        meta_parts = [f'<span class="chip">{escape(type_label)}</span>']
        if topic:
            meta_parts.append(f'<span class="chip-soft">{escape(topic)}</span>')
        if source_name:
            meta_parts.append(f'<span class="muted">{escape(source_name)}</span>')
        meta_parts.append(f'<span class="muted">· {escape(date_str)}</span>')
        # Separate chips with spaces so CSS-stripped renderers don't run them together.
        meta_html = " ".join(meta_parts)

        summary_html = ""
        if item.summary:
            summary_html = f'<p class="summary">{escape(item.summary)}</p>'

        blocks.append(f"""
<article class="item">
  <div class="meta">{meta_html}</div>
  <h3 class="title"><a href="{escape(item.canonical_url)}">{escape(item.title)}</a></h3>
  {summary_html}
</article>""")

    body = "\n".join(blocks) if blocks else """
<p class="muted">Nothing fresh today — the ingest pipeline didn't return new items in the last 24 hours.</p>"""

    return _HTML_TEMPLATE.replace("{{date}}", escape(date_label)).replace("{{body}}", body)


def _render_text(items: Sequence[Item], date_label: str) -> str:
    lines = [f"Hotpot Tech Feed — {date_label}", "=" * 50, ""]
    if not items:
        lines.append("Nothing fresh today.")
        return "\n".join(lines)
    for item in items:
        topic = next((t.tag[6:] for t in item.tags if t.tag.startswith("topic:")), "")
        ctype = _TYPE_LABEL.get(item.content_type, "Item")
        src = item.source.name if item.source else ""
        date_str = (item.published_at or item.fetched_at).strftime("%b %-d")

        head = f"[{ctype}{(' · ' + topic) if topic else ''}] {item.title}"
        lines.append(head)
        lines.append(item.canonical_url)
        if item.summary:
            lines.append(item.summary)
        lines.append(f"  — {src}, {date_str}")
        lines.append("")
    lines.append("---")
    lines.append(f"feed.{settings.digest_from_email.split('@', 1)[-1] or 'ai2wj.com'}")
    return "\n".join(lines)


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Hotpot Tech Feed</title>
<style>
  body { font-family: Georgia, serif; background: #FAFAFA; color: #1F2937; margin: 0; padding: 24px 12px; }
  .wrap { max-width: 640px; margin: 0 auto; background: #fff; border: 1px solid #E5E7EB; border-radius: 8px; }
  .header { padding: 20px 24px; border-bottom: 1px solid #E5E7EB; }
  .header h1 { margin: 0; font-size: 20px; color: #1A1F3A; }
  .header .date { font-size: 12px; color: #6B7280; margin-top: 4px; font-family: -apple-system, sans-serif; }
  .item { padding: 18px 24px; border-bottom: 1px solid #F3F4F6; }
  .item:last-child { border-bottom: none; }
  .meta { font-size: 11px; color: #6B7280; margin-bottom: 6px; font-family: -apple-system, sans-serif; }
  .meta .chip { display: inline-block; background: #FBE7E5; color: #C4302B; padding: 2px 8px; border-radius: 999px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; margin-right: 6px; }
  .meta .chip-soft { display: inline-block; background: #F3F4F6; color: #1F2937; padding: 2px 8px; border-radius: 999px; margin-right: 6px; }
  .meta .muted { color: #6B7280; margin-right: 6px; }
  .title { font-size: 16px; line-height: 1.35; margin: 0 0 6px 0; }
  .title a { color: #1A1F3A; text-decoration: none; }
  .title a:hover { color: #C4302B; }
  .summary { font-size: 14px; line-height: 1.5; color: #1F2937; margin: 6px 0 0 0; font-family: -apple-system, sans-serif; }
  .footer { padding: 16px 24px; font-size: 11px; color: #9CA3AF; text-align: center; font-family: -apple-system, sans-serif; }
  .footer a { color: #9CA3AF; }
  .muted { color: #6B7280; }
</style>
</head>
<body>
  <div class="wrap">
    <div class="header">
      <h1>Hotpot Tech Feed</h1>
      <div class="date">{{date}}</div>
    </div>
    {{body}}
    <div class="footer">
      <a href="https://feed.ai2wj.com">feed.ai2wj.com</a> ·
      Daily CS digest
    </div>
  </div>
</body>
</html>
"""
