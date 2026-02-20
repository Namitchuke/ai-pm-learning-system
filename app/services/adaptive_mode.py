"""
app/services/adaptive_mode.py — Unified adaptive difficulty state machine
TDD v2.0 §Core Services (adaptive_mode.py)
PRD v2.0 §FR-05 Adaptive Difficulty System
FRD v2.0 §FS-05 Adaptive Mode Service (L2-05, L2-07 fixes)
L2-05 fix: Zero-grading days are NEUTRAL — don't affect any counter.
L2-07 fix: Single MODE_CONFIG source of truth for all thresholds.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from loguru import logger

from app.config import get_settings
from app.core import logging as app_logging
from app.models import ModeHistoryEntry, Metrics, TopicMode
from app.utils.timezone import today_ist_str

settings = get_settings()


# ── Single source of truth for all mode thresholds — L2-07 fix ───────────────
# FRD FS-05.3 MODE_CONFIG: Each entry defines threshold and recovery behavior.
MODE_CONFIG = {
    TopicMode.NORMAL: {
        "daily_quota": 5,
        "transitions_to_reduced_after_low_days": settings.mode_low_days_reduced_3,
        "lower_mode": TopicMode.REDUCED_3,
    },
    TopicMode.REDUCED_3: {
        "daily_quota": 3,
        "transitions_to_reduced_after_low_days": settings.mode_low_days_reduced_2,
        "lower_mode": TopicMode.REDUCED_2,
        "recovery_target": TopicMode.NORMAL,
        "recovery_days_needed": settings.mode_recovery_days,
    },
    TopicMode.REDUCED_2: {
        "daily_quota": 2,
        "transitions_to_reduced_after_low_days": settings.mode_low_days_minimal,
        "lower_mode": TopicMode.MINIMAL,
        "recovery_target": TopicMode.REDUCED_3,
        "recovery_days_needed": settings.mode_recovery_days,
    },
    TopicMode.MINIMAL: {
        "daily_quota": 1,
        "lower_mode": None,
        "recovery_target": TopicMode.REDUCED_2,
        "recovery_days_needed": settings.mode_recovery_days,
    },
}


def _is_low_day(today_avg: float, topics_graded: int) -> bool:
    """Return True if today's mastery average falls below recovery threshold."""
    if topics_graded == 0:
        return False  # L2-05: Zero-grading days are neutral
    return today_avg < settings.mastery_advance_threshold


def _is_recovery_day(today_avg: float, topics_graded: int) -> bool:
    """Return True if today's mastery average meets or exceeds recovery threshold."""
    if topics_graded == 0:
        return False  # L2-05: Zero-grading days are neutral
    return today_avg >= settings.mastery_recovery_threshold


