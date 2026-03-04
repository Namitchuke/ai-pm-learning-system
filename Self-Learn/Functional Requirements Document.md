# FRD: AI PM Autonomous Learning & Intelligence System

**Version**: 2.0
**Date**: 2026-02-16
**Status**: Draft
**Based on**: PRD v2.0 — AI PM Autonomous Learning & Intelligence System (2026-02-15)
**Supersedes**: FRD v1.0 (2026-02-15)

---

## Changes from FRD v1.0

FRD v2.0 incorporates all 20 loophole fixes from PRD v2.0, expands the RSS source system from 3 tiers (18 feeds) to 6 tiers (42 validated feeds), and updates all schemas and flows accordingly.

### Key Updates

| Area | v1.0 | v2.0 |
|------|------|------|
| RSS Sources | 18 feeds, 3 tiers | 42 validated feeds, 6 tiers |
| Pipeline Tracking | Single daily status | Per-slot (morning/midday/evening) independent tracking |
| Cron Jobs | 7 jobs (exceeds free tier) | Exactly 4 jobs (1 slot reserved) |
| Write Safety | asyncio.Lock only | ETag-based optimistic locking + asyncio.Lock |
| Grading Cache | Implicit state transitions | Display-only (no state transitions on cache hit) |
| Title Dedup | Single-phase (80% threshold) | Two-phase (85% definite, 60-85% ambiguous with Gemini confirm) |
| API Auth | Single method per endpoint | Dual-auth (API key OR Basic Auth+CSRF) |
| Adaptive Difficulty | Separate logic per feature | Unified canonical state machine |
| Evening Articles | No handling | next_day_priority_queue carry-over |
| RPD Tracking | None | Per-model tracking with automatic fallback |
| Model Config | Hardcoded | Env var based for deprecation resilience |
| Summary Cache Key | URL only | URL + extraction_method |
| Blocklist | Glob patterns | Split: BLOCKED_DOMAINS + BLOCKED_URL_PATTERNS (regex) |
| Streak Definition | Undefined | Formally defined: consecutive email_sent days |
| Reteaching | No timeout | 14-day auto-revert |
| Zero-grading Days | Undefined | Neutral (no counter impact) + 7-day pause rule |

---

## User Personas

### Persona 1: The System Owner (Primary & Only User)

| Attribute | Detail |
|-----------|--------|
| **Name** | Namit (AI Product Manager) |
| **Role** | AI PM at a technology/ed-tech company |
| **Goal** | Systematically build deep AI PM expertise across 5 domains without spending more than 15-20 minutes per day |
| **Behavior** | Reads email digest over lunch, submits grading answers in the evening, checks dashboard weekly for progress overview |
| **Pain Points** | Information overload from 42 RSS sources; passive reading leads to shallow retention; no accountability loop; existing tools (newsletters, courses) are too broad, too expensive, or lack comprehension testing |
| **Technical Comfort** | Can deploy to Render, configure cron-job.org, set up Google Cloud OAuth — but after initial setup, expects zero manual intervention |
| **Interaction Pattern** | 90% passive consumer (email), 10% active participant (dashboard grading forms) |
| **Devices** | Email: mobile (Gmail app) + desktop (Gmail web). Dashboard: desktop browser only |

### Persona 2: The External Cron Service (System Actor)

| Attribute | Detail |
|-----------|--------|
| **Identity** | cron-job.org scheduled HTTP requests |
| **Role** | The autonomous trigger that drives all daily operations |
| **Behavior** | Sends authenticated GET requests to exactly 4 trigger endpoints at scheduled IST times |
| **Requirement** | Must include `X-Cron-Secret` header. Tolerates 30-60 second cold start response times. Retries once on failure after 5 minutes |

---

## Feature Specifications

### FS-01: RSS Content Pipeline

**Purpose**: Autonomously discover, fetch, and pre-process AI PM articles from curated RSS sources 3x daily with per-slot tracking.

#### FS-01.1: RSS Source Management

| Field | Specification |
|-------|---------------|
| **Source file** | `rss_sources.json` in Google Drive `AI_PM_SYSTEM/` folder |
| **Format** | JSON array of source objects organized into 6 tiers |
| **Configurability** | User edits file directly on Google Drive; no UI for management |
| **Feed health tracking** | Consecutive failure counter per feed; auto-disable after 5 failures |

**Source object schema**:
```json
{
  "source_id": "uuid-v4",
  "name": "OpenAI Blog",
  "feed_url": "https://openai.com/news/rss.xml",
  "tier": 2,
  "category_bias": "ml_engineering",
  "enabled": true,
  "consecutive_failures": 0,
  "last_success": "ISO-8601",
  "added_at": "ISO-8601"
}
```

**Default sources (42 feeds across 6 tiers)**:

**Tier 1 — Academic & Research (7 feeds)**:

| Source | Feed URL | Category Bias | Notes |
|--------|----------|---------------|-------|
| arXiv cs.AI | `https://rss.arxiv.org/rss/cs.AI` | ml_engineering | High volume; pre-filter by title keywords |
| arXiv cs.LG | `https://rss.arxiv.org/rss/cs.LG` | ml_engineering | Machine learning papers |
| MIT News AI | `https://news.mit.edu/rss/topic/artificial-intelligence2` | ml_engineering | Institutional; public |
| BAIR Blog (Berkeley) | `https://bair.berkeley.edu/blog/feed.xml` | ml_engineering | Excellent depth; ~biweekly |
| CMU ML Blog | `https://blog.ml.cmu.edu/feed` | ml_engineering | Faculty/student authored |
| Stanford HAI | `https://hai.stanford.edu/news/all/rss` | ai_ethics | AI policy + research |
| The Gradient | `https://thegradient.pub/rss/` | ml_engineering | Curated AI research publication |

**Tier 2 — AI Research Labs (7 feeds)**:

| Source | Feed URL | Category Bias | Notes |
|--------|----------|---------------|-------|
| OpenAI Blog | `https://openai.com/news/rss.xml` | ml_engineering | Official feed |
| DeepMind Blog | `https://deepmind.google/blog/rss.xml` | ml_engineering | Public, active |
| Google Research | `https://research.google/blog/rss` | ml_engineering | Broad AI/ML research |
| Microsoft Research | `https://www.microsoft.com/en-us/research/blog/feed/` | ml_engineering | Broad research including AI |
| Meta Engineering | `https://engineering.fb.com/feed` | infrastructure | Covers AI + engineering |
| HuggingFace Blog | `https://huggingface.co/blog/feed.xml` | mlops | Open-source ML tooling |
| Anthropic (community) | `https://raw.githubusercontent.com/conoro/anthropic-engineering-rss-feed/main/anthropic_engineering_rss.xml` | ai_ethics | Community-maintained |

**Tier 3 — Engineering Blogs (10 feeds)**:

| Source | Feed URL | Category Bias | Notes |
|--------|----------|---------------|-------|
| Uber Engineering | `https://www.uber.com/blog/engineering/rss/` | infrastructure | Strong ML platform content |
| Netflix Tech Blog | `https://netflixtechblog.com/feed` | infrastructure | ML experimentation |
| Stripe Engineering | `https://stripe.com/blog/feed.rss` | infrastructure | ML for fraud/payments |
| Airbnb Tech Blog | `https://medium.com/feed/airbnb-engineering` | product_strategy | Data science + experimentation |
| DoorDash Engineering | `https://doordash.engineering/blog/rss` | infrastructure | ML search/logistics |
| Slack Engineering | `https://slack.engineering/feed` | infrastructure | Product engineering |
| Dropbox Tech | `https://dropbox.tech/feed` | infrastructure | Systems engineering |
| Pinterest Engineering | `https://medium.com/feed/pinterest-engineering` | ml_engineering | Recommendation systems |
| Spotify Engineering | `https://engineering.atspotify.com/feed/` | mlops | ML personalization |
| LinkedIn Engineering | `https://engineering.linkedin.com/blog.rss.html` | ml_engineering | Ranking/recommendations |

**Tier 4 — Product & Strategy (7 feeds)**:

| Source | Feed URL | Category Bias | Notes |
|--------|----------|---------------|-------|
| a16z Blog | `https://a16z.com/feed/` | product_strategy | VC tech/AI strategy |
| First Round Review | `https://review.firstround.com/feed.xml` | product_strategy | Tactical startup/PM content |
| Stratechery | `https://stratechery.com/feed` | product_strategy | Free weekly articles only |
| Lenny's Newsletter | `https://www.lennysnewsletter.com/feed` | product_strategy | Free tier only |
| SVPG | `https://www.svpg.com/feed/` | product_strategy | Marty Cagan; lower frequency |
| Mind the Product | `https://www.mindtheproduct.com/feed/` | product_strategy | Broad PM content |
| Intercom Blog | `https://www.intercom.com/blog/feed/` | product_strategy | AI-in-product perspectives |

**Tier 5 — Data & MLOps (7 feeds)**:

| Source | Feed URL | Category Bias | Notes |
|--------|----------|---------------|-------|
| Towards Data Science | `https://towardsdatascience.com/feed` | ml_engineering | High volume; filter paywalled |
| Databricks Blog | `https://databricks.com/feed` | mlops | Strong MLOps/LLM content |
| Chip Huyen's Blog | `https://huyenchip.com/feed.xml` | mlops | ML systems; excellent quality |
| Eugene Yan's Blog | `https://eugeneyan.com/rss/` | product_strategy | ML + product intersection |
| Lilian Weng's Blog | `https://lilianweng.github.io/index.xml` | ml_engineering | Outstanding ML tutorials |
| Weights & Biases | `https://wandb.ai/fully-connected/rss.xml` | mlops | MLOps tools and practices |
| Sebastian Raschka | `https://magazine.sebastianraschka.com/feed` | ml_engineering | LLM research distillation |

**Tier 6 — AI Education & Commentary (4 feeds)**:

| Source | Feed URL | Category Bias | Notes |
|--------|----------|---------------|-------|
| deeplearning.ai (The Batch) | `https://www.deeplearning.ai/the-batch/feed/` | ml_engineering | Andrew Ng |
| fast.ai Blog | `https://www.fast.ai/atom.xml` | ml_engineering | Atom feed; high quality |
| Simon Willison's Blog | `https://simonwillison.net/atom/everything/` | ml_engineering | Prolific LLM/AI tools coverage |
| KDnuggets | `https://www.kdnuggets.com/feed` | ml_engineering | Data science news aggregator |

#### FS-01.2: arXiv Volume Management

**Problem**: arXiv feeds produce ~100+ entries/day — too much to process without overwhelming API costs.

**Solution**:

| Step | Specification |
|------|---------------|
| **Pre-filter** | Before content extraction, filter arXiv entries by title keywords |
| **Keyword list** | `["product", "deployment", "production", "recommendation", "ranking", "serving", "inference", "optimization", "fine-tuning", "RLHF", "alignment", "evaluation", "benchmark"]` |
| **Volume cap** | Max 10 arXiv articles per fetch cycle (across both cs.AI and cs.LG) |
| **Scoring bonus** | +1 tier bonus to arXiv articles during relevance scoring (compensates for academic writing style) |

