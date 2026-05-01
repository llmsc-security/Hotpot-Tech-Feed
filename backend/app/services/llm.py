"""Qwen access via the OpenAI SDK pointed at api.ai2wj.com/v1.

All prompt logic lives here. Each method returns plain Python types so callers
don't have to think about the chat-completion shape.
"""
from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

# Curated top-level CS topics — match the plan.
TOPICS: list[str] = [
    "ML", "Systems", "Theory", "Security", "HCI", "PL", "DB",
    "Networks", "Graphics", "Robotics", "Other",
]
CONTENT_TYPES: list[str] = [
    "paper", "blog", "news", "lab_announcement", "tutorial", "oss_release", "other",
]


def _client() -> OpenAI:
    return OpenAI(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        timeout=settings.llm_timeout_s,
    )


def _chat(model: str, system: str, user: str, max_tokens: int = 400) -> str:
    """Single-shot chat completion.

    `extra_body.chat_template_kwargs.enable_thinking=False` disables Qwen3.5's
    thinking-mode prefix so the model returns clean JSON straight away. vLLM /
    Qwen ignore unknown extras silently, so this is a no-op on other backends.
    """
    client = _client()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    return (resp.choices[0].message.content or "").strip()


# ---------- Tagging ----------

_TAG_SYSTEM = (
    "You classify computer science content. Return strict JSON with keys: "
    "  topics      — array of EXACTLY 2 strings chosen from the allowed topics, "
    "                 ordered most-relevant first (closed vocabulary). "
    "  open_topic  — ONE additional short free-form category that best describes "
    "                 the content even if it's not in the allowed list "
    "                 (e.g. 'Distributed-Systems', 'DevOps', 'Bioinformatics', "
    "                 'AI-Safety', 'Cryptography'). 1–3 words, TitleCase, "
    "                 distinct from the topics array. This is the open-vocabulary slot. "
    "  content_type — one of the allowed content_types. "
    "  tags        — array of free-form lowercase subfield tags, max 5. "
    "No prose, JSON only."
)


def tag_item(title: str, excerpt: str | None) -> dict[str, Any]:
    """Returns {topics: [...], content_type: str, tags: [...]}.

    Falls back to a permissive default on parse failure so the pipeline never
    blocks on a flaky LLM response.
    """
    excerpt = (excerpt or "")[:1500]
    user = (
        f"Allowed topics: {', '.join(TOPICS)}\n"
        f"Allowed content_types: {', '.join(CONTENT_TYPES)}\n\n"
        f"TITLE: {title}\n\nEXCERPT: {excerpt}\n\n"
        "Respond with JSON only."
    )
    try:
        raw = _chat(settings.llm_model_tagger, _TAG_SYSTEM, user, max_tokens=300)
        data = _extract_json(raw)

        # Closed-vocabulary slots (must be from TOPICS).
        allowed = [t for t in (data.get("topics") or []) if t in TOPICS]
        # Pad to exactly 2 from the curated TOPICS list if the LLM was stingy.
        seen = set(allowed)
        for fallback in TOPICS:
            if len(allowed) >= 2:
                break
            if fallback not in seen:
                allowed.append(fallback)
                seen.add(fallback)
        allowed = allowed[:2]

        # Open-vocabulary slot — one free-form category. Anything is allowed
        # except a duplicate of what's already in `allowed`.
        open_topic_raw = data.get("open_topic")
        open_topic: str | None = None
        if isinstance(open_topic_raw, str):
            cleaned = re.sub(r"\s+", "-", open_topic_raw.strip())[:48]
            if cleaned and cleaned not in seen:
                open_topic = cleaned

        topics = list(allowed)
        if open_topic:
            topics.append(open_topic)

        ctype = data.get("content_type", "other")
        if ctype not in CONTENT_TYPES:
            ctype = "other"
        tags = [str(t).lower()[:32] for t in (data.get("tags") or [])][:5]
        return {
            "topics": topics,
            "open_topic": open_topic,
            "content_type": ctype,
            "tags": tags,
        }
    except Exception as e:  # pragma: no cover
        log.warning("tag_item failed", err=str(e))
        return {
            "topics": ["Other", "ML"],
            "open_topic": None,
            "content_type": "other",
            "tags": [],
        }


