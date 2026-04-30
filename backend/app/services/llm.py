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
    "You classify computer science content. Return strict JSON with keys "
    "topics (array of strings from the allowed topics), content_type (string), "
    "tags (array of free-form lowercase subfield tags, max 5). No prose, JSON only."
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
        topics = [t for t in data.get("topics", []) if t in TOPICS] or ["Other"]
        ctype = data.get("content_type", "other")
        if ctype not in CONTENT_TYPES:
            ctype = "other"
        tags = [str(t).lower()[:32] for t in (data.get("tags") or [])][:5]
        return {"topics": topics, "content_type": ctype, "tags": tags}
    except Exception as e:  # pragma: no cover
        log.warning("tag_item failed", err=str(e))
        return {"topics": ["Other"], "content_type": "other", "tags": []}


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


def nl_filter(query: str, current_year: int) -> dict[str, Any]:
    """Extract structured filters from a natural-language search query.

    Returns a dict with optional keys: topic, content_type, source, year, q.
    Falls back to {"q": query} on any LLM/parse failure so the caller still
    has something useful.
    """
    user = (
        f"Today's year: {current_year}.\n"
        f"Allowed topics: {', '.join(t for t in TOPICS if t != 'Other')}\n"
        f"Allowed content_types: {', '.join(c for c in CONTENT_TYPES if c != 'other')}\n"
        "Allowed sort values: date_desc (newest), date_asc (oldest), "
        "fetched_desc (recently ingested), fetched_asc.\n\n"
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
        '{"topic":null,"content_type":null,"source":null,"year":null,"q":"transformer attention","sort":null}\n\n'
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
        "date_desc", "date_asc", "fetched_desc", "fetched_asc",
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
