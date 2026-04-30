---
name: Qwen3.5 thinking-mode trap
description: Every chat call must pass enable_thinking=false in extra_body or JSON-emitting prompts (tagger, NL filter) silently degrade.
type: project
originSessionId: 49058c9f-2756-4919-ae2a-049ce8c5f18e
---
The Qwen3.5 served at `api.ai2wj.com` defaults to thinking-mode (`<think>...</think>` prefix). With `max_tokens` budgets in the 200–400 range, the thinking block eats the entire budget and the model returns no JSON — so `_extract_json` raises `"no JSON found in LLM response"` and every tagger call falls back to `topic:Other`. The corpus ends up entirely "Other"-tagged and the topic filter looks broken.

**Fix already in place** (`backend/app/services/llm.py`, `_chat`):
```python
resp = client.chat.completions.create(
    model=model,
    messages=[...],
    max_tokens=max_tokens,
    temperature=0.2,
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)
```
Plus `_extract_json` strips `</think>` defensively if a thinking block ever leaks through.

**Why:** Found by inspecting backend logs during the first ingest — saw `<think>` in vLLM stdout that the user surfaced, and tagger fallback rate was ~100%. After disabling thinking, tags came out as `topic:HCI`, `topic:Systems`, real subfield strings.

**How to apply:**
- **Any new code path that calls Qwen via the OpenAI SDK in this repo must go through `_chat()`** so it inherits the `extra_body`. Don't reach for `client.chat.completions.create` directly.
- If switching models (away from Qwen3.5), the `extra_body` is silently ignored by other backends — leave it in.
- If tagger output suddenly becomes "Other" again, check first whether someone added a new chat call site that bypasses `_chat()`.