def update_adaptive_mode(
    metrics: Metrics,
    today_avg: float,
    topics_graded: int,
) -> TopicMode:
    """
    Unified adaptive mode state machine.
    L2-07 fix: All transition logic goes through MODE_CONFIG.
    L2-05 fix: Zero-grading days (topics_graded == 0) are NEUTRAL.
    They do NOT increment consecutive_low_days or consecutive_recovery_days.
    They DO increment consecutive_neutral_days (for pause detection).

    Transitions:
    - 5 consecutive low days → NORMAL → REDUCED_3
    - 10 consecutive low days → REDUCED_3 → REDUCED_2
    - 15 consecutive low days → REDUCED_2 → MINIMAL
    - 3 consecutive recovery days → step UP one level
    - 7 consecutive neutral days → PAUSE (email alert, no mode change)

    Returns the (possibly updated) TopicMode.
    """
    current_mode = metrics.current_topic_mode
    old_mode = current_mode

    if topics_graded == 0:
        # L2-05: Neutral day — only neutral counter increments
        metrics.consecutive_neutral_days += 1
        # Do NOT touch: consecutive_low_days, consecutive_recovery_days
        logger.debug(
            f"Neutral day #{metrics.consecutive_neutral_days}. "
            f"Mode unchanged: {current_mode}"
        )

        # Check pause threshold (7 consecutive neutral days)
        if metrics.consecutive_neutral_days >= settings.mode_pause_neutral_days:
            logger.warning(
                f"PAUSE: {metrics.consecutive_neutral_days} consecutive inactive days. "
                f"Email alert recommended."
            )
            # NOTE: No mode change on pause — email alert is separate concern
            # Handled by email_service as an alert condition
        return current_mode

    # Active grading day — reset neutral counter
    metrics.consecutive_neutral_days = 0

    if _is_recovery_day(today_avg, topics_graded):
        # Recovery day
        metrics.consecutive_recovery_days += 1
        metrics.consecutive_low_days = 0  # Reset low counter
        logger.debug(
            f"Recovery day #{metrics.consecutive_recovery_days} (avg: {today_avg:.1f})"
        )

        config = MODE_CONFIG.get(current_mode, {})
        needed = config.get("recovery_days_needed", settings.mode_recovery_days)
        recovery_target = config.get("recovery_target")

        if (
            metrics.consecutive_recovery_days >= needed
            and recovery_target is not None
        ):
            # Step UP one mode level
            metrics.current_topic_mode = recovery_target
            metrics.consecutive_recovery_days = 0
            _record_mode_transition(
                metrics, old_mode, recovery_target,
                f"{needed}_consecutive_recovery_days_avg_{today_avg:.1f}"
            )
            app_logging.log_mode_transition(old_mode, recovery_target, "recovery")
            logger.info(f"Mode UP: {old_mode} → {recovery_target}")

    elif _is_low_day(today_avg, topics_graded):
        # Low performance day
        metrics.consecutive_low_days += 1
        metrics.consecutive_recovery_days = 0  # Reset recovery counter
        logger.debug(
            f"Low day #{metrics.consecutive_low_days} (avg: {today_avg:.1f})"
        )

        config = MODE_CONFIG.get(current_mode, {})
        low_threshold = config.get(
            "transitions_to_reduced_after_low_days",
            settings.mode_low_days_reduced_3,
        )
        lower_mode = config.get("lower_mode")

        if (
            metrics.consecutive_low_days >= low_threshold
            and lower_mode is not None
        ):
            # Step DOWN one mode level
            metrics.current_topic_mode = lower_mode
            metrics.consecutive_low_days = 0
            _record_mode_transition(
                metrics, old_mode, lower_mode,
                f"{low_threshold}_consecutive_low_days_avg_{today_avg:.1f}"
            )
            app_logging.log_mode_transition(old_mode, lower_mode, "performance_decline")
            logger.info(f"Mode DOWN: {old_mode} → {lower_mode}")

    else:
        # Neither low nor recovery — mediocre performance resets both counters
        metrics.consecutive_low_days = max(0, metrics.consecutive_low_days - 1)
        metrics.consecutive_recovery_days = max(0, metrics.consecutive_recovery_days - 1)

    return metrics.current_topic_mode


def _record_mode_transition(
    metrics: Metrics,
    from_mode: TopicMode,
    to_mode: TopicMode,
    reason: str,
) -> None:
    """Append a mode transition record to metrics.topic_reduction_history."""
    metrics.topic_reduction_history.append(
        ModeHistoryEntry(
            date=today_ist_str(),
            from_mode=from_mode.value,
            to_mode=to_mode.value,
            reason=reason,
        )
    )


def update_daily_mastery_average(
    metrics: Metrics,
    today_avg: float,
    topics_graded: int,
) -> None:
    """
    Append today's mastery average to the rolling daily log.
    FRD FS-05.5: Daily mastery averages used to compute adaptive mode.
    Only appends if today's entry doesn't already exist (idempotent).
    """
    from app.models import DailyMasteryEntry
    today = today_ist_str()

    # Check if today already exists
    if any(e.date == today for e in metrics.daily_mastery_averages):
        return

    metrics.daily_mastery_averages.append(
        DailyMasteryEntry(
            date=today,
            avg_mastery=round(today_avg, 2),
            topics_graded=topics_graded,
        )
    )

    # Keep only last 90 days
    if len(metrics.daily_mastery_averages) > 90:
        metrics.daily_mastery_averages = metrics.daily_mastery_averages[-90:]


def is_paused(metrics: Metrics) -> bool:
    """Return True if the user is in a pause state (7+ neutral days)."""
    return metrics.consecutive_neutral_days >= settings.mode_pause_neutral_days
