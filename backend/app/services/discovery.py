"""Source discovery + quality scoring + health checks.

Three jobs, each invokable via the `hotpot` CLI and schedulable in cron:

  1. discover_sources()       — mine new candidates (outbound links, user
                                contributions, GitHub trending, HN). Bootstraps
                                from `data/seed_candidates.yaml` on first run.
  2. score_sources()          — recompute trust_score from real click data +
                                LLM noise-ratio sample. Auto-probation /
                                auto-pause for the bottom of the distribution.
  3. health_check_sources()   — HEAD each source URL, mark broken/degraded.

Each job is idempotent and can be re-run safely.
"""
from __future__ import annotations

import os
import re
import statistics
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.discovery import SourceCandidate, SourceQualityRun
from app.models.item import Item, ItemTag
from app.models.source import HealthStatus, Source, SourceKind, SourceStatus

log = get_logger(__name__)

# ---------- helpers ----------

_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
_WX_OA_RE = re.compile(r'var\s+nickname\s*=\s*["\']([^"\']+)["\']')


def _domain(url: str) -> str | None:
    try:
        host = urlparse(url).netloc.lower()
        if not host:
            return None
        # strip leading "www." for grouping
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return None


def _expand_env(s: str) -> str:
    """Resolve ${VAR} placeholders against settings + os.environ."""
    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        if key.lower() == "rsshub_url":
            return settings.rsshub_url
        return os.environ.get(key, "")
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", repl, s)


# ---------- Job 1: discover ----------

def bootstrap_from_seed(db: Session, path: str | None = None) -> int:
    """Load `data/seed_candidates.yaml` into source_candidates. Idempotent."""
    path = path or settings.discovery_seed_path
    if not os.path.exists(path):
        log.warning("seed_candidates.yaml missing", path=path)
        return 0

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    n = 0
    for entry in data.get("candidates", []):
        url = _expand_env(entry["url"])
        if entry.get("requires") == "rsshub" and not settings.rsshub_url:
            # User hasn't enabled the rsshub profile — skip these silently.
            continue

        domain = _domain(url) or url
        existing = db.execute(
            select(SourceCandidate).where(SourceCandidate.domain == domain)
        ).scalar_one_or_none()
        if existing is not None:
            continue
        # Also skip if already a Source.
        if db.execute(
            select(Source).where(Source.url == url)
        ).scalar_one_or_none() is not None:
            continue

        c = SourceCandidate(
            domain=domain,
            sample_url=url,
            name_hint=entry["name"],
            language=entry.get("language"),
            signal_score=float(entry.get("signal_score", 0.5)),
            llm_verdict="signal",
            llm_rationale=entry.get("rationale"),
            is_llm_focused=bool(entry.get("is_llm_focused", False)),
            academic_depth=entry.get("academic_depth"),
            suggested_kind=entry.get("kind"),
            suggested_rss_url=url if entry.get("kind") == "rss" else None,
            source_signal="seed",
            status="pending",
        )
        db.add(c)
        n += 1
    db.flush()
    log.info("bootstrap candidates inserted", count=n)
    return n


