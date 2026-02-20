"""
app/core/cache_manager.py — In-memory cache coordinator
TDD v2.0 §Cache Manager
PRD v2.0 §NFR-06 Cache Management (Loophole #21 fix + L2-20)
FRD v2.0 §FS-03.4 Summary Caching, FS-06.2 Grading Cache
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any, Optional

from app.models import (
    CacheData,
    EmailCacheEntry,
    GradingCacheEntry,
    GradingCacheResult,
    GradingDecision,
    ProcessedURLEntry,
    SummaryCacheEntry,
    TopicSummary,
    ExtractionMethod,
)
from app.config import get_settings

settings = get_settings()


# ──────────────────────────────────────────────────────────────────────────────
# Hash utilities
# ──────────────────────────────────────────────────────────────────────────────

def hash_url(url: str) -> str:
    """SHA-256 hash of URL for processed_urls dedup. PRD FR-01."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def hash_summary_key(url: str, extraction_method: str) -> str:
    """
    SHA-256 cache key for summary cache.
    L2-20 fix: Key includes extraction_method so different methods
    produce separate cache entries.
    FRD FS-03.4: cache_key = SHA256(url + extraction_method)
    """
    combined = f"{url}|{extraction_method}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def hash_grading_key(topic_id: str, depth: int, answer_text: str) -> str:
    """
    SHA-256 cache key for grading cache.
    FRD FS-06.1: Key = SHA256(topic_id + depth + answer_hash)
    """
    answer_hash = hashlib.sha256(
        answer_text.strip().lower().encode("utf-8")
    ).hexdigest()
    combined = f"{topic_id}:{depth}:{answer_hash}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def hash_answer(answer_text: str) -> str:
    """SHA-256 hash of normalized answer text for dedup check."""
    return hashlib.sha256(
        answer_text.strip().lower().encode("utf-8")
    ).hexdigest()


# ──────────────────────────────────────────────────────────────────────────────
# TTL helpers
# ──────────────────────────────────────────────────────────────────────────────

def is_expired(added_at: datetime, ttl_days: int) -> bool:
    """Return True if the cache entry has passed its TTL."""
    return datetime.utcnow() > added_at + timedelta(days=ttl_days)


# ──────────────────────────────────────────────────────────────────────────────
# Processed URL cache — PRD FR-01 / FRD FS-01.3
# ──────────────────────────────────────────────────────────────────────────────

def is_url_processed(cache: CacheData, url: str) -> bool:
    """
    Check if URL was processed within the last 30 days.
    PRD FR-01: skip if URL hash found and added_at within 30 days.
    """
    url_hash = hash_url(url)
    entry = cache.processed_urls.get(url_hash)
    if entry is None:
        return False
    if is_expired(entry.added_at, entry.ttl_days):
        # Remove expired (will be cleaned up in batch)
        del cache.processed_urls[url_hash]
        return False
    return True


