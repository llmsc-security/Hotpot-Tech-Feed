# Content Quality Upgrade Plan

Date: 2026-05-01

## Goal

Improve three user-facing behaviors without adding manual filter UI:

1. Better crawler intake quality
2. Better ranking of items by substance and end-user appeal
3. Better query suggestions that help users discover ideas

Assumption: the repo already has a working LLM configured in `.env`, and all new
LLM calls must continue to go through `backend/app/services/llm.py::_chat()`.

Current `.env` reality:

- Qwen is available through `OPENAI_BASE_URL=https://api.ai2wj.com/v1/`.
- `LLM_MODEL_TAGGER`, `LLM_MODEL_SUMMARY`, and `LLM_MODEL_COMMENTARY` are not
  explicitly set in `.env`; `docker-compose.yml` defaults them to
  `Qwen/Qwen3.5-397B-A17B`, and a runtime scoring probe succeeded through that
  model alias.
- Qdrant is configured.
- BGE-M3 embeddings are configured but disabled with `EMBEDDINGS_ENABLED=false`.

Implication:

- Qwen-based quality scoring and cached suggestion generation are available now.
- Hybrid semantic retrieval with BGE-M3/Qdrant should remain a later switch
  unless embeddings are enabled and the backend image includes the embeddings
  extra.

Current hardware/tooling reality:

- The host has four NVIDIA L40S GPUs.
- GPU index `3` is the free device and should be used for local embedding or
  reranker experiments.
- `uv` is installed and can create an isolated environment for model/tool
  evaluation before dependencies are baked into Docker.

Execution constraint:

- Run local embedding/reranker experiments with `CUDA_VISIBLE_DEVICES=3`.
- Use a `uv` virtualenv for exploratory libraries first.
- Only move dependencies into `backend/pyproject.toml` and Docker after the
  experiment proves useful.

## Implementation Status

Implemented on 2026-05-01:

- Added Trafilatura extraction via `backend/app/services/extract.py`.
- HTML sitemap ingestion now fetches each page once, extracts title and main
  text, and stores the extracted body as `excerpt`.
- RSS ingestion now supports `max_results`, `max_age_days`, and optional
  `extract_full_text` for weak feed excerpts.
- arXiv ingestion now supports optional `max_age_days`.
- Added Qwen-backed pointwise item quality scoring in
  `backend/app/services/llm.py::score_item_quality()`, with a heuristic
  fallback when the LLM or JSON parse fails.
- Enrichment now writes `Item.score` when missing or zero; `hotpot enrich-all`
  now backfills missing summaries or missing quality scores.
- `/items` defaults to `sort=smart`, combining text relevance, item quality,
  freshness, source trust, engagement, and content-type prior, followed by a
  simple source/topic/title diversity pass.
- Text search now covers title, excerpt, summary, lab, venue, and tags.
- Added deterministic `/items/suggest` typeahead suggestions from recent
  queries, sources, topics, titles, and templated idea prompts.
- Browse UI now uses the suggestion endpoint while keeping the single natural
  language input + chips product shape.
- Added an exposure signal for repeated coverage:
  - `items.exposure_count`
  - `items.exposure_sources`
  - duplicate ingest now records independent sources instead of discarding the
    signal after deduplication.
- Added `/items/hot`, which clusters recent canonical items by CVE/title
  and ranks them by repeated exposure, LLM quality score, freshness, source
  trust, and clicks.
- Browse homepage now shows 20 hot-news cards when no filter chips are active.
- Added Chinese security intake:
  - Doonsec WeChat category adapter for security warnings, reproduction,
    original posts, hot posts, and high-read discussion items.
  - FreeBuf, 安全客, 先知, Seebug Paper, 安全脉搏, 嘶吼, SecWiki, 离别歌, 360CERT.
  - 量子位 QbitAI for Chinese AI/tech news.
- Added cron-polled HTML intake:
  - `backend/app/adapters/html_index.py` turns ordinary blog/news listing pages
    into RSS-like sources by extracting article links and relying on canonical
    URL dedup as the seen-set.
  - `hotpot ingest-kind html` and `scripts/cron_hotpot.sh ingest-html` let the
    host crontab poll non-RSS sources separately from RSS/arXiv.
  - Added capped sources for AI2, Mistral, ByteDance Seed, Supabase, Wiz, plus
    additional validated RSS/Atom sources across AI labs, infra, security, and
    independent explainers.

