"""Hotpot CLI.

  hotpot seed-sources [--file PATH]    Load sources from YAML.
  hotpot ingest-now                    Pull every active source once, sync.
  hotpot ingest-source NAME            Pull a single source by name.
  hotpot list-sources                  Print every source row.
"""
from __future__ import annotations

import json

import click
from sqlalchemy import select

from app.core.db import session_scope
from app.core.logging import configure_logging, get_logger
from app.models.source import Source
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
def ingest_now() -> None:
    """Run a synchronous pull across every active source."""
    counts = ingest_all_sync()
    click.echo(json.dumps(counts, indent=2))


@cli.command("ingest-source")
@click.argument("name")
def ingest_one(name: str) -> None:
    with session_scope() as db:
        source = db.execute(select(Source).where(Source.name == name)).scalar_one_or_none()
        if not source:
            raise click.ClickException(f"no source named {name!r}")
        counts = ingest_source(db, source)
        click.echo(json.dumps(counts, indent=2))


@cli.command("list-sources")
def list_sources() -> None:
    with session_scope() as db:
        rows = db.execute(select(Source).order_by(Source.kind, Source.name)).scalars().all()
        for r in rows:
            click.echo(
                f"[{r.kind.value:6}] {r.name:40}  {r.url}  "
                f"({r.status.value}, health={r.health_status.value})"
            )


if __name__ == "__main__":
    cli()