#### FS-01.3: RSS Fetching with Per-Slot Tracking (L2-01 Fix)

| Field | Specification |
|-------|---------------|
| **Trigger** | `GET /api/trigger/rss-fetch` with `X-Cron-Secret` header |
| **Schedule** | 7:55 AM (morning), 11:55 AM (midday), 4:55 PM (evening) IST |
| **Library** | `feedparser` (Python) |
| **Timeout** | 30 seconds per feed |
| **Slot detection** | Based on current IST time: 6-10 AM → morning, 10 AM-2 PM → midday, 2-7 PM → evening |

**Per-slot tracking (L2-01 fix)**:
- Each slot (morning/midday/evening) has independent status lifecycle
- Morning `DONE` does NOT block midday or evening runs
- Each slot tracks its own: `run_id`, `status`, `articles_fetched`, `articles_scored`, etc.
- Status enum: `PENDING | FETCHING | SCORING | SUMMARIZING | SELECTING | DONE | FAILED`

**Processing flow per feed**:
1. Parse RSS XML via `feedparser`
2. For each entry, extract: `title`, `link`, `published_date`, `description`
3. Check `link` against `cache.json → processed_urls` (SHA-256 hash of URL)
4. If hash exists and `added_at` is within 30 days → **SKIP** (duplicate)
5. If hash exists but `added_at` is > 30 days → re-process (content may have updated)
6. If hash does not exist → add to candidate list

**Feed health monitoring**:
- Track `consecutive_failures` per feed in `rss_sources.json`
- After 5 consecutive failures (403, timeout, parse error) → auto-set `enabled: false`
- Log warning and send alert email
- User must manually re-enable after investigating

**Output**: List of candidate article objects:
```json
{
  "url": "string",
  "url_hash": "sha256",
  "title": "string",
  "source_name": "string",
  "source_tier": 1,
  "category_bias": "ml_engineering",
  "published_date": "ISO-8601",
  "rss_description": "string (truncated to 500 chars)"
}
```

#### FS-01.4: Article Content Extraction

**Layered extraction strategy** (execute in order, stop at first success):

| Priority | Library | Strengths | Failure Indicator |
|----------|---------|-----------|-------------------|
| 1 | Trafilatura | Best general-purpose; handles blogs well | Returns empty or < 200 words |
| 2 | readability-lxml | Good for news sites | Returns empty or < 200 words |
| 3 | Newspaper3k | Wide compatibility | Returns empty or < 200 words |
| 4 | RSS `<description>` | Guaranteed available | Always available (may be truncated) |

**HTTP request configuration**:
```
User-Agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
Timeout: 15 seconds
Max redirects: 3
```

**Per-domain rate limiting**:
- Track request timestamps per domain in memory (dict of `domain → [timestamp_list]`)
- Max 3 requests per minute per domain
- If limit exceeded, sleep until window resets

**HTTP error handling**:

| Status Code | Action |
|------------|--------|
| 200 | Process normally |
| 301/302 | Follow redirect (max 3 hops) |
| 403 | Skip + log "access denied" to `errors.json`, increment `consecutive_failures` |
| 429 | Exponential backoff: wait 2s, retry. Max 3 retries. Then skip + log |
| 5xx | Retry once after 3s. Then skip + log |
| Timeout | Skip + log |

**Content validation rules**:

| Rule | Action |
|------|--------|
| Word count < 200 | Reject — likely failed extraction. Try next layer |
| Word count > 5,000 | Truncate to first 3,000 words |
| Contains paywall markers (`subscribe to read`, `members only`, `premium content`) | Reject + log to `discarded.json` with reason "paywall_detected" |
| Non-text content (PDF, video, podcast link) | Reject + log with reason "non_text_content" |
| Non-UTF-8 encoding | Attempt decode with `chardet`. If fails, skip |

**Blocklist (L2-18 Fix)**:

Two separate blocklist mechanisms:

```python
# Exact domain matches (checked via domain extraction)
BLOCKED_DOMAINS = [
    "paywall-site.com",
    "premium-only.com",
]

# Regex patterns for URL path matching (checked via re.search)
BLOCKED_URL_PATTERNS = [
    r"medium\.com/.*/membership",
    r"towardsdatascience\.com/.*/membership",
    r"/premium/",
    r"/subscribe-to-unlock/",
]
```

Both lists stored in `config.py` and optionally overridable via `rss_sources.json` `blocked_domains` and `blocked_patterns` fields.

**Output per article**:
```json
{
  "url": "string",
  "url_hash": "sha256",
  "title": "string",
  "source_name": "string",
  "source_tier": 1,
  "category_bias": "ml_engineering",
  "published_date": "ISO-8601",
  "extracted_text": "string (max 3,000 words)",
  "word_count": 1234,
  "extraction_method": "trafilatura | readability | newspaper3k | rss_description",
  "fetched_at": "ISO-8601"
}
```

---

### FS-02: AI Relevance & Credibility Scoring

**Purpose**: Score each candidate article on AI PM relevance and source credibility using a single combined Gemini call (L2-12 fix), filtering out low-quality and promotional content.

#### FS-02.1: Combined Scoring Call (L2-12 Fix)

| Field | Specification |
|-------|---------------|
| **Model** | `GEMINI_BULK_MODEL` env var (default: `gemini-2.0-flash-lite`) |
| **Temperature** | 0 |
| **max_output_tokens** | 200 |
| **Max input** | Article text truncated to 1,500 tokens |

**Single combined prompt** (`prompts/scoring.txt`):
```
You are an AI PM content evaluator. Score this article on relevance and credibility in a SINGLE evaluation.

## Calibration Examples
[INSERT 2-3 examples from prompts/scoring_examples.json]

## Article to Score
Title: {title}
Source: {source_name} (Tier {source_tier})
Text: {extracted_text_truncated}

## Relevance Scoring Dimensions (1-10 each)
1. Real-world deployment applicability: Does this describe actual deployed AI systems?
2. Productization potential: Could an AI PM directly use these insights in product decisions?
3. Technical depth: Does it go beyond surface-level explanations?
4. Real-time system capability: Does it relate to production-grade, responsive systems?
5. Business impact: Does it connect to measurable business outcomes?

## Credibility Assessment (1-10)
- Are claims cited, data-backed, technically specific?
- Is there author credibility or institutional backing?
- Are research references included?

## Also Assess
- Is this promotional/sales content? (yes/no)

## Output Format (JSON only)
{"scores": {"deployment": N, "productization": N, "technical_depth": N, "responsiveness": N, "business_impact": N}, "avg_score": N.N, "credibility": N, "is_promotional": false, "rejection_reason": null}
```

**Scoring examples file** (`prompts/scoring_examples.json`):
```json
[
  {
    "title": "How We Scaled Our ML Pipeline to 10M Predictions/Day",
    "source": "Uber Engineering",
    "expected_scores": {"deployment": 9, "productization": 8, "technical_depth": 8, "responsiveness": 9, "business_impact": 8},
    "expected_avg": 8.4,
    "expected_credibility": 9
  },
  {
    "title": "Top 10 AI Tools Every PM Should Know",
    "source": "Random Blog",
    "expected_scores": {"deployment": 2, "productization": 3, "technical_depth": 1, "responsiveness": 1, "business_impact": 2},
    "expected_avg": 1.8,
    "expected_credibility": 2,
    "expected_promotional": true
  },
  {
    "title": "Attention Is All You Need - Transformer Architecture Explained",
    "source": "Google Research",
    "expected_scores": {"deployment": 7, "productization": 6, "technical_depth": 10, "responsiveness": 7, "business_impact": 6},
    "expected_avg": 7.2,
    "expected_credibility": 10
  }
]
```

#### FS-02.2: Rejection Logic

| Condition | Action |
|-----------|--------|
| `avg_score < 6.5` | Reject → log to `discarded.json` with reason `"low_relevance_score"` |
| `credibility < 6` | Reject → reason `"low_credibility"` |
| `is_promotional == true` | Reject → reason `"promotional_content"` |
| Gemini returns malformed JSON | Retry once. If still malformed, reject → reason `"scoring_parse_error"` |
| Gemini API error (429/500) | Retry with backoff. After 3 failures, skip article → reason `"api_error"` |

**Discarded article log entry**:
```json
{
  "url": "string",
  "title": "string",
  "source_name": "string",
  "source_tier": 3,
  "avg_score": 5.2,
  "credibility": 4,
  "is_promotional": false,
  "rejection_reason": "low_relevance_score",
  "scores_detail": {"deployment": 5, "productization": 6, "technical_depth": 5, "responsiveness": 4, "business_impact": 6},
  "discarded_at": "ISO-8601"
}
```

---

### FS-03: Anti-Hallucination Summarization Pipeline

**Purpose**: Generate faithful, grounded summaries using a 3-step extractive-then-abstractive pipeline with verification.

#### FS-03.1: Step 1 — Extractive Phase

| Field | Specification |
|-------|---------------|
| **Model** | `GEMINI_BULK_MODEL` env var (default: `gemini-2.0-flash-lite`) |
| **Temperature** | 0 |
| **max_output_tokens** | 400 |
| **Max input** | 2,000 tokens (article text) |

**Prompt** (`prompts/extraction.txt`):
```
Extract exactly 5 key sentences from this article that capture the core ideas.
Return them as a JSON array with the approximate word position in the text.

Article: {extracted_text}

Output format:
{"sentences": [{"text": "exact sentence from article", "position": 150}, ...]}
```

**Verification logic** (in `anti_hallucination.py`):
```python
from fuzzywuzzy import fuzz

def verify_extractions(sentences: list, source_text: str) -> list:
    verified = []
    for s in sentences:
        # Check if sentence exists in source with ≥85% fuzzy match
        best_ratio = fuzz.partial_ratio(s["text"].lower(), source_text.lower())
        if best_ratio >= 85:
            verified.append({**s, "verified": True, "match_score": best_ratio})
        else:
            verified.append({**s, "verified": False, "match_score": best_ratio})
    return verified
```

**Rules**:
- If fewer than 3 sentences verify at ≥85% → flag article as "extraction_failed" → skip summarization → log to `errors.json`
- If 3-4 verify → proceed with verified subset only
- If all 5 verify → proceed normally

#### FS-03.2: Step 2 — Summarization Phase

| Field | Specification |
|-------|---------------|
| **Model** | `GEMINI_BULK_MODEL` env var |
| **Temperature** | 0.1 (slight creativity for readability) |
| **max_output_tokens** | 600 |
| **Max input** | 800 tokens (verified sentences only + prompt) |

