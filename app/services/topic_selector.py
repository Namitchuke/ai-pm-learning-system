"""
app/services/topic_selector.py — Daily topic selection with adaptive mode quotas
TDD v2.0 §Core Services (topic_selector.py)
PRD v2.0 §FR-04 Topic Selection, §FR-05 Adaptive Difficulty
FRD v2.0 §FS-04 Topic Selector Service, §FS-05 Adaptive Mode
Implements: mode quotas, evening carry-over (L2-06), category balance.
"""
from __future__ import annotations

import random
from collections import Counter
from datetime import datetime
from typing import Any, Optional

from loguru import logger

from app.config import get_settings
from app.models import (
    Category,
    Metrics,
    PipelineState,
    QueuedArticle,
    SummarizedArticle,
    Topic,
    TopicStatus,
    TopicSummary,
    TopicsFile,
    TopicMode,
    ExtractionMethod,
)
from app.utils.timezone import get_iso_week_key, today_ist_str

settings = get_settings()

# ── Mode quotas — PRD FR-04.5 / FRD FS-05.2 ──────────────────────────────────
MODE_QUOTAS: dict[str, int] = {
    TopicMode.NORMAL: 5,
    TopicMode.REDUCED_3: 3,
    TopicMode.REDUCED_2: 2,
    TopicMode.MINIMAL: 1,
}


def get_topic_quota(mode: TopicMode) -> int:
    """Return max topics for today based on adaptive mode."""
    return MODE_QUOTAS.get(mode, 5)


# ──────────────────────────────────────────────────────────────────────────────
# Category drought counter — PRD FR-04.4 / FRD FS-04.3
# ──────────────────────────────────────────────────────────────────────────────

def _update_drought_counter(
    metrics: Metrics,
    selected_categories: list[str],
) -> None:
    """
    Increment drought counter for categories NOT selected today.
    Reset to 0 for categories that WERE selected.
    FRD FS-04.3: Force-select a category after 7 consecutive drought days.
    """
    all_categories = [c.value for c in Category]
    for cat in all_categories:
        if cat in selected_categories:
            metrics.category_drought_counter[cat] = 0
        else:
            metrics.category_drought_counter[cat] = (
                metrics.category_drought_counter.get(cat, 0) + 1
            )


def _get_drought_forced_category(metrics: Metrics) -> Optional[str]:
    """
    FRD FS-04.3: If any category has 7+ drought days, force-include one article from it.
    Returns the most drought-starved category, or None.
    """
    droughts = metrics.category_drought_counter
    max_drought_cat = max(droughts, key=lambda c: droughts.get(c, 0), default=None)
    if max_drought_cat and droughts.get(max_drought_cat, 0) >= 7:
        return max_drought_cat
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Weekly category distribution — PRD FR-04.3 / FRD FS-04.4
# ──────────────────────────────────────────────────────────────────────────────

def _get_week_category_counts(metrics: Metrics) -> dict[str, int]:
    """Get current week's category article counts for balancing."""
    week_key = get_iso_week_key()
    return metrics.weekly_category_distribution.get(week_key, {})


def _update_week_distribution(metrics: Metrics, categories: list[str]) -> None:
    """Update weekly category distribution with newly selected categories."""
    week_key = get_iso_week_key()
    if week_key not in metrics.weekly_category_distribution:
        metrics.weekly_category_distribution[week_key] = {}
    for cat in categories:
        metrics.weekly_category_distribution[week_key][cat] = (
            metrics.weekly_category_distribution[week_key].get(cat, 0) + 1
        )


# ──────────────────────────────────────────────────────────────────────────────
# Evening carry-over — L2-06 fix
# ──────────────────────────────────────────────────────────────────────────────

def process_evening_carry_over(pipeline_state: PipelineState) -> list[SummarizedArticle]:
    """
    L2-06 fix: Process next_day_priority_queue from previous day's evening slot.
    These articles have higher priority than today's new articles.
    Returns rehydrated SummarizedArticle list from queued data.
    """
    queued = pipeline_state.next_day_priority_queue
    if not queued:
        return []

    carried_over: list[SummarizedArticle] = []
    for q in queued:
        try:
            # Re-hydrate from queued data (already scored + summarized)
            summary_data = q.summary if q.summary else {}
            summary = TopicSummary(**summary_data) if summary_data else TopicSummary()

            # Build minimal SummarizedArticle from queued data
            article = SummarizedArticle(
                url=q.url,
                url_hash=q.url_hash,
                title=q.title,
                source_name=q.source_name,
                source_tier=q.source_tier,
                category_bias=q.category_bias,
                rss_description="",
                extracted_text="",
                word_count=0,
                extraction_method=ExtractionMethod.RSS_DESCRIPTION,
                fetched_at=q.added_at,
                scores=q.scores,
                avg_score=float(q.scores.get("avg_score", 7.0)),
                credibility=float(q.scores.get("credibility", 7.0)),
                is_promotional=False,
                summary=summary,
                faithfulness_score=8.0,
                low_confidence=False,
            )
            carried_over.append(article)
        except Exception as exc:
            logger.warning(f"Failed to rehydrate carry-over article {q.url}: {exc}")

    logger.info(f"Carry-over: {len(carried_over)} articles from yesterday's evening queue.")

    # Clear the queue after processing
    pipeline_state.next_day_priority_queue.clear()
    return carried_over