def _mine_outbound_links(db: Session, lookback_days: int = 30) -> Counter[str]:
    """Domain mention counts from items' raw_html_path / excerpt outbound links."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    rows = db.execute(
        select(Item.excerpt).where(
            and_(Item.fetched_at >= cutoff, Item.excerpt.is_not(None))
        )
    ).all()
    counts: Counter[str] = Counter()
    for (excerpt,) in rows:
        if not excerpt:
            continue
        for m in _HREF_RE.finditer(excerpt):
            d = _domain(m.group(1))
            if d:
                counts[d] += 1
    return counts


def _mine_user_contributions(db: Session, lookback_days: int = 30) -> Counter[str]:
    """Count distinct contributed URLs per domain (user-source items)."""
    from app.services.contribute import USER_SOURCE_URL

    user_src = db.execute(
        select(Source.id).where(Source.url == USER_SOURCE_URL)
    ).scalar_one_or_none()
    if user_src is None:
        return Counter()

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    rows = db.execute(
        select(Item.canonical_url).where(
            and_(Item.source_id == user_src, Item.fetched_at >= cutoff)
        )
    ).all()
    counts: Counter[str] = Counter()
    for (url,) in rows:
        d = _domain(url)
        if d:
            counts[d] += 1
    return counts


def _mine_github_trending() -> list[dict[str, Any]]:
    """Top public repos by stars-this-week. Falls back gracefully if rate-limited."""
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    one_week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    q = f"created:>{one_week_ago} stars:>50"
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(
                "https://api.github.com/search/repositories",
                params={"q": q, "sort": "stars", "order": "desc", "per_page": 20},
                headers=headers,
            )
        if r.status_code != 200:
            log.warning("github_trending failed", code=r.status_code)
            return []
        return r.json().get("items", []) or []
    except Exception as e:
        log.warning("github_trending error", err=str(e))
        return []


def _mine_hn() -> list[dict[str, Any]]:
    """HN top stories tagged llm/ml/ai from the last week (Algolia, no auth)."""
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(
                "https://hn.algolia.com/api/v1/search",
                params={
                    "query": "llm OR transformer OR foundation-model",
                    "tags": "story",
                    "numericFilters": (
                        f"created_at_i>{int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())}"
                    ),
                    "hitsPerPage": 30,
                },
            )
        if r.status_code != 200:
            return []
        return r.json().get("hits", []) or []
    except Exception as e:
        log.warning("hn_algolia error", err=str(e))
        return []


def _llm_verdict(name: str, sample_titles: list[str]) -> dict[str, Any]:
    """Ask Qwen whether this candidate is signal vs noise for our discovery focus."""
    from app.services.llm import _chat, _extract_json

    focus = settings.discovery_focus.replace(",", " + ")
    titles = "\n".join(f"- {t[:120]}" for t in sample_titles[:10])
    system = (
        "You evaluate whether a domain is a high-quality CS source for a "
        "personalized feed. Penalize: clickbait, product launches, recycled "
        "aggregators. Reward: technical depth, lab announcements, paper "
        f"walkthroughs, original analysis. The reader prioritizes: {focus}. "
        "Return strict JSON only: "
        "{verdict: 'signal'|'noise'|'unclear', "
        "rationale: <one sentence>, "
        "is_llm_focused: bool, "
        "academic_depth: 'high'|'medium'|'low', "
        "suggested_kind: 'rss'|'html'|'github', "
        "language: 'en'|'zh'}"
    )
    try:
        raw = _chat(
            settings.llm_model_tagger,
            system,
            f"Domain/source: {name}\n\nRecent titles:\n{titles or '(no samples)'}",
            max_tokens=200,
        )
        return _extract_json(raw)
    except Exception as e:
        log.warning("llm_verdict failed", err=str(e), name=name)
        return {"verdict": "unclear", "rationale": "(LLM unavailable)"}


def discover_sources(db: Session, *, bootstrap: bool = False) -> dict[str, int]:
    """Run a discovery sweep. Returns counts of what happened.

    bootstrap=True also loads `data/seed_candidates.yaml` first.
    """
    counts = {"seeded": 0, "outbound": 0, "contributions": 0, "github": 0, "hn": 0}

    if bootstrap:
        counts["seeded"] = bootstrap_from_seed(db)

    # Aggregate signals into a per-domain dict.
    agg: dict[str, dict[str, Any]] = {}

    for d, n in _mine_outbound_links(db).items():
        agg.setdefault(d, {"mention_count": 0, "contributor_count": 0,
                           "name_hint": d, "sample_url": f"https://{d}",
                           "signal": "outbound"})
        agg[d]["mention_count"] += n
    counts["outbound"] = len(agg)

    for d, n in _mine_user_contributions(db).items():
        e = agg.setdefault(d, {"mention_count": 0, "contributor_count": 0,
                               "name_hint": d, "sample_url": f"https://{d}",
                               "signal": "user-contrib"})
        e["contributor_count"] += n
        if e["signal"] != "user-contrib":
            e["signal"] = "outbound+user-contrib"
    counts["contributions"] = len(_mine_user_contributions(db))

    for repo in _mine_github_trending():
        d = _domain(repo.get("html_url") or "")
        if not d:
            continue
        e = agg.setdefault(d, {"mention_count": 0, "contributor_count": 0,
                               "name_hint": repo.get("full_name", d),
                               "sample_url": repo.get("html_url", f"https://{d}"),
                               "signal": "github"})
        e["mention_count"] += int(repo.get("stargazers_count", 0)) // 100
    counts["github"] = sum(1 for v in agg.values() if v.get("signal") == "github")

    for hit in _mine_hn():
        url = hit.get("url") or ""
        d = _domain(url)
        if not d:
            continue
        e = agg.setdefault(d, {"mention_count": 0, "contributor_count": 0,
                               "name_hint": d, "sample_url": url,
                               "signal": "hn"})
        e["mention_count"] += int(hit.get("points", 0)) // 50
    counts["hn"] = sum(1 for v in agg.values() if v.get("signal") == "hn")

    # Persist as candidates, skipping anything already known.
    known_sources = {
        d for (d,) in db.execute(
            select(func.lower(Source.url))
        ).all()
    }
    known_candidate_domains = {
        d for (d,) in db.execute(select(SourceCandidate.domain)).all()
    }

    new_count = 0
    for domain, info in agg.items():
        if domain in known_candidate_domains:
            # Just bump mention/contributor counts.
            db.execute(
                SourceCandidate.__table__.update()
                .where(SourceCandidate.domain == domain)
                .values(
                    mention_count=SourceCandidate.mention_count + info["mention_count"],
                    contributor_count=SourceCandidate.contributor_count + info["contributor_count"],
                    last_seen_at=datetime.now(timezone.utc),
                )
            )
            continue
        if any(domain in u for u in known_sources):
            continue

        # Light score from raw signal — LLM verdict bumps later.
        signal_score = min(
            1.0,
            0.05 * info["mention_count"]
            + 0.25 * info["contributor_count"]
            + (0.2 if info.get("signal") in {"github", "hn"} else 0.1),
        )
        c = SourceCandidate(
            domain=domain,
            sample_url=info["sample_url"][:2048],
            name_hint=info["name_hint"][:255],
            mention_count=info["mention_count"],
            contributor_count=info["contributor_count"],
            signal_score=signal_score,
            source_signal=info["signal"],
            status="pending",
        )
        db.add(c)
        new_count += 1
    db.flush()

    counts["new_candidates"] = new_count
    log.info("discover_sources done", **counts)
    return counts


def verdict_pending_candidates(db: Session, limit: int = 10) -> int:
    """Run LLM verdict on candidates that don't yet have one. Cheap to do online."""
    rows = db.execute(
        select(SourceCandidate)
        .where(SourceCandidate.llm_verdict.is_(None))
        .where(SourceCandidate.status == "pending")
        .order_by(SourceCandidate.signal_score.desc())
        .limit(limit)
    ).scalars().all()
    n = 0
    for c in rows:
        v = _llm_verdict(c.name_hint or c.domain, [])
        c.llm_verdict = (v.get("verdict") or "unclear")[:16]
        c.llm_rationale = (v.get("rationale") or "")[:1000]
        c.is_llm_focused = bool(v.get("is_llm_focused", False))
        c.academic_depth = (v.get("academic_depth") or "")[:8] or None
        c.suggested_kind = (v.get("suggested_kind") or "")[:16] or None
        c.language = (v.get("language") or "")[:10] or c.language
        # Bump score for an LLM-confirmed signal hit.
        if c.llm_verdict == "signal":
            c.signal_score = min(1.0, c.signal_score + 0.3)
        n += 1
    db.flush()
    return n


