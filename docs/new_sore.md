# New Design Spec: Hotpot `/security` Filtering, Scoring, Ranking, and Anti-软文 System

## 1. Product split

Hotpot should keep two independent user experiences:

```text
/
General tech feed.
Keep the existing algorithm mostly unchanged.

/security
Security intelligence feed.
New filter, scoring, ranking, dedup, and anti-软文 logic.
```

The `/security` branch should not be a “security-flavored general feed.” It should be a strict, evidence-based security intelligence feed.

The product promise:

```text
Real CVEs, real attacks, concrete cases, source-backed reports.
No generic marketing / 软文.
```

## 1.1 Score ownership and `/security` page contract

The security score must be separate from the general feed score.

```text
/
Uses the existing generic Item.score.
This score can reward broad technical quality, novelty, attractiveness, and
general usefulness.

/security
Uses a dedicated security score.
This score rewards verified security evidence, exploitation, actionability, and
source-backed facts.
```

Implementation rule:

```text
Do not overwrite or reinterpret Item.score as the security score.
Store or compute a dedicated final_security_score for /security.
```

The separated `/security` page has two primary reads:

```text
Top 10 hot
    group-level view
    accepted security stories only
    sorted mostly by final_security_score
    small tie-break boosts for freshness, corroboration, and clicks

Paged feed
    group-level view
    accepted security stories only
    supports limit/offset
    default sort: final_security_score desc, event_time desc, group_key
```

The page must not use a generic query like:

```text
/items?q=security
```

That would return security-looking content. `/security` must read from the
accepted, security-scored candidate set.

---

# 2. Design goal

The crawler may ingest a very large number of items:

```text
1,000,000 crawled items
```

But `/security` should only surface a small, high-confidence subset.

The dataflow should be:

```text
raw crawled items
    ↓
feature extraction
    ↓
security relevance filter
    ↓
软文 / marketing filter
    ↓
evidence scoring
    ↓
exploitation scoring
    ↓
content quality scoring
    ↓
impact scoring
    ↓
actionability scoring
    ↓
dedup / grouping
    ↓
ranking
    ↓
persisted security score
    ↓
top 10 hot + paged feed with “why ranked”
```

The important principle:

```text
Do not rank first and hope bad items go down.
Filter aggressively first, then rank.
```

---

# 3. Source strategy

The source survey should be lightweight. We do not need dozens of sources at first.

Use 2–3 mature upstreams as validation and enrichment signals.

## 3.1 Core upstreams

### Source 1: CVEProject / cvelistV5

Purpose:

```text
Canonical CVE identity source.
```

Use it to validate:

```text
Does the mentioned CVE actually exist?
What is the official description?
What references are attached?
What vendor/product is affected?
```

Algorithm use:

```text
If article mentions CVE and CVE exists in cvelistV5:
    increase evidence score.
```

---

### Source 2: GitHub Advisory Database

Purpose:

```text
Open-source package vulnerability source.
```

Use it to validate:

```text
GHSA IDs
OSS package vulnerabilities
affected package versions
patched versions
ecosystem: npm, PyPI, Go, Maven, Rust, etc.
```

Algorithm use:

```text
If article matches GitHub Advisory:
    increase evidence score.
    increase actionability if patched version exists.
```

---

### Source 3: CISA KEV + EPSS

Purpose:

```text
Exploitation priority signal.
```

Use CISA KEV for:

```text
Known exploited in the wild.
```

Use EPSS for:

```text
Near-term exploitation probability.
```

Algorithm use:

```text
If CVE is in CISA KEV:
    exploitation score = maximum.

If EPSS percentile is high:
    increase impact / exploit likelihood.
```

---

## 3.2 Optional later source

### ProjectDiscovery nuclei-templates

Use only as a weak enrichment signal:

```text
Detection / exploit-check template exists.
```

Do not treat it as proof of real-world exploitation.

```text
Nuclei template exists ≠ actively exploited.
GitHub PoC exists ≠ actively exploited.
```

---

# 4. Data model for scoring

Each crawled item should be converted into a structured feature object.

The LLM can help extract these fields, but the final scoring should be deterministic.

## 4.1 Article features

