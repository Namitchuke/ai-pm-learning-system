# PRD: AI PM Autonomous Learning & Intelligence System

**Version**: 2.0
**Date**: 2026-02-15
**Status**: Draft
**Supersedes**: PRD v1.0 (2026-02-15)

---

## Changes from v1.0

PRD v2.0 addresses 20 loopholes discovered during adversarial review of PRD v1.0 and FRD v1.0, and expands the RSS source system from 3 tiers (18 feeds) to 6 tiers (42 validated feeds). All 25 original loophole fixes from v1.0 are preserved.

### Critical Fixes (3)

| # | Loophole | Fix Summary |
|---|----------|-------------|
| L2-01 | Pipeline idempotency blocks 2nd/3rd daily RSS fetch — `DONE` status is per-day, so morning completion prevents midday/evening runs | Per-slot granular status: `pipeline_state.json` tracks morning/midday/evening slots independently, each with own status lifecycle |
| L2-02 | 7 cron jobs needed but cron-job.org free tier allows only 5 | Combine quarterly report + daily cleanup + weekly backup into morning RSS trigger via date-gating. Reduces to exactly 4 cron jobs |
| L2-03 | Grading cache hit returns score but doesn't specify whether state transitions (depth advance, retry increment) should fire | Cache is display-only: cached results shown to user but NO state transitions occur. Only fresh Gemini calls trigger state changes |

### High Fixes (6)

| # | Loophole | Fix Summary |
|---|----------|-------------|
| L2-04 | `asyncio.Lock` only protects single-instance; Render could spin multiple instances | ETag-based optimistic locking on Google Drive writes. `If-Match` header prevents stale overwrites across instances |
| L2-05 | Days with 0 grading attempts are undefined in adaptive difficulty counters | Zero-grading days are "neutral" — don't increment or reset counters. 7+ consecutive no-grading days = "pause" (freeze adaptive state) |
| L2-06 | Evening RSS fetch (4:55 PM) produces content after email (12:25 PM) with no consumption path | Evening articles stored in `next_day_priority_queue`; morning selection prioritizes them for next day's email |
| L2-07 | Selection algorithm has separate logic from mode state machine; `minimal` mode has no trigger threshold | Unified canonical state machine: normal→reduced_3→reduced_2→minimal at 5/10/15 consecutive low days. Single source of truth |
| L2-08 | Gemini 2.5 Flash has 100 RPD free-tier limit; a busy grading day could exhaust it | Track RPD per model in `metrics.json`. At 90 RPD, auto-fallback to flash-lite for grading with quality warning flag |
| L2-09 | `/tmp/` fallback on Render is ephemeral — data lost on restart | Documented as accepted risk. Mitigations: short-term only, sync-on-reconnect, startup orphan check |

### Medium Fixes (8)

| # | Loophole | Fix Summary |
|---|----------|-------------|
| L2-10 | Streak logic never formally defined | `streak_count` = consecutive calendar days with `email_sent == true`. No grading requirement. Tracked in `metrics.json` |
| L2-11 | Fuzzy title dedup (fuzz.ratio ≥ 80%) produces false positives on short titles | Two-phase dedup: ≥85% = definite duplicate; 60-85% = ambiguous → Gemini flash-lite confirmation call (50 tokens) |
| L2-12 | PRD cost table shows separate scoring calls; FRD shows combined single call | Aligned: relevance + credibility scoring in single Gemini call. All cost tables updated |
| L2-13 | HTML `<form>` POST cannot send `X-API-Key` header | `/api/grade` accepts either X-API-Key OR Basic Auth + CSRF token. HTML forms use Basic Auth natively |
| L2-14 | `reteaching` status has no timeout — topics can be stuck forever | Auto-revert to `active` (retries=0) after 14 days without grading attempt. Enforced by daily cleanup |
| L2-15 | `mastery_score` update semantics ambiguous on retry attempts | `mastery_score` = latest grading score (any attempt). Daily averages include ALL scores (advances + retries + reteaches) |
| L2-16 | Daily cron for quarterly report wastes a job slot | Subsumed into L2-02 fix — quarterly is date-gated inside morning RSS trigger |
| L2-17 | Gemini model deprecation has no fallback | Model IDs in env vars (`GEMINI_BULK_MODEL`, `GEMINI_GRADE_MODEL`). On "model not found" → alert + fallback to bulk model for all ops |

### Low Fixes (3)

| # | Loophole | Fix Summary |
|---|----------|-------------|
| L2-18 | Blocked domain patterns use invalid glob syntax (`medium.com/@*/membership`) | Split into `BLOCKED_DOMAINS` (exact match) + `BLOCKED_URL_PATTERNS` (regex via `re.search`) |
| L2-19 | Dashboard JS `fetch()` has no access to `X-API-Key` | `/api/dashboard-data` accepts Basic Auth as alternative to API key. JS uses `credentials: "include"` |
| L2-20 | Summary cache key (`SHA256(url)`) ignores extraction method variability | Cache key = `SHA256(url + extraction_method)`. Different extraction methods → different cache entries |

### RSS Source Expansion

- **v1.0**: 3 tiers, 18 feeds (High Authority, Engineering, Community)
- **v2.0**: 6 tiers, 42 validated feeds (Academic, AI Labs, Engineering, Product & Strategy, Data & MLOps, AI Education)
- All feed URLs validated for public accessibility
- 16 low-quality/unavailable sources removed; 24+ high-quality sources added

---

## Problem Statement

AI Product Management is a rapidly evolving discipline where staying current requires daily engagement with technical research, engineering blogs, and deployment case studies. The challenge is threefold: (1) the volume of content across dozens of sources is overwhelming to curate manually, (2) passive reading without structured recall leads to shallow retention, and (3) there is no personal system that curates, teaches, tests, and tracks mastery progression over time — all while operating at near-zero cost.

Existing solutions (newsletters, courses, bookmarking tools) are either too broad, too expensive, or lack any feedback loop to verify comprehension. A PM needs a system that acts as an autonomous learning coach — one that finds the right content, summarizes it with rigor, tests understanding, adapts difficulty, and runs entirely on autopilot with daily accountability via email.

## Goals & Objectives

**Primary Goal**: Build a fully autonomous personal AI PM learning platform that curates, teaches, tests, and tracks mastery across AI/ML product management topics — running reliably under ₹100/month in API costs, with zero manual intervention after initial setup.

**Objectives**:

1. **Autonomous Content Curation**: Scrape RSS feeds from 42 authoritative sources across 6 tiers 3x daily, fetch full free-access article content, and filter using AI-powered relevance + credibility scoring — rejecting promotional, paywalled, or low-quality content automatically
2. **Structured Daily Learning**: Deliver exactly 3 new topics + 2 deepening topics (depth < 5) each day via a structured HTML email at ~12:30 PM IST, with adaptive topic count reduction when performance drops (5→3→2→1 topics)
3. **Active Mastery Tracking**: Test comprehension via a grading engine with a 4-dimension rubric, enforce depth progression (levels 1-5) requiring ≥70% to advance, support 2 retries with reteaching mode on failure
4. **Self-Correcting Intelligence**: Implement anti-hallucination controls via extractive-then-summarize pipeline with fuzzy verification, two-phase duplicate detection across feeds, and few-shot calibrated scoring prompts
5. **Observable Dashboard**: Serve a Jinja2-based web dashboard showing learning streak, topic distribution, mastery scores, depth distribution, weakest competencies, version history, and discarded insights
6. **Quarterly Accountability**: Auto-generate quarterly performance reports summarizing topics covered, average mastery, depth progression, weakest areas, and learning velocity trends
7. **Ultra-Low Cost Operation**: Run all Gemini API usage under ₹100/month (~$1.18) using a split-model strategy (Flash-Lite for bulk tasks, 2.5 Flash for grading), hard token limits, cost tracking with kill switch, and aggressive caching
8. **Reliability on Free Infrastructure**: Deploy on Render free tier with external cron triggers (cron-job.org, exactly 4 jobs) to guarantee scheduled execution despite Render's 15-minute sleep policy, with Google Drive JSON storage hardened via ETag-based optimistic locking