def queue_for_next_day(
    article: SummarizedArticle,
    pipeline_state: PipelineState,
) -> None:
    """
    L2-06 fix: Queue an overflow article for tomorrow's morning priority queue.
    Called when today's quota is already full and article is high quality.
    """
    q = QueuedArticle(
        url=article.url,
        url_hash=article.url_hash,
        title=article.title,
        source_name=article.source_name,
        source_tier=article.source_tier,
        category_bias=article.category_bias,
        summary=article.summary.model_dump() if article.summary else {},
        scores={
            **article.scores,
            "avg_score": article.avg_score,
            "credibility": article.credibility,
        },
        added_at=datetime.utcnow(),
    )
    pipeline_state.next_day_priority_queue.append(q)


# ──────────────────────────────────────────────────────────────────────────────
# Topic creation from summarized article
# ──────────────────────────────────────────────────────────────────────────────

def _article_to_topic(article: SummarizedArticle) -> Topic:
    """Convert a SummarizedArticle to a new Topic record."""
    return Topic(
        topic_name=article.title,
        category=article.category_bias,
        current_depth=1,
        mastery_score=0.0,
        status=TopicStatus.ACTIVE,
        source_url=article.url,
        source_title=article.title,
        source_tier=article.source_tier,
        credibility_score=article.credibility,
        faithfulness_score=article.faithfulness_score,
        extraction_method=article.extraction_method,
        summary=article.summary,
        created_at=datetime.utcnow(),
        last_updated=datetime.utcnow(),
        last_active=datetime.utcnow(),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main selection algorithm
# ──────────────────────────────────────────────────────────────────────────────

def select_daily_topics(
    summarized_articles: list[SummarizedArticle],
    existing_topics_file: TopicsFile,
    pipeline_state: PipelineState,
    metrics: Metrics,
    slot: str,
) -> tuple[list[Topic], list[SummarizedArticle]]:
    """
    Select topics for the day based on adaptive mode quota.
    PRD FR-04 / FRD FS-04:
    1. Process carry-over queue first (L2-06)
    2. Enforce mode quota
    3. Category drought check
    4. Category balance (weekly distribution)
    5. Sort by tier then score
    6. Queue overflow for tomorrow (only in evening slot)

    Returns (selected_topics, overflow_articles).
    """
    quota = get_topic_quota(metrics.current_topic_mode)

    # Prioritize carry-over articles
    carry_over = process_evening_carry_over(pipeline_state)
    all_candidates = carry_over + summarized_articles

    if not all_candidates:
        logger.info(f"[{slot}] No candidates to select from.")
        return [], []

    # Existing topic names for de-dup (already done upstream)
    selected: list[SummarizedArticle] = []
    overflow: list[SummarizedArticle] = []

    # Drought forced selection
    forced_cat = _get_drought_forced_category(metrics)
    week_counts = _get_week_category_counts(metrics)

    # Sort by: tier (asc) → avg_score (desc) — Tier 1 preferred
    candidates_sorted = sorted(
        all_candidates,
        key=lambda a: (a.source_tier, -a.avg_score),
    )

    # If drought category exists, pull one article from it first
    if forced_cat and len(selected) < quota:
        forced = next(
            (a for a in candidates_sorted if a.category_bias.value == forced_cat),
            None,
        )
        if forced:
            selected.append(forced)
            candidates_sorted.remove(forced)
            logger.info(
                f"[{slot}] Drought override: forced category {forced_cat}."
            )

    # Fill remaining quota slots
    for article in candidates_sorted:
        if len(selected) >= quota:
            overflow.append(article)
            continue

        # Category balance: skip if this category is 2x the weekly average
        cat = article.category_bias.value
        cat_count_this_week = week_counts.get(cat, 0)
        all_counts = list(week_counts.values()) if week_counts else [0]
        avg_count = sum(all_counts) / len(all_counts) if all_counts else 0
        if cat_count_this_week > max(2, avg_count * 2):
            overflow.append(article)
            logger.debug(
                f"[{slot}] Skipping {cat} (overrepresented: {cat_count_this_week} this week)."
            )
            continue

        selected.append(article)

    # Convert selected to Topic objects
    new_topics = [_article_to_topic(a) for a in selected]

    # Queue overflow for tomorrow (evening slot only — L2-06)
    if slot == "evening":
        for article in overflow[:5]:  # Cap queue at 5
            queue_for_next_day(article, pipeline_state)
        logger.info(
            f"[{slot}] Queued {min(len(overflow), 5)} articles for tomorrow."
        )

    # Update category stats
    selected_cats = [a.category_bias.value for a in selected]
    _update_week_distribution(metrics, selected_cats)
    _update_drought_counter(metrics, selected_cats)

    logger.info(
        f"[{slot}] Selected {len(new_topics)} topics "
        f"(quota: {quota}, mode: {metrics.current_topic_mode})."
    )
    return new_topics, overflow
