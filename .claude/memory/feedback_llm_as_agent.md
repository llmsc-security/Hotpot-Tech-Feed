---
name: LLM-as-agent over hardcoded UI
description: For LLM-backed search/filter surfaces, default to a single NL input + active-filter chips; do not introduce manual dropdowns or rule-based fallbacks.
type: feedback
originSessionId: 49058c9f-2756-4919-ae2a-049ce8c5f18e
---
In LLM-backed UI features, prefer "single NL input → LLM extracts structured intent → applied as removable chips" over hardcoded dropdowns / multi-selects / rule-based parsing.

**Why:** The user said verbatim *"i dinot like you use the rule or hardcode to service or response the user, instead, you have the LLm as agent, llm will understand user and interact with you by formular user filter /sort /serach condidtion"* after seeing a Browse page that paired the Ask box with a row of topic / type / sort dropdowns. They want the agent to own the search surface; chips are the only knobs.

**How to apply:**
- New filter/search UI in this repo → start with one input + Ask button + clickable example tips + active-chip display. No `<select>` rows.
- Backend extraction must be defensive (handle null fields, fall back to `q=query`, alias domain-specific synonyms inside the LLM prompt rather than via post-hoc rules in code).
- Don't bring back manual dropdowns "just for power users." If the LLM gets it wrong, the answer is a better prompt or better chip-removal UX, not a parallel ruleset.