## Target Users

**Single User**: This is a personal-use system for one AI Product Manager. There is no multi-user support, no registration flow, and no collaborative features. The sole user is the system owner who:

- Wants to systematically build deep AI PM expertise across ML Engineering, Product Strategy, MLOps, AI Ethics, and Infrastructure
- Prefers structured, accountable learning over ad-hoc article reading
- Needs daily digestible content delivered to their inbox without manual curation
- Values depth over breadth — wants to progress from surface awareness (depth 1) to expert familiarity (depth 5) per topic
- Requires a cost-effective, self-hosted solution with full data ownership

## Requirements

### Functional Requirements

**FR-01: RSS Content Pipeline**

- The system must scrape RSS feeds from a configurable tiered source list stored in `rss_sources.json` (not hardcoded in Python), organized into 6 tiers with 42 validated feeds:

**Tier 1 — Academic & Research** (7 feeds):

| Source | Feed URL | Category Bias | Notes |
|--------|----------|---------------|-------|
| arXiv cs.AI | `https://rss.arxiv.org/rss/cs.AI` | ml_engineering | High volume (~100+/day); pre-filter by title relevance |
| arXiv cs.LG | `https://rss.arxiv.org/rss/cs.LG` | ml_engineering | Machine learning papers; high volume |
| MIT News AI | `https://news.mit.edu/rss/topic/artificial-intelligence2` | ml_engineering | Institutional; public; good volume |
| BAIR Blog (Berkeley) | `https://bair.berkeley.edu/blog/feed.xml` | ml_engineering | Excellent depth; ~biweekly |
| CMU ML Blog | `https://blog.ml.cmu.edu/feed` | ml_engineering | Faculty/student authored; biweekly |
| Stanford HAI | `https://hai.stanford.edu/news/all/rss` | ai_ethics | AI policy + research; may need URL verification |
| The Gradient | `https://thegradient.pub/rss/` | ml_engineering | Curated AI research publication |

**Tier 2 — AI Research Labs** (7 feeds):

| Source | Feed URL | Category Bias | Notes |
|--------|----------|---------------|-------|
| OpenAI Blog | `https://openai.com/news/rss.xml` | ml_engineering | Official feed |
| DeepMind Blog | `https://deepmind.google/blog/rss.xml` | ml_engineering | Public, active |
| Google Research | `https://research.google/blog/rss` | ml_engineering | Broad AI/ML research |
| Microsoft Research | `https://www.microsoft.com/en-us/research/blog/feed/` | ml_engineering | Broad research including AI |
| Meta Engineering | `https://engineering.fb.com/feed` | infrastructure | Covers AI + engineering broadly |
| HuggingFace Blog | `https://huggingface.co/blog/feed.xml` | mlops | Open-source ML tooling |
| Anthropic (community) | `https://raw.githubusercontent.com/conoro/anthropic-engineering-rss-feed/main/anthropic_engineering_rss.xml` | ai_ethics | Community-maintained; verify periodically |

**Tier 3 — Engineering Blogs** (10 feeds):

| Source | Feed URL | Category Bias | Notes |
|--------|----------|---------------|-------|
| Uber Engineering | `https://www.uber.com/blog/engineering/rss/` | infrastructure | Strong ML platform content |
| Netflix Tech Blog | `https://netflixtechblog.com/feed` | infrastructure | ML experimentation; Medium-hosted |
| Stripe Engineering | `https://stripe.com/blog/feed.rss` | infrastructure | ML for fraud/payments |
| Airbnb Tech Blog | `https://medium.com/feed/airbnb-engineering` | product_strategy | Data science + experimentation |
| DoorDash Engineering | `https://doordash.engineering/blog/rss` | infrastructure | ML search/logistics |
| Slack Engineering | `https://slack.engineering/feed` | infrastructure | Product engineering |
| Dropbox Tech | `https://dropbox.tech/feed` | infrastructure | Systems engineering |
| Pinterest Engineering | `https://medium.com/feed/pinterest-engineering` | ml_engineering | Recommendation systems |
| Spotify Engineering | `https://engineering.atspotify.com/feed/` | mlops | ML personalization |
| LinkedIn Engineering | `https://engineering.linkedin.com/blog.rss.html` | ml_engineering | Ranking/recommendations |

**Tier 4 — Product & Strategy** (7 feeds):

| Source | Feed URL | Category Bias | Notes |
|--------|----------|---------------|-------|
| a16z Blog | `https://a16z.com/feed/` | product_strategy | VC tech/AI strategy |
| First Round Review | `https://review.firstround.com/feed.xml` | product_strategy | Tactical startup/PM content |
| Stratechery | `https://stratechery.com/feed` | product_strategy | Free weekly articles only; premium is paywalled |
| Lenny's Newsletter | `https://www.lennysnewsletter.com/feed` | product_strategy | Free tier only; Substack-hosted |
| SVPG | `https://www.svpg.com/feed/` | product_strategy | Marty Cagan; lower frequency |
| Mind the Product | `https://www.mindtheproduct.com/feed/` | product_strategy | Broad PM content |
| Intercom Blog | `https://www.intercom.com/blog/feed/` | product_strategy | AI-in-product perspectives |

**Tier 5 — Data & MLOps** (7 feeds):

| Source | Feed URL | Category Bias | Notes |
|--------|----------|---------------|-------|
| Towards Data Science | `https://towardsdatascience.com/feed` | ml_engineering | High volume; some paywalled (filter) |
| Databricks Blog | `https://databricks.com/feed` | mlops | Strong MLOps/LLM content |
| Chip Huyen's Blog | `https://huyenchip.com/feed.xml` | mlops | ML systems; excellent quality |
| Eugene Yan's Blog | `https://eugeneyan.com/rss/` | product_strategy | ML + product intersection |
| Lilian Weng's Blog | `https://lilianweng.github.io/index.xml` | ml_engineering | Outstanding ML tutorials (OpenAI) |
| Weights & Biases | `https://wandb.ai/fully-connected/rss.xml` | mlops | MLOps tools and practices |
| Sebastian Raschka | `https://magazine.sebastianraschka.com/feed` | ml_engineering | LLM research distillation; Substack |

**Tier 6 — AI Education & Commentary** (4 feeds):