# ---------- Summarization ----------

_SUMMARY_SYSTEM = (
    "You write a one or two sentence neutral summary of a computer science item "
    "for a daily digest. No hype, no marketing language, no emoji. <= 60 words."
)


def summarize(title: str, excerpt: str | None) -> str | None:
    if not excerpt:
        return None
    user = f"TITLE: {title}\n\nEXCERPT: {excerpt[:2000]}\n\nWrite the summary."
    try:
        return _chat(settings.llm_model_summary, _SUMMARY_SYSTEM, user, max_tokens=160)
    except Exception as e:  # pragma: no cover
        log.warning("summarize failed", err=str(e))
        return None


# ---------- Quality scoring ----------

_QUALITY_SYSTEM = (
    "You score whether a computer-science feed item is worth opening for a "
    "technical reader. Return strict JSON only with keys: "
    "technical_depth, specificity, novelty, usefulness, credibility, "
    "attractiveness, hype_penalty, confidence. Each value is a float from 0 to 1. "
    "Reward concrete methods, benchmarks, incidents, releases, tutorials, "
    "measurements, and clear research contributions. Penalize vague marketing "
    "copy, empty news, generic announcements, and titles with too little evidence."
)


def score_item_quality(
    title: str,
    excerpt: str | None,
    *,
    summary: str | None = None,
    content_type: str | None = None,
    source_name: str | None = None,
    source_trust: float | None = None,
) -> float:
    """Return a stable [0, 1] quality prior for ranking."""
    excerpt = (excerpt or "").strip()
    summary = (summary or "").strip()
    heuristic = _heuristic_quality_score(
        title=title,
        excerpt=excerpt,
        summary=summary,
        content_type=content_type,
        source_trust=source_trust,
    )
    if not excerpt and not summary:
        return heuristic

    user = (
        f"CONTENT_TYPE: {content_type or 'unknown'}\n"
        f"SOURCE: {source_name or 'unknown'}\n"
        f"SOURCE_TRUST: {source_trust if source_trust is not None else 'unknown'}\n\n"
        f"TITLE: {title[:500]}\n\n"
        f"SUMMARY: {summary[:500]}\n\n"
        f"EXCERPT: {excerpt[:2200]}\n\n"
        "Respond with JSON only."
    )
    try:
        raw = _chat(settings.llm_model_summary, _QUALITY_SYSTEM, user, max_tokens=220)
        data = _extract_json(raw)
        technical_depth = _coerce_unit_float(data.get("technical_depth"))
        specificity = _coerce_unit_float(data.get("specificity"))
        novelty = _coerce_unit_float(data.get("novelty"))
        usefulness = _coerce_unit_float(data.get("usefulness"))
        credibility = _coerce_unit_float(data.get("credibility"))
        attractiveness = _coerce_unit_float(data.get("attractiveness"))
        hype_penalty = _coerce_unit_float(data.get("hype_penalty"))
        if any(
            v is None for v in (
                technical_depth, specificity, novelty, usefulness,
                credibility, attractiveness, hype_penalty,
            )
        ):
            return heuristic
        score = (
            technical_depth * 0.22
            + specificity * 0.18
            + novelty * 0.16
            + usefulness * 0.18
            + credibility * 0.12
            + attractiveness * 0.14
            - hype_penalty * 0.18
        )
        return max(0.05, min(0.98, round(score, 4)))
    except Exception as e:  # pragma: no cover
        log.warning("score_item_quality failed", err=str(e))
        return heuristic


def _heuristic_quality_score(
    *,
    title: str,
    excerpt: str,
    summary: str,
    content_type: str | None,
    source_trust: float | None,
) -> float:
    text = f"{title}\n{summary}\n{excerpt}".lower()
    score = 0.34
    if len(excerpt) >= 180:
        score += 0.07
    if len(excerpt) >= 500:
        score += 0.05
    if summary:
        score += 0.05
    if content_type in {"paper", "tutorial", "lab_announcement"}:
        score += 0.08
    elif content_type == "news":
        score += 0.04
    if source_trust is not None:
        score += max(-0.08, min(0.08, (source_trust - 0.5) * 0.25))

    strong_terms = (
        "benchmark", "evaluation", "dataset", "architecture", "method",
        "attack", "vulnerability", "cve-", "release", "agent", "retrieval",
        "compiler", "database", "kernel", "training", "inference",
        "robot", "deployment", "postmortem", "measurement",
    )
    weak_terms = (
        "roundup", "weekly", "opinion", "thoughts", "welcome", "hiring",
        "webinar", "event recap",
    )
    if any(term in text for term in strong_terms):
        score += 0.08
    if any(term in text for term in weak_terms):
        score -= 0.09
    return max(0.08, min(0.92, round(score, 4)))