```text
ArticleFeatures
    id
    title
    url
    source
    source_type
    published_at
    body_text

Security identity:
    mentioned_cves
    mentioned_ghsas
    mentioned_cwes
    mentioned_products
    mentioned_vendors
    affected_versions

External validation:
    cvelist_match
    github_advisory_match
    cisa_kev_match
    epss_score
    epss_percentile
    vendor_advisory_match
    primary_research_match
    credible_media_match

Attack / incident evidence:
    attack_status
    has_victim
    has_threat_actor
    has_campaign
    has_timeline
    has_ioc
    has_poc

Actionability:
    has_patch
    has_mitigation
    has_detection
    patch_versions
    mitigation_text

Impact:
    cvss_score
    product_popularity
    exposure
    attack_complexity

Soft article / 软文 signals:
    promotional_cta_count
    product_pitch_count
    generic_security_phrase_count
    source_links_count
    sponsored_label
    report_download_gate
    webinar_cta
```

## 4.2 Persisted security score object

The scoring result should be a durable object, not only a transient frontend
sort.

Recommended shape:

```text
SecurityItemScore
    item_id
    accepted
    reject_reason
    score_version

    group_key
    representative_item_id
    section
    event_time

    security_relevance_score
    evidence_score
    exploitation_score
    content_quality_score
    impact_score
    actionability_score
    source_authority_score
    freshness_score
    corroboration_score
    soft_article_score

    final_security_score
    security_hot_score

    badges
    why_ranked
    source_chain
    computed_at
```

Storage options:

```text
Preferred:
    security_item_scores table

Acceptable v1:
    JSONB score payload attached to a security-specific projection table
```

Do not store these fields only in the UI. The backend must own the scores so
pagination, top 10 hot, and future backfills produce the same ordering.

Recompute triggers:

```text
On ingest/enrich:
    score the new item once text, tags, source, and summary are available.

Daily scheduled refresh:
    recompute accepted security scores for recent items and any item with
    upstream changes.

When KEV / EPSS / advisory caches change:
    recompute affected CVE / GHSA groups.

When the formula changes:
    increment score_version and backfill security_item_scores only.
    Do not rerun the general Item.score backfill.
```

Suggested indexes:

```text
accepted, final_security_score desc, event_time desc
accepted, security_hot_score desc
section, accepted, final_security_score desc
group_key
```

## 4.3 Group-level scoring

The `/security` page should display security story groups, not raw duplicate
items.

For each group:

```text
group_final_security_score =
    max(item.final_security_score)
  + min(0.06, 0.015 * additional_authoritative_sources)

group_security_hot_score =
    max(item.security_hot_score)
  + min(0.05, 0.0125 * additional_recent_sources)

Clamp both to 1.0.
```

The representative card should be the item with the highest
`final_security_score`. If scores tie, prefer the most authoritative source,
then the newest important event time.

---

# 5. LLM role

The LLM should not directly decide ranking.

Bad design:

```text
Ask LLM: “Is this article good? Give score 1–10.”
```

Better design:

```text
Ask LLM to extract observable facts.
Then deterministic code calculates the score.
```

## 5.1 LLM extraction task

The LLM should return strict structured output:

```text
Extract only facts explicitly supported by the article.

Return:
- CVE IDs
- GHSA IDs
- affected vendor
- affected product
- affected version
- exploit status
- whether exploitation is confirmed
- whether this is a real case
- victim
- threat actor
- campaign
- patch availability
- mitigation
- IoCs
- PoC
- detection artifacts
- source links
- promotional CTA count
- product pitch count
- generic security phrase count
- confidence
```

Important extraction rule:

```text
Do not infer exploitation unless the article explicitly says it.
Do not treat marketing claims as evidence.
Do not treat a GitHub PoC as confirmed exploitation.
```

---

# 6. Stage 1: Security relevance filter

This filter decides whether the item belongs in `/security` at all.

## 6.1 Security relevance score

Signals that increase security relevance:

```text
CVE mentioned
GHSA mentioned
CVE validated by cvelistV5
GitHub Advisory match
CISA KEV match
victim mentioned
threat actor mentioned
IoC included
timeline included
patch included
mitigation included
affected version included
```

## 6.2 Suggested scoring