Verified on 2026-05-01:

- `python3 -m compileall app`
- `docker compose build backend gateway`
- gateway frontend build ran `tsc -b && vite build`
- `docker compose up -d backend gateway`
- `GET /api/stats` returned `{"items":5680,"sources":77}`
- `GET /api/items/suggest?q=agent&limit=5` returned topic/title suggestions
- `GET /api/items?limit=5&sort=smart` returned ranked items
- `POST /api/items/nl-search` maps "recent" to `date_desc`, not
  `fetched_desc`
- `hotpot enrich-all --limit 20` processed 20 items successfully and produced
  non-zero quality scores

Remaining rollout:

- Run a larger `hotpot enrich-all --limit N` backfill in batches until most
  canonical items have non-zero `Item.score`.
- Rebuild backend/gateway after seed/source changes because seed data is baked
  into the backend image and the frontend is baked into the gateway image.
- Seed the expanded source list, then ingest the new Chinese/security sources.
- Install or refresh the host crontab from `crontab.example` if HTML index
  sources should keep acting like feeds without Celery.
- Add Postgres FTS/`pg_trgm` indexes once query volume justifies migrations.
- Add source-governance metrics after enough scored items exist.
- Evaluate BGE-M3/Qdrant hybrid retrieval and local rerankers later on
  `CUDA_VISIBLE_DEVICES=3`.

## Pre-Implementation Survey

### Code-path survey

- Before this implementation, ingest persisted new items, then enriched them in
  parallel:
  - `backend/app/tasks/ingest.py`
  - `backend/app/tasks/enrich.py`
- Enrichment added tags, summary, optional commentary, embeddings.
  - It did **not** compute a per-item quality score.
- `Item.score` existed in the schema but was unused in practice:
  - `backend/app/models/item.py`
  - `backend/alembic/versions/0001_initial.py`
- Browse/search ranking was limited to:
  - `published_at`
  - `fetched_at`
  - no content-quality ranking
  - `backend/app/api/routes/items.py`
- The input box supported:
  - LLM NL filter extraction
  - recent-search recall
  - no real suggestion engine
  - `frontend/src/pages/Browse.tsx`
- RSS intake pulled full feeds with no feed-level recency/volume guardrail:
  - `backend/app/adapters/rss.py`
- HTML sitemap intake fetched titles but often had no excerpt/body text:
  - `backend/app/adapters/html.py`

### Live corpus survey

Observed against the local stack before implementation on 2026-05-01:

- Canonical items: `5680`
- Average item score: `0.000`
- Min/max item score: `0 / 0`
- Zero-scored canonical items: `5680`

This means the system currently has **no item-level ranking signal** at all.

Top sources by canonical-item count:

- Datadog Engineering: `1507`
- Vercel Blog: `1045`
- OpenAI Blog: `853`
- PlanetScale Blog: `252`
- NVIDIA Developer Blog: `100`
- arXiv cs.LG: `100`

Content-type mix:

- `blog`: `3351`
- `lab_announcement`: `1253`
- `paper`: `780`
- `news`: `295`

Click-signal survey:

- clicked items: `2`
- average clicks across clicked items: `2.5`
- max clicks: `3`

Source-quality run survey:

- `source_quality_runs`: `0`
- `search_logs`: `19`

This means the current trust and ranking system is still mostly bootstrapped
from static seed assumptions, not real usage.

### Freshness skew survey

The biggest volume sources were backfilled in one shot:

- Datadog Engineering:
  - oldest published item: `2011-12-20`
  - newest published item: `2026-04-23`
  - all fetched on: `2026-05-01`
- Vercel Blog:
  - oldest published item: `2017-05-15`
  - all fetched on: `2026-04-30`
- OpenAI Blog:
  - oldest published item: `2016-02-25`
  - all fetched on: `2026-04-30`

Implication:

- any ranking mode using `fetched_at desc` treats old backfilled material as
  “fresh”
- this distorts “recent/latest” user queries

### Text-coverage survey

Canonical items missing excerpt: `186 / 5680`

By kind:

- `rss`: `118 / 4830`
- `arxiv`: `0 / 780`
- `html`: `68 / 70`

Notable excerpt-poor sources:

- OpenAI Blog: `100 / 853` missing excerpt
- Princeton Language + Intelligence: `29 / 29`
- Anthropic News: `27 / 27`
- DeepSeek news: `10 / 10`