# ---------- Commentary (off until tuned) ----------

_COMMENTARY_PROMPTS: dict[str, str] = {
    "paper": (
        "You are a senior CS researcher. In 3-5 sentences, explain: "
        "(1) what this paper contributes, (2) who should care, "
        "(3) how it relates to recent work in the same area. "
        "No hype, no marketing voice."
    ),
    "blog": (
        "You are a thoughtful engineer. In 3-5 sentences, summarize the core "
        "argument and who would benefit from reading. No hype."
    ),
    "news": (
        "In 3-5 sentences explain what happened and why it matters to a "
        "computer science audience."
    ),
    "lab_announcement": (
        "In 3-5 sentences, summarize the announcement and connect it to the "
        "lab's recent direction. No hype."
    ),
}


def commentary(title: str, excerpt: str | None, content_type: str) -> str | None:
    if not excerpt:
        return None
    system = _COMMENTARY_PROMPTS.get(content_type, _COMMENTARY_PROMPTS["blog"])
    user = f"TITLE: {title}\n\nEXCERPT: {excerpt[:2500]}"
    try:
        return _chat(settings.llm_model_commentary, system, user, max_tokens=350)
    except Exception as e:  # pragma: no cover
        log.warning("commentary failed", err=str(e))
        return None


# ---------- Natural-language filter extraction ----------

_NL_FILTER_SYSTEM = (
    "You convert a user's free-form search query into a JSON object of filters "
    "for a CS feed reader. Return strict JSON only — no prose, no markdown. "
    "All fields are optional; omit them or set to null when not present in the query."
)


_TYPO_FIXES = {
    "recenty": "recent",
    "recnt": "recent",
    "lastest": "latest",
    "newst": "newest",
}

_TOPIC_ALIASES: dict[str, str] = {
    "security": "Security", "cybersecurity": "Security", "cve": "Security",
    "vulnerability": "Security", "vulnerabilities": "Security",
    "threat": "Security", "exploit": "Security", "malware": "Security",
    "ml": "ML", "machine learning": "ML", "deep learning": "ML", "ai": "ML",
    "llm": "ML", "neural": "ML",
    "systems": "Systems", "distributed": "Systems", "operating system": "Systems",
    "database": "DB", "databases": "DB", "db": "DB", "sql": "DB",
    "network": "Networks", "networks": "Networks", "networking": "Networks",
    "robotics": "Robotics", "robot": "Robotics",
    "hci": "HCI", "human-computer": "HCI",
    "programming language": "PL", "programming languages": "PL", "compiler": "PL",
    "theory": "Theory", "complexity": "Theory",
    "graphics": "Graphics", "rendering": "Graphics",
}

_SOURCE_HINTS = (
    "arxiv", "openai", "anthropic", "deepmind", "google", "meta",
    "microsoft", "nvidia", "apple", "hugging face", "cloudflare",
    "github", "vercel", "stripe", "wechat", "krebs", "talos", "mandiant",
    "unit 42", "crowdstrike", "cisa", "schneier", "portswigger",
    "trail of bits", "project zero",
)

_HEURISTIC_STOPWORDS = {
    "show", "me", "the", "a", "an", "of", "about", "from", "with", "for",
    "recent", "recently", "recenty", "latest", "newest", "fresh",
    "this", "last", "year", "years", "first",
    "news", "papers", "paper", "blogs", "blog", "posts", "post",
    "report", "reports", "tutorial", "tutorials", "release", "releases",
}