```text
security_relevance_score =
    CVE mentioned                         +0.35
    GHSA mentioned                        +0.25
    cvelistV5 match                       +0.30
    GitHub Advisory match                 +0.30
    CISA KEV match                        +0.50
    victim present                        +0.20
    threat actor present                  +0.15
    IoC present                           +0.15
    timeline present                      +0.10
    patch present                         +0.15
    mitigation present                    +0.10
    affected version present              +0.10

Clamp to 1.0.
```

## 6.3 Pass threshold

```text
Pass security relevance if:

security_relevance_score >= 0.40
```

This removes:

```text
general AI / tech articles
generic startup news
general software releases
security-adjacent thought leadership
```

---

# 7. Stage 2: 软文 detection

## 7.1 Definition of 软文

For this product:

```text
软文 = promotional / SEO / thought-leadership content with weak concrete security evidence.
```

It is important not to define it as:

```text
vendor blog = 软文
```

A vendor blog can be valuable if it contains:

```text
CVE
affected versions
exploit details
patch information
IoCs
mitigation
real incident data
original research
```

Correct principle:

```text
Promotional language alone is not enough to reject.
Promotional language + weak evidence = reject.
```

---

## 7.2 Strong 软文 indicators

Strong negative signals:

```text
book a demo
request a demo
contact sales
download the whitepaper
download the report
register for webinar
join our webinar
talk to an expert
our platform
our solution
our customers
free trial
industry-leading
next-generation
AI-powered platform
unified platform
single pane of glass
```

Weak negative signals:

```text
best practices
top trends
ultimate guide
what you need to know
why it matters
security posture
cyber resilience
digital transformation
modern security teams
CISO guide
checklist
```

Weak negative signals should not reject by themselves. They only matter when the article has weak evidence.

---

## 7.3 Soft article score

```text
soft_article_score =
    promotional CTA count                 up to +0.30
    product pitch language                up to +0.25
    generic security phrases              up to +0.24
    no CVE / GHSA                         +0.15
    no patch / mitigation / IoC           +0.15
    no victim / actor / affected version  +0.10
    no external source links              +0.10

Clamp to 1.0.
```

## 7.4 软文 rejection rules

Reject immediately if:

```text
soft_article_score >= 0.75
```

Reject if:

```text
soft_article_score >= 0.55
AND evidence_score < 0.45
```

Reject if:

```text
No CVE
AND no GHSA
AND no victim
AND no threat actor
AND no patch
AND no IoC
AND soft_article_score >= 0.45
```

This should reject examples like:

```text
“Top 10 cybersecurity trends for 2026”
“Why every CISO needs an AI-native security platform”
“Ultimate guide to cyber resilience”
“Download our latest ransomware report”
“5 best practices for cloud security posture”
```

But keep examples like:

```text
“CVE-2026-XXXX exploited in Product X; patch released”
“GHSA-xxxx affects npm package Y”
“Threat actor Z exploited appliance A; IoCs published”
“Vendor advisory confirms active exploitation”
```

---

# 8. Evidence score

Evidence score measures whether the item contains verifiable security facts.

This is one of the most important scores.

## 8.1 Evidence signals

Reward:

```text
CVE validated by cvelistV5
GHSA validated by GitHub Advisory Database
CISA KEV match
vendor advisory
primary research
credible security media
patch
mitigation
affected version
IoC
PoC
victim
threat actor
timeline
external source links
```

## 8.2 Suggested scoring

```text
evidence_score =
    cvelistV5 match                       +0.25
    CVE mentioned but not validated       +0.15

    GitHub Advisory match                 +0.20
    GHSA mentioned but not validated      +0.12

    CISA KEV match                        +0.30

    PoC present                           +0.08

    victim present                        +0.10
    threat actor present                  +0.08
    timeline present                      +0.06

    affected version present              +0.08
    patch present                         +0.08
    mitigation present                    +0.05
    IoC present                           +0.08

    vendor advisory match                 +0.08
    primary research match                +0.08
    credible media match                  +0.04

    3+ source links                       +0.06
    1+ source link                        +0.03

Clamp to 1.0.
```

## 8.3 Interpretation

```text
0.80–1.00    very strong evidence
0.60–0.80    good evidence
0.40–0.60    acceptable evidence
0.20–0.40    weak evidence
0.00–0.20    not useful for /security
```

---

# 9. Exploitation score

Exploitation score should strongly influence ranking.

