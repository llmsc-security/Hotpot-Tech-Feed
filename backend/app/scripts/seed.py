"""Seed Source rows from a YAML file.

Idempotent — re-running updates fields on existing rows (matched by URL)
without creating duplicates.

YAML schema:

  sources:
    - name: arXiv cs.LG
      kind: arxiv
      url: https://arxiv.org/list/cs.LG/recent
      lab: null
      language: en
      extra:
        category: cs.LG
        max_results: 50
"""
from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select

from app.core.db import session_scope
from app.core.logging import get_logger
from app.models.source import HealthStatus, Source, SourceKind, SourceStatus

log = get_logger(__name__)


def seed_from_yaml(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"seed file not found: {path}")

    data = yaml.safe_load(p.read_text())
    sources = data.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError("expected top-level key 'sources' to be a list")

    counts = {"created": 0, "updated": 0, "skipped": 0}
    with session_scope() as db:
        for entry in sources:
            url = entry.get("url")
            kind_value = entry.get("kind")
            name = entry.get("name")
            if not url or not kind_value or not name:
                counts["skipped"] += 1
                continue
            try:
                kind = SourceKind(kind_value)
            except ValueError:
                log.warning("unknown source kind", kind=kind_value)
                counts["skipped"] += 1
                continue

            existing = db.execute(select(Source).where(Source.url == url)).scalar_one_or_none()
            if existing:
                existing.name = name
                existing.kind = kind
                existing.language = entry.get("language", existing.language)
                existing.lab = entry.get("lab", existing.lab)
                existing.extra = entry.get("extra", {}) or {}
                if "trust_score" in entry:
                    existing.trust_score = float(entry["trust_score"])
                counts["updated"] += 1
            else:
                db.add(
                    Source(
                        name=name,
                        url=url,
                        kind=kind,
                        language=entry.get("language", "en"),
                        lab=entry.get("lab"),
                        extra=entry.get("extra", {}) or {},
                        trust_score=float(entry.get("trust_score", 0.6)),
                        status=SourceStatus.active,
                        health_status=HealthStatus.unknown,
                    )
                )
                counts["created"] += 1
    return counts
