"""Hotpot CLI.

  hotpot seed-sources [--file PATH]      Load sources from YAML.
  hotpot ingest-now                      Pull every active source once, sync.
  hotpot ingest-source NAME              Pull a single source by name.
  hotpot ingest-kind KIND                Pull every active source of one kind.
  hotpot ingest-deep [--passes N]        Run N full ingest passes with sleeps.
  hotpot enrich-all [--limit N]          Backfill summaries and quality scores.
  hotpot enrich-all --quality-only       Backfill ranking quality scores only.
  hotpot score-security                  Backfill the /security score projection.
  hotpot list-sources                    Print every source row.
  hotpot send-test-digest --to EMAIL     Render today's digest and send it.
  hotpot preview-digest [--out PATH]     Write the rendered digest HTML to a file.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import click
from sqlalchemy import or_, select

from app.core.db import session_scope
from app.core.logging import configure_logging, get_logger
from app.models.source import Source, SourceKind, SourceStatus
from app.services.contribute import USER_SOURCE_URL
from app.tasks.ingest import ingest_all_sync, ingest_source

configure_logging()
log = get_logger(__name__)


@click.group()
def cli() -> None:
    """Hotpot Tech Feed admin CLI."""


@cli.command("seed-sources")
@click.option("--file", "path", default="data/seed_sources.yaml", show_default=True)
def seed_sources(path: str) -> None:
    """Load source rows from YAML. Idempotent: existing rows (matched by URL) are updated."""
    from app.scripts.seed import seed_from_yaml
    counts = seed_from_yaml(path)
    click.echo(json.dumps(counts, indent=2))


@cli.command("ingest-now")
@click.option("--workers", type=int, default=None,
              help="Per-item enrichment threads (defaults to INGEST_WORKERS = cpu/2).")
@click.option("--source-workers", type=int, default=None,
              help="Sources processed concurrently (default 1).")
def ingest_now(workers: int | None, source_workers: int | None) -> None:
    """Run a synchronous pull across every active source."""
    counts = ingest_all_sync(workers=workers, source_workers=source_workers)
    click.echo(json.dumps(counts, indent=2))


@cli.command("ingest-source")
@click.argument("name")
@click.option("--workers", type=int, default=None,
              help="Per-item enrichment threads (defaults to INGEST_WORKERS = cpu/2).")
def ingest_one(name: str, workers: int | None) -> None:
    with session_scope() as db:
        source = db.execute(select(Source).where(Source.name == name)).scalar_one_or_none()
        if not source:
            raise click.ClickException(f"no source named {name!r}")
        counts = ingest_source(db, source, workers=workers)
        click.echo(json.dumps(counts, indent=2))


@cli.command("ingest-kind")
@click.argument("kind", type=click.Choice([k.value for k in SourceKind]))
@click.option("--workers", type=int, default=None,
              help="Per-item enrichment threads (defaults to INGEST_WORKERS = cpu/2).")
def ingest_kind_cmd(kind: str, workers: int | None) -> None:
    """Run ingest on every active source of one adapter kind."""
    aggregate = {"sources": 0, "fetched": 0, "new": 0, "dup": 0, "errors": 0}
    with session_scope() as db:
        sources = db.execute(
            select(Source)
            .where(Source.kind == SourceKind(kind))
            .where(Source.status != SourceStatus.paused)
            .where(Source.url != USER_SOURCE_URL)
            .order_by(Source.name)
        ).scalars().all()
        for source in sources:
            counts = ingest_source(db, source, workers=workers)
            aggregate["sources"] += 1
            for key in ("fetched", "new", "dup", "errors"):
                aggregate[key] += int(counts.get(key, 0))
    click.echo(json.dumps(aggregate, indent=2))


@cli.command("list-sources")
def list_sources() -> None:
    with session_scope() as db:
        rows = db.execute(select(Source).order_by(Source.kind, Source.name)).scalars().all()
        for r in rows:
            click.echo(
                f"[{r.kind.value:6}] {r.name:40}  {r.url}  "
                f"({r.status.value}, health={r.health_status.value})"
            )


@cli.command("ingest-deep")
@click.option("--passes", default=3, show_default=True, help="Number of full ingest passes to run.")
@click.option("--sleep", default=30, show_default=True, help="Seconds to wait between passes.")
@click.option("--workers", type=int, default=None,
              help="Per-item enrichment threads (defaults to INGEST_WORKERS = cpu/2).")
@click.option("--source-workers", type=int, default=None,
              help="Sources processed concurrently (default 1).")
def ingest_deep(passes: int, sleep: int, workers: int | None, source_workers: int | None) -> None:
    """Crawl aggressively: run multiple full passes with sleeps in between.

    Useful for the first bootstrap on a new install — RSS feeds will return
    new items between runs, and arXiv often updates listings throughout the day.
    """
    import time as _time
    aggregate = {"sources": 0, "fetched": 0, "new": 0, "dup": 0, "errors": 0}
    for i in range(1, passes + 1):
        click.echo(f"--- pass {i}/{passes} ---")
        counts = ingest_all_sync(workers=workers, source_workers=source_workers)
        for k, v in counts.items():
            aggregate[k] = aggregate.get(k, 0) + v if k != "sources" else v
        click.echo(json.dumps(counts, indent=2))
        if i < passes:
            click.echo(f"sleeping {sleep}s before next pass…")
            _time.sleep(sleep)
    click.echo("--- aggregate ---")
    click.echo(json.dumps(aggregate, indent=2))


@cli.command("enrich-all")
@click.option("--limit", default=1000, show_default=True, help="Max items to process this run.")
@click.option("--missing-only/--all", default=True, show_default=True,
              help="Only enrich items without a summary or quality score, or re-enrich everything.")
@click.option("--workers", default=1, show_default=True, type=click.IntRange(1, 8),
              help="Parallel item workers, max 8. Each worker may call the LLM.")
@click.option("--claim/--fixed-batch", default=False, show_default=True,
              help="Use row locks with SKIP LOCKED; safe for multiple concurrent CLI jobs.")
@click.option("--quality-only", is_flag=True,
              help="Only process items with score <= 0. Best for quality-rank backfills.")
def enrich_all(limit: int, missing_only: bool, workers: int, claim: bool, quality_only: bool) -> None:
    """Backfill summaries, tags, and quality scores on items already in the DB.

    Useful after a snapshot restore (Postgres dump preserves enrichment, so
    this is mostly a no-op then) or after the LLM endpoint becomes reachable.
    """
    from app.models.item import Item

    if claim:
        _enrich_claimed_items(
            limit=limit,
            missing_only=missing_only,
            workers=workers,
            quality_only=quality_only,
        )
        return

    with session_scope() as db:
        stmt = _enrich_item_query(Item).limit(limit)
        if quality_only:
            stmt = stmt.where(Item.score <= 0)
        elif missing_only:
            stmt = stmt.where(or_(Item.summary.is_(None), Item.score <= 0))
        item_ids = db.execute(stmt).scalars().all()
    click.echo(f"enriching {len(item_ids)} items with {workers} worker(s)…")
    ok = 0
    errors = 0
    if workers == 1:
        for item_id in item_ids:
            item_ok, err = _enrich_one_item(item_id)
            if item_ok:
                ok += 1
            else:
                errors += 1
                click.echo(f"  err: {item_id}  {err}")
    else:
        completed = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_enrich_one_item, item_id): item_id for item_id in item_ids}
            for fut in as_completed(futures):
                item_id = futures[fut]
                completed += 1
                try:
                    item_ok, err = fut.result()
                except Exception as e:  # pragma: no cover
                    item_ok, err = False, str(e)
                if item_ok:
                    ok += 1
                else:
                    errors += 1
                    click.echo(f"  err: {item_id}  {err}")
                if completed % 50 == 0 or completed == len(item_ids):
                    click.echo(f"  progress: {completed}/{len(item_ids)}")

    click.echo(json.dumps({"processed": len(item_ids), "ok": ok, "errors": errors}, indent=2))


def _enrich_claimed_items(
    *,
    limit: int,
    missing_only: bool,
    workers: int,
    quality_only: bool,
) -> None:
    click.echo(f"claim-enriching up to {limit} items with {workers} worker(s)…")
    lock = Lock()
    state = {"claimed": 0, "processed": 0, "ok": 0, "errors": 0, "empty": False}

    def work_loop() -> None:
        while True:
            with lock:
                if state["empty"] or state["claimed"] >= limit:
                    return
                state["claimed"] += 1

            item_id, item_ok, err = _claim_and_enrich_one_item(
                missing_only=missing_only,
                quality_only=quality_only,
            )
            with lock:
                if item_id is None:
                    state["empty"] = True
                    return
                state["processed"] += 1
                if item_ok:
                    state["ok"] += 1
                else:
                    state["errors"] += 1
                    click.echo(f"  err: {item_id}  {err}")
                done = state["processed"]
                if done % 50 == 0 or done == limit:
                    click.echo(f"  progress: {done}/{limit}")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(work_loop) for _ in range(workers)]
        for fut in as_completed(futures):
            fut.result()

    click.echo(json.dumps({
        "processed": state["processed"],
        "ok": state["ok"],
        "errors": state["errors"],
    }, indent=2))


def _enrich_item_query(Item):
    return select(Item.id).order_by(Item.fetched_at.desc())


def _claim_and_enrich_one_item(
    *,
    missing_only: bool,
    quality_only: bool,
) -> tuple[object | None, bool, str | None]:
    from app.models.item import Item
    from app.tasks.enrich import enrich_item

    item_id = None
    try:
        with session_scope() as db:
            stmt = select(Item).order_by(Item.fetched_at.desc()).limit(1)
            if quality_only:
                stmt = stmt.where(Item.score <= 0)
            elif missing_only:
                stmt = stmt.where(or_(Item.summary.is_(None), Item.score <= 0))
            stmt = stmt.with_for_update(skip_locked=True)
            item = db.execute(stmt).scalars().first()
            if not item:
                return None, False, None
            item_id = item.id
            enrich_item(db, item)
            return item_id, True, None
    except Exception as e:
        return item_id, False, str(e)


def _enrich_one_item(item_id) -> tuple[bool, str | None]:
    from app.models.item import Item
    from app.tasks.enrich import enrich_item

    with session_scope() as db:
        item = db.get(Item, item_id)
        if not item:
            return False, "item not found"
        try:
            enrich_item(db, item)
            return True, None
        except Exception as e:
            return False, str(e)


@cli.command("send-test-digest")
@click.option("--to", required=True, help="Recipient email address.")
@click.option("--hours", default=24, show_default=True, help="Look-back window in hours.")
@click.option("--limit", default=25, show_default=True, help="Max items to include.")
def send_test_digest(to: str, hours: int, limit: int) -> None:
    """Render today's digest and send it to one address. Tests SMTP end-to-end."""
    from app.services.digest import pick_items, render_digest
    from app.services.email import send_email

    with session_scope() as db:
        items = pick_items(db, hours=hours, limit=limit)
        rendered = render_digest(items, recipient=to)
    msg_id = send_email(
        to=to,
        subject=rendered.subject,
        html=rendered.html,
        text=rendered.text,
    )
    click.echo(json.dumps({"sent": True, "to": to, "items": len(items), "message_id": msg_id}, indent=2))