This answers:

```text
Is this vulnerability or attack actually being used?
```

## 9.1 Exploitation ladder

```text
CISA KEV
    strongest proof of known exploitation

vendor confirms exploitation
    very strong

credible incident report claims exploitation
    strong

public PoC available
    medium

theoretical vulnerability only
    weak

unknown
    zero
```

## 9.2 Suggested scoring

```text
exploitation_score =
    CISA KEV match                         1.00
    confirmed in the wild                  0.90
    vendor-confirmed exploitation          0.85
    credible report claims exploitation    0.70
    public PoC available                   0.45
    theoretical only                       0.20
    unknown                                0.00
```

Important rule:

```text
GitHub PoC ≠ confirmed exploitation.
Nuclei template ≠ confirmed exploitation.
```

They are useful as weak exploitability signals, not proof of real-world attacks.

---

# 10. Content quality score

Content quality measures whether the item is useful to security practitioners.

It is different from evidence.

An article may mention a real CVE but still be low quality if it only rewrites a title and gives no details.

## 10.1 Quality signals

Reward:

```text
specific CVE / GHSA
specific affected product
affected version range
patch version
mitigation
IoC
threat actor
victim
timeline
source links
PoC
technical detail
```

Penalize:

```text
generic security phrases
no source links
no product/version detail
no patch/mitigation
no case detail
```

## 10.2 Suggested scoring

```text
content_quality_score =
    CVE present                            +0.12
    GHSA present                           +0.10
    product present                        +0.08
    affected version present               +0.10

    patch present                          +0.12
    mitigation present                     +0.08
    IoC present                            +0.10

    victim present                         +0.08
    threat actor present                   +0.08
    timeline present                       +0.06

    3+ source links                        +0.10
    1+ source link                         +0.05

    PoC present                            +0.08

    generic phrase penalty                 up to -0.18

Clamp between 0 and 1.
```

---

# 11. Impact score

Impact score measures how important the vulnerability or attack is.

It should not be confused with exploitation.

A high-CVSS bug may be severe but not exploited.
A lower-CVSS bug may be more urgent if it is being exploited in the wild.

## 11.1 Impact signals

Reward:

```text
high CVSS
high EPSS percentile
widely used product
critical enterprise product
internet-facing exposure
low attack complexity
```

## 11.2 Suggested scoring

```text
impact_score =
    CVSS >= 9.0                            +0.25
    CVSS >= 7.0                            +0.15
    CVSS >= 5.0                            +0.08

    EPSS percentile >= 0.95                +0.30
    EPSS percentile >= 0.80                +0.20
    EPSS percentile >= 0.50                +0.10

    critical enterprise/common product     +0.20
    widely used product                    +0.12

    internet-facing exposure               +0.15

    low attack complexity                  +0.10
    medium attack complexity               +0.05

Clamp to 1.0.
```

---

# 11.5 Actionability score

Actionability answers:

```text
Can a reader do something concrete after opening this item?
```

This score is important for `/security` because a lower-hype advisory with
patch versions, mitigations, or detections is more useful than a high-level
article that only says a threat exists.

## 11.5.1 Actionability signals

Reward:

```text
patch available
patched version listed
mitigation steps
detection logic
YARA / Sigma / Snort / Suricata rule
IoCs
affected versions
workaround
upgrade path
configuration guidance
```

## 11.5.2 Suggested scoring

```text
actionability_score =
    patch available                         +0.22
    patched version listed                  +0.18
    mitigation steps                        +0.16
    detection logic                         +0.14
    IoCs                                    +0.12
    affected versions                       +0.10
    workaround                              +0.08
    configuration guidance                  +0.06

Clamp to 1.0.
```

Do not reward generic advice like:

```text
stay vigilant
improve your security posture
follow best practices
contact your vendor
```

unless the article also provides concrete affected products, versions, patches,
detections, or mitigations.

---

# 12. Source authority score

Keep source authority simple and explainable.

## 12.1 Suggested source tiers

```text
CISA KEV                         1.00
CVEProject cvelistV5             0.95
vendor advisory                  0.90
GitHub Advisory Database         0.85
OSV                               0.80
primary research                  0.80
credible security media           0.65
aggregator                        0.40
social / forum                    0.25
vendor marketing blog             0.20
general tech blog                 0.15
```

