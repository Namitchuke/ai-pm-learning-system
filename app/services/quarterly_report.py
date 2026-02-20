"""
app/services/quarterly_report.py — Quarterly learning report generation
TDD v2.0 §Core Services (quarterly_report.py)
PRD v2.0 §FR-09 Quarterly Progress Report
FRD v2.0 §FS-09 Quarterly Report Service
Generated on first day of each new quarter (Jan 1, Apr 1, Jul 1, Oct 1).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from app.models import (
    ArchivedTopicsFile,
    Category,
    Metrics,
    QuarterlyReport,
    QuarterlyReportsFile,
    Topic,
    TopicsFile,
    TopicStatus,
)
from app.utils.timezone import get_quarter, is_first_day_of_quarter, get_year


def _compute_avg_mastery_by_category(topics: list[Topic]) -> dict[str, float]:
    """Compute average mastery score grouped by category."""
    by_cat: dict[str, list[float]] = {}
    for topic in topics:
        cat = topic.category.value
        if cat not in by_cat:
            by_cat[cat] = []
        if topic.mastery_score > 0:
            by_cat[cat].append(topic.mastery_score)
    return {
        cat: round(sum(scores) / len(scores), 1)
        for cat, scores in by_cat.items()
        if scores
    }


def _compute_depth_progression(topics: list[Topic]) -> dict[str, int]:
    """Count topics at each depth level 1-5."""
    distribution: dict[str, int] = {str(i): 0 for i in range(1, 6)}
    for topic in topics:
        depth_key = str(topic.current_depth)
        distribution[depth_key] = distribution.get(depth_key, 0) + 1
    return distribution


def generate_quarterly_report(
    topics_file: TopicsFile,
    archived_file: ArchivedTopicsFile,
    metrics: Metrics,
) -> QuarterlyReport:
    """
    Generate a quarterly learning report.
    PRD FR-09 / FRD FS-09.1.
    Called on the first day of each new quarter (is_first_day_of_quarter() == True).
    """
    now = datetime.utcnow()
    quarter_label = get_quarter(now)

    # All topics (active + archived) for this quarter's metrics
    all_topics = topics_file.topics + archived_file.topics

    completed = [t for t in all_topics if t.status == TopicStatus.COMPLETED]
    attempted = [t for t in all_topics if len(t.history) > 0]
    reteached = [t for t in all_topics if any(h.decision.value == "reteach" for h in t.history)]

    # Mastery averages
    mastered_scores = [t.mastery_score for t in all_topics if t.mastery_score > 0]
    avg_mastery_overall = round(sum(mastered_scores) / len(mastered_scores), 1) if mastered_scores else 0.0

    avg_by_category = _compute_avg_mastery_by_category(all_topics)
    depth_distribution = _compute_depth_progression(all_topics)

    # Weakest / strongest categories
    sorted_cats = sorted(avg_by_category.items(), key=lambda x: x[1])
    weakest = [c for c, _ in sorted_cats[:2]] if len(sorted_cats) >= 2 else []
    strongest = [c for c, _ in sorted_cats[-2:]] if len(sorted_cats) >= 2 else []
    strongest.reverse()

    # Learning velocity
    topics_advanced = len([t for t in all_topics if t.current_depth > 1])
    learning_velocity = (
        round(topics_advanced / len(attempted), 2) if attempted else 0.0
    )

    # Streak this quarter
    streak_max = metrics.longest_streak

    # Days in topic reduction modes
    reduction_days = sum(
        1 for entry in metrics.topic_reduction_history
        if entry.to_mode != "normal"
    )

    report = QuarterlyReport(
        quarter=quarter_label,
        period_start=f"{now.year}-{((now.month - 4) % 12) + 1:02d}-01",
        period_end=f"{now.year}-{now.month:02d}-{now.day:02d}",
        topics_covered=len(all_topics),
        topics_completed=len(completed),
        topics_attempted=len(attempted),
        avg_mastery_overall=avg_mastery_overall,
        avg_mastery_by_category=avg_by_category,
        depth_progression=depth_distribution,
        weakest_categories=weakest,
        strongest_categories=strongest,
        learning_velocity=learning_velocity,
        streak_max=streak_max,
        topic_reduction_days=reduction_days,
        reteach_count=len(reteached),
        generated_at=now,
    )

    logger.info(f"Quarterly report generated: {quarter_label}")
    return report


def save_quarterly_report(
    report: QuarterlyReport,
    reports_file: QuarterlyReportsFile,
) -> None:
    """Append the new report to the quarterly reports file."""
    # Avoid duplicate reports for the same quarter
    existing_quarters = [r.quarter for r in reports_file.reports]
    if report.quarter not in existing_quarters:
        reports_file.reports.append(report)
        logger.info(f"Saved quarterly report for {report.quarter}.")
    else:
        logger.info(f"Quarterly report for {report.quarter} already exists. Skipping.")


def should_generate_quarterly_report() -> bool:
    """Return True if today is the first day of a quarter."""
    return is_first_day_of_quarter()