def _heuristic_nl_filter(query: str, current_year: int) -> dict[str, Any]:
    """Deterministic parser for common feed-search phrases.

    Runs before the LLM so obvious queries (e.g. "show me recent security
    reports") don't depend on model behavior, and tolerates typos like
    "recenty". Returns whichever fields it could pin down.
    """
    text = query.strip()
    low = text.lower()
    for typo, fix in _TYPO_FIXES.items():
        low = re.sub(rf"\b{re.escape(typo)}\b", fix, low)

    out: dict[str, Any] = {}

    if re.search(r"\b(ingested|crawled|fetched)\b", low):
        out["sort"] = "fetched_desc"
    elif re.search(r"\b(recent|latest|newest|fresh)\b", low):
        out["sort"] = "date_desc"
    elif "oldest" in low:
        out["sort"] = "date_asc"

    if "this year" in low:
        out["year"] = current_year
    elif "last year" in low:
        out["year"] = current_year - 1
    else:
        m = re.search(r"\b(199\d|20\d{2}|2100)\b", low)
        if m:
            year = int(m.group(1))
            if 1990 <= year <= current_year + 1:
                out["year"] = year

    for phrase, topic in _TOPIC_ALIASES.items():
        if re.search(rf"\b{re.escape(phrase)}\b", low):
            out["topic"] = topic
            break

    if re.search(r"\b(paper|papers|arxiv|preprint|preprints)\b", low):
        out["content_type"] = "paper"
    elif re.search(r"\b(report|reports|news|incident|breach|advisory|advisories|alert|alerts)\b", low):
        out["content_type"] = "news"
    elif re.search(r"\b(tutorial|tutorials|guide|walkthrough)\b", low):
        out["content_type"] = "tutorial"
    elif re.search(r"\b(release|releases|oss release)\b", low):
        out["content_type"] = "oss_release"
    elif re.search(r"\b(announcement|launch)\b", low):
        out["content_type"] = "lab_announcement"
    elif re.search(r"\b(blog|engineering)\b", low):
        out["content_type"] = "blog"

    for src in _SOURCE_HINTS:
        if src in low:
            out["source"] = src
            break

    # AI-lab posts are lab_announcement, not blog (matches the LLM prompt rule).
    _AI_LABS = {"openai", "deepmind", "anthropic", "google", "meta",
                "microsoft", "nvidia", "apple", "bair", "sail"}
    if out.get("content_type") == "blog" and out.get("source") in _AI_LABS:
        out["content_type"] = "lab_announcement"

    if re.search(r"\b(report|reports)\b", low):
        out["q"] = "report"
    else:
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", low)
        residual = [
            t for t in tokens
            if t not in _HEURISTIC_STOPWORDS
            and t not in _TOPIC_ALIASES
            and t not in _SOURCE_HINTS
            and len(t) > 2
        ]
        if residual:
            out["q"] = " ".join(residual[:6])

    return out