## 12.2 Vendor nuance

Do not automatically punish all vendor content.

```text
Vendor content + strong evidence = useful.
Vendor content + marketing + weak evidence = 软文.
```

Suggested rule:

```text
If source is vendor blog and evidence_score >= 0.70:
    source_authority_score = 0.75

If source is vendor blog and soft_article_score >= 0.55:
    source_authority_score = 0.20
```

---

# 13. Freshness score

Freshness should matter, but not dominate.

A fresh marketing article should not outrank a slightly older CISA KEV item.

## 13.1 Suggested decay

```text
age <= 24h       freshness = 1.00
age <= 72h       freshness = 0.80
age <= 7d        freshness = 0.55
age <= 30d       freshness = 0.25
older            freshness = 0.05
```

## 13.2 Important event freshness

For vulnerabilities, freshness should be based on the newest important event, not just article publication time.

Important event time:

```text
max(
    article_published_at,
    cisa_kev_added_at,
    epss_jump_at,
    patch_released_at,
    exploit_confirmed_at,
    advisory_updated_at
)
```

Persist this value as `event_time` on the security score projection and use it
for pager tie-breaks.

Reason:

```text
A CVE from two years ago can become important today if it enters CISA KEV today.
```

---

# 14. Corroboration score

Corroboration rewards multi-source confirmation.

## 14.1 Corroboration sources

```text
cvelistV5
GitHub Advisory Database
CISA KEV
vendor advisory
primary research
credible media
```

## 14.2 Suggested scoring

```text
4+ independent source types       1.00
3 independent source types        0.80
2 independent source types        0.60
1 independent source type         0.30
0                                0.00
```

Example:

```text
Random blog only:
    low corroboration

CVEProject + GitHub Advisory:
    medium-high

CVEProject + vendor advisory + CISA KEV + media report:
    very high
```

---

# 15. Final ranking formula

After filtering, rank accepted items using:

```text
final_security_score =
    0.30 * evidence_score
  + 0.24 * exploitation_score
  + 0.14 * content_quality_score
  + 0.10 * impact_score
  + 0.08 * actionability_score
  + 0.06 * source_authority_score
  + 0.05 * corroboration_score
  + 0.03 * freshness_score
  - 0.22 * soft_article_score

Clamp between 0 and 1.
```

## 15.1 Ranking priority

This formula means:

```text
Most important:
    evidence
    exploitation

Second:
    content quality
    impact
    actionability

Third:
    source authority
    corroboration
    freshness

Negative:
    软文 / promotional score
```

This directly matches the desired behavior:

```text
CVE, attack, concrete case, accurate report > generic security article.
Freshness and clicks cannot rescue weak evidence.
```

## 15.2 Top 10 hot formula

The `/security` top 10 hot strip should be mostly score-driven. Hotness should
not turn the page into a click leaderboard.

```text
security_hot_score =
    0.80 * final_security_score
  + 0.08 * freshness_score
  + 0.07 * corroboration_score
  + 0.03 * normalized_click_score
  + 0.02 * normalized_repeat_exposure_score

Clamp between 0 and 1.
```

Tie-break order:

```text
security_hot_score desc
final_security_score desc
exploitation_score desc
evidence_score desc
event_time desc
group_key asc
```

Top 10 eligibility:

```text
accepted = true
AND final_security_score >= 0.55
AND evidence_score >= 0.45
```

Exception:

```text
If CISA KEV match or confirmed exploitation:
    eligible for top 10 when accepted = true.
```

---

# 16. Acceptance rules

An item should be accepted into `/security` only if:

```text
security_relevance_score >= 0.40
AND evidence_score >= 0.35
AND not rejected as 软文
```

Special exception:

```text
If CISA KEV match:
    accept even if other evidence fields are sparse.
```

Because CISA KEV is already a strong exploitation signal.

## 16.1 Final accept condition

```text
accept_item =
    security_relevance_score >= 0.40
    AND (
        evidence_score >= 0.35
        OR cisa_kev_match = true
        OR attack_status in (
            confirmed_in_the_wild,
            vendor_confirmed_exploitation
        )
    )
    AND soft_article_reject = false
    AND final_security_score >= 0.30
```

