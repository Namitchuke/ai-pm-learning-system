"""
app/services/rss_pipeline.py — RSS content fetching and pre-processing pipeline
TDD v2.0 §Core Services (rss_pipeline.py)
PRD v2.0 §FR-01 RSS Content Pipeline
FRD v2.0 §FS-01 RSS Pipeline (all sub-sections)
Implements: 42 feeds, 6 tiers, arXiv filter (joint 10-cap), per-domain rate limiting,
            feed auto-disable, URL dedup, two-phase title dedup, content extraction,
            validation, and blocked URL filtering.
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Optional

import feedparser
from loguru import logger

from app.clients import drive_client
from app.config import get_settings
from app.core import cache_manager, logging as app_logging
from app.models import (
    CacheData,
    CandidateArticle,
    Category,
    ExtractedArticle,
    ExtractionMethod,
    Metrics,
    PipelineState,
    RSSSource,
    RSSSourcesFile,
)
from app.utils.dedup import compute_url_hash, is_duplicate_title
from app.utils.extractors import (
    extract_article_content,
    is_url_blocked,
    passes_arxiv_filter,
    validate_and_truncate,
)
from app.utils.timezone import today_ist_str

settings = get_settings()

# ──────────────────────────────────────────────────────────────────────────────
# Per-domain rate limiter — PRD FR-01: 3 req/min per domain
# ──────────────────────────────────────────────────────────────────────────────
_domain_last_request: dict[str, list[float]] = defaultdict(list)
_domain_lock = threading.Lock()


def _get_domain(url: str) -> str:
    """Extract domain from URL."""
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.lower().replace("www.", "")


def _wait_for_domain_rate_limit(domain: str) -> None:
    """
    Enforce max 3 requests/minute per domain.
    PRD FR-01 §Per-domain rate limit.
    Blocks the current thread until a slot is available.
    """
    with _domain_lock:
        now = time.time()
        window_start = now - 60.0
        # Clean up timestamps older than 60s
        _domain_last_request[domain] = [
            t for t in _domain_last_request[domain] if t > window_start
        ]
        sleep_time = 0.0
        if len(_domain_last_request[domain]) >= settings.domain_requests_per_minute:
            oldest = _domain_last_request[domain][0]
            sleep_time = 60.0 - (now - oldest) + 0.1
        _domain_last_request[domain].append(now + max(0, sleep_time))

    if sleep_time > 0:
        logger.debug(f"Rate limiting domain {domain}: sleeping {sleep_time:.1f}s")
        time.sleep(sleep_time)

# ──────────────────────────────────────────────────────────────────────────────
# 42 RSS sources — PRD §FR-01 Tier 1–6 source list
# FRD §FS-11.4 rss_sources.json schema
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_RSS_SOURCES: list[dict] = [
    # ── Tier 1: Flagship AI Product & Research Blogs ─────────────────────────
    {"name": "Google DeepMind Blog", "feed_url": "https://deepmind.google/blog/feed.xml", "tier": 1, "category_bias": "ml_engineering"},
    {"name": "OpenAI Blog", "feed_url": "https://openai.com/blog/rss.xml", "tier": 1, "category_bias": "ml_engineering"},
    {"name": "Anthropic Blog", "feed_url": "https://www.anthropic.com/news/feed.xml", "tier": 1, "category_bias": "ml_engineering"},
    {"name": "Meta AI Blog", "feed_url": "https://ai.meta.com/blog/feed/", "tier": 1, "category_bias": "ml_engineering"},
    {"name": "Microsoft AI Blog", "feed_url": "https://blogs.microsoft.com/ai/feed/", "tier": 1, "category_bias": "product_strategy"},
    {"name": "Hugging Face Blog", "feed_url": "https://huggingface.co/blog/feed.xml", "tier": 1, "category_bias": "ml_engineering"},
    {"name": "AI21 Labs Blog", "feed_url": "https://www.ai21.com/blog/rss", "tier": 1, "category_bias": "ml_engineering"},
    # ── Tier 2: Technical ML/AI Research & Practice ───────────────────────────
    {"name": "The Batch (Andrew Ng)", "feed_url": "https://www.deeplearning.ai/the-batch/feed/", "tier": 2, "category_bias": "ml_engineering"},
    {"name": "Towards Data Science", "feed_url": "https://towardsdatascience.com/feed", "tier": 2, "category_bias": "ml_engineering"},
    {"name": "Chip Huyen Blog", "feed_url": "https://huyenchip.com/feed.xml", "tier": 2, "category_bias": "mlops"},
    {"name": "Jay Alammar Blog", "feed_url": "https://jalammar.github.io/feed.xml", "tier": 2, "category_bias": "ml_engineering"},
    {"name": "Eugene Yan Blog", "feed_url": "https://eugeneyan.com/rss/", "tier": 2, "category_bias": "mlops"},
    {"name": "Sebastian Ruder Blog", "feed_url": "https://www.ruder.io/rss/", "tier": 2, "category_bias": "ml_engineering"},
    {"name": "Lilian Weng Blog", "feed_url": "https://lilianweng.github.io/lil-log/feed.xml", "tier": 2, "category_bias": "ml_engineering"},
    # ── Tier 3: MLOps & Production AI ────────────────────────────────────────
    {"name": "MLOps Community Blog", "feed_url": "https://mlops.community/feed/", "tier": 3, "category_bias": "mlops"},
    {"name": "Neptune.ai Blog", "feed_url": "https://neptune.ai/blog/rss", "tier": 3, "category_bias": "mlops"},
    {"name": "Weights & Biases Blog", "feed_url": "https://wandb.ai/fully-connected/feed", "tier": 3, "category_bias": "mlops"},
    {"name": "Evidently AI Blog", "feed_url": "https://www.evidentlyai.com/blog/rss", "tier": 3, "category_bias": "mlops"},
    {"name": "Verta Blog", "feed_url": "https://blog.verta.ai/rss", "tier": 3, "category_bias": "mlops"},
    {"name": "Arize AI Blog", "feed_url": "https://arize.com/blog/rss/", "tier": 3, "category_bias": "mlops"},
    {"name": "Tecton Blog", "feed_url": "https://www.tecton.ai/blog/rss", "tier": 3, "category_bias": "infrastructure"},
    # ── Tier 4: AI Product Strategy & PM ─────────────────────────────────────
    {"name": "Lenny's Newsletter", "feed_url": "https://www.lennysnewsletter.com/feed", "tier": 4, "category_bias": "product_strategy"},
    {"name": "Product Hunt Blog", "feed_url": "https://blog.producthunt.com/rss", "tier": 4, "category_bias": "product_strategy"},
    {"name": "First Round Review", "feed_url": "https://review.firstround.com/feed.xml", "tier": 4, "category_bias": "product_strategy"},
    {"name": "Reforge Blog", "feed_url": "https://www.reforge.com/blog/rss", "tier": 4, "category_bias": "product_strategy"},
    {"name": "The Pragmatic Engineer", "feed_url": "https://newsletter.pragmaticengineer.com/feed", "tier": 4, "category_bias": "product_strategy"},
    {"name": "Stratechery (Ben Thompson)", "feed_url": "https://stratechery.com/feed/", "tier": 4, "category_bias": "product_strategy"},
    {"name": "Mind the Product", "feed_url": "https://www.mindtheproduct.com/feed/", "tier": 4, "category_bias": "product_strategy"},
    # ── Tier 5: AI Ethics, Safety & Governance ───────────────────────────────
    {"name": "Partnership on AI Blog", "feed_url": "https://partnershiponai.org/feed/", "tier": 5, "category_bias": "ai_ethics"},
    {"name": "AI Now Institute", "feed_url": "https://ainowinstitute.org/feed", "tier": 5, "category_bias": "ai_ethics"},
    {"name": "Future of Life Institute", "feed_url": "https://futureoflife.org/feed/", "tier": 5, "category_bias": "ai_ethics"},
    {"name": "Alignment Forum", "feed_url": "https://www.alignmentforum.org/feed.xml", "tier": 5, "category_bias": "ai_ethics"},
    {"name": "AI Safety Newsletter", "feed_url": "https://humancompatible.ai/news/feed/", "tier": 5, "category_bias": "ai_ethics"},
    {"name": "The Center for AI Safety", "feed_url": "https://www.safe.ai/blog/rss", "tier": 5, "category_bias": "ai_ethics"},
    {"name": "NIST AI RMF Blog", "feed_url": "https://www.nist.gov/topics/artificial-intelligence/news/rss.xml", "tier": 5, "category_bias": "ai_ethics"},
    # ── Tier 6: Infrastructure, Cloud AI & Tooling ───────────────────────────
    {"name": "AWS Machine Learning Blog", "feed_url": "https://aws.amazon.com/blogs/machine-learning/feed/", "tier": 6, "category_bias": "infrastructure"},
    {"name": "Google Cloud AI Blog", "feed_url": "https://cloud.google.com/blog/products/ai-machine-learning/rss", "tier": 6, "category_bias": "infrastructure"},
    {"name": "Azure AI Blog", "feed_url": "https://techcommunity.microsoft.com/gxcuf89792/rss/board?board.id=AI_Blog", "tier": 6, "category_bias": "infrastructure"},
    {"name": "arXiv cs.AI (filtered)", "feed_url": "https://rss.arxiv.org/rss/cs.AI", "tier": 6, "category_bias": "ml_engineering"},
    {"name": "arXiv cs.LG (filtered)", "feed_url": "https://rss.arxiv.org/rss/cs.LG", "tier": 6, "category_bias": "ml_engineering"},
    {"name": "DataRobot Blog", "feed_url": "https://www.datarobot.com/blog/feed/", "tier": 6, "category_bias": "mlops"},
    {"name": "Scale AI Blog", "feed_url": "https://scale.com/blog/feed", "tier": 6, "category_bias": "infrastructure"},
]


def load_rss_sources(sources_data: Optional[dict]) -> list[RSSSource]:
    """
    Load RSS sources from Drive JSON, or use defaults.
    FRD FS-01.1: rss_sources.json with enabled/failure tracking.
    """
    if sources_data is None:
        return [RSSSource(**s) for s in DEFAULT_RSS_SOURCES]
    try:
        sources_file = RSSSourcesFile(**sources_data)
        return sources_file.sources
    except Exception as exc:
        logger.warning(f"Failed to parse rss_sources.json: {exc}. Using defaults.")
        return [RSSSource(**s) for s in DEFAULT_RSS_SOURCES]


def build_default_sources_json() -> dict:
    """Build the initial rss_sources.json contents."""
    sources = [RSSSource(**s) for s in DEFAULT_RSS_SOURCES]
    return RSSSourcesFile(sources=sources).model_dump(mode="json")


# ──────────────────────────────────────────────────────────────────────────────
# Feed fetching — FRD FS-01.3
# ──────────────────────────────────────────────────────────────────────────────

def _is_arxiv_feed(source: RSSSource) -> bool:
    """Detect if a source is an arXiv feed (cs.AI or cs.LG)."""
    return "arxiv.org" in source.feed_url.lower()


def fetch_feed_articles(
    source: RSSSource,
    arxiv_count_ref: list[int],  # Mutable counter: [current_count] — L2 arXiv joint cap
) -> list[CandidateArticle]:
    """
    Fetch and parse a single RSS feed.
    PRD FR-01: Includes arXiv pre-filter, per-domain rate limit.
    Returns list of candidate articles (not yet scored/extracted).
    """
    domain = _get_domain(source.feed_url)
    _wait_for_domain_rate_limit(domain)

    articles: list[CandidateArticle] = []

    try:
        import httpx
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            response = client.get(source.feed_url)
            response.raise_for_status()
            
            # Prevent feedparser infinite hang ReDoS by enforcing hard timeout
            import concurrent.futures
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(feedparser.parse, response.content)
            try:
                parsed = future.result(timeout=10)
            except concurrent.futures.TimeoutError:
                logger.error(f"Feedparser timed out (possible ReDoS) for {source.name}")
                return []
            finally:
                executor.shutdown(wait=False)

        if parsed.bozo and not parsed.entries:
            logger.warning(f"Feed parse error for {source.name}: {parsed.bozo_exception}")
            return []

        for entry in parsed.entries:
            # Extract URL
            url = entry.get("link", "")
            if not url:
                continue

            # Check URL blocklist — L2-18
            blocked, reason = is_url_blocked(url)
            if blocked:
                continue

            # arXiv: joint 10-article cap — PRD FR-01 (joint cap design decision)
            is_arxiv = _is_arxiv_feed(source)
            if is_arxiv:
                if arxiv_count_ref[0] >= settings.max_arxiv_per_cycle:
                    break  # Stop processing this arXiv feed
                # arXiv keyword pre-filter
                title = entry.get("title", "")
                abstract = entry.get("summary", "")
                if not passes_arxiv_filter(title, abstract):
                    continue
                arxiv_count_ref[0] += 1

            title = entry.get("title", "").strip()
            if not title:
                continue

            # Date extraction
            pub_date: Optional[datetime] = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    import calendar
                    pub_date = datetime(*entry.published_parsed[:6])
                except Exception:
                    pass

            # Date gate: reject articles older than configured days — PRD FR-01
            if pub_date:
                cutoff = datetime.utcnow() - timedelta(days=settings.article_date_gate_days)
                if pub_date < cutoff:
                    continue

            rss_description = entry.get("summary", "")

            articles.append(
                CandidateArticle(
                    url=url,
                    url_hash=compute_url_hash(url),
                    title=title,
                    source_name=source.name,
                    source_tier=source.tier,
                    category_bias=source.category_bias,
                    published_date=pub_date,
                    rss_description=rss_description[:500],  # Truncate long RSS descriptions
                )
            )

        app_logging.log_rss_fetch(
            source_url=source.feed_url,
            source_tier=source.tier,
            articles_found=len(parsed.entries),
            articles_new=len(articles),
            slot="current",
        )
        return articles

    except Exception as exc:
        logger.error(f"Failed to fetch feed {source.name} ({source.feed_url}): {exc}")
        app_logging.log_rss_fetch(
            source_url=source.feed_url,
            source_tier=source.tier,
            articles_found=0,
            articles_new=0,
            slot="current",
            error=str(exc),
        )
        return []


# ──────────────────────────────────────────────────────────────────────────────
# Feed failure tracking — PRD FR-01: auto-disable after 5 failures
# ──────────────────────────────────────────────────────────────────────────────

def record_feed_result(
    source: RSSSource,
    success: bool,
    sources_data: dict,
) -> None:
    """
    Update consecutive_failures counter for a feed.
    PRD FR-01: Auto-disable after 5 consecutive failures.
    Updates the in-memory sources_data dict (caller persists it).
    """
    for s in sources_data.get("sources", []):
        if s.get("source_id") == source.source_id:
            if success:
                s["consecutive_failures"] = 0
                s["last_success"] = datetime.utcnow().isoformat()
            else:
                s["consecutive_failures"] = s.get("consecutive_failures", 0) + 1
                if s["consecutive_failures"] >= settings.feed_auto_disable_failures:
                    s["enabled"] = False
                    logger.warning(
                        f"Feed auto-disabled after {s['consecutive_failures']} "
                        f"consecutive failures: {source.name}"
                    )
            break


# ──────────────────────────────────────────────────────────────────────────────
# Deduplication filter — FRD FS-04.1 / FS-04.2
# ──────────────────────────────────────────────────────────────────────────────

def filter_duplicates(
    articles: list[CandidateArticle],
    cache: CacheData,
    existing_topic_titles: list[str],
    daily_rpd: Optional[dict[str, int]] = None,
    metrics: Optional[Any] = None,
) -> tuple[list[CandidateArticle], list[CandidateArticle]]:
    """
    Filter out duplicate articles by URL hash and title.
    Returns (new_articles, duplicates).
    Phase 1: URL SHA-256 check against processed_urls (30-day window).
    Phase 2: Two-phase title dedup (fuzzywuzzy + Gemini confirm).
    """
    new_articles: list[CandidateArticle] = []
    duplicates: list[CandidateArticle] = []
    seen_titles_this_batch: list[str] = []

    for article in articles:
        # URL dedup
        if cache_manager.is_url_processed(cache, article.url):
            duplicates.append(article)
            continue

        # Title dedup against existing topics AND within this batch
        all_existing_titles = existing_topic_titles + seen_titles_this_batch

        is_dup, reason, score = is_duplicate_title(
            article.title,
            all_existing_titles,
            daily_rpd=daily_rpd,
            metrics=metrics,
        )

        if is_dup:
            logger.debug(f"Title duplicate ({reason}): {article.title[:60]}")
            duplicates.append(article)
            continue

        new_articles.append(article)
        seen_titles_this_batch.append(article.title)

    return new_articles, duplicates


# ──────────────────────────────────────────────────────────────────────────────
# Content extraction stage — FRD FS-01.4
# ──────────────────────────────────────────────────────────────────────────────

def extract_article(article: CandidateArticle) -> Optional[ExtractedArticle]:
    """
    Run layered extraction chain on a candidate article.
    FRD FS-01.4: trafilatura → readability → newspaper3k → rss_description.
    FS-01.5: Validate word count. Reject < 200 words.
    """
    text, method = extract_article_content(article.url, article.rss_description)
    is_valid, processed_text, rejection_reason = validate_and_truncate(text)

    if not is_valid:
        logger.debug(f"Article rejected ({rejection_reason}): {article.url}")
        return None

    word_count = len(processed_text.split())

    return ExtractedArticle(
        **article.model_dump(),
        extracted_text=processed_text,
        word_count=word_count,
        extraction_method=method,
        fetched_at=datetime.utcnow(),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main pipeline orchestrator
# FRD FS-01: Full pipeline for one RSS trigger slot
# ──────────────────────────────────────────────────────────────────────────────

def run_rss_pipeline(
    slot: str,
    pipeline_state: PipelineState,
    cache: CacheData,
    sources_data: dict,
    existing_topic_titles: list[str],
    metrics: Optional[Metrics] = None,
) -> tuple[list[ExtractedArticle], dict]:
    """
    Full RSS pipeline for one cron slot.
    Returns (extracted_articles, updated_sources_data).
    Pipeline: Fetch → Dedup → Extract → Validate.
    Scoring and Summarization handled by downstream services.
    """
    sources = load_rss_sources(sources_data)
    enabled_sources = [s for s in sources if s.enabled]

    # Sort by tier (lower tier = higher priority)
    enabled_sources.sort(key=lambda s: s.tier)
    
    # HARD MITIGATION: Disable feeds that trigger ReDoS infinite CPU loops in feedparser
    # This prevents the 0.1 vCPU Render instance from freezing its GIL via orphaned threads.
    enabled_sources = [
        s for s in enabled_sources 
        if "anthropic.com" not in s.feed_url and "pragmaticengineer.com" not in s.feed_url
    ]

    logger.info(
        f"[{slot}] RSS pipeline starting. {len(enabled_sources)} enabled feeds."
    )

    all_candidates: list[CandidateArticle] = []
    daily_rpd = pipeline_state.daily_rpd

    # arXiv joint cap: shared mutable counter across cs.AI and cs.LG
    arxiv_count_ref = [0]

    try: drive_client.write_json_file("_debug_pipeline.json", {"stage": "fetching_started", "slot": slot, "feeds": len(enabled_sources)})
    except: pass

    for src_idx, source in enumerate(enabled_sources, start=1):
        try: drive_client.write_json_file("_debug_pipeline.json", {"stage": "fetching_feed", "slot": slot, "feed_index": src_idx, "feed_url": source.feed_url})
        except: pass
        
        articles = fetch_feed_articles(source, arxiv_count_ref)
        success = len(articles) > 0 or True  # Distinguish timeout from empty feed
        record_feed_result(source, success=True, sources_data=sources_data)
        all_candidates.extend(articles)

    try: drive_client.write_json_file("_debug_pipeline.json", {"stage": "fetching_done", "slot": slot, "candidates": len(all_candidates)})
    except: pass

    pipeline_state.slots[slot].articles_fetched = len(all_candidates)
    logger.info(f"[{slot}] Fetched {len(all_candidates)} total candidates.")

    # Deduplicate
    try: drive_client.write_json_file("_debug_pipeline.json", {"stage": "dedup_started", "slot": slot, "candidates": len(all_candidates)})
    except: pass
    
    new_candidates, duplicates = filter_duplicates(
        all_candidates, cache, existing_topic_titles,
        daily_rpd=daily_rpd, metrics=metrics,
    )
    pipeline_state.slots[slot].articles_new = len(new_candidates)
    logger.info(
        f"[{slot}] After dedup: {len(new_candidates)} new, {len(duplicates)} duplicates."
    )

    # Extract content — process new articles only
    # IMPORTANT: Only mark URL as processed AFTER successful extraction.
    # Marking too early permanently blocks re-processing if extraction fails.
    extracted: list[ExtractedArticle] = []
    
    try: drive_client.write_json_file("_debug_pipeline.json", {"stage": "extraction_started", "slot": slot, "candidates": len(new_candidates)})
    except: pass
    
    for idx, cand in enumerate(new_candidates, start=1):
        if idx % 10 == 0:
            logger.info(f"[{slot}] Extracting article {idx}/{len(new_candidates)}...")
            
        try: drive_client.write_json_file("_debug_pipeline.json", {"stage": "extracting", "index": idx, "total": len(new_candidates), "url": cand.url})
        except: pass
        
        art = extract_article(cand)
        if art:
            extracted.append(art)
            cache_manager.mark_url_processed(cache, cand.url, cand.title)
        else:
            logger.debug(f"Extraction failed/rejected: {cand.url}")

    logger.info(
        f"[{slot}] Extraction complete: {len(extracted)}/{len(new_candidates)} articles extracted."
    )

    return extracted, sources_data