**Prompt** (`prompts/summarization.txt`):
```
You are creating a learning summary for an AI Product Manager.
Use ONLY the verified sentences below as your source material.
Think step-by-step before writing each section.

If you do not have sufficient information from the sentences to answer any section,
explicitly state "Information not found in source" rather than speculating.

## Source Sentences
{verified_sentences_json}

## Original Article
Title: {title}
Source: {source_name}
URL: {url}

## Generate these sections (JSON output):
{
  "why_it_matters": "2-3 sentences on AI PM relevance",
  "core_mechanism": "2-3 sentences on how the technology/approach works",
  "product_applications": "2-3 specific product use cases",
  "risks_limitations": "1-2 key risks or limitations",
  "key_takeaways": ["takeaway 1", "takeaway 2", "takeaway 3"],
  "tldr": "Max 2 sentences",
  "keywords_glossary": {"term1": "definition1"}
}
```

**Keywords glossary filtering**:
- Before generating, load all existing `keywords_glossary` entries from `topics.json`
- Include instruction: "Only include terms NOT in this existing list: {existing_terms}"
- If Gemini includes a term that already exists, filter it out post-response

#### FS-03.3: Step 3 — Faithfulness Verification

| Field | Specification |
|-------|---------------|
| **Model** | `GEMINI_BULK_MODEL` env var |
| **Temperature** | 0 |
| **max_output_tokens** | 150 |
| **Max input** | 1,000 tokens |

**Prompt** (`prompts/faithfulness.txt`):
```
Rate the faithfulness of this summary to the original source sentences on a scale of 1-10.
List any claims in the summary that are NOT supported by the source sentences.

Source sentences: {verified_sentences}
Summary: {generated_summary}

Output: {"faithfulness_score": N, "ungrounded_claims": ["claim1", ...]}
```

**Decision logic**:

| Faithfulness Score | Action |
|-------------------|--------|
| ≥ 8 | Accept as high-confidence summary |
| 7 | Accept but flag as "moderate confidence" in email/dashboard |
| < 7 | Flag as "low confidence" — display warning badge in email + dashboard |
| Gemini parse error | Default to score 5 (low confidence) |

#### FS-03.4: Summary Caching (L2-20 Fix)

**Cache key construction**:
```python
cache_key = hashlib.sha256(f"{article_url}|{extraction_method}".encode()).hexdigest()
```

**Rationale**: Different extraction methods (trafilatura vs. readability vs. newspaper3k) may produce meaningfully different text. Each deserves its own cache entry.

**Cache lookup before summarization**:
```python
if cache_key in cache["summary_cache"]:
    return cache["summary_cache"][cache_key]["summary"]  # Skip all 3 steps
```

---

### FS-04: Topic Selection Engine

**Purpose**: Select the optimal daily mix of new and deepening topics using the unified adaptive mode state machine.

#### FS-04.1: Selection Algorithm with Evening Carry-Over (L2-06 + L2-07 Fix)

**Input**:
- Scored + summarized articles from today's pipeline (morning + midday slots)
- `next_day_priority_queue` from previous evening
- Existing `topics.json`
- Current adaptive mode from `metrics.json → current_topic_mode`

**Algorithm (pseudocode)**:
```
1. Load topics.json
2. Load current_topic_mode from metrics.json
3. Determine quotas from unified mode state machine (L2-07 fix):

   MODE_QUOTAS = {
     "normal": {"new": 3, "deepen": 2, "total": 5},
     "reduced_3": {"new": 2, "deepen": 1, "total": 3},
     "reduced_2": {"new": 1, "deepen": 1, "total": 2},
     "minimal": {"new": 1, "deepen": 0, "total": 1}
   }
   quotas = MODE_QUOTAS[current_topic_mode]

4. Process next_day_priority_queue FIRST (L2-06 fix):
   - These are yesterday's evening articles (already scored + summarized)
   - Fill new-topic slots from this queue before today's articles
   - Remove consumed items from queue

5. Select DEEPENING topics (fill up to quotas["deepen"]):
   - Filter topics.json: status == "active" AND current_depth < 5
   - Sort by: current_depth ASC, then mastery_score ASC (lowest first)
   - Check category balance (if any category has 0 topics in last 2 weeks, prioritize)
   - Select top N deepening candidates
   - If fewer candidates than quota → reduce deepening, increase new

6. Select NEW topics (fill remaining quotas["new"] slots):
   - From today's scored articles (after next_day_priority_queue consumed)
   - Exclude any whose topic_name matches existing topic via two-phase dedup (L2-11 fix)
   - Sort by: avg_score DESC (highest relevance first)
   - Apply category balance: if a category is underrepresented, boost its articles
   - Select top N new articles

7. If total selected < 1 → skip email, log to errors.json
8. Return selected list
```

#### FS-04.2: Two-Phase Title Deduplication (L2-11 Fix)

**Problem**: Single-threshold fuzzy matching (80%) produces false positives on short titles like "Transformers" vs "Transform Your Business."

**Solution**:

```python
from fuzzywuzzy import fuzz

def is_duplicate_topic(new_title: str, existing_titles: list[str]) -> bool:
    for existing in existing_titles:
        ratio = fuzz.token_sort_ratio(new_title, existing)

        # Phase 1: Definite duplicate
        if ratio >= 85:
            logger.info(f"Definite duplicate: '{new_title}' ≈ '{existing}' ({ratio}%)")
            return True

        # Phase 2: Ambiguous zone → ask Gemini
        if 60 <= ratio < 85:
            is_same = confirm_duplicate_with_gemini(new_title, existing)
            if is_same:
                logger.info(f"Gemini confirmed duplicate: '{new_title}' ≈ '{existing}'")
                return True

    return False

def confirm_duplicate_with_gemini(title_a: str, title_b: str) -> bool:
    """Lightweight Gemini call to confirm ambiguous duplicates."""
    prompt = f"""Are these two titles about the same specific topic?
Title A: '{title_a}'
Title B: '{title_b}'
Answer only: yes or no."""

    try:
        response = call_gemini(
            model=os.getenv("GEMINI_BULK_MODEL", "gemini-2.0-flash-lite"),
            prompt=prompt,
            max_output_tokens=50,
            temperature=0
        )
        return response.strip().lower() == "yes"
    except Exception:
        # On API error, treat as NOT duplicate (conservative)
        return False
```

#### FS-04.3: Category Balance Tracking

**Stored in `metrics.json`**:
```json
{
  "weekly_category_distribution": {
    "2026-W07": {
      "ml_engineering": 4,
      "product_strategy": 3,
      "mlops": 2,
      "ai_ethics": 1,
      "infrastructure": 3
    }
  },
  "category_drought_counter": {
    "ai_ethics": 1
  }
}
```

**Rules**:
- Update weekly distribution after each daily selection
- If `category_drought_counter[category] >= 2` (2 consecutive weeks with 0 topics), set a bias flag
- When bias flag is active: if any article from the drought category scored ≥ 5.5 (relaxed threshold from 6.5), include it

---

### FS-05: Depth & Mastery Progression System

**Purpose**: Track topic mastery through a 5-level depth system with unified adaptive difficulty state machine.

#### FS-05.1: Depth Level Definitions

| Depth | Label | Question Complexity | Expected Answer Length |
|-------|-------|--------------------|-----------------------|
| 1 | Introduction | "What is X and why does it matter for AI PMs?" | 100-150 words |
| 2 | Fundamentals | "Explain the core mechanism of X and its key trade-offs" | 150-200 words |
| 3 | Application | "Describe a specific product scenario where X would be applied, including implementation considerations" | 200-300 words |
| 4 | Analysis | "Compare X with alternative approaches. What are the decision criteria for choosing X?" | 250-350 words |
| 5 | Expert | "Design a product strategy incorporating X. Address scalability, risks, and measurement" | 300-400 words |

#### FS-05.2: Mastery State Machine

```
                    ┌──────────┐
         ┌─────────│  ACTIVE   │─────────┐
         │         │ depth 1-4 │         │
         │         └─────┬─────┘         │
         │               │               │
    score ≥ 70%     score < 70%     90 days
    retries=0       retries < 2     inactive
         │               │               │
         ▼               ▼               ▼
    ┌─────────┐   ┌───────────┐   ┌──────────┐
    │ ADVANCE │   │   RETRY   │   │ ARCHIVED │
    │depth + 1│   │retries + 1│   │          │
    └────┬────┘   └─────┬─────┘   └──────────┘
         │               │
         │          retries == 2
         │          score < 70%
         │               │
         │               ▼
         │        ┌────────────┐
         │        │  RETEACH   │◄──── 14-day timeout (L2-14)
         │        │simplified  │      auto-revert to active
         │        └─────┬──────┘
         │               │
         │          re-test once
         │          (any score)
         │               │
         ▼               ▼
    ┌──────────────────────┐
    │  depth == 5?         │
    │  YES → COMPLETED     │
    │  NO  → ACTIVE (next) │
    └──────────────────────┘
```

**State transitions**:

| Current State | Trigger | Condition | Next State | Action |
|--------------|---------|-----------|------------|--------|
| active | grading_result | score ≥ 70 AND depth < 5 | active | depth += 1, retries_used = 0, mastery_score = score |
| active | grading_result | score ≥ 70 AND depth == 5 | completed | Move to completed topics |
| active | grading_result | score < 70 AND retries < 2 | active | retries_used += 1 |
| active | grading_result | score < 70 AND retries == 2 | reteaching | Generate reteaching content, set `reteaching_entered_at` |
| reteaching | reteach_grading | any score | active | retries_used = 0, depth unchanged |
| reteaching | cleanup_check | `reteaching_entered_at` > 14 days ago | active | retries_used = 0 (L2-14 fix) |
| active | inactivity_check | last_active > 90 days ago | archived | Move to `archived_topics.json` |
| completed | — | — | — | Terminal state |

**Mastery score semantics (L2-15 fix)**:
- `mastery_score` field = LATEST grading score (from any attempt type)
- Daily mastery averages in `metrics.json` include ALL scores (advances + retries + reteaches)

#### FS-05.3: Unified Adaptive Difficulty State Machine (L2-07 Fix)

**Canonical mode definitions** (single source of truth):

| Mode | New Topics | Deepening | Total | Entry Trigger | Exit (Recovery) |
|------|-----------|-----------|-------|---------------|-----------------|
| `normal` | 3 | 2 | 5 | Default; OR 3 consecutive recovery days from `reduced_3` | — |
| `reduced_3` | 2 | 1 | 3 | 5 consecutive low days (avg mastery < 70%) | 3 consecutive days ≥ 75% → `normal` |
| `reduced_2` | 1 | 1 | 2 | 10 consecutive low days | 3 consecutive days ≥ 75% → `reduced_3` |
| `minimal` | 1 | 0 | 1 | 15 consecutive low days | 3 consecutive days ≥ 75% → `reduced_2` |