Implication:

- the HTML adapter often gives only a title
- some RSS feeds provide weak summaries
- LLM tagging/summarization/ranking has too little evidence for those items

## Root Causes Of Poor Content Quality

### 1. No item-level quality scoring exists in practice

This is the primary failure.

- `Item.score` exists but all current items have `score = 0`
- `backend/app/tasks/enrich.py` never assigns a meaningful quality score
- `backend/app/api/routes/items.py` never ranks by quality

Result:

- a weak vendor post and a strong paper are treated almost the same if they are
  similarly recent

### 2. The system confuses crawl-time freshness with publication freshness

`backend/app/adapters/rss.py` ingests whatever the feed exposes. There is no
RSS-side `max_results` or `max_age_days` intake guardrail today.

Result:

- large historical backfills from high-volume sources flood the corpus
- `fetched_at` becomes a crawler artifact, not a freshness signal
- “recent/latest” queries are vulnerable to backfill pollution

### 3. Source mix is volume-biased, not user-value-biased

The current source set is heavily dominated by broad engineering blogs and lab
announcement feeds. That is not automatically wrong, but without a downstream
quality/ranking layer it biases the feed toward:

- corporate publishing velocity
- old historical archives
- announcement-heavy content

instead of:

- strong papers
- concrete technical writeups
- high-signal security/research items

### 4. Source trust is not yet learning from real behavior

`backend/app/services/discovery.py::score_sources()` exists, but there are
currently:

- no `source_quality_runs`
- almost no click data

Result:

- `trust_score` is mostly seed-time prior, not a true learned signal
- the system cannot downweight disappointing high-volume sources yet

### 5. Weak content extraction reduces LLM judgment quality

Two specific problems:

- HTML sitemap sources usually provide only title + URL
- some RSS feeds provide poor or missing summaries

Result:

- the LLM sees too little technical content to judge substance well
- summaries, tags, and future ranking signals become less reliable

### 6. The suggestion layer is nearly absent

Current browse UX only has:

- NL query box
- recent-search recall

It does **not** generate:

- source suggestions
- topic hints
- title/entity completions
- idea prompts

Result:

- users need to invent queries from scratch
- the product does not actively guide discovery

## SOTA And Practical Algorithm Survey

### What mature recommendation systems do

Modern production recommenders are usually multi-stage systems, not one model:

1. candidate generation
2. scoring/ranking
3. final re-ranking

This is the architecture described in Google's recommendation-system guidance:
candidate generation narrows the corpus, scoring ranks a smaller set, and
re-ranking handles freshness, diversity, fairness, and business/product
constraints.

Why this matters for Hotpot:

- Hotpot should not ask the LLM to rank the whole corpus.
- The first stage should be cheap and broad.
- The LLM should be used where it adds judgment: scoring item quality and
  optionally reranking a small top-K list.

Reference:

- Google recommendation overview: https://developers.google.com/machine-learning/recommendation/overview/types
- Google candidate generation: https://developers.google.com/machine-learning/recommendation/overview/candidate-generation
- Google scoring: https://developers.google.com/machine-learning/recommendation/dnn/scoring
- Google re-ranking: https://developers.google.com/machine-learning/recommendation/dnn/re-ranking

### Retrieval and first-stage ranking

The practical first-stage retrieval choices are:

- lexical retrieval: PostgreSQL full-text search / BM25-style scoring
- fuzzy matching: `pg_trgm`
- semantic retrieval: embeddings in Qdrant
- hybrid fusion: combine lexical + semantic result lists

SOTA direction:

- Dense retrieval is useful for semantic matching, but exact technical terms,
  source names, CVE IDs, model names, and arXiv phrases still need lexical
  matching.
- Sparse learned retrieval such as SPLADE improves lexical retrieval with term
  expansion, but it is heavier than Hotpot needs for the first implementation.
- BGE-M3 is a strong future fit because it supports dense, sparse, and
  multi-vector retrieval in one multilingual model family.

Recommendation for Hotpot:

- Phase 1 should use PostgreSQL text/fuzzy matching and the existing fields.
- Phase 2 can enable `BAAI/bge-m3` + Qdrant for hybrid recall.
- Do not add SPLADE/ColBERT-style serving infrastructure before the simpler
  ranking loop works.

References:

