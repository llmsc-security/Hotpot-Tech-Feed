---
name: AI-lab posts are lab_announcement, not blog
description: NL search must alias "blog from <AI lab>" to content_type=lab_announcement; the tagger labels them that way at ingest time.
type: project
originSessionId: 49058c9f-2756-4919-ae2a-049ce8c5f18e
---
The ingest tagger classifies posts from major AI labs (OpenAI Blog, DeepMind Blog, Anthropic News, Google Research Blog, Meta AI Blog, Microsoft Research Blog, NVIDIA Developer Blog, Apple Machine Learning, Berkeley BAIR, Stanford SAIL) as `content_type = lab_announcement`, not `blog`. `blog` is reserved for engineering/company blogs (Vercel, Stripe, Cloudflare, GitHub, Netflix, Discord, Airbnb, Spotify, Dropbox, Meta Engineering, …).

**Implication:** A user query like *"openai 2026 blog posts, newest first"* must extract `content_type: "lab_announcement"`. The NL filter prompt (`backend/app/services/llm.py::nl_filter`) carries explicit aliasing rules for the AI labs above, with a worked example.

**Why:** Without the alias, the NL search said "0 items" for any AI-lab-blog query — confusing because the items existed (172 OpenAI items in 2026 alone) but were tagged differently. Discovered when the user typed the query and saw zero results.

**How to apply:**
- Adding a new source: decide whether it's an AI-lab announcement feed or an engineering blog, and either match the existing tagger pattern or update the alias list.
- Adding a new content_type: extend the alias rules in the NL prompt so the LLM keeps mapping vernacular ("blog post") to the correct enum value.
- Don't try to "fix" the tagger to use `blog` for AI labs — the distinction is useful in the digest output and the alias keeps the user-facing query natural.