def mark_url_processed(cache: CacheData, url: str, title: str) -> None:
    """Add URL to processed_urls cache."""
    url_hash = hash_url(url)
    cache.processed_urls[url_hash] = ProcessedURLEntry(
        url=url,
        title=title,
        added_at=datetime.utcnow(),
        ttl_days=settings.url_dedup_ttl_days,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Summary cache — L2-20 fix: key = SHA256(url + extraction_method)
# ──────────────────────────────────────────────────────────────────────────────

def get_cached_summary(
    cache: CacheData,
    url: str,
    extraction_method: str,
) -> Optional[TopicSummary]:
    """
    Retrieve cached summary if present and not expired.
    L2-20 fix: Different extraction methods produce separate cache entries.
    """
    key = hash_summary_key(url, extraction_method)
    entry = cache.summary_cache.get(key)
    if entry is None:
        return None
    if is_expired(entry.added_at, entry.ttl_days):
        del cache.summary_cache[key]
        return None
    return entry.summary


def set_cached_summary(
    cache: CacheData,
    url: str,
    extraction_method: str,
    summary: TopicSummary,
) -> None:
    """Store a summary in the cache with TTL."""
    key = hash_summary_key(url, extraction_method)
    cache.summary_cache[key] = SummaryCacheEntry(
        added_at=datetime.utcnow(),
        ttl_days=settings.summary_cache_ttl_days,
        extraction_method=ExtractionMethod(extraction_method),
        summary=summary,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Grading cache — L2-03 fix: display-only, no state transitions on hit
# ──────────────────────────────────────────────────────────────────────────────

def get_cached_grade(
    cache: CacheData,
    topic_id: str,
    depth: int,
    answer_text: str,
) -> Optional[GradingCacheEntry]:
    """
    Check grading cache. Returns entry if found and not expired.
    L2-03 fix: Cached results are display-only. Caller must NOT apply
    state transitions (depth advance, retry increment) on cache hit.
    FRD FS-06.2.
    """
    key = hash_grading_key(topic_id, depth, answer_text)
    entry = cache.grading_cache.get(key)
    if entry is None:
        return None
    if is_expired(entry.added_at, entry.ttl_days):
        del cache.grading_cache[key]
        return None
    return entry


def set_cached_grade(
    cache: CacheData,
    topic_id: str,
    depth: int,
    answer_text: str,
    score: float,
    breakdown: dict[str, float],
    feedback: str,
    decision: str,
    model_used: str,
) -> GradingCacheEntry:
    """Store a grading result in cache. Returns the new entry."""
    key = hash_grading_key(topic_id, depth, answer_text)

    existing = cache.grading_cache.get(key)
    submission_count = (existing.submission_count + 1) if existing else 1

    entry = GradingCacheEntry(
        added_at=datetime.utcnow(),
        ttl_days=settings.grading_cache_ttl_days,
        submission_count=submission_count,
        result=GradingCacheResult(
            score=score,
            breakdown=breakdown,
            feedback=feedback,
            decision=GradingDecision(decision),
            model_used=model_used,
        ),
    )
    cache.grading_cache[key] = entry
    return entry


def get_answer_submission_count(
    cache: CacheData,
    topic_id: str,
    depth: int,
    answer_text: str,
) -> int:
    """
    Return how many times this exact answer was submitted for this topic+depth.
    FRD FS-06.1: Reject if same hash submitted ≥ 3 times.
    Note: FRD §BR-05c says reject at 3+ times.
    """
    entry = get_cached_grade(cache, topic_id, depth, answer_text)
    if entry is None:
        return 0
    return entry.submission_count


# ──────────────────────────────────────────────────────────────────────────────
# Email cache — L2-10 fix: streak + idempotency
# ──────────────────────────────────────────────────────────────────────────────

def is_email_sent_today(cache: CacheData, date_str: str) -> bool:
    """
    Check if email was already sent today for idempotency.
    PRD FR-07 / L2-10 / Loophole #25 fix: Do not send email twice.
    """
    entry = cache.email_cache.get(date_str)
    return entry is not None and entry.sent


def mark_email_sent(cache: CacheData, date_str: str, topics_count: int) -> None:
    """Record that today's email was sent in the cache."""
    cache.email_cache[date_str] = EmailCacheEntry(
        sent=True,
        generated_at=datetime.utcnow(),
        topics_count=topics_count,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Cache eviction — PRD NFR-06 / FRD FS-12.4
# Run during morning cleanup (FRD FS-10.2)
# ──────────────────────────────────────────────────────────────────────────────

def evict_expired_cache(cache: CacheData) -> dict[str, int]:
    """
    Remove all expired entries from all cache sections.
    If total entries exceed max_cache_entries, evict oldest first (FIFO).
    PRD NFR-06: Eviction runs during morning RSS trigger daily cleanup.
    Returns dict of how many entries were removed per section.
    """
    removed: dict[str, int] = {
        "processed_urls": 0,
        "grading_cache": 0,
        "summary_cache": 0,
        "email_cache": 0,
    }

    # Evict expired processed_urls
    expired_urls = [
        k for k, v in cache.processed_urls.items()
        if is_expired(v.added_at, v.ttl_days)
    ]
    for k in expired_urls:
        del cache.processed_urls[k]
    removed["processed_urls"] = len(expired_urls)

    # Evict expired grading_cache
    expired_grades = [
        k for k, v in cache.grading_cache.items()
        if is_expired(v.added_at, v.ttl_days)
    ]
    for k in expired_grades:
        del cache.grading_cache[k]
    removed["grading_cache"] = len(expired_grades)

    # Evict expired summary_cache
    expired_summaries = [
        k for k, v in cache.summary_cache.items()
        if is_expired(v.added_at, v.ttl_days)
    ]
    for k in expired_summaries:
        del cache.summary_cache[k]
    removed["summary_cache"] = len(expired_summaries)

    # Enforce total entry cap
    total_entries = (
        len(cache.processed_urls)
        + len(cache.grading_cache)
        + len(cache.summary_cache)
    )
    if total_entries > settings.max_cache_entries:
        # Evict oldest grading cache entries (FIFO)
        overage = total_entries - settings.max_cache_entries
        sorted_keys = sorted(
            cache.grading_cache.keys(),
            key=lambda k: cache.grading_cache[k].added_at,
        )
        for k in sorted_keys[:overage]:
            del cache.grading_cache[k]
            removed["grading_cache"] += 1

    cache.last_cleanup = datetime.utcnow()
    return removed