- SPLADE: https://arxiv.org/abs/2107.05720
- SPLADE v2: https://arxiv.org/abs/2109.10086
- BGE-M3: https://arxiv.org/abs/2402.03216
- BGE-M3 model card: https://huggingface.co/BAAI/bge-m3
- Qdrant hybrid queries: https://qdrant.tech/documentation/search/hybrid-queries/
- Qdrant reranking tutorial: https://qdrant.tech/documentation/advanced-tutorials/reranking-hybrid-search/

### LLM scoring and reranking

Recent work shows LLMs are useful rankers, but mostly as rerankers over a
limited candidate set.

Useful patterns:

- pointwise scoring: ask the model to assign fine-grained labels/scores to one
  item at a time
- pairwise ranking: ask which of two candidates is better
- listwise ranking: ask the model to order a short list
- self-calibrated/list-view scoring: make scores comparable across candidates

Findings that apply to Hotpot:

- Fine-grained labels are better than binary yes/no relevance labels.
- Pairwise prompting can be strong but gets expensive as candidate count grows.
- Listwise reranking is useful for a top-K page, but direct global ranking over
  thousands of items is not practical.
- LLM-generated labels can be noisy; post-processing/calibration and fallback
  heuristics are necessary.

Recommendation for Hotpot:

- Use pointwise LLM scoring at ingest for stable `Item.score`.
- Use a structured rubric, not a single vague "quality" prompt.
- Use optional listwise reranking only for top 20-50 search candidates later.
- Avoid pairwise ranking for now because Qwen calls would multiply quickly.

References:

- RankGPT / listwise LLM ranking: https://aclanthology.org/2023.emnlp-main.923/
- Pairwise Ranking Prompting: https://aclanthology.org/2024.findings-naacl.97/
- Fine-grained relevance labels: https://aclanthology.org/2024.naacl-short.31/
- Self-calibrated listwise reranking: https://arxiv.org/abs/2411.04602
- LLM4Rerank: https://arxiv.org/abs/2406.12433
- Consolidating LLM ranking/relevance predictions: https://aclanthology.org/2024.emnlp-main.25/

### Feed/content quality scoring

For this product, quality should mean "worth opening for a technical reader",
not "likely to get clicks at any cost".

The scoring rubric should separate:

- technical depth
- specificity
- novelty/new information
- actionability or research value
- credibility/source grounding
- attractiveness/open-worthiness
- hype or vagueness penalty

This follows the practical pattern from recommendation systems: the scoring
model should optimize for user satisfaction, while final reranking handles
freshness, diversity, and safety constraints. It also avoids turning raw clicks
into the only definition of quality while the project has little usage data.

Practical open-source examples support this direction:

- Horizon uses AI-powered item scoring to filter noisy multi-source feeds.
- Kagi Kite emphasizes curated high-quality source sets and enough feeds per
  category to preserve coverage/diversity.
- Metarank is a practical learn-to-rank engine, but it needs event volume that
  Hotpot does not yet have.

Recommendation for Hotpot:

- Start with LLM-scored item quality because Hotpot is cold-start and
  content-heavy.
- Add impression/click learning later after there is enough behavior data.
- Keep source-level quality separate from item-level quality.

References:

- Horizon: https://github.com/Thysrael/Horizon
- Kagi Kite public repo: https://github.com/kagisearch/kite-public
- Metarank: https://github.com/metarank/metarank

### Freshness, popularity, and diversity

News/feed recommendation research and production guidance agree that freshness,
popularity, and diversity should be explicit ranking features or reranking
constraints.

Relevant lessons:

- News recommendation often combines content matching with time-aware
  popularity, especially for cold-start users.
- Recommendation systems need diversity because a page full of near-duplicates
  reduces discovery value.
- Popularity/click signals are useful but can create popularity bias if they
  dominate too early.

Recommendation for Hotpot:

- Use `published_at` for content freshness.
- Use `fetched_at` only as a fallback or for an explicit "recently ingested"
  intent.
- Add source/topic diversity in the final top-N page.
- Use `click_count` as a small boost until impressions exist.
- Add impression logging before any serious CTR learning.

References:

- PP-Rec time-aware news popularity: https://aclanthology.org/2021.acl-long.424/
- Diversity/cold-start content recommendation: https://aclanthology.org/2024.lrec-main.766/
- Accuracy, novelty, and coverage reranking: https://arxiv.org/abs/1803.00146
- Personalized re-ranking: https://arxiv.org/abs/1904.06813

### Suggestion algorithms