**Implementation**:
```python
MODE_CONFIG = {
    "normal": {"new": 3, "deepen": 2, "total": 5, "low_threshold": 5, "next_down": "reduced_3"},
    "reduced_3": {"new": 2, "deepen": 1, "total": 3, "low_threshold": 10, "next_down": "reduced_2", "next_up": "normal"},
    "reduced_2": {"new": 1, "deepen": 1, "total": 2, "low_threshold": 15, "next_down": "minimal", "next_up": "reduced_3"},
    "minimal": {"new": 1, "deepen": 0, "total": 1, "next_up": "reduced_2"}  # Hard floor
}

def update_adaptive_mode(metrics: dict, today_avg: float, topics_graded: int) -> str:
    """Single source of truth for mode transitions."""
    current_mode = metrics["current_topic_mode"]

    # L2-05 fix: Zero-grading days are neutral
    if topics_graded == 0:
        metrics["consecutive_neutral_days"] = metrics.get("consecutive_neutral_days", 0) + 1
        # L2-05 fix: 7+ consecutive no-grading days = pause
        if metrics["consecutive_neutral_days"] >= 7:
            log_mode_event(metrics, "pause", "7+ days without grading")
        return current_mode  # No change

    # Reset neutral counter on grading day
    metrics["consecutive_neutral_days"] = 0

    # Check for recovery (≥ 75%)
    if today_avg >= 75:
        metrics["consecutive_low_days"] = 0
        metrics["consecutive_recovery_days"] = metrics.get("consecutive_recovery_days", 0) + 1

        if metrics["consecutive_recovery_days"] >= 3:
            next_up = MODE_CONFIG[current_mode].get("next_up")
            if next_up:
                log_mode_event(metrics, next_up, f"3 recovery days from {current_mode}")
                metrics["consecutive_recovery_days"] = 0
                return next_up
    else:
        metrics["consecutive_recovery_days"] = 0

    # Check for degradation (< 70%)
    if today_avg < 70:
        metrics["consecutive_low_days"] = metrics.get("consecutive_low_days", 0) + 1

        threshold = MODE_CONFIG[current_mode].get("low_threshold", float('inf'))
        if metrics["consecutive_low_days"] >= threshold:
            next_down = MODE_CONFIG[current_mode].get("next_down")
            if next_down:
                log_mode_event(metrics, next_down, f"{threshold} consecutive low days")
                return next_down
    else:
        metrics["consecutive_low_days"] = 0

    return current_mode
```

**Tracked in `metrics.json`**:
```json
{
  "current_topic_mode": "normal",
  "consecutive_low_days": 0,
  "consecutive_recovery_days": 0,
  "consecutive_neutral_days": 0,
  "topic_reduction_history": [
    {"date": "2026-02-10", "from": "normal", "to": "reduced_3", "reason": "5 consecutive days < 70%"}
  ]
}
```

---

### FS-06: Grading Engine

**Purpose**: Evaluate user-submitted answers using a structured rubric via Gemini, with display-only cache behavior.

#### FS-06.1: Answer Submission

**Endpoint**: `POST /api/grade`

**Authentication (L2-13 Fix)**: Dual-auth — accepts EITHER:
1. `X-API-Key` header matching `API_KEY` env var, OR
2. Valid HTTP Basic Auth session + valid CSRF token

**Request body (Pydantic model)**:
```python
class GradeRequest(BaseModel):
    topic_id: str  # UUID
    answer_text: str = Field(min_length=50, max_length=2000)
    csrf_token: Optional[str] = None  # Required for Basic Auth path

    @validator('answer_text')
    def validate_word_count(cls, v):
        if len(v.split()) < 50:
            raise ValueError("Please provide a more detailed answer (minimum 50 words)")
        return v.strip()
```

**Pre-grading checks (in order)**:
1. Validate authentication (API key OR Basic Auth + CSRF)
2. Validate `topic_id` exists in `topics.json` and status is `active` or `reteaching`
3. Compute `answer_hash = SHA256(answer_text.strip().lower())`
4. Check `cache.json → grading_cache` for key `SHA256(topic_id + depth + answer_hash)`
   - **If cache hit (L2-03 fix)**: Return cached result with `"cached": true` flag. **NO state transitions**
5. Check submission history: if same `answer_hash` for same `topic_id + depth` has been submitted ≥ 2 times → reject
6. Check rate limit: max 5 grading submissions per minute per IP

#### FS-06.2: Grading Cache Behavior (L2-03 Fix)

**Display-only cache**: When a cache hit occurs:

```python
def handle_grading_request(request: GradeRequest, topic: dict, cache: dict) -> dict:
    cache_key = compute_cache_key(request.topic_id, topic["current_depth"], request.answer_text)

    if cache_key in cache["grading_cache"]:
        cached = cache["grading_cache"][cache_key]
        # Return cached result for DISPLAY ONLY
        return {
            "success": True,
            "topic_id": request.topic_id,
            "score": cached["result"]["score"],
            "breakdown": cached["result"]["breakdown"],
            "feedback": cached["result"]["feedback"],
            "decision": cached["result"]["decision"],
            "cached": True,  # Critical flag
            "message": "This is a cached result from a previous identical submission. No progress changes applied. Modify your answer for a fresh evaluation."
        }
        # NOTE: NO state transitions (depth, retries, mastery_score) on cache hit

    # Fresh Gemini call - state transitions DO occur here
    result = call_gemini_grading(topic, request.answer_text)
    apply_state_transitions(topic, result)  # Only on fresh calls
    cache_result(cache_key, result)
    return {**result, "cached": False}
```

#### FS-06.3: Grading Prompt with RPD Tracking (L2-08 Fix)

| Field | Specification |
|-------|---------------|
| **Model** | `GEMINI_GRADE_MODEL` env var (default: `gemini-2.5-flash`) — with RPD fallback |
| **Temperature** | 0 |
| **max_output_tokens** | 400 |
| **Max input** | 800 tokens |

**RPD-aware model selection**:
```python
def get_grading_model(pipeline_state: dict) -> tuple[str, bool]:
    """Returns (model_id, quality_warning)."""
    grade_model = os.getenv("GEMINI_GRADE_MODEL", "gemini-2.5-flash")
    bulk_model = os.getenv("GEMINI_BULK_MODEL", "gemini-2.0-flash-lite")

    grade_model_rpd = pipeline_state.get("daily_rpd", {}).get(grade_model, 0)

    if grade_model_rpd >= 90:  # L2-08 threshold
        logger.warning(f"RPD limit approaching ({grade_model_rpd}/100). Falling back to bulk model.")
        return bulk_model, True  # quality_warning = True

    return grade_model, False
```

**Prompt** (`prompts/grading.txt`):
```
You are grading an AI PM's understanding of a topic. Use the rubric strictly.

## Topic Context
Topic: {topic_name}
Depth Level: {current_depth} ({depth_label})
Summary: {topic_summary_tldr}

## Rubric (score each dimension)
1. Concept Clarity (0-30 points):
   - 0-7: Vague or incorrect understanding
   - 8-15: Partially correct, missing key aspects
   - 16-23: Clear understanding with correct terminology
   - 24-30: Exceptional clarity, precise domain terminology

2. Technical Correctness (0-30 points):
   - 0-7: Contains factual errors
   - 8-15: Mostly correct, some imprecisions
   - 16-23: Accurate with good technical specifics
   - 24-30: Technically impeccable

3. Application Thinking (0-20 points):
   - 0-5: No practical application mentioned
   - 6-10: Generic application reference
   - 11-15: Specific, concrete use case described
   - 16-20: Novel, well-reasoned application with trade-offs

4. AI PM Relevance (0-20 points):
   - 0-5: No PM perspective
   - 6-10: Surface-level PM connection
   - 11-15: Clear PM decision implications articulated
   - 16-20: Strategic PM insight with business impact

## Calibration Examples
Example 1 (Score: 82/100 at Depth 3):
Answer: {example_high_answer}
Breakdown: Clarity=25, Technical=24, Application=17, PM_Relevance=16

Example 2 (Score: 45/100 at Depth 2):
Answer: {example_low_answer}
Breakdown: Clarity=12, Technical=15, Application=10, PM_Relevance=8

## Student's Answer
{answer_text}

## Output (JSON only)
{
  "total_score": N,
  "breakdown": {
    "concept_clarity": N,
    "technical_correctness": N,
    "application_thinking": N,
    "ai_pm_relevance": N
  },
  "feedback": "2-3 sentences of specific improvement advice",
  "decision": "advance | retry | reteach"
}
```

#### FS-06.4: Grading Response

**Response schema**:
```json
{
  "success": true,
  "topic_id": "uuid",
  "topic_name": "string",
  "depth": 2,
  "score": 78,
  "breakdown": {
    "concept_clarity": 22,
    "technical_correctness": 24,
    "application_thinking": 16,
    "ai_pm_relevance": 16
  },
  "feedback": "Strong technical understanding. Consider adding specific deployment metrics.",
  "decision": "advance",
  "new_depth": 3,
  "retries_remaining": 2,
  "model_used": "gemini-2.5-flash",
  "quality_warning": null,
  "cached": false
}
```

**Decision mapping (ONLY applied on fresh calls, NOT cache hits)**:

| Condition | `decision` | Side Effects |
|-----------|-----------|--------------|
| score ≥ 70 AND depth < 5 | `advance` | `current_depth += 1`, `retries_used = 0`, `mastery_score = score` |
| score ≥ 70 AND depth == 5 | `advance` | `status = "completed"`, move to completed |
| score < 70 AND retries_used < 2 | `retry` | `retries_used += 1` |
| score < 70 AND retries_used == 2 | `reteach` | `status = "reteaching"`, `reteaching_entered_at = now()` |

#### FS-06.5: Reteaching Engine with Timeout (L2-14 Fix)

**Trigger**: When a topic enters `reteaching` status

| Field | Specification |
|-------|---------------|
| **Model** | `GEMINI_BULK_MODEL` env var |
| **Temperature** | 0.2 |
| **max_output_tokens** | 500 |
| **Max input** | 500 tokens |

**Timeout handling (L2-14 fix)**:
- When entering reteaching: set `reteaching_entered_at = utc_now()`
- During daily cleanup: check all reteaching topics
- If `reteaching_entered_at` > 14 days ago AND no grading attempt in that period:
  - Auto-revert to `active`, `retries_used = 0`
  - Log to `topic_reduction_history`: "reteaching timeout after 14 days"

**Prompt** (`prompts/reteach.txt`):
```
A learner has struggled with this topic at depth {depth}.
Break it down into simpler sub-concepts and re-explain.

Topic: {topic_name}
Summary: {topic_summary_tldr}
Previous scores: {history_scores}

Generate:
1. 3 simpler sub-concepts that build toward understanding
2. A simplified explanation of each (2-3 sentences each)
3. 1 simpler comprehension question for re-testing

Output JSON: {"sub_concepts": [...], "reteach_question": "string"}
```

#### FS-06.6: Model Deprecation Handling (L2-17 Fix)

