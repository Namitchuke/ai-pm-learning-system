"""
app/services/cleanup.py — Daily cleanup, archival, and cache eviction
TDD v2.0 §Core Services (cleanup.py)
PRD v2.0 §FR-11 Data Management
FRD v2.0 §FS-10 Daily Cleanup & Maintenance
L2-02 fix: cleanup runs as part of the morning RSS trigger (not a separate cron job).
L2-14 fix: Reteaching auto-revert after 14 days.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from app.config import get_settings
from app.core.cache_manager import evict_expired_cache
from app.models import (
    ArchivedTopicsFile,
    CacheData,
    ErrorsFile,
    Metrics,
    Topic,
    TopicStatus,
    TopicsFile,
)
from app.utils.timezone import today_ist_str, is_sunday

settings = get_settings()


# ──────────────────────────────────────────────────────────────────────────────
# Reteaching auto-revert — L2-14 fix
# PRD FR-06 / FRD FS-06.7: After reteaching_timeout_days, revert to active.
# ──────────────────────────────────────────────────────────────────────────────

def revert_timed_out_reteaching(topics_file: TopicsFile) -> int:
    """
    L2-14 fix: If a topic has been in RETEACHING for >= 14 days,
    automatically revert it to ACTIVE status.
    Returns count of topics reverted.
    """
    timeout_dt = timedelta(days=settings.reteaching_timeout_days)
    reverted = 0

    for topic in topics_file.topics:
        if topic.status != TopicStatus.RETEACHING:
            continue
        if topic.reteaching_entered_at is None:
            # No timestamp — set it now and skip
            topic.reteaching_entered_at = datetime.utcnow()
            continue
        age = datetime.utcnow() - topic.reteaching_entered_at
        if age >= timeout_dt:
            topic.status = TopicStatus.ACTIVE
            topic.reteaching_entered_at = None
            topic.retries_used = 0
            logger.info(
                f"Auto-reverted reteaching topic after {age.days} days: "
                f"{topic.topic_name[:60]}"
            )
            reverted += 1

    return reverted


# ──────────────────────────────────────────────────────────────────────────────
# Topic archival — FRD FS-10.3
# PRD FR-04: Archive topics inactive for 90+ days.
# ──────────────────────────────────────────────────────────────────────────────

def archive_inactive_topics(
    topics_file: TopicsFile,
    archived_topics_file: ArchivedTopicsFile,
) -> int:
    """
    Move topics to archived_topics.json if:
    1. Status is COMPLETED, or
    2. Status is ACTIVE and last_active > 90 days ago.
    Returns count archived.
    """
    cutoff = datetime.utcnow() - timedelta(days=settings.topic_archive_inactive_days)
    to_archive: list[Topic] = []
    to_keep: list[Topic] = []

    for topic in topics_file.topics:
        if topic.status == TopicStatus.COMPLETED:
            to_archive.append(topic)
        elif topic.status == TopicStatus.ACTIVE and topic.last_active < cutoff:
            topic.status = TopicStatus.ARCHIVED
            to_archive.append(topic)
        else:
            to_keep.append(topic)

    if to_archive:
        archived_topics_file.topics.extend(to_archive)
        archived_topics_file.last_updated = datetime.utcnow()
        topics_file.topics = to_keep
        topics_file.last_updated = datetime.utcnow()
        logger.info(f"Archived {len(to_archive)} topics.")

    return len(to_archive)


# ──────────────────────────────────────────────────────────────────────────────
# Error log pruning — FRD FS-11.4 / PRD FR-11
# ──────────────────────────────────────────────────────────────────────────────

def prune_error_log(errors_file: ErrorsFile) -> int:
    """
    Keep at most MAX_ERRORS (200) entries in errors.json (FIFO).
    Returns count removed.
    """
    if len(errors_file.errors) > errors_file.max_entries:
        excess = len(errors_file.errors) - errors_file.max_entries
        errors_file.errors = errors_file.errors[excess:]
        logger.debug(f"Pruned {excess} old error log entries.")
        return excess
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Main cleanup orchestrator — FRD FS-10 / L2-02 fix
# Called from the morning RSS trigger in triggers.py
# ──────────────────────────────────────────────────────────────────────────────

def run_morning_cleanup(
    topics_file: TopicsFile,
    archived_topics_file: ArchivedTopicsFile,
    cache: CacheData,
    errors_file: ErrorsFile,
) -> dict[str, Any]:
    """
    Morning cleanup operations. L2-02 fix: Runs as part of the morning trigger
    (not a separate 5th cron job).

    Operations:
    1. Evict expired cache entries
    2. Revert timed-out reteaching topics (L2-14)
    3. Archive inactive/completed topics
    4. Prune error log

    Returns summary dict.
    """
    logger.info("Running morning cleanup...")

    # 1. Cache eviction
    evict_summary = evict_expired_cache(cache)

    # 2. Reteaching auto-revert — L2-14
    reverted = revert_timed_out_reteaching(topics_file)

    # 3. Archive inactive topics
    archived = archive_inactive_topics(topics_file, archived_topics_file)

    # 4. Prune error log
    errors_pruned = prune_error_log(errors_file)

    summary = {
        "cache_evicted": evict_summary,
        "reteaching_reverted": reverted,
        "topics_archived": archived,
        "errors_pruned": errors_pruned,
        "ran_at": datetime.utcnow().isoformat(),
    }

    logger.info(f"Morning cleanup complete: {summary}")
    return summary