The suggestion box should help users form better natural-language queries.
It should not become a manual filter UI.

Practical suggestion sources:

- recent user searches
- high-quality sources/labs matching the prefix
- topics and tags with strong item counts
- titles/entities from high-score items
- generated idea prompts from trending topics

Recommended architecture:

- Keystroke path: deterministic, cached, fast.
- Use SQL prefix/fuzzy matching and existing corpus metadata.
- Do not call the LLM on every keystroke.
- Optional LLM idea generation should run in the background or be cached from
  daily corpus statistics.

Why:

- Suggestions must feel instant.
- LLM calls on every input change would add latency and cost.
- The user-facing surface remains NL input + chips, matching the project rule.

## Algorithm Selection For Hotpot

### Further adapted-tool investigation

The first survey identified broad ranking patterns. A second pass compared
available tools and algorithms against Hotpot's actual constraints:

- existing FastAPI/Postgres/Qdrant stack
- Qwen already configured through `.env` and reachable via the existing
  OpenAI-compatible endpoint
- mixed arXiv/RSS/HTML-sitemap corpus
- very little click/impression data
- user preference for LLM-agent search, not manual filter UI
- single-host deployment with low operational overhead

The better fit is not to add a large ranking subsystem immediately. The highest
leverage adapted idea is:

1. improve evidence quality by extracting article text better
2. score item value at ingest with Qwen and a stable rubric
3. combine quality with relevance/freshness/source trust at query time
4. rerank the final page for diversity and anti-backfill behavior
5. add learned ranking only after impression data exists

### Tool fit matrix

Adopt now:

- Trafilatura for article text extraction from HTML-sitemap pages and weak RSS
  excerpts.
- PostgreSQL full-text search with weighted `tsvector` and `ts_rank_cd` for
  lexical relevance.
- PostgreSQL `pg_trgm` for fuzzy suggestions and source/title matching.
- Qwen pointwise scoring for item-quality labels during enrichment, using the
  configured `Qwen/Qwen3.5-397B-A17B` model through `_chat()`.
- Maximal Marginal Relevance (MMR) style page reranking for diversity.

Adopt later:

- BGE-M3 + Qdrant hybrid retrieval after the deterministic ranking loop works.
- A local cross-encoder/reranker such as `mxbai-rerank-base-v2`,
  `bge-reranker`, or a SentenceTransformers CrossEncoder for top-K query
  relevance.
- XGBoost LambdaMART or Metarank after Hotpot records enough impressions and
  clicks to train with position-bias awareness.

Do not adopt now:

- ColBERT/late-interaction serving.
- DPP-based diversity.
- LLM listwise ranking over the whole corpus.
- LLM suggestions on every keystroke.
- Metarank as a service before the event stream exists.

### Why Trafilatura is now the first recommended tool

The current HTML sitemap adapter often stores only title + URL, which weakens
LLM classification, summaries, scoring, and search. Trafilatura is a better fit
than building custom extraction rules because it can extract main text and
metadata, has fallback algorithms such as readability/jusText, and is designed
for article/blog extraction. Newspaper4k is simpler and useful for news, but
Trafilatura is the better general-purpose choice for this corpus because Hotpot
has engineering blogs, lab pages, and sitemap-derived HTML pages, not only
traditional news sites.

Adapted design:

- Keep RSS/arXiv adapters as canonical source discovery.
- When `RawItem.excerpt` is missing or too short, fetch the canonical URL and
  run Trafilatura.
- Store extracted text as `excerpt` capped to the existing size budget.
- Track extraction coverage per source for source governance.
- Do not require JavaScript rendering in phase 1; only add Playwright for a
  small allowlist of JS-only sources if necessary.

References:

- Trafilatura project: https://github.com/adbar/trafilatura
- Trafilatura core functions: https://trafilatura.readthedocs.io/en/latest/corefunctions.html
- Newspaper4k quickstart: https://newspaper4k.readthedocs.io/en/latest/user_guide/quickstart.html

### Why Postgres FTS + pg_trgm is the first retrieval layer

Hotpot is not yet at a corpus size where a separate search service is required.
Postgres already owns the item metadata, tags, source names, and search logs.
The practical first step is to add a weighted text-search vector:

- title: highest weight
- source/lab/venue: high weight
- tags/categories: medium weight
- summary/excerpt: medium/low weight

Then combine `ts_rank_cd` with non-text features in the application ranking
formula. `pg_trgm` should support fuzzy source/title/query-history suggestions.