```python
def call_gemini_with_fallback(model_env_var: str, prompt: str, **kwargs) -> dict:
    model = os.getenv(model_env_var, DEFAULT_MODELS[model_env_var])
    bulk_model = os.getenv("GEMINI_BULK_MODEL", "gemini-2.0-flash-lite")

    try:
        return call_gemini(model, prompt, **kwargs)
    except GeminiModelNotFoundError as e:
        # L2-17: Model deprecated
        logger.critical(f"Model {model} not found. Falling back to {bulk_model}.")
        send_alert_email(
            subject="CRITICAL: Gemini Model Deprecated",
            body=f"Model '{model}' returned 'not found'. System is running in degraded mode using '{bulk_model}'. Please update {model_env_var} env var."
        )
        return call_gemini(bulk_model, prompt, **kwargs)
```

---

### FS-07: Daily Email Digest

**Purpose**: Deliver the daily learning content as a structured, email-client-compatible HTML digest.

#### FS-07.1: Email Generation

**Trigger**: `GET /api/trigger/email-send` with `X-Cron-Secret` header

**Pre-send checks**:
1. Read `pipeline_state.json` — check if ANY slot has topics selected
2. Read `cache.json → email_cache` — if today's date exists with `sent: true`, skip (idempotency)
3. Load today's selected topics from all slots
4. If no topics selected today, skip email and log

**Streak tracking (L2-10 fix)**:
```python
def update_streak(email_cache: dict, metrics: dict) -> None:
    """Streak = consecutive calendar days with email_sent == true."""
    today = get_today_date()
    yesterday = today - timedelta(days=1)

    if yesterday.isoformat() in email_cache and email_cache[yesterday.isoformat()].get("sent"):
        metrics["streak_count"] += 1
    else:
        # Streak broken
        metrics["streak_count"] = 1
        metrics["streak_start_date"] = today.isoformat()

    # Update longest streak
    if metrics["streak_count"] > metrics.get("longest_streak", 0):
        metrics["longest_streak"] = metrics["streak_count"]
```

**Email metadata**:
```
From: {SENDER_EMAIL}
To: {RECIPIENT_EMAIL}
Subject: "Daily AI Learning Digest — {date} | {streak_count} Day Streak"
Content-Type: multipart/alternative (HTML + plain-text)
```

#### FS-07.2: HTML Email Template Rules

| Rule | Reason |
|------|--------|
| Table-based layout only (no `<div>` for structure) | Outlook uses Word renderer |
| 100% inline CSS (no `<style>` tags) | Gmail strips embedded CSS |
| Max width: 600px | Mobile compatibility |
| Fonts: Arial, Helvetica, sans-serif only | Universal support |
| Images: hosted URLs only (no base64, no CID) | Gmail strips embedded images |
| No JavaScript | All clients strip JS |
| No `<form>` elements | Clients block forms |
| All links use absolute URLs | Relative links break |
| Progress bars: text-based `[████░░░░] 50%` | ASCII art renders everywhere |
| Background colors: inline `bgcolor` attribute on `<td>` | Outlook ignores CSS backgrounds |

#### FS-07.3: Email Content Structure

**Header block**:
```html
<table width="600" cellpadding="0" cellspacing="0" border="0" align="center">
  <tr>
    <td bgcolor="#1a1a2e" style="padding: 20px; color: #ffffff; font-family: Arial, sans-serif;">
      <h1 style="margin: 0; font-size: 22px;">Daily AI Learning Digest</h1>
      <p style="margin: 5px 0 0; font-size: 14px; color: #a0a0a0;">{formatted_date}</p>
      <p style="margin: 10px 0 0; font-size: 16px;">
        Progress: [{"█" * filled}{"░" * (10-filled)}] {progress_pct}%
      </p>
    </td>
  </tr>
</table>
```

**Per-topic block** (repeated 1-5 times via Jinja2 `{% for topic in topics %}`):
- Topic title + depth badge (e.g., "Level 3 of 5")
- Faithfulness indicator: if score < 7 → display "⚠ Low Confidence" badge
- Sections: Why it matters, Core mechanism, Product applications, Risks & limitations, Key takeaways (bulleted), TL;DR, Keywords (new terms only)
- Article link
- Credibility score as star rating: ★★★★☆ (e.g., 4/5 = round(score/2))
- If deepening topic: include comprehension question for this depth level

**Footer block**:
- 🔥 Streak: {streak_count} days
- 📊 Avg Mastery (7-day): {avg_mastery}%
- ⚠ Weakest: {weakest_category}
- Current mode indicator (if not `normal`): "📉 Reduced mode: {current_mode}"
- Motivational line (rotate from set of 10 predefined lines)
- Link to dashboard

#### FS-07.4: Plain-Text Fallback

Every email includes a `text/plain` MIME part with identical content using ASCII formatting.

---

### FS-08: Web Dashboard

**Purpose**: Provide a visual interface for learning progress tracking and grading submissions.

#### FS-08.1: Page Specifications

**Page: `/dashboard` (Main View)**

| Component | Data Source | Visualization |
|-----------|------------|---------------|
| Learning Streak | `metrics.json → streak_count` | Large number with flame emoji |
| Topic Distribution | `topics.json` grouped by category | Bar chart (Chart.js) |
| Mastery Over Time | `metrics.json → daily_mastery_averages` (last 30 days) | Line chart (Chart.js) |
| Depth Distribution | `topics.json` grouped by current_depth | Horizontal bar chart |
| Weakest Competency | Category with lowest avg mastery | Text badge |
| Topic Reduction Status | `metrics.json → current_topic_mode` | Conditional banner (if mode ≠ normal) |
| Recent Topics | Last 5 topics sorted by `last_updated` | Table |

**Cold start handling**:
1. FastAPI returns HTML skeleton immediately (no data, just layout + loading spinners)
2. Skeleton includes `<script>` that calls `GET /api/dashboard-data`
3. JavaScript populates charts/tables client-side
4. If API call takes > 5 seconds, skeleton shows "Loading..." message

**Page: `/topic/{topic_id}` (Topic Detail)**

| Component | Data Source |
|-----------|------------|
| Topic Name + Status Badge | `topics.json → topic_id` |
| Current Depth Indicator | Visual 5-step progress bar |
| Summary | `topic.summary` object |
| Article Link | `topic.source_url` |
| Credibility Score | Star rating |
| Faithfulness Score | Score + confidence badge |
| Version History | `topic.history[]` — table: date, depth, score, decision, model_used, cached |
| Grading Form | HTML form → `POST /api/grade` (only if status == active or reteaching) |

**Grading form with dual-auth (L2-13 fix)**:
```html
<form method="POST" action="/api/grade">
  <!-- CSRF token for Basic Auth path -->
  <input type="hidden" name="csrf_token" value="{csrf_token}">
  <input type="hidden" name="topic_id" value="{topic_id}">

  <label>Your Answer (minimum 50 words):</label>
  <textarea name="answer_text" rows="8" required minlength="200"></textarea>
  <p id="word-count">0 words</p>

  <button type="submit">Submit Answer</button>
</form>
```

**Page: `/discarded` (Discarded Insights)**

| Component | Data Source |
|-----------|------------|
| Paginated list | `discarded.json` — 20 items per page |
| Per item | title, source, tier, avg score, credibility, rejection reason, date |
| Sorting | Most recent first (by `discarded_at`) |

**Page: `/health` (System Health)**

| Component | Data Source |
|-----------|------------|
| System Status | Computed: healthy/degraded/unhealthy |
| Last RSS Fetch (per slot) | `pipeline_state.json → slots.{slot}.completed_at` |
| Last Email Sent | `cache.json → email_cache → latest date` |
| OAuth Status | Live check via `google-auth` |
| Daily/Monthly Token Usage | `cost_tracker` accumulated |
| Daily RPD (per model) | `pipeline_state.json → daily_rpd` |
| Errors Last 24h | `errors.json` count |
| Pipeline State (per slot) | `pipeline_state.json → slots.{slot}.status` |
| Active Feeds | Count of `enabled: true` in `rss_sources.json` |
| Adaptive Mode | `metrics.json → current_topic_mode` |

#### FS-08.2: Authentication Flow

**Dashboard pages**: HTTP Basic Auth
1. Browser requests `/dashboard`
2. FastAPI middleware checks for `Authorization: Basic {base64(user:pass)}`
3. If missing → 401 with `WWW-Authenticate: Basic` → browser login dialog
4. If present → compare against `DASHBOARD_USER` and `DASHBOARD_PASS` env vars

**API endpoints (L2-13 + L2-19 fix)**:

| Endpoint | Auth Method 1 | Auth Method 2 |
|----------|--------------|---------------|
| `GET /api/dashboard-data` | `X-API-Key` header | HTTP Basic Auth (via `credentials: "include"`) |
| `POST /api/grade` | `X-API-Key` header | HTTP Basic Auth + CSRF token |

```python
def authenticate_dual(request: Request) -> bool:
    """L2-13/L2-19: Accept either auth method."""
    # Method 1: API Key
    api_key = request.headers.get("X-API-Key")
    if api_key and api_key == os.getenv("API_KEY"):
        return True

    # Method 2: Basic Auth
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Basic "):
        credentials = base64.b64decode(auth_header[6:]).decode()
        username, password = credentials.split(":", 1)
        if (username == os.getenv("DASHBOARD_USER") and
            password == os.getenv("DASHBOARD_PASS")):
            return True

    return False
```

---

### FS-09: Quarterly Report Generation

**Purpose**: Generate periodic performance summaries for self-accountability.

#### FS-09.1: Report Generation (L2-02 Fix — Date-Gated)

**Trigger**: Part of morning RSS trigger. NOT a separate cron job.

```python
def should_generate_quarterly_report() -> bool:
    """Check if today is a quarterly report date."""
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    return today.day == 1 and today.month in [1, 4, 7, 10]
```

**Execution**: After RSS processing completes on Jan 1, Apr 1, Jul 1, Oct 1.

**Data collection** (for the past quarter):
```json
{
  "quarter": "Q1 2026",
  "period": {"start": "2025-10-01", "end": "2025-12-31"},
  "topics_covered": 45,
  "topics_completed": 8,
  "topics_attempted": 52,
  "avg_mastery_overall": 74.5,
  "avg_mastery_by_category": {
    "ml_engineering": 78,
    "product_strategy": 72,
    "mlops": 75,
    "ai_ethics": 68,
    "infrastructure": 71
  },
  "depth_progression": {
    "depth_1_to_2": 35,
    "depth_2_to_3": 25,
    "depth_3_to_4": 12,
    "depth_4_to_5": 8
  },
  "weakest_categories": ["ai_ethics", "infrastructure"],
  "strongest_categories": ["ml_engineering", "mlops"],
  "learning_velocity": 0.65,
  "streak_max": 22,
  "topic_reduction_days": 5,
  "reteach_count": 3
}
```

**Storage**: Append to `quarterly_reports_{YYYY}.json`
**Email**: Send as special email with subject "Quarterly Learning Report — {quarter}"

---

### FS-10: Scheduling & Trigger System

**Purpose**: Drive all autonomous operations through external HTTP triggers with exactly 4 cron jobs.