The stricter threshold is intentional. The general feed can be broad; the
security page should have high precision.

---

# 17. Rejection rules

Reject if:

```text
security_relevance_score < 0.40
```

Reject if:

```text
soft_article_score >= 0.75
```

Reject if:

```text
soft_article_score >= 0.55
AND evidence_score < 0.45
```

Reject if:

```text
evidence_score < 0.35
AND cisa_kev_match = false
AND attack_status not in (
    confirmed_in_the_wild,
    vendor_confirmed_exploitation
)
```

Reject if:

```text
final_security_score < 0.30
```

Reject if:

```text
No CVE
No GHSA
No victim
No threat actor
No patch
No IoC
AND soft_article_score >= 0.45
```

---

# 18. Deduplication and grouping

The ranking should not show 10 versions of the same CVE story.

Group items by canonical security entity.

## 18.1 Canonical key priority

```text
1. CVE ID
2. GHSA ID
3. OSV ID
4. vendor advisory ID
5. normalized incident key
6. normalized title/product/date fallback
```

## 18.2 Group behavior

For each group:

```text
Choose best representative card.
Attach supporting sources.
Use max score or weighted group score.
Show source chain.
```

Example group:

```text
CVE-2026-XXXX
    CISA KEV entry
    vendor advisory
    BleepingComputer report
    researcher writeup
    GitHub advisory
```

Display as one card:

```text
CVE-2026-XXXX exploited in Product X

Sources:
CISA KEV · Vendor advisory · Researcher writeup · Security media

Why ranked:
Known exploited · patch available · affected versions · high EPSS
```

---

# 19. Section-specific ranking

The `/security` page should not be backed by a generic item list. It should use
the accepted, grouped, security-scored projection.

Page layout:

```text
1. Top 10 Hot Security Stories
2. Paged Security Feed
3. Optional section filters
```

## 19.0 Top 10 hot + pager behavior

Top 10 hot:

```text
GET /api/security/hot?limit=10

Input:
    accepted security story groups

Sort:
    security_hot_score desc
    final_security_score desc
    exploitation_score desc
    evidence_score desc
    event_time desc

Output:
    exactly up to 10 groups
    one representative card per group
    badges and why_ranked included
```

Paged feed:

```text
GET /api/security/items?limit=25&offset=0&section=all&sort=score_desc

Input:
    accepted security story groups

Default sort:
    final_security_score desc
    event_time desc
    group_key asc

Output:
    items
    total
    limit
    offset
```

Pager rule:

```text
Pagination must happen after filtering and grouping.
Do not paginate raw items before dedup.
```

The top 10 hot strip may overlap with the first page unless the frontend asks
for `exclude_hot=true`. Keeping overlap is acceptable for v1 because the top
strip is a separate summary view, not a separate feed.

Recommended optional sections:

```text
1. Exploited Now
2. New Important CVEs
3. Real Attack Cases
4. Technical Analysis
5. Vendor Advisories
6. OSS Package Vulnerabilities
```

The sections are filters on the accepted security projection. They are not
separate scoring systems.

## 19.1 Exploited Now

Show if:

```text
CISA KEV match
OR attack_status in:
    confirmed_in_the_wild
    vendor_confirmed_exploitation
```

Ranking emphasis:

```text
exploitation > evidence > freshness > impact
```

---

## 19.2 New Important CVEs

Show if:

```text
CVE present
AND evidence_score >= 0.45
AND (
    CVSS >= 8.0
    OR EPSS percentile >= 0.80
    OR GitHub Advisory match
)
```

Ranking emphasis:

```text
impact > evidence > source authority > freshness
```

---

## 19.3 Real Attack Cases

Show if:

```text
has_victim
OR has_threat_actor
OR has_ioc
OR has_timeline
```

And:

```text
evidence_score >= 0.50
```

Ranking emphasis:

```text
case detail > evidence > source authority > freshness
```

---

## 19.4 Technical Analysis

Show if:

```text
has_poc
OR has_ioc
OR has_affected_version
OR has_mitigation
```

And:

```text
content_quality_score >= 0.55
```

Ranking emphasis:

```text
technical depth > evidence > actionability
```

---

## 19.5 Vendor Advisories

Show if:

```text
vendor_advisory_match
AND (
    has_patch
    OR has_mitigation
    OR has_affected_version
)
```