Adapted design:

- Postgres handles first-stage candidate retrieval and suggestions.
- Qdrant only joins once embeddings are enabled and measured.
- No Elasticsearch/OpenSearch service is needed for the current scale.

References:

- PostgreSQL ranking functions: https://www.postgresql.org/docs/current/textsearch-controls.html
- PostgreSQL GIN text search indexes: https://www.postgresql.org/docs/17/textsearch-indexes.html
- PostgreSQL `pg_trgm`: https://www.postgresql.org/docs/17/pgtrgm.html

### Why MMR beats heavier diversity methods here

Diversity is important because sources like Datadog, Vercel, and OpenAI can
dominate a page after a backfill. DPPs and learned diverse rerankers are more
powerful, but they add complexity and need better feature calibration. MMR is a
good adapted fit because it is cheap, explainable, and can use existing fields:

- source name
- content type
- primary topic
- title similarity
- optional embedding similarity later

Adapted design:

- First compute a base score.
- Build the visible page greedily.
- Penalize candidates similar to already selected items.
- Similarity starts as same source/topic plus trigram title overlap.
- Later, replace or augment similarity with embeddings.

References:

- Google re-ranking guidance: https://developers.google.com/machine-learning/recommendation/dnn/re-ranking
- MMR background: https://aclanthology.org/X98-1025.pdf
- DPP recommendation reference: https://arxiv.org/abs/1805.09916

### Why local cross-encoder reranking is a later option

The SOTA retrieval pattern is hybrid retrieval followed by a neural reranker.
For Hotpot, a cross-encoder can be useful for query relevance once the
candidate pool is already good. But it should not be the first fix because the
known failures are currently:

- missing content text
- all `Item.score = 0`
- backfill freshness pollution
- no impression data

Candidate tools for later:

- `rerankers`: unified API for cross-encoders, FlashRank, RankLLM, ColBERT, and
  API rerankers.
- `mxbai-rerank-base-v2`: multilingual/code-capable open reranker, useful for
  technical content if GPU memory allows.
- SentenceTransformers CrossEncoder: stable, well-documented, can score
  query-document pairs directly.
- FlashRank: useful if CPU-only low-latency reranking is required.

Adapted design:

- Add a reranker abstraction only after Postgres ranking has a measurable
  baseline.
- Rerank at most top 50 candidates.
- Cache query/document rerank scores for repeated queries.
- Keep Qwen listwise reranking as an evaluation tool or admin-only experiment,
  not the default request path.

References:

- `rerankers` library: https://github.com/AnswerDotAI/rerankers
- Mixedbread rerankers: https://github.com/mixedbread-ai/mxbai-rerank
- SentenceTransformers CrossEncoder: https://www.sbert.net/docs/package_reference/cross_encoder/
- FlashRank: https://github.com/PrithivirajDamodaran/FlashRank

### Why LambdaMART/Metarank is not phase 1

Learning-to-rank is the right long-term direction once Hotpot records enough
ranking events. But today the project has almost no clicks and no impressions,
so a LambdaMART model would learn little and risk overfitting source popularity.

Adapted design:

- First add impression logging: query, returned item IDs, positions, filters,
  timestamp.
- Keep click events.
- After enough events exist, train XGBoost LambdaMART or use Metarank.
- Use position-bias-aware training when click data is the label source.

References:

- XGBoost learning to rank: https://xgboost.readthedocs.io/en/release_3.2.0/tutorials/learning_to_rank.html
- Metarank: https://github.com/metarank/metarank
- Metarank supported models: https://docs.metarank.ai/reference/overview/supported-ranking-models

### Adapted final architecture

The best-fit architecture for this repo is:

1. Source intake:
   - RSS/arXiv/HTML adapters
   - max age/result caps
   - Trafilatura fallback extraction for weak excerpts
2. Enrichment:
   - Qwen tags
   - Qwen summary
   - Qwen item-quality rubric
   - quality fallback heuristic
3. Candidate retrieval:
   - filters from NL agent
   - Postgres FTS/trigram
   - optional Qdrant hybrid recall later
4. Ranking:
   - weighted relevance
   - `Item.score`
   - source trust
   - publication freshness
   - small engagement prior
5. Page reranking:
   - MMR diversity
   - source caps
   - stale backfill penalty
6. Suggestions:
   - deterministic SQL suggestions
   - cached idea prompts generated offline from high-quality topics/sources