# ---------- Job 1.5: promote / reject ----------

def promote_candidate(db: Session, candidate_id: uuid.UUID, *, kind: str | None = None) -> Source:
    c = db.execute(
        select(SourceCandidate).where(SourceCandidate.id == candidate_id)
    ).scalar_one()
    chosen_kind = kind or c.suggested_kind or "html"
    try:
        sk = SourceKind(chosen_kind)
    except ValueError:
        sk = SourceKind.html

    src = Source(
        name=(c.name_hint or c.domain)[:200],
        url=(c.suggested_rss_url or c.sample_url)[:2048],
        kind=sk,
        language=(c.language or "en")[:10],
        trust_score=0.5,
        health_status=HealthStatus.unknown,
        status=SourceStatus.active,
        editorial_focus={
            "llm": bool(c.is_llm_focused),
            "academic": c.academic_depth or "medium",
            "lineage": "discovery",
        },
        extra={"discovered_from": c.source_signal or "manual"},
    )
    db.add(src)
    db.flush()
    c.status = "promoted"
    c.promoted_to_source_id = src.id
    db.flush()

    _kick_off_first_ingest(src.id, src.name)
    return src


def _kick_off_first_ingest(source_id: uuid.UUID, source_name: str) -> None:
    """Background ingest of a freshly promoted source so it doesn't sit empty.

    Runs in a daemon thread with its own session_scope. The HTTP request that
    triggered the promote returns immediately; the ingest progresses on its
    own and shows up in the UI within a few minutes.
    """
    import threading

    def _runner() -> None:
        from app.core.db import session_scope
        from app.tasks.ingest import ingest_source

        try:
            with session_scope() as bg_db:
                src = bg_db.execute(select(Source).where(Source.id == source_id)).scalar_one()
                counts = ingest_source(bg_db, src)
                log.info("first ingest done", source=source_name, **counts)
        except Exception as e:  # noqa: BLE001
            log.warning("first ingest failed", source=source_name, err=str(e))

    threading.Thread(target=_runner, name=f"ingest-{source_name[:20]}", daemon=True).start()