Ranking emphasis:

```text
patch/actionability > impact > freshness
```

---

## 19.6 OSS Package Vulnerabilities

Show if:

```text
GitHub Advisory match
OR GHSA present
```

Ranking emphasis:

```text
package ecosystem relevance > patched version > severity > freshness
```

---

# 20. UI card design

Every `/security` card should explain why it appears.

## 20.1 Card fields

```text
Title
Primary label:
    CVE / GHSA / Incident / Advisory / Exploit Analysis

Scores:
    final_security_score
    evidence_score
    exploitation_score
    actionability_score
    soft_article_score

Badges:
    KEV
    Exploited
    Patch Available
    Mitigation
    IoCs
    PoC
    High EPSS
    Critical CVSS
    Affected Versions

Evidence:
    CVE:
    GHSA:
    Product:
    Affected versions:
    Exploit status:
    Patch:
    Sources:

Why ranked:
    short bullet explanation
```

For the first `/security` implementation, the UI does not need to show every
numeric sub-score. It should expose enough of the score explanation to make the
ranking auditable:

```text
Security score: 0.82
Why ranked: KEV · valid CVE · patch available · high EPSS · low 软文
```

## 20.2 Example card

```text
CVE-2026-XXXX exploited in Product X

Badges:
KEV · Exploited · Patch Available · High EPSS

Evidence:
CVE: CVE-2026-XXXX
Product: Product X
Exploit status: confirmed in the wild
Patch: available
Sources: CISA KEV · Vendor advisory · Security media

Why ranked:
- Known exploited vulnerability
- Valid CVE record
- Vendor patch available
- High EPSS percentile
- Low 软文 score
```

This makes ranking transparent.

---

# 21. Full dataflow spec

## Step 1: Crawl

Input:

```text
RSS feeds
GitHub advisories
CVE feeds
CISA KEV
security blogs
vendor advisories
security media
```

Output:

```text
raw_items
```

---

## Step 2: Normalize

Normalize:

```text
title
url
domain
source
published_at
body_text
language
canonical_url
```

Output:

```text
normalized_items
```

---

## Step 3: Extract features

Use rules + LLM.

Extract:

```text
CVE IDs
GHSA IDs
products
vendors
affected versions
patch
mitigation
IoCs
PoC
threat actor
victim
timeline
source links
marketing phrases
CTA phrases
generic phrases
```

Output:

```text
ArticleFeatures
```

---

## Step 4: Enrich with upstream sources

Lookup:

```text
cvelistV5
GitHub Advisory Database
CISA KEV
EPSS
optional vendor advisory index
```

Add:

```text
cvelist_match
github_advisory_match
cisa_kev_match
epss_score
epss_percentile
cvss_score
```

Output:

```text
enriched_features
```

---

## Step 5: Score

Calculate:

```text
security_relevance_score
soft_article_score
evidence_score
exploitation_score
content_quality_score
impact_score
actionability_score
source_authority_score
freshness_score
corroboration_score
final_security_score
security_hot_score
```

Output:

```text
scored_items
```

---

## Step 6: Filter

Apply:

```text
security relevance threshold
evidence threshold
soft article rejection
```

Output:

```text
accepted_security_items
```

---

## Step 7: Dedup / group

Group by:

```text
CVE
GHSA
OSV
vendor advisory
incident key
```

Output:

```text
security_story_groups
```

---

## Step 8: Persist security projection

Persist:

```text
accepted_security_items
security_story_groups
final_security_score
security_hot_score
why_ranked
badges
source_chain
```

Output:

```text
security_item_scores
```

---

## Step 9: Rank

Rank group representatives by:

```text
final_security_score
security_hot_score for the top 10 hot view
```

Output:

```text
ranked_security_feed
security_hot_top10
```

---

## Step 10: Explain

For each displayed item, generate:

```text
why_ranked
why_not_soft_article
source_chain
evidence_badges
```

Output:

```text
security UI cards
```

---

# 22. Million-item demo narrative

This is how to explain the algorithm to stakeholders.

## Input

```text
Crawler collected 1,000,000 items.
```

They include:

```text
general tech news
AI articles
startup announcements
security vendor marketing
generic best-practice articles
real CVEs
vendor advisories
CISA KEV items
attack reports
technical exploit writeups
OSS advisories
```