7. Learning loop:
   - impressions + clicks
   - source quality recalibration
   - optional LambdaMART/Metarank after data volume is real

### Selected approach

Use a three-layer ranking system:

1. Candidate retrieval:
   - current SQL filters
   - title/excerpt/summary/source/tag text matching
   - later: optional Qdrant/BGE-M3 semantic candidates
2. Scoring:
   - query relevance
   - LLM item quality score
   - source trust
   - publication freshness
   - weak engagement boost
3. Re-ranking:
   - source diversity cap
   - topic/content-type diversity cap
   - stale backfill penalty
   - duplicate/near-duplicate penalty

### Why this is the best project fit

- The corpus is small enough that PostgreSQL ranking is adequate now.
- The project already has Qwen configured and a safe `_chat()` wrapper.
- `Item.score` already exists, so item quality can be added without a schema
  migration.
- Qdrant and BGE-M3 are already anticipated by the codebase, but embeddings are
  disabled; they should be the second retrieval upgrade, not the first fix.
- The host has a free L40S GPU, so local BGE-M3 and reranker experiments are
  realistic once the deterministic baseline exists.
- The project has almost no click data, so learning-to-rank systems are
  premature.

### Recommended score formula

Initial deterministic rank after filters:

`rank = 0.40 * relevance + 0.25 * item_quality + 0.15 * freshness + 0.10 * source_trust + 0.05 * engagement + 0.05 * content_type_prior`

Where:

- `relevance`: text match against title, excerpt, summary, lab, venue, tags
- `item_quality`: LLM-scored `Item.score`, with heuristic fallback
- `freshness`: decay from `published_at`, fallback to `fetched_at`
- `source_trust`: existing `Source.trust_score`
- `engagement`: `log1p(click_count)`, capped
- `content_type_prior`: small boost for papers/lab announcements/tutorials when
  query intent is broad

Final top-N reranking:

- no single source should dominate the first page
- downweight multiple items with very similar titles/tags
- do not let historical backfills outrank newly published items on "latest"
  queries

### LLM quality prompt shape

The LLM should return strict JSON:

```json
{
  "technical_depth": 0.0,
  "specificity": 0.0,
  "novelty": 0.0,
  "usefulness": 0.0,
  "credibility": 0.0,
  "attractiveness": 0.0,
  "hype_penalty": 0.0,
  "confidence": 0.0
}
```

The stored `Item.score` should be a blended value:

`score = 0.22*technical_depth + 0.18*specificity + 0.16*novelty + 0.18*usefulness + 0.12*credibility + 0.14*attractiveness - 0.18*hype_penalty`

Then clamp to `[0.05, 0.98]`.

### Suggestion ranking formula

Suggestion rank should combine:

- prefix/fuzzy match strength
- source/topic popularity in the corpus
- item/source quality
- freshness
- recent user query reuse

Suggestion types:

- `recent_query`
- `source`
- `topic`
- `tag`
- `title`
- `idea`

Example suggestions:

- `recent arxiv papers on retrieval`
- `OpenAI and Anthropic lab announcements this year`
- `security reports about supply chain attacks`
- `systems papers with benchmarks`

## Design Plan

### Phase 1: Fix intake quality before ranking

Goal: stop low-signal and stale bulk content from dominating the candidate pool.

Changes to design:

- Add per-source intake caps for RSS, similar to HTML’s `max_results`.
- Add optional per-source `max_age_days` for RSS and arXiv, not just HTML.
- Add source quotas by type:
  - company blogs
  - lab announcements
  - papers
  - news/security
- Treat large historical imports as bootstrap mode, not normal ranking input.
- Mark backfilled items with a bootstrap penalty or separate freshness treatment.

Why this matters:

- better ranking alone cannot fully fix a polluted candidate pool

### Phase 2: Add item-level quality scoring

Goal: give every item a stable quality prior.

Use the existing LLM in `.env` to score each item during enrichment.

Recommended score dimensions:

- `technical_depth`
- `specificity`
- `novelty_or_new_information`
- `actionability_or_research_value`
- `credibility`
- `hype_penalty`

Stored output:

- `Item.score` as the final blended score

Recommended definition of “attractive”:

- worth opening for a technical reader because it is concrete, novel, or useful
- not because it is vague or sensational

Important rule:

- use the LLM only as a scorer on real content text
- do not let “attractive” mean clickbait