@cli.command("preview-digest")
@click.option("--out", default="digest_preview.html", show_default=True)
@click.option("--hours", default=24, show_default=True)
@click.option("--limit", default=25, show_default=True)
def preview_digest(out: str, hours: int, limit: int) -> None:
    """Render the digest to a local HTML file (no email sent). Open in a browser to verify."""
    from pathlib import Path

    from app.services.digest import pick_items, render_digest

    with session_scope() as db:
        items = pick_items(db, hours=hours, limit=limit)
        rendered = render_digest(items)
    Path(out).write_text(rendered.html, encoding="utf-8")
    click.echo(json.dumps({"wrote": out, "items": len(items), "subject": rendered.subject}, indent=2))


@cli.command("discover-sources")
@click.option("--bootstrap/--no-bootstrap", default=False,
              help="Also load data/seed_candidates.yaml on this run.")
@click.option("--verdict-limit", default=10, show_default=True,
              help="Max LLM verdicts to run for un-verdicted candidates.")
def discover_sources_cmd(bootstrap: bool, verdict_limit: int) -> None:
    """Mine new source candidates from corpus + user contribs + GitHub + HN."""
    from app.services.discovery import discover_sources, verdict_pending_candidates
    with session_scope() as db:
        counts = discover_sources(db, bootstrap=bootstrap)
        n_verdict = verdict_pending_candidates(db, limit=verdict_limit)
        counts["llm_verdicts"] = n_verdict
        click.echo(json.dumps(counts, indent=2))


