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
    """Single-shot chat completion."""
    client = _client()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
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


# ---------- Helpers ----------

_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def _extract_json(s: str) -> dict[str, Any]:
    """Pull the first {...} block out of an LLM response and parse it."""
    s = s.strip()
    # Strip markdown fences if present.
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?", "", s).rstrip("`").strip()
    m = _JSON_BLOCK.search(s)
    if not m:
        raise ValueError("no JSON found in LLM response")
    return json.loads(m.group(0))