### Phase 3: Replace date-only ranking with smart ranking

Goal: rank by value, not just recency.

Recommended ranking formula:

`final_rank = relevance + quality + source_trust + freshness + engagement - redundancy`

Suggested initial weighting:

- relevance: `0.45`
- item quality: `0.25`
- freshness: `0.15`
- source trust: `0.10`
- engagement: `0.05`

Key ranking rules:

- `published_at` should dominate freshness for normal browse/search
- `fetched_at` should only be used carefully for “recently ingested” workflows
- backfilled items should not outrank newly published items just because they
  were crawled today
- repeated similar items from the same source/topic cluster should be diversity-penalized

### Phase 4: Improve source-quality governance

Goal: prevent noisy high-volume feeds from overwhelming the system.

Add or strengthen these source-level metrics:

- median item quality score
- excerpt coverage rate
- stale-content ratio
- duplicate ratio
- click yield
- long-tail open rate

Recommended source actions:

- low-value but high-volume sources go to probation
- low-excerpt HTML sources require deeper extraction before full promotion
- source quotas prevent one blog from occupying too much of the home feed

### Phase 5: Add suggestions that help users think

Goal: suggestions should inspire queries, not just echo history.

Suggestion types:

- `recent`: prior user queries
- `source`: “latest OpenAI announcements”, “recent Datadog engineering posts”
- `topic`: “recent retrieval papers”, “security reports on MCP”
- `title/entity`: strong title or keyword matches
- `idea`: templated NL suggestions from hot topics and active sources

Important product rule:

- keep the UI as one NL box plus suggestions/chips
- do not add manual dropdown filter bars

Design note:

- suggestions should be fast and deterministic on keystroke
- optional LLM-generated “idea hints” should be cached/background, not called on every keypress

### Phase 6: Build a feedback loop only after ranking is meaningful

Today the click dataset is too small to drive ranking.

After Phases 1–4:

- start recording impressions, not just clicks
- compute per-source and per-item CTR with proper denominators
- add dwell/open signals if desired
- periodically recalibrate source trust and ranking weights

## Recommended Tooling For This Repo

Best fit for the current project shape:

1. Existing Qwen path for:
   - ingest-time item quality scoring
   - top-K reranking if needed later
   - NL query parsing
2. PostgreSQL full-text search + `pg_trgm` for:
   - fast suggestions
   - lexical retrieval
   - fuzzy matching on source/title/query history
3. Existing Qdrant + `bge-m3` only as the next stage:
   - hybrid semantic recall
   - not required for the first ranking-quality fix

Not recommended as the first upgrade:

- heavy ColBERT-style infra
- LLM-on-every-keystroke suggestions
- replacing the current product with a fully opaque end-to-end semantic search stack

## Practical Rollout Order

1. intake guardrails
2. item-level quality score
3. smart ranking formula
4. suggestion engine
5. source-governance loop
6. optional hybrid retrieval

## Survey References

Primary references reviewed for the ranking/suggestion direction:

- RankGPT: https://aclanthology.org/2023.emnlp-main.923/
- PRP / pairwise LLM reranking: https://arxiv.org/abs/2306.17563
- Fine-grained LLM relevance scoring: https://aclanthology.org/2024.naacl-short.31/
- Qdrant hybrid search / reranking: https://qdrant.tech/documentation/advanced-tutorials/reranking-hybrid-search/
- Qdrant hybrid queries: https://qdrant.tech/documentation/search/hybrid-queries/
- PostgreSQL text search: https://www.postgresql.org/docs/current/functions-textsearch.html
- PostgreSQL full-text and prefix matching: https://www.postgresql.org/docs/15/datatype-textsearch.html
- PostgreSQL `pg_trgm`: https://www.postgresql.org/docs/17/pgtrgm.html
- BGE-M3: https://arxiv.org/abs/2402.03216
- BGE-M3 model card: https://huggingface.co/BAAI/bge-m3
- ColBERT reference: https://arxiv.org/abs/2004.12832

## Bottom Line

The poor content-quality problem is not mainly “the LLM is missing”.

The deeper causes are:

- no per-item quality score
- ranking by time instead of value
- backfill pollution from large RSS feeds
- source mix dominated by high-volume blogs
- weak text extraction for some sources
- almost no real feedback data yet

The correct fix is to repair the pipeline in that order, not to add more model
calls on top of the current ranking logic.