def ingest_empty_sources(db: Session) -> dict[str, int]:
    """Run ingest on every active source that has zero items.

    Used by the host cron + the new-source backfill flow. Bypasses paused /
    probation sources. Skips the user-contributions pseudo-source.
    """
    from app.services.contribute import USER_SOURCE_URL
    from app.tasks.ingest import ingest_source

    rows = db.execute(
        select(Source)
        .where(Source.status == SourceStatus.active)
        .where(Source.url != USER_SOURCE_URL)
    ).scalars().all()

    out = {"checked": 0, "ingested": 0, "skipped_nonempty": 0, "fetched": 0, "new": 0}
    for src in rows:
        out["checked"] += 1
        # Cheap count instead of join.
        n = db.execute(
            select(func.count()).select_from(Item).where(Item.source_id == src.id)
        ).scalar_one()
        if n > 0:
            out["skipped_nonempty"] += 1
            continue
        try:
            counts = ingest_source(db, src)
            out["ingested"] += 1
            out["fetched"] += int(counts.get("fetched", 0))
            out["new"] += int(counts.get("new", 0))
            log.info("ingest_empty source done", source=src.name, **counts)
        except Exception as e:  # noqa: BLE001
            log.warning("ingest_empty source failed", source=src.name, err=str(e))

    log.info("ingest_empty_sources done", **out)
    return out


def reject_candidate(db: Session, candidate_id: uuid.UUID) -> None:
    db.execute(
        SourceCandidate.__table__.update()
        .where(SourceCandidate.id == candidate_id)
        .values(status="rejected")
    )


# ---------- Job 2: score ----------