@cli.command("score-sources")
def score_sources_cmd() -> None:
    """Recompute trust_score for every source from real click data + LLM signal."""
    from app.services.discovery import score_sources
    with session_scope() as db:
        click.echo(json.dumps(score_sources(db), indent=2))


@cli.command("score-security")
@click.option("--limit", default=1000, show_default=True, type=click.IntRange(1),
              help="Max canonical items to score. Ignored with --all.")
@click.option("--all", "all_items", is_flag=True,
              help="Score every canonical item.")
@click.option("--missing-only", is_flag=True,
              help="Only score items that do not yet have a security score row.")
@click.option("--recent-days", type=click.IntRange(1), default=None,
              help="Only score items published or fetched within this many days.")
def score_security_cmd(
    limit: int,
    all_items: bool,
    missing_only: bool,
    recent_days: int | None,
) -> None:
    """Recompute the dedicated /security filtering and ranking projection."""
    from app.services.security_scoring import score_security_items
    with session_scope() as db:
        click.echo(json.dumps(
            score_security_items(
                db,
                limit=None if all_items else limit,
                missing_only=missing_only,
                recent_days=recent_days,
            ),
            indent=2,
        ))


@cli.command("health-check-sources")
def health_check_cmd() -> None:
    """HEAD every active source URL and update health_status."""
    from app.services.discovery import health_check_sources
    with session_scope() as db:
        click.echo(json.dumps(health_check_sources(db), indent=2))


@cli.command("ingest-empty")
def ingest_empty_cmd() -> None:
    """Run ingest on every active source that has zero items.

    Useful right after promoting candidates from the Discovery queue, or as a
    daily host-cron job to keep newly added sources from sitting empty.
    """
    from app.services.discovery import ingest_empty_sources
    with session_scope() as db:
        click.echo(json.dumps(ingest_empty_sources(db), indent=2))


@cli.command("list-candidates")
@click.option("--status", default="pending", show_default=True)
@click.option("--limit", default=20, show_default=True)
def list_candidates(status: str, limit: int) -> None:
    """Print discovery candidates for review."""
    from app.models.discovery import SourceCandidate
    with session_scope() as db:
        rows = db.execute(
            select(SourceCandidate)
            .where(SourceCandidate.status == status)
            .order_by(SourceCandidate.signal_score.desc())
            .limit(limit)
        ).scalars().all()
        for c in rows:
            mark = "🎓" if c.is_llm_focused else "  "
            click.echo(
                f"{mark} {c.signal_score:.2f}  [{c.llm_verdict or '?'}]  "
                f"{c.name_hint or c.domain:<40}  {c.sample_url}"
            )


if __name__ == "__main__":
    cli()