#### FS-10.1: API Endpoint Specifications

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/trigger/rss-fetch` | GET | `X-Cron-Secret` | Fetch + score + summarize + select (per-slot) |
| `/api/trigger/email-send` | GET | `X-Cron-Secret` | Generate + send daily email |
| `/api/grade` | POST | Dual-auth | Grade submitted answer |
| `/api/dashboard-data` | GET | Dual-auth | JSON data for dashboard |
| `/health` | GET | `X-API-Key` | System health check |
| `/dashboard` | GET | HTTP Basic Auth | Main dashboard page |
| `/topic/{id}` | GET | HTTP Basic Auth | Topic detail page |
| `/discarded` | GET | HTTP Basic Auth | Discarded insights page |

#### FS-10.2: Morning Trigger Extras (L2-02 Fix)

The morning RSS trigger (`slot=morning`) also runs:

**Daily cleanup** (before RSS fetching):
- Cache eviction (expired TTL entries)
- Archive topics inactive > 90 days
- Trim `discarded.json` to 500 entries (FIFO)
- Trim `errors.json` to 200 entries (FIFO)
- Revert stale reteaching topics (> 14 days per L2-14)
- Update daily mastery averages

**Weekly backup** (Sunday only, date-gated):
- Copy all JSON files to `AI_PM_SYSTEM/backups/{YYYY-MM-DD}/`
- Delete backup folders older than 28 days

**Quarterly report** (Jan 1, Apr 1, Jul 1, Oct 1, date-gated):
- Generate quarterly report after RSS processing completes

#### FS-10.3: cron-job.org Configuration (L2-02 Fix — Exactly 4 Jobs)

| Job # | Name | URL | Schedule (IST) | UTC Equivalent | Timeout | Retry |
|-------|------|-----|----------------|----------------|---------|-------|
| 1 | RSS Morning | `/api/trigger/rss-fetch` | 7:55 AM | 2:25 AM | 60s | 1 retry after 5 min |
| 2 | RSS Midday | `/api/trigger/rss-fetch` | 11:55 AM | 6:25 AM | 60s | 1 retry after 5 min |
| 3 | RSS Evening | `/api/trigger/rss-fetch` | 4:55 PM | 11:25 AM | 60s | 1 retry after 5 min |
| 4 | Email Send | `/api/trigger/email-send` | 12:25 PM | 6:55 AM | 60s | 1 retry after 5 min |

**1 unused slot** reserved for future use or emergency manual triggers.

**All jobs include header**: `X-Cron-Secret: {value_from_env}`

#### FS-10.4: Slot Detection

```python
def detect_current_slot() -> Optional[str]:
    """Determine which slot based on current IST time."""
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    hour = now_ist.hour

    if 6 <= hour < 10:
        return "morning"
    elif 10 <= hour < 14:
        return "midday"
    elif 14 <= hour < 19:
        return "evening"
    else:
        return None  # Outside scheduled window
```

---

### FS-11: Google Drive Storage Layer

**Purpose**: Provide persistent, structured JSON storage with ETag-based optimistic locking.

#### FS-11.1: File Inventory

| File | Purpose | Max Size Strategy | Schema Version |
|------|---------|-------------------|----------------|
| `topics.json` | Active topics | Archival after depth 5 or 90 days | 2.0 |
| `archived_topics.json` | Completed/inactive topics | Partitioned yearly after 2000+ entries | 2.0 |
| `daily_logs_{YYYY_MM}.json` | Daily pipeline execution logs | Monthly partitioned | 2.0 |
| `discarded.json` | Rejected articles | Capped at 500 entries (FIFO) | 2.0 |
| `metrics.json` | Aggregated performance metrics | Single file, pruned quarterly | 2.0 |
| `quarterly_reports_{YYYY}.json` | Annual quarterly report collection | Yearly partitioned | 2.0 |
| `cache.json` | URL dedup + grading cache + email cache + summary cache | Capped at 1,000 entries (TTL) | 2.0 |
| `pipeline_state.json` | Current pipeline execution state with per-slot tracking | Single file, overwritten each run | 2.0 |
| `errors.json` | Error log | Capped at 200 entries (FIFO) | 2.0 |
| `system_logs_{YYYY_MM}.json` | Detailed system logs | Monthly partitioned | 2.0 |
| `rss_sources.json` | RSS feed configuration (42 feeds across 6 tiers) | User-managed | 2.0 |

#### FS-11.2: Write Safety Protocol with ETag Locking (L2-04 Fix)

**Sequence for every write operation**:

```
1. ACQUIRE asyncio.Lock (in-memory, per-file)
2. READ current file from Google Drive
   - CAPTURE ETag/revision from response headers
3. VALIDATE current file is valid JSON + schema_version matches
   - If corrupt → READ {filename}.backup → use backup
   - If backup also corrupt → initialize with empty schema
4. APPLY modifications in memory
5. VALIDATE modified data against expected schema
6. UPLOAD current file as {filename}.backup to Drive
7. UPLOAD modified data as {filename} to Drive
   - Include If-Match: {captured_etag} header (L2-04)
8. HANDLE response:
   - 200 OK → success
   - 412 Precondition Failed (ETag mismatch) → re-read, re-merge, retry (max 3)
9. READ back {filename} from Drive
10. VALIDATE read-back matches what was written
    - If mismatch → LOG error, RESTORE from backup
11. RELEASE asyncio.Lock
```

**Error handling during write**:

| Error | Action |
|-------|--------|
| Google Drive 403 (forbidden) | Check OAuth token → refresh if expired → retry |
| Google Drive 412 (precondition failed) | Re-read latest, re-merge changes, retry (max 3) |
| Google Drive 429 (rate limit) | Backoff 1s → 2s → 4s. Max 3 retries |
| Google Drive 5xx | Retry once after 2s |
| Network timeout | Write to local `/tmp/{filename}` as fallback. Set flag for sync on next successful connection |
| JSON serialization error | Log error, do not write. Return original file contents |

#### FS-11.3: Local Fallback Handling (L2-09 Fix — Accepted Risk)

```python
async def write_with_fallback(filename: str, data: dict) -> bool:
    """Write to Drive with local fallback for crash recovery."""
    try:
        await write_to_drive(filename, data)
        return True
    except DriveUnreachableError:
        # Short-term fallback only
        local_path = f"/tmp/{filename}"
        with open(local_path, "w") as f:
            json.dump(data, f)
        logger.warning(f"Drive unreachable. Wrote to {local_path} for later sync.")
        return False

async def startup_sync() -> None:
    """On app startup, sync any orphaned /tmp/ files to Drive."""
    for filename in os.listdir("/tmp/"):
        if filename.endswith(".json"):
            local_path = f"/tmp/{filename}"
            try:
                with open(local_path) as f:
                    data = json.load(f)
                await write_to_drive(filename, data)
                os.remove(local_path)
                logger.info(f"Synced orphaned file {filename} to Drive")
            except Exception as e:
                logger.error(f"Failed to sync {filename}: {e}")
```

**Accepted risk**: Render restarts will erase `/tmp/`. This is crash recovery, not persistent storage.

#### FS-11.4: Complete JSON Schemas (v2.0)

**pipeline_state.json (L2-01 fix — per-slot tracking)**:
```json
{
  "schema_version": "2.0",
  "date": "2026-02-16",
  "slots": {
    "morning": {
      "run_id": "uuid-v4",
      "status": "PENDING | FETCHING | SCORING | SUMMARIZING | SELECTING | DONE | FAILED",
      "started_at": "ISO-8601",
      "completed_at": "ISO-8601",
      "articles_fetched": 12,
      "articles_new": 8,
      "articles_scored": 8,
      "articles_passed": 5,
      "articles_summarized": 5,
      "topics_selected": 5,
      "errors": [],
      "cleanup_ran": true,
      "backup_ran": false,
      "quarterly_ran": false
    },
    "midday": {
      "run_id": "uuid-v4",
      "status": "PENDING",
      "started_at": null,
      "completed_at": null,
      "articles_fetched": 0,
      "articles_new": 0,
      "articles_scored": 0,
      "articles_passed": 0,
      "articles_summarized": 0,
      "topics_selected": 0,
      "errors": []
    },
    "evening": {
      "run_id": null,
      "status": "PENDING",
      "started_at": null,
      "completed_at": null,
      "articles_fetched": 0,
      "articles_new": 0,
      "articles_scored": 0,
      "articles_passed": 0,
      "articles_summarized": 0,
      "topics_selected": 0,
      "errors": []
    }
  },
  "email_sent": false,
  "next_day_priority_queue": [
    {
      "url": "string",
      "url_hash": "sha256",
      "title": "string",
      "source_name": "string",
      "source_tier": 3,
      "category_bias": "infrastructure",
      "summary": {},
      "scores": {},
      "added_at": "ISO-8601"
    }
  ],
  "daily_rpd": {
    "gemini-2.0-flash-lite": 45,
    "gemini-2.5-flash": 12
  }
}
```

**topics.json (v2.0)**:
```json
{
  "schema_version": "2.0",
  "last_updated": "ISO-8601",
  "topics": [
    {
      "topic_id": "uuid-v4",
      "topic_name": "string",
      "category": "ml_engineering | product_strategy | mlops | ai_ethics | infrastructure",
      "current_depth": 1,
      "mastery_score": 0,
      "status": "active | completed | archived | reteaching",
      "retries_used": 0,
      "source_url": "string",
      "source_title": "string",
      "source_tier": 1,
      "credibility_score": 0.0,
      "faithfulness_score": 0.0,
      "extraction_method": "trafilatura | readability | newspaper3k | rss_description",
      "created_at": "ISO-8601",
      "last_updated": "ISO-8601",
      "last_active": "ISO-8601",
      "reteaching_entered_at": null,
      "summary": {
        "why_it_matters": "string",
        "core_mechanism": "string",
        "product_applications": "string",
        "risks_limitations": "string",
        "key_takeaways": ["string"],
        "tldr": "string",
        "keywords_glossary": {"term": "definition"}
      },
      "history": [
        {
          "date": "ISO-8601",
          "depth": 1,
          "score": 75,
          "answer_hash": "sha256",
          "decision": "advance | retry | reteach",
          "feedback": "string",
          "model_used": "gemini-2.5-flash",
          "cached": false,
          "reteach_content": null
        }
      ]
    }
  ]
}
```

**metrics.json (v2.0)**:
```json
{
  "schema_version": "2.0",
  "streak_count": 15,
  "streak_start_date": "ISO-8601",
  "longest_streak": 30,
  "current_topic_mode": "normal | reduced_3 | reduced_2 | minimal",
  "consecutive_low_days": 0,
  "consecutive_recovery_days": 0,
  "consecutive_neutral_days": 0,
  "daily_mastery_averages": [
    {"date": "ISO-8601", "avg_mastery": 72.5, "topics_graded": 3}
  ],
  "weekly_category_distribution": {
    "2026-W07": {
      "ml_engineering": 4,
      "product_strategy": 3,
      "mlops": 2,
      "ai_ethics": 1,
      "infrastructure": 3
    }
  },
  "category_drought_counter": {
    "ai_ethics": 1
  },
  "topic_reduction_history": [
    {"date": "ISO-8601", "from": "normal", "to": "reduced_3", "reason": "string"}
  ],
  "monthly_cost_tracker": {
    "2026-02": {
      "total_input_tokens": 330000,
      "total_output_tokens": 225000,
      "total_cost_usd": 0.124,
      "calls_by_operation": {
        "combined_scoring": {"count": 150, "input_tokens": 225000, "output_tokens": 30000},
        "summarization": {"count": 150, "input_tokens": 50000, "output_tokens": 55000},
        "grading": {"count": 30, "input_tokens": 24000, "output_tokens": 12000}
      }
    }
  }
}
```

**cache.json (v2.0 — L2-20 fix)**:
```json
{
  "schema_version": "2.0",
  "last_cleanup": "ISO-8601",
  "processed_urls": {
    "sha256_hash": {
      "url": "string",
      "title": "string",
      "added_at": "ISO-8601",
      "ttl_days": 30
    }
  },
  "grading_cache": {
    "sha256_of_topic_depth_answer": {
      "added_at": "ISO-8601",
      "ttl_days": 30,
      "submission_count": 1,
      "result": {
        "score": 78,
        "breakdown": {},
        "feedback": "string",
        "decision": "advance",
        "model_used": "gemini-2.5-flash"
      }
    }
  },
  "email_cache": {
    "2026-02-16": {
      "sent": true,
      "generated_at": "ISO-8601",
      "topics_count": 5
    }
  },
  "summary_cache": {
    "sha256_of_url_plus_extraction_method": {
      "added_at": "ISO-8601",
      "ttl_days": 90,
      "extraction_method": "trafilatura",
      "summary": {}
    }
  }
}
```

**errors.json (v2.0)**:
```json
{
  "schema_version": "2.0",
  "max_entries": 200,
  "errors": [
    {
      "error_id": "uuid-v4",
      "timestamp": "ISO-8601",
      "component": "rss_pipeline | article_fetcher | relevance_scorer | summarizer | grading_engine | gmail_sender | drive_storage",
      "operation": "string",
      "error_type": "string",
      "error_message": "string",
      "stack_trace": "string (truncated to 500 chars)",
      "context": {
        "url": "string",
        "topic_id": "string",
        "retry_count": 2,
        "slot": "morning"
      },
      "resolved": false
    }
  ]
}
```

---

### FS-12: Cost Tracking & Budget Control

**Purpose**: Track every Gemini API call's cost and enforce budget limits with RPD tracking.

#### FS-12.1: Per-Call Logging

**After every Gemini API call**, log to `metrics.json → monthly_cost_tracker`:
```python
log_entry = {
    "timestamp": utc_now(),
    "model": model_id,
    "operation": "combined_scoring | summarization | grading | title_dedup | reteaching",
    "input_tokens": response.usage_metadata.prompt_token_count,
    "output_tokens": response.usage_metadata.candidates_token_count,
    "cost_usd": calculate_cost(model, input_tokens, output_tokens),
    "tier_used": "free | paid"
}
```

#### FS-12.2: RPD Tracking (L2-08 Fix)

```python
def track_rpd(pipeline_state: dict, model: str) -> None:
    """Track requests-per-day for each model."""
    if "daily_rpd" not in pipeline_state:
        pipeline_state["daily_rpd"] = {}

    current = pipeline_state["daily_rpd"].get(model, 0)
    pipeline_state["daily_rpd"][model] = current + 1