def score_sources(db: Session) -> dict[str, int]:
    """Recompute trust_score for every source from click + LLM data."""
    from app.services.llm import _chat

    counts = {"scored": 0, "probation": 0, "paused": 0}
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    sources = db.execute(select(Source)).scalars().all()
    for src in sources:
        # Aggregate item click data over the last 30 days.
        rows = db.execute(
            select(Item.click_count, Item.title).where(
                and_(Item.source_id == src.id, Item.fetched_at >= cutoff)
            )
        ).all()
        item_count = len(rows)
        if item_count == 0:
            continue

        clicks = [int(c or 0) for (c, _) in rows]
        titles = [t for (_, t) in rows[:5]]
        items_with_click = sum(1 for c in clicks if c > 0)
        ctr = items_with_click / item_count
        median_clicks = float(statistics.median(clicks)) if clicks else 0.0

        # Cheap LLM noise check on a small title sample.
        noise_ratio = None
        rationale = None
        if titles:
            try:
                resp = _chat(
                    settings.llm_model_tagger,
                    "Of the following titles, how many are high-signal CS "
                    "content (vs clickbait / product PR / off-topic)? Return "
                    "strict JSON: {signal: int, noise: int, rationale: <one sentence>}.",
                    "\n".join(f"- {t[:120]}" for t in titles),
                    max_tokens=120,
                )
                from app.services.llm import _extract_json
                d = _extract_json(resp)
                s = int(d.get("signal", 0))
                n = int(d.get("noise", 0))
                if s + n > 0:
                    noise_ratio = n / (s + n)
                rationale = d.get("rationale")
            except Exception:
                pass

        # Compose new trust score: weighted CTR + median clicks + LLM signal.
        ts_before = src.trust_score
        ts = (
            0.4 * ctr
            + 0.3 * min(1.0, median_clicks / 5.0)
            + 0.3 * (1 - (noise_ratio if noise_ratio is not None else 0.3))
        )
        # Decay toward the new score (don't whiplash on one bad week).
        ts_after = round(0.6 * ts_before + 0.4 * ts, 3)

        action = None
        if ts_after < settings.score_probation_threshold:
            recent_low = db.execute(
                select(func.count())
                .select_from(SourceQualityRun)
                .where(SourceQualityRun.source_id == src.id)
                .where(SourceQualityRun.trust_score_after < settings.score_probation_threshold)
            ).scalar_one()
            if recent_low + 1 >= settings.score_pause_after_n_low_runs and src.status == SourceStatus.probation:
                src.status = SourceStatus.paused
                action = "paused"
                counts["paused"] += 1
            elif src.status == SourceStatus.active:
                src.status = SourceStatus.probation
                action = "probation"
                counts["probation"] += 1
        elif src.status in {SourceStatus.probation, SourceStatus.paused} and ts_after >= settings.score_probation_threshold:
            src.status = SourceStatus.active
            action = "reinstated"

        src.trust_score = ts_after
        db.add(SourceQualityRun(
            source_id=src.id,
            ctr_30d=round(ctr, 3),
            median_clicks_30d=median_clicks,
            item_count_30d=item_count,
            llm_noise_ratio=noise_ratio,
            llm_rationale=rationale,
            trust_score_before=ts_before,
            trust_score_after=ts_after,
            action_taken=action,
        ))
        counts["scored"] += 1

    db.flush()
    log.info("score_sources done", **counts)
    return counts


# ---------- Job 3: health ----------

def health_check_sources(db: Session) -> dict[str, int]:
    """HEAD each active source URL; mark broken/degraded after consecutive failures."""
    counts = {"ok": 0, "degraded": 0, "broken": 0, "skipped": 0}
    sources = db.execute(
        select(Source).where(Source.status != SourceStatus.paused)
    ).scalars().all()
    for src in sources:
        if src.url.startswith("user-contributions://"):
            counts["skipped"] += 1
            continue
        try:
            with httpx.Client(timeout=8, follow_redirects=True) as client:
                r = client.head(src.url, headers={"User-Agent": settings.user_agent})
                if r.status_code == 405:  # not allowed → fall through to GET
                    r = client.get(src.url, headers={"User-Agent": settings.user_agent})
            ok = r.status_code < 400
        except Exception:
            ok = False

        if ok:
            src.health_status = HealthStatus.ok
            src.failure_streak = 0
            counts["ok"] += 1
        else:
            src.failure_streak = (src.failure_streak or 0) + 1
            if src.failure_streak >= 3:
                src.health_status = HealthStatus.broken
                counts["broken"] += 1
            else:
                src.health_status = HealthStatus.degraded
                counts["degraded"] += 1
    db.flush()
    log.info("health_check_sources done", **counts)
    return counts