---

## Filtering result example

```text
1,000,000 raw items

Removed by low security relevance:
    ~820,000

Removed as 软文 / marketing:
    ~100,000

Removed by weak evidence:
    ~30,000

Accepted into /security candidate pool:
    ~50,000

After dedup / grouping:
    ~20,000 security stories

Displayed on /security:
    top 10 hot
    paged feed over the remaining accepted story groups
```

The exact numbers will vary, but the story is:

```text
Most crawled data should never reach /security.
```

---

## Why a top item appears

Top item example:

```text
CVE-2026-XXXX exploited in Product X
```

Selected because:

```text
CISA KEV match
valid CVE
vendor advisory exists
patch available
affected versions listed
high EPSS percentile
credible media report confirms exploitation
low soft_article_score
```

High scores:

```text
exploitation_score:     1.00
evidence_score:         0.95
content_quality_score:  0.85
impact_score:           0.90
soft_article_score:     0.05
```

---

## Why a soft article is rejected

Rejected item example:

```text
“Ultimate Guide to AI-Powered Cloud Security”
```

Rejected because:

```text
no CVE
no GHSA
no vendor advisory
no affected version
no patch
no IoC
many product-pitch phrases
CTA: request demo / download report
generic best-practices wording
```

Scores:

```text
security_relevance_score: 0.10
evidence_score:           0.05
soft_article_score:       0.85
```

Decision:

```text
Reject as 软文.
```

---

# 23. Evaluation metrics

To tune the algorithm, manually label a small dataset.

## 23.1 Label set

Label 300–500 items:

```text
must_include
good_include
optional
low_value
soft_article
reject
```

Also label reasons:

```text
has CVE
has KEV
has confirmed exploitation
has specific case
has patch
has IoC
has technical analysis
is marketing
is generic
is SEO rewrite
```

---

## 23.2 Product metrics

Track:

```text
Precision@10
Precision@25
Precision@50
soft_article_rate_top25
CVE_coverage_top25
KEV_coverage_top25
confirmed_exploit_coverage_top25
primary_source_rate_top25
duplicate_rate_top25
```

Suggested targets:

```text
soft_article_rate_top25 < 5%

CVE_or_confirmed_attack_rate_top25 > 70%

duplicate_rate_top25 < 10%

primary_or_authoritative_source_rate_top25 > 60%
```

---

# 24. Final design summary

The `/security` branch should be built around this principle:

```text
Rank verified security evidence, not security-looking content.
```

The full algorithm is:

```text
1. Extract structured features.
2. Validate against 2–3 mature upstreams.
3. Compute:
   - security relevance
   - evidence
   - exploitation
   - content quality
   - impact
   - actionability
   - source authority
   - freshness
   - corroboration
   - soft article score
4. Reject low-relevance and high-软文 items.
5. Deduplicate by CVE / GHSA / incident.
6. Rank by evidence + exploitation + quality.
7. Show why each item was selected.
```

The core acceptance rule:

```text
accept =
    security_relevance_score >= 0.40
    AND (
        evidence_score >= 0.35
        OR cisa_kev_match = true
        OR confirmed exploitation = true
    )
    AND not soft_article_reject
    AND final_security_score >= 0.30
```

The core ranking formula:

```text
final_security_score =
    0.30 * evidence_score
  + 0.24 * exploitation_score
  + 0.14 * content_quality_score
  + 0.10 * impact_score
  + 0.08 * actionability_score
  + 0.06 * source_authority_score
  + 0.05 * corroboration_score
  + 0.03 * freshness_score
  - 0.22 * soft_article_score

Clamp between 0 and 1.
```

The `/security` page contract:

```text
Top 10 hot:
    sort accepted story groups by security_hot_score desc.

Paged feed:
    paginate accepted story groups after filtering and dedup.

Both views:
    use security scores, not the generic Item.score.
```

The core 软文 rule:

```text
软文 =
    promotional intent
    + generic language
    + weak concrete security evidence
```

The product result:

```text
/security becomes a strict security intelligence page:
CVE, attacks, concrete cases, advisories, exploitation, patches, IoCs.

General marketing, soft vendor content, SEO summaries, and vague security advice are filtered out.
```