def should_fallback_to_bulk(pipeline_state: dict, grade_model: str) -> bool:
    """L2-08: Check if grading should fall back to bulk model."""
    return pipeline_state.get("daily_rpd", {}).get(grade_model, 0) >= 90
```

#### FS-12.3: Cost Calculation

```python
PRICING = {
    "gemini-2.0-flash-lite": {"input": 0.075 / 1_000_000, "output": 0.30 / 1_000_000},
    "gemini-2.5-flash": {"input": 0.30 / 1_000_000, "output": 2.50 / 1_000_000}
}

def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = PRICING.get(model, PRICING["gemini-2.0-flash-lite"])
    return (input_tokens * rates["input"]) + (output_tokens * rates["output"])
```

#### FS-12.4: Budget Enforcement

| Threshold | Action |
|-----------|--------|
| Daily > ₹3.00 ($0.035) | Log warning, send alert email |
| Monthly > ₹90 ($1.06) | **YELLOW ALERT**: Disable faithfulness checks. Continue scoring + grading |
| Monthly > ₹95 ($1.12) | **RED ALERT**: Disable ALL Gemini calls. Send critical alert. Serve cached data only |

---

## User Flows

### UF-01: Daily Autonomous Pipeline (No User Interaction)

```
07:55 AM IST — Morning RSS Trigger
  cron-job.org → GET /api/trigger/rss-fetch
    │
    ├─ Render cold start (up to 30s)
    │
    ├─ Authenticate X-Cron-Secret ── fail → 401 + log
    │
    ├─ Detect slot = "morning" (by IST time)
    │
    ├─ Run daily cleanup (morning only):
    │   ├─ Evict expired cache entries
    │   ├─ Archive inactive topics (>90 days)
    │   ├─ Trim discarded.json to 500
    │   ├─ Trim errors.json to 200
    │   ├─ Revert stale reteaching topics (>14 days)
    │   └─ Update mastery averages
    │
    ├─ Check if Sunday → run weekly backup (date-gated)
    │
    ├─ Check if quarterly date → queue quarterly report
    │
    ├─ Check pipeline_state.json → slots.morning
    │   └─ Already DONE? → return "slot already completed"
    │
    ├─ STATUS: morning.FETCHING
    │   ├─ For each enabled RSS source (42 feeds):
    │   │   ├─ Parse feed (feedparser)
    │   │   ├─ For each entry: check URL hash → skip if duplicate
    │   │   ├─ arXiv: pre-filter by title keywords, cap at 10
    │   │   └─ For new entries: extract content (layered strategy)
    │   └─ Output: candidate articles list
    │
    ├─ STATUS: morning.SCORING
    │   ├─ For each candidate:
    │   │   ├─ Check budget → skip if exceeded
    │   │   ├─ Combined Gemini call: relevance + credibility (L2-12)
    │   │   ├─ Track RPD
    │   │   ├─ Reject if avg < 6.5, credibility < 6, or promotional
    │   │   └─ Log rejected to discarded.json
    │   └─ Output: passed articles
    │
    ├─ STATUS: morning.SUMMARIZING
    │   ├─ For top passed articles:
    │   │   ├─ Check summary_cache (key = url + extraction_method)
    │   │   ├─ Step 1: Extractive phase → verify sentences
    │   │   ├─ Step 2: Summarization phase → generate summary
    │   │   └─ Step 3: Faithfulness check → rate + flag
    │   └─ Output: summarized topics
    │
    ├─ STATUS: morning.SELECTING
    │   ├─ Load current_topic_mode (unified state machine)
    │   ├─ Consume next_day_priority_queue first (L2-06)
    │   ├─ Apply two-phase title dedup (L2-11)
    │   ├─ Select deepening + new topics per mode quota
    │   └─ Output: final daily topic list
    │
    ├─ STATUS: morning.DONE
    │   ├─ Update pipeline_state.json (per-slot)
    │   ├─ Add processed URLs to cache.json
    │   ├─ Update daily_logs
    │   └─ Return success response
    │
    ├─ If quarterly report queued → generate after RSS
    │
    └─ On any failure: morning.FAILED, log to errors.json

11:55 AM IST — Midday RSS Trigger
  │
  └─ Same flow, slot = "midday", no cleanup/backup/quarterly

12:25 PM IST — Email Send Trigger
  cron-job.org → GET /api/trigger/email-send
    │
    ├─ Check: any slot has topics selected? email_cache not sent?
    ├─ Generate HTML email from topics
    ├─ Update streak (L2-10 — consecutive email_sent days)
    ├─ Send via Gmail API (multipart: HTML + plain-text)
    ├─ Update email_cache + pipeline_state
    └─ If send fails: retry once → if still fails, log

04:55 PM IST — Evening RSS Trigger
  │
  ├─ Same flow, slot = "evening"
  └─ Topics selected → add to next_day_priority_queue (L2-06)
      (since email already sent)
```

### UF-02: User Submits Grading Answer

```
User visits dashboard (desktop browser)
  │
  ├─ Browser shows HTTP Basic Auth dialog → enters credentials
  │
  ├─ Cold start: sees loading skeleton → data populates
  │
  ├─ Clicks on a topic → /topic/{topic_id}
  │
  ├─ Reads summary + comprehension question
  │
  ├─ Types answer in textarea (live word count)
  │
  ├─ Clicks "Submit Answer"
  │   ├─ Dual-auth: Basic Auth (from session) + CSRF token (L2-13)
  │   ├─ Answer validated (length, dedup check)
  │   ├─ Cache checked:
  │   │   ├─ HIT: Return cached result with "cached": true
  │   │   │       NO state transitions (L2-03)
  │   │   │       Message: "Modify your answer for fresh evaluation"
  │   │   └─ MISS: Continue to Gemini grading
  │   ├─ Check RPD → use grade model or fallback (L2-08)
  │   ├─ Gemini grades answer
  │   ├─ Apply state transitions (only on fresh call)
  │   └─ Display result:
  │       ├─ Score: 78/100
  │       ├─ Breakdown: Clarity 22/30, Technical 24/30, etc.
  │       ├─ Feedback: "Consider adding deployment metrics..."
  │       ├─ Decision: "✅ Advance to Level 3!"
  │       ├─ Model used + quality warning if applicable
  │       └─ Cached flag (true/false)
  │
  ├─ If "retry": form re-appears
  │
  └─ If "reteach": simplified explanation + reteach question
```

---

## Data Requirements

### DR-01: Data Flow Diagram (Updated for v2.0)

```
RSS Feeds (42 sources, 6 tiers)
        │
        ▼
  ┌─────────────┐     ┌──────────────┐
  │ RSS Pipeline │────►│ cache.json   │ (dedup check)
  │ (per-slot)   │     │ processed_urls│
  └──────┬──────┘     └──────────────┘
         │
         ├─ arXiv pre-filter (title keywords)
         │
         ▼
  ┌─────────────┐     ┌──────────────┐
  │  Combined    │────►│ discarded.json│ (rejected articles)
  │  Scorer      │     │ (FIFO 500)   │
  │  (L2-12)     │     └──────────────┘
  └──────┬──────┘
         │ (passed articles)
         ▼
  ┌─────────────┐     ┌──────────────┐
  │ Summarizer  │────►│ cache.json   │ (summary cache)
  │ (3-step)    │     │ key: url+method│ (L2-20)
  └──────┬──────┘     └──────────────┘
         │
         ▼
  ┌─────────────┐     ┌──────────────────┐
  │   Topic      │────►│ topics.json      │ (new/updated topics)
  │   Selector   │     │ metrics.json     │ (mode + category tracking)
  │ (L2-07 mode) │     │ pipeline_state   │ (per-slot + next_day_queue)
  └──────┬──────┘     └──────────────────┘
         │
         ▼
  ┌─────────────┐     ┌──────────────┐
  │   Email      │────►│ email_cache  │ (idempotency + streak)
  │   Sender     │     │ metrics.json │ (streak_count L2-10)
  └─────────────┘     └──────────────┘

  User (Dashboard)
         │
         ▼
  ┌─────────────┐     ┌──────────────┐
  │   Grading    │────►│ topics.json  │ (score + depth, only fresh calls)
  │   Engine     │     │ cache.json   │ (grading cache, display-only L2-03)
  │ (L2-03,L2-08)│     │ metrics.json │ (mastery averages)
  └─────────────┘     │ pipeline_state│ (daily_rpd L2-08)
                      └──────────────┘