def nl_filter(query: str, current_year: int) -> dict[str, Any]:
    """Extract structured filters from a natural-language search query.

    Returns a dict with optional keys: topic, content_type, source, year, q, sort.
    Falls back to {"q": query} on any LLM/parse failure so the caller still
    has something useful.
    """
    heuristic = _heuristic_nl_filter(query, current_year=current_year)
    structured_keys = {"topic", "content_type", "source", "year", "sort"}
    if len(structured_keys & heuristic.keys()) >= 2:
        return heuristic

    user = (
        f"Today's year: {current_year}.\n"
        f"Allowed topics: {', '.join(t for t in TOPICS if t != 'Other')}\n"
        f"Allowed content_types: {', '.join(c for c in CONTENT_TYPES if c != 'other')}\n"
        "Allowed sort values: smart (best overall), "
        "date_desc (newest by published date), "
        "date_asc (oldest by published date), "
        "fetched_desc (recently ingested), fetched_asc.\n"
        "When the user says recent/latest/newest/fresh, prefer date_desc. "
        "Use fetched_desc only when they explicitly mean recently ingested, crawled, or fetched.\n\n"
        "Important taxonomy hints:\n"
        "- Posts from major AI labs (OpenAI, DeepMind, Anthropic, Google Research, "
        "Meta AI, Microsoft Research, NVIDIA, Apple, BAIR, SAIL) are categorized "
        "as `lab_announcement`, NOT `blog`. If the query mentions one of these labs "
        "and the word \"blog\" or \"post\", set content_type to `lab_announcement`.\n"
        "- Plain `blog` is for engineering / company blogs (Vercel, Stripe, Cloudflare, "
        "GitHub, Netflix, Discord, Airbnb, Spotify, Dropbox, Meta Engineering, etc.).\n"
        "- arXiv content is `paper`.\n\n"
        "Output schema: {\n"
        '  "topic":        one of the allowed topics or null,\n'
        '  "content_type": one of the allowed content_types or null,\n'
        '  "source":       short case-insensitive substring of a source name '
        '(e.g. "arxiv", "openai", "wechat", "deepmind") or null,\n'
        '  "year":         4-digit integer year (resolve "this year" / "last year") or null,\n'
        '  "q":            free-text title keyword(s) (only the salient words) or null,\n'
        '  "sort":         one of the allowed sort values or null\n'
        "}\n\n"
        "Examples:\n"
        '  "ML papers from arxiv this year, newest first"  -> '
        f'{{"topic":"ML","content_type":"paper","source":"arxiv","year":{current_year},"q":null,"sort":"date_desc"}}\n'
        '  "openai 2026 blog posts, newest first"          -> '
        f'{{"topic":null,"content_type":"lab_announcement","source":"openai","year":2026,"q":null,"sort":"date_desc"}}\n'
        '  "vercel 2025 blog"                              -> '
        '{"topic":null,"content_type":"blog","source":"vercel","year":2025,"q":null,"sort":null}\n'
        '  "wechat: large model news"                      -> '
        '{"topic":null,"content_type":null,"source":"wechat","year":null,"q":"large model","sort":null}\n'
        '  "robotics tutorials"                            -> '
        '{"topic":"Robotics","content_type":"tutorial","source":null,"year":null,"q":null,"sort":null}\n'
        '  "transformer attention"                         -> '
        '{"topic":null,"content_type":null,"source":null,"year":null,"q":"transformer attention","sort":null}\n'
        '  "show me the recent security report"            -> '
        '{"topic":"Security","content_type":"news","source":null,"year":null,"q":"report","sort":"date_desc"}\n\n'
        f"User query: {query}\n\nRespond with JSON only."
    )
    try:
        raw = _chat(settings.llm_model_tagger, _NL_FILTER_SYSTEM, user, max_tokens=200)
        data = _extract_json(raw)
    except Exception as e:  # pragma: no cover
        log.warning("nl_filter failed", err=str(e))
        return {"q": query.strip() or None}

    out: dict[str, Any] = {}
    topic = data.get("topic")
    if isinstance(topic, str) and topic in TOPICS and topic != "Other":
        out["topic"] = topic

    ctype = data.get("content_type")
    if isinstance(ctype, str) and ctype in CONTENT_TYPES and ctype != "other":
        out["content_type"] = ctype

    source = data.get("source")
    if isinstance(source, str) and source.strip():
        out["source"] = source.strip()[:64]

    year = data.get("year")
    if isinstance(year, int) and 1990 <= year <= current_year + 1:
        out["year"] = year

    q = data.get("q")
    if isinstance(q, str) and q.strip():
        out["q"] = q.strip()[:200]

    sort = data.get("sort")
    if isinstance(sort, str) and sort in {
        "smart", "date_desc", "date_asc", "fetched_desc", "fetched_asc",
    }:
        out["sort"] = sort

    # If the LLM returned valid JSON but every field was null/invalid,
    # fall back to a plain title-substring search so the UI still does
    # something with the user's query.
    if not out:
        text = query.strip()
        if text:
            out["q"] = text[:200]

    return out


# ---------- Helpers ----------

_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def _extract_json(s: str) -> dict[str, Any]:
    """Pull the first {...} block out of an LLM response and parse it."""
    s = s.strip()
    # Strip Qwen3.5 thinking-mode block if it leaked through.
    if "</think>" in s:
        s = s.split("</think>", 1)[1].strip()
    # Strip markdown fences if present.
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?", "", s).rstrip("`").strip()
    m = _JSON_BLOCK.search(s)
    if not m:
        raise ValueError("no JSON found in LLM response")
    return json.loads(m.group(0))


def _coerce_unit_float(v: Any) -> float | None:
    if isinstance(v, (int, float)):
        out = float(v)
    elif isinstance(v, str):
        try:
            out = float(v.strip())
        except ValueError:
            return None
    else:
        return None
    return out if 0.0 <= out <= 1.0 else None