| Source | Feed URL | Category Bias | Notes |
|--------|----------|---------------|-------|
| deeplearning.ai (The Batch) | `https://www.deeplearning.ai/the-batch/feed/` | ml_engineering | Andrew Ng; may need feed verification |
| fast.ai Blog | `https://www.fast.ai/atom.xml` | ml_engineering | Atom feed; lower frequency but high quality |
| Simon Willison's Blog | `https://simonwillison.net/atom/everything/` | ml_engineering | Prolific LLM/AI tools coverage; daily |
| KDnuggets | `https://www.kdnuggets.com/feed` | ml_engineering | Data science news aggregator |

**arXiv volume management**: arXiv feeds produce ~100+ entries/day. To manage volume without missing important papers:
- Pre-filter arXiv entries by title keywords BEFORE content extraction (keyword list: `["product", "deployment", "production", "recommendation", "ranking", "serving", "inference", "optimization", "fine-tuning", "RLHF", "alignment", "evaluation", "benchmark"]`)
- Process max 10 arXiv articles per fetch cycle
- Score arXiv articles with a +1 tier bonus to compensate for academic writing style scoring lower on "business impact"

- RSS fetching must run 3x daily, triggered by external cron at 7:55 AM, 11:55 AM, and 4:55 PM IST via `GET /api/trigger/rss-fetch`
- **Per-slot pipeline tracking (L2-01 fix)**: Each fetch slot (morning/midday/evening) is tracked independently in `pipeline_state.json`. A completed morning slot does NOT block midday or evening fetches. See FR-10 and FR-12 for schema details
- Only free-access, full-text articles are processed. The system must reject: paywalled content, course promotions, affiliate content, PDF/video/podcast links
- **Duplicate detection (Loophole #7 fix)**: Before any Gemini API call, check article URL hash against `processed_urls` set in `cache.json`. If the URL (or a URL + title hash) was processed in the last 30 days, skip entirely. Deduplicate across RSS feeds (same article appearing in multiple sources)
- **Two-phase title deduplication (L2-11 fix)**: When checking a new article against existing topics:
  - Phase 1: `fuzzywuzzy.fuzz.token_sort_ratio` ≥ 85% → definite duplicate, skip
  - Phase 2: ratio between 60-85% → ambiguous → lightweight Gemini flash-lite call (`max_output_tokens=50`): "Are these two titles about the same specific topic? Title A: '{new_title}', Title B: '{existing_title}'. Answer only: yes or no." If "yes" → duplicate. If "no" or API error → treat as new topic
- **Layered content extraction (Loophole #8 fix)**: Use a fallback chain — Trafilatura (primary) → readability-lxml (fallback 1) → Newspaper3k (fallback 2) → RSS `<description>` field (fallback 3). If all fail, log to `errors.json` and skip the article. Record which extraction method succeeded
- **Per-domain rate limiting (Loophole #8 fix)**: Max 3 HTTP requests per minute to any single domain. Set User-Agent to a real browser string. Handle 403 → skip + log; 429 → exponential backoff (max 3 retries); 5xx → retry once
- **Content validation**: Reject extracted articles with fewer than 200 words (likely failed extraction). Reject articles longer than 5,000 words (truncate to first 3,000 words to save tokens)
- **Blocklist (L2-18 fix)**: Maintain two configurable blocklists:
  - `BLOCKED_DOMAINS`: Exact domain matches (e.g., `"paywall-site.com"`). Checked via simple string comparison against the article URL's domain
  - `BLOCKED_URL_PATTERNS`: Regex patterns for URL path matching (e.g., `r"medium\.com/.*/membership"`, `r"towardsdatascience\.com/.*/membership"`). Checked via Python's `re.search()`
  - Both lists stored in `config.py` and overridable via `rss_sources.json` `blocked_domains` field
- **Feed health monitoring**: Track consecutive failures per feed in `rss_sources.json`. After 5 consecutive fetch failures (403, timeout, parse error) for any feed, auto-disable that feed (`enabled: false`) and log a warning. User must manually re-enable after investigating

**FR-02: AI Relevance & Credibility Scoring**

- Each article scored 1-10 on 5 equally weighted dimensions via a **single combined Gemini call (L2-12 fix)**:
  1. Real-world deployment applicability
  2. Productization potential
  3. Technical depth
  4. Responsiveness (real-time system capability)
  5. Business impact
- The same call also produces:
  - Credibility score (1-10) based on: citations present, technical specificity, author credibility, data-backed claims, research references
  - Promotional tone detection flag
- Final Score = average of all 5 dimensions. Reject if Final Score < 6.5
- Reject if Credibility < 6. Reject if promotional == true regardless of scores
- **Few-shot calibration (Loophole #23 fix)**: Every scoring prompt must include 2-3 example articles with expected scores to anchor Gemini's judgment. Example articles stored in `prompts/scoring_examples.json`
- All rejected articles logged to `discarded.json` with: URL, title, scores, rejection reason, timestamp
- **Model (L2-17 fix)**: Use model from env var `GEMINI_BULK_MODEL` (default: `gemini-2.0-flash-lite`). Set `max_output_tokens=200` per scoring call. Set `temperature=0` for determinism

**FR-03: Content Summarization**

- Summarize only the top 5 candidates that pass scoring (3 new topics + 2 deepening topics)
- **Anti-hallucination pipeline (Loophole #4 fix)**:
  1. **Step 1 — Extractive phase**: Prompt Gemini to extract exactly 5 key sentences from the article text, including their approximate position. Verify extracted sentences exist in source text using fuzzy string matching (fuzzywuzzy, threshold ≥ 85%)
  2. **Step 2 — Summarization phase**: Prompt Gemini to synthesize a summary using ONLY the verified extracted sentences. Include the instruction: "If you do not have sufficient information from the article to answer, explicitly state 'Information not found in source' rather than speculating"
  3. **Step 3 — Faithfulness check**: Use a second Gemini call to rate faithfulness 1-10 and list any ungrounded claims. If faithfulness < 7, flag summary as "low confidence" in the email and dashboard
- Use Chain-of-Thought prompting in all summarization prompts
- **Model (L2-17 fix)**: Use `GEMINI_BULK_MODEL` env var. Set `max_output_tokens=600` per summary
- Each summary must include: Title, Level (1-5), Why this matters for AI PM, Core mechanism, Product applications, Risk & limitations, Key takeaways, TL;DR (max 2 sentences), Article link, Credibility score, Keywords glossary (only terms not previously encountered — check against `topics.json` history)
- **Summary caching (L2-20 fix)**: Cache key = `SHA256(article_url + extraction_method)`. Different extraction methods produce different cache entries. Do NOT regenerate a summary if one already exists in cache for the same key

**FR-04: Topic Selection Engine**

- Daily selection based on current adaptive mode (from `metrics.json → current_topic_mode`):
  - `normal`: 3 new + 2 deepening = 5 total
  - `reduced_3`: 2 new + 1 deepening = 3 total
  - `reduced_2`: 1 new + 1 deepening = 2 total
  - `minimal`: 1 new + 0 deepening = 1 total
- **Unified mode state machine (L2-07 fix)**: The selection algorithm reads `current_topic_mode` from `metrics.json` and uses the corresponding quota directly. There is NO separate logic for determining topic counts — the mode state machine is the single source of truth
- **Evening carry-over (L2-06 fix)**: Before selecting new articles, check `pipeline_state.json → next_day_priority_queue`. Articles in this queue (scored + summarized from previous evening) are given priority and fill new-topic slots first. Remaining slots are filled from today's morning/midday pipeline output
- **Deepening topic selection priority**: Topics with lowest depth first, then within same depth, topics with lowest mastery score
- **Topic exhaustion handling (Loophole #10 fix)**:
  - If fewer deepening candidates exist than quota, fill remaining slots with additional new topics
  - If fewer new articles pass scoring than quota on a given day, send the email with however many passed (minimum 1 total topic to send email; if 0 topics, skip email and log to `errors.json`)
- **Category balance (Loophole #10 fix)**: Define 5 categories — `ml_engineering`, `product_strategy`, `mlops`, `ai_ethics`, `infrastructure`. Track weekly category distribution in `metrics.json`. If any category has 0 topics for 2 consecutive weeks, bias the next day's selection toward that category (relax scoring threshold to 5.5 for that category)
- **Topic lifecycle (Loophole #10 fix)**:
  - Topics at depth 5 → status changes to `COMPLETED`
  - Topics not accessed for 90 days → status changes to `ARCHIVED`, moved to `archived_topics.json`
  - **Reteaching timeout (L2-14 fix)**: Topics in `reteaching` status for >14 days without a grading attempt → auto-revert to `active` with `retries_used = 0`
  - Status enum: `active | completed | archived | reteaching`

**FR-05: Depth & Mastery Progression System**

- Each topic progresses through depths 1 (introductory) to 5 (expert)
- Advancement requires mastery score ≥ 70% at current depth
- Maximum 2 retries per depth level
- After 2 consecutive failures at the same depth → enter simplified reteaching mode (break the topic into smaller sub-concepts, re-explain at a simpler level, then re-test)
- **Mastery score semantics (L2-15 fix)**: The `mastery_score` field on the topic object always stores the LATEST grading score (whether from an advance, retry, or reteach attempt). For daily mastery averages in `metrics.json`, ALL grading scores from that day contribute to the average, including retries and reteach attempts
- **Adaptive difficulty (Loophole #24 fix + L2-05 + L2-07 unified fix)**:
  - **Canonical mode state machine** (single source of truth):

    | Mode | New Topics | Deepening | Total | Entry Trigger | Exit (Recovery) |
    |------|-----------|-----------|-------|---------------|-----------------|
    | `normal` | 3 | 2 | 5 | Default; OR 3 consecutive recovery days from `reduced_3` | — |
    | `reduced_3` | 2 | 1 | 3 | 5 consecutive low days (avg mastery < 70%) | 3 consecutive days ≥ 75% → `normal` |
    | `reduced_2` | 1 | 1 | 2 | 10 consecutive low days | 3 consecutive days ≥ 75% → `reduced_3` |
    | `minimal` | 1 | 0 | 1 | 15 consecutive low days | 3 consecutive days ≥ 75% → `reduced_2` |

  - **Zero-grading day handling (L2-05 fix)**: Only days where `topics_graded > 0` count toward `consecutive_low_days` and `consecutive_recovery_days`. Days with 0 grading are "neutral" — they neither increment nor reset any counter
  - **Extended pause rule (L2-05 fix)**: If no grading occurs for 7+ consecutive calendar days, enter "pause" state — freeze adaptive counters entirely. Resume counting on next grading day. The pause is logged in `metrics.json → topic_reduction_history`
  - Scale back up: recovery is one step at a time (minimal → reduced_2 → reduced_3 → normal), each requiring 3 consecutive recovery days ≥ 75%
  - Hard floor: never fewer than 1 topic per day

**FR-06: Check Your Understanding (Grading Engine)**

- User submits text answers via the dashboard form for each topic at their current depth
- **Input validation (Loophole #11 fix)**: Reject answers shorter than 50 words with a user-facing message: "Please provide a more detailed answer (minimum 50 words)"
- **Answer deduplication (Loophole #11 fix)**: Hash the answer text (SHA-256). If the same hash was submitted for the same topic+depth combo, return the cached result instead of re-grading. Reject if the same hash is submitted more than 2 times with a message: "Please revise your answer before resubmitting"
- **Grading cache behavior (L2-03 fix)**: On cache hit:
  - Return the cached score, breakdown, and feedback to the user for display
  - Include `"cached": true` flag in the response so the user knows this is a prior result
  - Do NOT apply any state transitions (no depth advancement, no retry increment, no mastery score update)
  - State transitions ONLY occur on fresh Gemini grading calls
  - If the user wants a fresh evaluation, they must modify their answer text
- **Grading rubric** (operationalized with scoring bands):
  - Concept Clarity (30%): 0-7 = vague/wrong; 8-15 = partially correct; 16-23 = clear understanding; 24-30 = exceptional clarity with precise terminology
  - Technical Correctness (30%): 0-7 = factual errors; 8-15 = mostly correct; 16-23 = accurate with good specifics; 24-30 = technically impeccable
  - Application Thinking (20%): 0-5 = no application; 6-10 = generic mention; 11-15 = specific use case; 16-20 = novel, well-reasoned application
  - AI PM Relevance Articulation (20%): 0-5 = no PM angle; 6-10 = surface connection; 11-15 = clear PM implications; 16-20 = strategic PM insight
- **Model (L2-08 + L2-17 fix)**: Use model from env var `GEMINI_GRADE_MODEL` (default: `gemini-2.5-flash`). Set `temperature=0`. Set `max_output_tokens=400`. Before each call, check today's RPD count for this model:
  - If RPD < 90 → use `GEMINI_GRADE_MODEL` as normal
  - If RPD ≥ 90 → fallback to `GEMINI_BULK_MODEL` with quality warning. Set `quality_warning: "Graded with lighter model due to daily rate limit"` in response
- Include 2 example graded answers in the prompt (few-shot) for calibration
- Return: numeric score (0-100), per-dimension breakdown, improvement feedback (2-3 sentences), decision (`advance` / `retry` / `reteach`), `model_used` field, `cached` flag (true/false)
- **Cache**: Key = `SHA256(topic_id + depth + answer_hash)`, TTL = 30 days, max 1,000 entries
- **Model deprecation handling (L2-17 fix)**: If Gemini returns "model not found" or deprecation error:
  1. Log CRITICAL error
  2. Send alert email to user
  3. Fallback to `GEMINI_BULK_MODEL` for this and all subsequent grading calls
  4. Continue operating in degraded mode until user updates `GEMINI_GRADE_MODEL` env var

**FR-07: Daily Email Digest**

- Triggered by external cron at 12:25 PM IST via `GET /api/trigger/email-send`
- Sent via Gmail API to the configured recipient address
- **Email template (Loophole #9 fix)**:
  - Use table-based HTML layout with 100% inline CSS (no `<style>` tags — Gmail strips them)
  - No embedded JavaScript, no forms, no interactive elements
  - Replace "infographic" requirement with text-based progress bars: `[████████░░] 80%`
  - For charts: generate static PNG via matplotlib → upload to Google Drive → set sharing to "anyone with link" → embed as `<img src="drive_public_url">`
  - Include a plain-text fallback version in every email
  - Template must work with 1-5 topics (not fixed at 5) — use Jinja2 loop
- **Email content structure**:
  - Header: "Daily AI Learning Digest" + Date + Overall Progress Summary (topics covered weighted by depth, as percentage toward total coverage)
  - Per topic (1-5 items): Title, Level indicator (depth 1-5), Why this matters for AI PM, Core mechanism, Product applications, Risk & limitations, Key takeaways, TL;DR, Article link, Credibility score, Keywords glossary (new terms only), Faithfulness confidence indicator (if low-confidence flagged)
  - Footer: Current streak count, Average mastery (last 7 days), Weakest category (lowest avg mastery), Topic reduction notice (if active), Current adaptive mode if not `normal`
- **Streak tracking (L2-10 fix)**: Before sending, update streak:
  - `streak_count` = number of consecutive calendar days where `email_sent == true` in `email_cache`
  - Streak breaks if any calendar day has no email sent (0 topics or pipeline failure)
  - Streak does NOT require grading activity — only email delivery
  - Update `streak_count`, `streak_start_date`, and `longest_streak` in `metrics.json` after each send
- **Idempotency (Loophole #25 fix)**: Before sending, check `cache.json → email_cache` for today's date. If an email was already sent today, do not send again. Log the check in pipeline state
- **Spam avoidance**: Add daily unique content (date, streak count, randomized motivational line from a small set) to differentiate each email

**FR-08: Web Dashboard**

- Server-rendered via FastAPI + Jinja2 templates
- **Pages**:
  - `/dashboard` — Main view: learning streak, topic distribution by category (bar chart via Chart.js), average mastery score (line chart over time), depth distribution (how many topics at each depth), weakest competency, current adaptive mode status if not `normal`, recent topics table
  - `/topic/{topic_id}` — Topic detail: full version history (all depth attempts with dates and scores), current summary, link to original article, status badge, retry count, grading form (if status is `active` or `reteaching`)
  - `/discarded` — Discarded insights log: paginated list from `discarded.json` with scores, rejection reasons, dates
  - `/health` — System health: last RSS fetch time per slot, last email sent time, OAuth token validity, daily/monthly token usage, RPD counts per model, error counts last 24h, pipeline state per slot
- **Cold start handling (Loophole #19 fix)**: The first request to a sleeping Render app takes up to 30 seconds. Add a lightweight HTML loading skeleton that renders immediately (no API calls) while the full data loads asynchronously via a JavaScript fetch call
- **Dashboard data authentication (L2-19 fix)**: The `/api/dashboard-data` endpoint accepts EITHER `X-API-Key` header OR valid HTTP Basic Auth credentials. Dashboard JavaScript uses `fetch()` with `credentials: "include"` to send the browser's Basic Auth session cookie — no API key needed in client-side JS
- Charts rendered client-side via Chart.js (loaded from CDN) — not generated server-side
- **Grading form authentication (L2-13 fix)**: The HTML form at `/topic/{topic_id}` submits to `POST /api/grade` using standard form submission with CSRF token. The `/api/grade` endpoint accepts TWO authentication methods:
  - `X-API-Key` header (for programmatic/JS access)
  - Valid HTTP Basic Auth session + valid CSRF token (for browser form submission)
  - If either authentication method passes, the request is authenticated

**FR-09: Quarterly Reports**

- **Trigger (L2-02 fix)**: Auto-generated as part of the morning RSS trigger. On every morning RSS fetch, the system checks if today is January 1, April 1, July 1, or October 1. If yes, generate the quarterly report AFTER RSS processing completes. No separate cron job needed
- **Content**: Topics covered (count + list), Average mastery (overall + per category), Depth progression (how many topics advanced per depth level), Weakest areas (categories with lowest avg mastery), Learning velocity = `topics_advanced_this_quarter / topics_attempted_this_quarter`
- **Storage**: Written to `quarterly_reports_{YYYY}.json`
- No external benchmarking — only compare against the user's own historical data
- Also sent as a special email (reuse email infrastructure)

**FR-10: Scheduling System**

- **Architecture (Loophole #1 fix)**: NO in-process scheduler (no APScheduler). The app is stateless and event-triggered
- **External cron via cron-job.org (L2-02 fix)** — exactly 4 cron jobs (within 5-job free tier limit):

  | Job # | Name | URL | Schedule (IST) | UTC Equivalent |
  |-------|------|-----|----------------|----------------|
  | 1 | RSS Morning | `GET /api/trigger/rss-fetch` | 7:55 AM | 2:25 AM |
  | 2 | RSS Midday | `GET /api/trigger/rss-fetch` | 11:55 AM | 6:25 AM |
  | 3 | RSS Evening | `GET /api/trigger/rss-fetch` | 4:55 PM | 11:25 AM |
  | 4 | Email Send | `GET /api/trigger/email-send` | 12:25 PM | 6:55 AM |

  All jobs: 60-second timeout, 1 retry after 5 minutes, `X-Cron-Secret` header required.

  **1 unused cron-job.org slot** reserved for future use or emergency manual triggers.

- **Morning RSS trigger extras (L2-02 fix)**: The morning RSS trigger (`slot=morning` detected by IST time check) also runs:
  - **Daily cleanup** (before RSS fetching): Cache eviction (expired TTL entries), archive topics inactive >90 days, trim `discarded.json` to 500 entries, trim `errors.json` to 200 entries, revert stale reteaching topics (>14 days per L2-14), update daily mastery averages
  - **Weekly backup** (Sunday only, date-gated): Copy all JSON files to `AI_PM_SYSTEM/backups/{YYYY-MM-DD}/`. Delete backup folders older than 28 days
  - **Quarterly report** (Jan 1, Apr 1, Jul 1, Oct 1, date-gated): Generate quarterly report after RSS processing
- **Trigger endpoint security**: Every trigger endpoint requires an `X-Cron-Secret` header matching an env var `CRON_SECRET`. Return 401 if missing/mismatched
- **Slot detection**: The system determines which slot (morning/midday/evening) is being triggered by checking the current IST time:
  - 6:00 AM - 10:00 AM IST → `morning`
  - 10:00 AM - 2:00 PM IST → `midday`
  - 2:00 PM - 7:00 PM IST → `evening`
  - Outside these windows → reject with "outside scheduled window" (prevents accidental manual triggers from affecting slot tracking)
- **Cold start handling**: cron-job.org's GET request will wake the Render app from sleep. The 30-second cold start means the request may time out on cron-job.org's side, but FastAPI will still process it. Set cron-job.org timeout to 60 seconds. Add retry: if the job fails, cron-job.org retries once after 5 minutes
- **Timezone (Loophole #16 fix)**: All internal timestamps in UTC. Use `zoneinfo.ZoneInfo('Asia/Kolkata')` (Python 3.9+) for IST conversions. cron-job.org supports timezone configuration — set all jobs to IST directly

**FR-11: Google Drive Storage**

- Folder: `AI_PM_SYSTEM/`
- **Files with schemas (Loophole #13 fix)**:
  - `topics.json` — All active topics
  - `archived_topics.json` — Topics at depth 5 or inactive 90+ days
  - `daily_logs_{YYYY_MM}.json` — Monthly partitioned daily pipeline logs (Loophole #2 fix: prevents unbounded file growth)
  - `discarded.json` — Rejected articles (capped at last 500 entries, FIFO eviction)
  - `metrics.json` — Aggregated metrics: daily mastery averages, weekly category distribution, streak counter, adaptive mode state, RPD tracking
  - `quarterly_reports_{YYYY}.json` — Annual partitioned quarterly reports
  - `cache.json` — Grading cache + processed URL hashes + summary cache + email generation cache (max 1,000 entries, TTL-based eviction)
  - `pipeline_state.json` — Current pipeline execution status with per-slot tracking + next-day priority queue
  - `errors.json` — Error log (capped at last 200 entries, FIFO eviction)
  - `system_logs_{YYYY_MM}.json` — Monthly structured logs for debugging
  - `rss_sources.json` — RSS feed configuration (42 feeds across 6 tiers)
- **Schema versioning (Loophole #13 fix)**: Every JSON file starts with `"schema_version": "2.0"`. The app validates schema_version on read and migrates if needed. v2.0 schemas include per-slot pipeline tracking, RPD counters, and next-day queue
- **Write safety with ETag locking (Loophole #2 fix + L2-04 fix)**:
  1. Before every write: validate current file is valid JSON (read + parse). If corrupt, restore from `.backup` file
  2. Before every write: copy current file to `{filename}.backup` on Drive
  3. **Capture ETag/revision** from the read response headers
  4. Write the new file with `If-Match: {etag}` header for optimistic locking
  5. **If 412 Precondition Failed** (ETag mismatch = concurrent write detected): re-read latest version, re-merge changes, retry write (max 3 attempts)
  6. After every write: re-read and validate the written file is valid JSON
  7. Implement in-memory `asyncio.Lock` per-file as local protection (prevents intra-process races)
  8. On Google Drive API 403/429: exponential backoff, max 3 retries, 1s → 2s → 4s delays
- **Weekly backup (Loophole #18 fix + L2-02 fix)**: Every Sunday morning (date-gated inside morning RSS trigger), copy all JSON files to `AI_PM_SYSTEM/backups/{YYYY-MM-DD}/`. Delete backup folders older than 28 days
- **Local fallback (L2-09 fix — accepted risk)**:
  - `/tmp/` on Render is used ONLY for short-term crash recovery (minutes to hours)
  - On every successful Google Drive reconnection, sync ALL `/tmp/` fallback data back to Drive
  - On app startup: check `/tmp/` for orphaned fallback files → sync to Drive before processing new requests
  - Do NOT rely on `/tmp/` for persistent storage. Render restarts will erase it
- Never store full raw article text — only structured summaries

**FR-12: Pipeline State Schema (L2-01 fix)**

```json
{
  "schema_version": "2.0",
  "date": "2026-02-15",
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

**Slot lifecycle**:
- Each slot starts as `PENDING` at the beginning of the day
- When triggered, transitions: `PENDING → FETCHING → SCORING → SUMMARIZING → SELECTING → DONE`
- If any slot fails: that slot goes to `FAILED`, other slots are unaffected
- Email trigger checks: are there ANY topics selected across ANY slot? If yes, proceed with email
- Evening slot: articles selected go into `next_day_priority_queue` (since email already sent). These are consumed by the next morning's selection algorithm

**FR-13: Topic Data Schema**

```json
{
  "schema_version": "2.0",
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
  "credibility_score": 0,
  "faithfulness_score": 0,
  "extraction_method": "trafilatura | readability | newspaper3k | rss_description",
  "created_at": "ISO-8601",
  "last_updated": "ISO-8601",
  "last_active": "ISO-8601",
  "reteaching_entered_at": null,
  "summary": {
    "why_it_matters": "",
    "core_mechanism": "",
    "product_applications": "",
    "risks_limitations": "",
    "key_takeaways": [],
    "tldr": "",
    "keywords_glossary": {}
  },
  "history": [
    {
      "date": "ISO-8601",
      "depth": 1,
      "score": 75,
      "answer_hash": "sha256",
      "decision": "advance | retry | reteach",
      "feedback": "",
      "model_used": "gemini-2.5-flash",
      "cached": false
    }
  ]
}
```

### Non-Functional Requirements

**NFR-01: Cost Control (Loophole #3 fix + L2-12 alignment)**

- Total Gemini API spend must not exceed ₹100/month (~$1.18)
- **Split-model strategy (L2-17 fix — env var based)**:
  - `GEMINI_BULK_MODEL` (default: `gemini-2.0-flash-lite`) for: RSS relevance+credibility scoring, summarization (extract + summarize + faithfulness), title dedup confirmation, reteaching, quarterly reports
  - `GEMINI_GRADE_MODEL` (default: `gemini-2.5-flash`) for: answer grading ONLY (where quality matters most)
- **Model deprecation fallback (L2-17 fix)**: If any model returns "model not found" or deprecation error → log CRITICAL → send alert email → fall back to `GEMINI_BULK_MODEL` for ALL operations → continue in degraded mode. User updates env var to restore
- **Hard token limits on every API call**:
  | Operation | Model (env var) | max_output_tokens | Max Input (truncate to) |
  |-----------|----------------|-------------------|---------------------------------|
  | Combined scoring (relevance + credibility) | BULK | 200 | 1,500 tokens |
  | Title dedup confirmation | BULK | 50 | 200 tokens |
  | Extractive step | BULK | 400 | 2,000 tokens |
  | Summarization | BULK | 600 | 800 tokens (extracted sentences only) |
  | Faithfulness check | BULK | 150 | 1,000 tokens |
  | Grading | GRADE | 400 | 800 tokens |
  | Reteaching | BULK | 500 | 500 tokens |
  | Quarterly report | BULK | 800 | 2,000 tokens |
- **Cost tracker module** (`cost_tracker.py`):
  - Log every API call: timestamp, model, operation, input_tokens, output_tokens, estimated_cost_usd
  - Sum daily and monthly totals
  - **Daily budget**: ₹3.33/day ($0.039). Alert via email if daily spend exceeds ₹3
  - **Monthly kill switch**: If cumulative monthly spend reaches ₹90, disable all non-essential Gemini calls (only grading remains active). At ₹95, disable everything and send alert email
- **Estimated monthly cost breakdown (L2-12 aligned — combined scoring)**:
  | Operation | Model | Monthly Calls | Monthly Input Tokens | Monthly Output Tokens | Monthly Cost |
  |-----------|-------|--------------|---------------------|----------------------|-------------|
  | Combined scoring (relevance + credibility) | flash-lite | ~450 | ~675K | ~90K | $0.078 |
  | Title dedup confirmation (ambiguous zone) | flash-lite | ~30 | ~6K | ~1.5K | $0.001 |
  | Summarization (extract + summarize + faithfulness) | flash-lite | ~450 | ~150K | ~165K | $0.061 |
  | Grading | 2.5-flash | ~30 | ~24K | ~12K | $0.037 |
  | Reteaching + Quarterly | flash-lite | ~5 | ~6K | ~3K | $0.001 |
  | **Total** | | **~965** | **~861K** | **~271.5K** | **~$0.178 (₹15.0)** |
- Note: With 42 feeds (vs 18 in v1.0), input article volume increases ~2.5x but scoring rejects most articles. Estimated ~15 articles/day pass scoring (vs ~8 in v1.0). Cost increase is modest due to token limits
- Significant buffer: ~₹85/month unused, absorbing price changes, feed volume spikes, or heavy grading days
- **RPD tracking (L2-08 fix)**: Track requests-per-day for each model in `pipeline_state.json → daily_rpd`. Reset daily. For `gemini-2.5-flash`: if RPD ≥ 90, all subsequent grading calls fall back to bulk model with quality warning
- **Free tier usage**: Attempt Gemini free tier first (15 RPM, 1,000 RPD for flash-lite; 5 RPM, 100 RPD for 2.5-flash). Fall back to paid tier only if free tier quota is exhausted. Log which tier was used per call

**NFR-02: Security (Loophole #5 fix + L2-13 + L2-19 fixes)**

- **API Key authentication (primary)**: All API endpoints require `X-API-Key` header matching env var `API_KEY`. Return 401 on mismatch. 5-second minimum interval between requests from the same IP for grading endpoints (implemented via `slowapi`)
- **HTTP Basic Auth (secondary)**: Dashboard pages protected by HTTP Basic Auth via FastAPI's `HTTPBasic` dependency. Username + password stored in env vars `DASHBOARD_USER` and `DASHBOARD_PASS`
- **Dual-auth API endpoints (L2-13 + L2-19 fix)**: The following endpoints accept EITHER authentication method:
  - `POST /api/grade`: `X-API-Key` header OR (Basic Auth + CSRF token)
  - `GET /api/dashboard-data`: `X-API-Key` header OR Basic Auth
  - This allows HTML forms to work natively with Basic Auth + CSRF (no JavaScript header injection needed) and allows dashboard JS to use `fetch()` with `credentials: "include"` for Basic Auth session cookies
- **Trigger endpoint security**: Separate `X-Cron-Secret` header for cron trigger endpoints, matching env var `CRON_SECRET`
- **CSRF protection (Loophole #5 fix)**: All form submissions (grading answers) protected via `fastapi-csrf-protect` library using Double Submit Cookie pattern
- **Rate limiting (Loophole #22 fix)**: Via `slowapi` middleware:
  - Dashboard pages: 60 requests/minute per IP
  - Grading submission: 5 requests/minute per IP (5-second interval)
  - Trigger endpoints: 10 requests/minute per IP
  - Health endpoint: 30 requests/minute per IP
- **Environment variables** (stored in Render dashboard, never in code):
  - `GEMINI_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`
  - `API_KEY`, `CRON_SECRET`, `DASHBOARD_USER`, `DASHBOARD_PASS`
  - `RECIPIENT_EMAIL`, `SENDER_EMAIL`
  - `GEMINI_BULK_MODEL`, `GEMINI_GRADE_MODEL` (L2-17 fix)
- **OAuth security (Loophole #6 fix)**:
  - Google OAuth consent screen MUST be set to "Production" status (Testing status expires tokens after 7 days)
  - Store refresh token in Render env var
  - Implement automatic access token refresh using `google-auth` library — refresh proactively 5 minutes before expiry
  - If refresh fails: log error, send alert via a fallback mechanism (write to `errors.json`), retry 3 times with backoff
  - Health endpoint must verify OAuth token validity on every check
- **Input validation**: All user inputs (grading answers, any form fields) validated via Pydantic models. Jinja2 auto-escaping enabled (default). Never use the `|safe` filter on user-provided content
- HTTPS enforced (Render provides TLS by default on `.onrender.com` domains)

**NFR-03: Reliability & Error Handling (Loophole #14, #25 fix + L2-01 + L2-09)**

- **Per-slot pipeline state machine (L2-01 fix)**: Each daily pipeline slot (morning/midday/evening) tracked independently in `pipeline_state.json` (see FR-12 for full schema). A `DONE` or `FAILED` in one slot does not affect other slots
- **Idempotent execution per slot**: If a trigger fires and the current slot is already `DONE`, return 200 with "slot already completed". If status is `FAILED` or `PENDING`, start/restart the slot pipeline
- **Partial success design**: The email template renders 1-5 topics. If only 2 articles pass scoring across all slots, send a 2-topic email. If 0 pass, skip the email and log to errors
- **Retry strategy**: All external API calls (Gemini, Google Drive, Gmail, HTTP fetches) wrapped in try/except with:
  - Max 3 retries
  - Exponential backoff: 1s → 2s → 4s
  - On final failure: log to `errors.json`, continue pipeline with partial data
- **Graceful degradation & /tmp/ fallback (L2-09 fix)**: If Google Drive is unreachable:
  - Use local filesystem (`/tmp/` on Render) as SHORT-TERM fallback only
  - On every successful Drive reconnection, sync ALL `/tmp/` data back to Drive
  - On app startup, check `/tmp/` for orphaned fallback files → sync to Drive before processing requests
  - Accepted risk: Render restarts will erase `/tmp/`. This is crash recovery, not persistent storage
- **Dead letter queue**: Failed operations logged to `errors.json` with enough context to manually retry or debug
- **Startup health check**: On app boot, verify: (1) Google Drive accessible, (2) OAuth token valid, (3) no orphaned `/tmp/` files, (4) `pipeline_state.json` is not corrupt. Log startup status

**NFR-04: Logging & Observability (Loophole #15 fix)**

- Use `loguru` for structured JSON logging
- Log to stdout (Render captures and displays in dashboard) + monthly `system_logs_{YYYY_MM}.json` on Google Drive
- **Mandatory log events**:
  - Every Gemini API call: timestamp, model, operation, input_tokens, output_tokens, cost_estimate, latency_ms, tier_used (free/paid), rpd_count
  - Every Google Drive read/write: timestamp, file, operation, success/failure, latency_ms, etag_used
  - Every RSS fetch: timestamp, source_url, source_tier, articles_found, articles_new, slot
  - Every email send: timestamp, topics_count, success/failure, streak_count
  - Every grading submission: timestamp, topic_id, depth, score, decision, model_used, cached
  - Every error: timestamp, component, error_type, error_message, stack_trace
  - Every slot transition: timestamp, slot, old_status, new_status
  - Every mode transition: timestamp, old_mode, new_mode, trigger_reason
- **Health endpoint** (`GET /health`): Returns JSON:
  ```json
  {
    "status": "healthy | degraded | unhealthy",
    "last_rss_fetch": {
      "morning": "ISO-8601",
      "midday": "ISO-8601",
      "evening": "ISO-8601"
    },
    "last_email_sent": "ISO-8601",
    "oauth_token_valid": true,
    "daily_token_usage": {"input": 11000, "output": 7500, "cost_usd": 0.004},
    "monthly_token_usage": {"input": 330000, "output": 225000, "cost_usd": 0.124},
    "daily_rpd": {"gemini-2.0-flash-lite": 45, "gemini-2.5-flash": 12},
    "errors_last_24h": 2,
    "pipeline_state": {
      "morning": "DONE",
      "midday": "DONE",
      "evening": "PENDING"
    },
    "adaptive_mode": "normal",
    "streak": 15,
    "active_feeds": 42,
    "disabled_feeds": 0
  }
  ```
- **Email alerting**: On critical failures (OAuth token invalid, budget exceeded, 3+ consecutive pipeline failures, model deprecation), send an alert email to the configured recipient using Gmail API

**NFR-05: Data Integrity & Backup (Loophole #2, #18 fix + L2-04)**

- JSON validation before and after every Drive write (parse + verify schema_version)
- **ETag-based optimistic locking (L2-04 fix)**: Every write includes `If-Match: {etag}` header. On 412 → re-read, re-merge, retry (max 3). This prevents cross-instance corruption
- Pre-write backup: copy current file to `{filename}.backup` before overwriting
- Weekly full backup to `AI_PM_SYSTEM/backups/{YYYY-MM-DD}/` (Sunday morning, date-gated inside RSS trigger)
- Leverage Google Drive's built-in file versioning (keeps last 100 versions for non-Google files)
- Monthly file partitioning for unbounded-growth files: `daily_logs_{YYYY_MM}.json`, `system_logs_{YYYY_MM}.json`
- Capped files for bounded collections: `discarded.json` (max 500 entries), `errors.json` (max 200 entries), `cache.json` (max 1,000 entries) — all use FIFO eviction

**NFR-06: Cache Management (Loophole #21 fix + L2-20)**

- **Cache structure** in `cache.json`:
  ```json
  {
    "schema_version": "2.0",
    "processed_urls": {
      "sha256_of_url": {"url": "string", "title": "string", "added_at": "ISO-8601", "ttl_days": 30}
    },
    "grading_cache": {
      "sha256_of_topic_depth_answer": {
        "added_at": "ISO-8601",
        "ttl_days": 30,
        "submission_count": 1,
        "result": {"score": 78, "breakdown": {}, "feedback": "string", "decision": "advance", "model_used": "gemini-2.5-flash"}
      }
    },
    "summary_cache": {
      "sha256_of_url_plus_extraction_method": {
        "added_at": "ISO-8601",
        "ttl_days": 90,
        "extraction_method": "trafilatura",
        "summary": {}
      }
    },
    "email_cache": {
      "YYYY-MM-DD": {"sent": true, "generated_at": "ISO-8601", "topics_count": 5}
    }
  }
  ```
- **Summary cache key (L2-20 fix)**: Key = `SHA256(url + extraction_method)`. Different extraction methods for the same URL produce separate cache entries. This is intentional: different methods may yield meaningfully different text
- **Eviction**: Run cache cleanup during morning RSS trigger's daily cleanup phase. Remove entries past TTL. If total entries exceed 1,000, evict oldest first
- **Cache hit logging**: Log every cache hit/miss for observability

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Daily email delivery rate** | ≥ 95% of days | Count of days email sent / total days system active |
| **Average topics per email** | ≥ 4 of 5 (when in normal mode) | Average topic count across all sent emails in normal mode |
| **Content quality (faithfulness)** | ≥ 8/10 average | Mean faithfulness score across all summaries |
| **Mastery progression rate** | ≥ 60% of topics advance per attempt | Topics that scored ≥ 70% / total grading attempts |
| **Monthly API cost** | ≤ ₹100 ($1.18) | Sum of cost_tracker logs |
| **System uptime (email not missed)** | ≥ 28/30 days per month | Email cache tracking |
| **Dashboard availability** | Response within 60s (including cold start) | Health check monitoring |
| **Category coverage** | All 5 categories represented per 2-week window | Weekly category distribution in metrics.json |
| **Depth 5 completion rate** | ≥ 10 topics reach depth 5 per quarter | Quarterly report data |
| **Zero data corruption incidents** | 0 per quarter | JSON validation + ETag conflict count + backup restore events |
| **Feed availability** | ≥ 40 of 42 feeds active | Disabled feed count in rss_sources.json |
| **Cron job reliability** | All 4 jobs fire successfully ≥ 95% of days | cron-job.org monitoring + pipeline_state.json slot tracking |
| **RPD limit breaches** | 0 hard failures (fallback absorbs all) | RPD tracking logs |

## Constraints

| Constraint | Details |
|------------|---------|
| **Budget** | Strict ₹100/month for Gemini API costs. Hosting/infra must be free tier |
| **Hosting** | Render free tier only — 512 MB RAM, 0.1 vCPU, 750 instance-hours/month, sleeps after 15 min inactivity |
| **Storage** | Google Drive JSON files only — no database, no Supabase, no MongoDB. ETag-based optimistic locking for write safety |
| **AI Model** | Gemini API only — `GEMINI_BULK_MODEL` (default: gemini-2.0-flash-lite) + `GEMINI_GRADE_MODEL` (default: gemini-2.5-flash). Model IDs in env vars for deprecation resilience |
| **Email** | Gmail API only — personal account, <500 sends/day |
| **Users** | Single personal user — no multi-tenancy, no user registration |
| **Authentication** | Dual-auth: API key primary + HTTP Basic Auth secondary. Both accepted on API endpoints for browser compatibility |
| **Frontend** | Server-rendered Jinja2 only — no React/Vue/SPA frameworks |
| **Content** | Free-access articles only — no paywalls, no scraping behind login |
| **Scheduling** | External cron only (cron-job.org, exactly 4 jobs) — no in-process APScheduler. 1 slot reserved |
| **Code** | Python + FastAPI only — no other languages or frameworks |
| **Data ownership** | All data stored in user's own Google Drive — full ownership and portability |
| **RSS Sources** | 42 validated feeds across 6 tiers. Configurable via `rss_sources.json` — user can add/remove/disable feeds without code changes |

## Open Questions

| # | Question | Impact | Default Assumption |
|---|----------|--------|--------------------|
| 1 | Should the system handle RSS feeds that change URLs (e.g., feed URL rotation)? | Medium — could miss content | No — static feed URLs. User manually updates `rss_sources.json` if a feed URL changes. Feed health monitoring (5 consecutive failures → auto-disable) mitigates silent breakage |
| 2 | What is the exact Gemini free tier quota as of deployment date? Google has changed this multiple times | High — affects whether the system costs ₹0 or ₹15/month | Assume 1,000 RPD free tier for flash-lite, 100 RPD for 2.5-flash. Build paid tier fallback regardless. RPD tracking provides visibility |
| 3 | Should archived topics (depth 5) ever be resurfaced for "refresher" testing? | Low — nice to have | No — once completed, topics are done. Consider for v3 |
| 4 | How should the system handle Google Drive API outages lasting >1 hour? | Medium — pipeline stalls | Write to local `/tmp/`, queue for Drive sync. Alert via email. Pipeline continues with local state. Accepted risk: Render restart erases `/tmp/` |
| 5 | Should the quarterly report include topic-level granularity or only category-level summaries? | Low — user preference | Category-level summaries in email. Topic-level detail accessible on dashboard |
| 6 | If cron-job.org goes down or changes free tier, what is the backup scheduler? | Medium — pipeline stops | Document fallback: GitHub Actions cron (free, 5 min resolution) or UptimeRobot (free, 5 min intervals) |
| 7 | How should the arXiv volume filter be tuned? 100+ papers/day is significant | Medium — could waste scoring tokens or miss important papers | Pre-filter by title keywords, cap at 10 per fetch cycle, +1 scoring bonus for academic tier. Tune keywords based on first 2 weeks of operation |
| 8 | Should the Anthropic community feed be treated differently since it's not official? | Low — feed could break without notice | Monitor separately. If community feed fails 5 times, auto-disable like any other feed. Document the dependency |
| 9 | With 42 feeds, will the morning RSS trigger + cleanup + backup + quarterly fit within Render's timeout? | Medium — could timeout on cold start | Implement progressive timeout: RSS fetching continues in background after returning 200 to cron-job.org. Use FastAPI `BackgroundTasks` for long-running operations after acknowledging the trigger |
| 10 | Should there be a mechanism to dynamically adjust the title dedup ambiguous zone (60-85%) based on false positive/negative rates? | Low — optimization | No — keep static thresholds in v2.0. Log all dedup decisions for manual review. Consider auto-tuning in v3 |

---
*Generated via @prd brainstorm agent — PRD v2.0*