```

### DR-02: Data Retention Policy

| Data | Retention | Archival Strategy |
|------|-----------|-------------------|
| Active topics | Indefinite (while status = active) | Archive after depth 5 or 90 days inactive |
| Archived topics | Indefinite | Yearly file partitioning after 2000 entries |
| Daily logs | 12 months | Monthly files, delete files older than 12 months |
| Discarded articles | Last 500 entries | FIFO eviction |
| Cache entries | 30-90 days (TTL-based) | Auto-evicted on cleanup |
| Error logs | Last 200 entries | FIFO eviction |
| System logs | 6 months | Monthly files, delete older than 6 months |
| Quarterly reports | Indefinite | Yearly file partitioning |
| Backups | 4 weeks | Delete backup folders older than 28 days |

---

## Business Rules

### BR-01: Content Quality Rules

| Rule | Condition | Action |
|------|-----------|--------|
| BR-01a | Relevance avg score < 6.5 | Reject article |
| BR-01b | Credibility score < 6 | Reject article |
| BR-01c | Promotional tone detected | Reject regardless of scores |
| BR-01d | Article < 200 words | Reject as failed extraction |
| BR-01e | Article > 5,000 words | Truncate to 3,000 words |
| BR-01f | Faithfulness score < 7 | Flag as low confidence (do not reject) |
| BR-01g | Fewer than 3 sentences verified | Skip summarization |
| BR-01h | arXiv article | Pre-filter by title keywords, +1 scoring bonus |

### BR-02: Mastery Progression Rules

| Rule | Condition | Action |
|------|-----------|--------|
| BR-02a | Score ≥ 70% at depth < 5 | Advance to next depth, reset retries |
| BR-02b | Score ≥ 70% at depth 5 | Mark topic as COMPLETED |
| BR-02c | Score < 70% with retries < 2 | Increment retry counter |
| BR-02d | Score < 70% with retries = 2 | Enter reteaching mode |
| BR-02e | After reteaching (any score) | Reset retries, stay at current depth |
| BR-02f | Topic inactive > 90 days | Archive automatically |
| BR-02g | Reteaching > 14 days without attempt | Auto-revert to active (L2-14) |
| BR-02h | Grading cache hit | Display-only, NO state transitions (L2-03) |

### BR-03: Adaptive Difficulty Rules (L2-07 Unified)

| Rule | Condition | Action |
|------|-----------|--------|
| BR-03a | Avg mastery < 70% for 5 days | Reduce to `reduced_3` (3 topics) |
| BR-03b | Avg mastery < 70% for 10 days | Reduce to `reduced_2` (2 topics) |
| BR-03c | Avg mastery < 70% for 15 days | Reduce to `minimal` (1 topic) |
| BR-03d | Avg mastery ≥ 75% for 3 consecutive days | Restore to previous mode (one step) |
| BR-03e | Zero grading activity | Neutral — no counter impact (L2-05) |
| BR-03f | 7+ consecutive zero-grading days | Enter pause state — freeze counters (L2-05) |
| BR-03g | Hard floor | Never fewer than 1 topic per day |

### BR-04: Budget Rules

| Rule | Condition | Action |
|------|-----------|--------|
| BR-04a | Daily spend > ₹3 | Warning alert email |
| BR-04b | Monthly spend > ₹90 | Disable non-essential AI calls |
| BR-04c | Monthly spend > ₹95 | Disable ALL AI calls, critical alert |
| BR-04d | Grading model RPD ≥ 90 | Fall back to bulk model with warning (L2-08) |

### BR-05: Pipeline Rules

| Rule | Condition | Action |
|------|-----------|--------|
| BR-05a | Slot already DONE | Skip re-execution, return "slot already completed" |
| BR-05b | Email already sent today | Skip email, return "already sent" |
| BR-05c | Same answer hash submitted 3+ times | Reject with "revise your answer" message |
| BR-05d | Same URL processed within 30 days | Skip article (duplicate) |
| BR-05e | Title match 85%+ | Definite duplicate (L2-11) |
| BR-05f | Title match 60-85% | Ambiguous — Gemini confirmation (L2-11) |
| BR-05g | Evening slot articles | Add to next_day_priority_queue (L2-06) |

### BR-06: Data Integrity Rules

| Rule | Condition | Action |
|------|-----------|--------|
| BR-06a | JSON file fails validation on read | Restore from .backup file |
| BR-06b | Backup file also corrupt | Initialize with empty schema |
| BR-06c | ETag mismatch on write (412) | Re-read, re-merge, retry (max 3) (L2-04) |
| BR-06d | Write validation fails post-write | Rollback to backup, log error |
| BR-06e | Google Drive unreachable | Use local `/tmp/` fallback, queue sync |

---

## Integration Points

### INT-01: Gemini API

| Attribute | Specification |
|-----------|---------------|
| **Service** | Google AI Gemini API |
| **Authentication** | API key via `GEMINI_API_KEY` env var |
| **Models used** | `GEMINI_BULK_MODEL` env var (default: `gemini-2.0-flash-lite`), `GEMINI_GRADE_MODEL` env var (default: `gemini-2.5-flash`) |
| **SDK** | `google-generativeai` Python SDK |
| **Rate limits (free tier)** | 15 RPM, 1,000 RPD (flash-lite); 5 RPM, 100 RPD (2.5-flash) |
| **RPD tracking** | Per-model in `pipeline_state.json → daily_rpd` |
| **Fallback** | At 90 RPD for grade model → fall back to bulk (L2-08) |
| **Deprecation handling** | On "model not found" → alert + fall back to bulk (L2-17) |

### INT-02: Google Drive API

| Attribute | Specification |
|-----------|---------------|
| **Service** | Google Drive API v3 |
| **Authentication** | OAuth 2.0 with refresh token |
| **Scopes** | `drive.file` (manage files created by this app only) |
| **Write safety** | ETag-based optimistic locking (L2-04) |
| **Rate limits** | 12,000 queries/day/user |
| **Error handling** | 412 → re-read, re-merge, retry. 403 → refresh OAuth. 429 → backoff |

### INT-03: Gmail API

| Attribute | Specification |
|-----------|---------------|
| **Service** | Gmail API v1 |
| **Authentication** | OAuth 2.0 (same credentials as Drive) |
| **Scopes** | `gmail.send` |
| **Rate limits** | 500 emails/day for @gmail.com |

### INT-04: RSS Feeds (42 External Sources)

| Attribute | Specification |
|-----------|---------------|
| **Protocol** | HTTP/HTTPS GET requests |
| **Format** | RSS 2.0 / Atom |
| **Library** | `feedparser` |
| **Rate limiting** | 3 requests/minute per domain |
| **Health monitoring** | Auto-disable after 5 consecutive failures |

### INT-05: cron-job.org (External Scheduler)

| Attribute | Specification |
|-----------|---------------|
| **Service** | cron-job.org free tier |
| **Jobs used** | Exactly 4 (1 slot reserved) |
| **Timeout** | 60 seconds |
| **Retry** | 1 retry after 5 minutes |

### INT-06: Render (Hosting Platform)

| Attribute | Specification |
|-----------|---------------|
| **Tier** | Free |
| **Limits** | 512 MB RAM, 0.1 vCPU, 750 instance-hours/month |
| **Sleep behavior** | Sleeps after 15 minutes inactivity. Cold start: up to 30 seconds |
| **Local fallback** | `/tmp/` for short-term crash recovery (accepted risk: erased on restart) |

---

## Constraints & Assumptions

### Constraints

| ID | Constraint | Implication |
|----|-----------|-------------|
| C-01 | ₹100/month strict budget | Split-model strategy; aggressive caching; token limits |
| C-02 | Render free tier (512 MB, 0.1 vCPU) | No in-process scheduler; lightweight processing |
| C-03 | Google Drive JSON only | ETag-based locking; no ACID; monthly partitioning |
| C-04 | Single user only | Basic security for public exposure |
| C-05 | Free-access articles only | ~30-40% of RSS items may be paywalled |
| C-06 | cron-job.org free tier (5 jobs) | Exactly 4 jobs used; 1 reserved |
| C-07 | 750 instance-hours/month | Cannot keep app awake 24/7 |
| C-08 | Gemini RPD limits | 100 RPD for 2.5-flash; fallback at 90 |

### Assumptions

| ID | Assumption | Risk if Wrong |
|----|-----------|---------------|
| A-01 | Gemini models remain available at current pricing | Budget recalculation needed |
| A-02 | cron-job.org continues 5-job free tier | Switch to GitHub Actions |
| A-03 | Google Drive quotas sufficient | Monitor + batch writes |
| A-04 | RSS feeds maintain XML format | feedparser handles variations |
| A-05 | OAuth consent in "Production" mode | Tokens expire after 7 days otherwise |
| A-06 | Render cold start ≤ 30s | cron-job.org timeout may fail |
| A-07 | 42 feeds don't overwhelm morning trigger | Use BackgroundTasks if needed |

---

## Open Questions

| # | Question | Impact | Current Default |
|---|----------|--------|-----------------|
| 1 | With 42 feeds, will morning trigger (cleanup + backup + quarterly + RSS) fit in Render timeout? | Medium | Use FastAPI BackgroundTasks for long-running ops after acknowledging trigger |
| 2 | Should the ambiguous title dedup zone (60-85%) be tunable? | Low | Fixed thresholds in v2.0. Log all decisions for manual review |
| 3 | What happens if Gemini pricing changes mid-month? | High | Centralized PRICING dict. Cost tracker catches overruns |
| 4 | Should there be a mechanism to manually re-enable disabled feeds? | Low | User edits `rss_sources.json` directly on Drive |
| 5 | How should the system handle RSS feeds that change URLs? | Medium | No auto-detection. User manually updates. Health monitoring catches silent breakage |
| 6 | Should archived topics ever be resurfaced for refresher testing? | Low | No — consider for v3 |
| 7 | If cron-job.org goes down, what's the backup? | Medium | Document fallback: GitHub Actions cron or UptimeRobot |
| 8 | Should the Anthropic community feed be treated differently? | Low | Monitor separately. Auto-disable like any other feed on failures |

---
*Generated via @frd brainstorm agent — FRD v2.0*
