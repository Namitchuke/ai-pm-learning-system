"""
tests/test_adaptive_mode.py — Unit tests for adaptive mode state machine
"""
from __future__ import annotations

import pytest
from app.models import Metrics, TopicMode
from app.services.adaptive_mode import update_adaptive_mode, is_paused


def test_normal_mode_unchanged_on_neutral_day():
    """L2-05: Zero-grading days don't change mode."""
    metrics = Metrics()
    mode = update_adaptive_mode(metrics, today_avg=0.0, topics_graded=0)
    assert mode == TopicMode.NORMAL
    assert metrics.consecutive_neutral_days == 1
    assert metrics.consecutive_low_days == 0


def test_pause_detection_after_7_neutral_days():
    """7 consecutive neutral days triggers pause signal."""
    metrics = Metrics()
    for _ in range(7):
        update_adaptive_mode(metrics, today_avg=0.0, topics_graded=0)
    assert is_paused(metrics)


def test_mode_downgrades_to_reduced_3_after_5_low_days():
    """5 consecutive low days → normal → reduced_3."""
    metrics = Metrics()
    metrics.current_topic_mode = TopicMode.NORMAL
    for _ in range(5):
        update_adaptive_mode(metrics, today_avg=50.0, topics_graded=3)
    assert metrics.current_topic_mode == TopicMode.REDUCED_3


def test_mode_recovers_after_3_high_days():
    """3 consecutive recovery days → reduced_3 → normal."""
    metrics = Metrics()
    metrics.current_topic_mode = TopicMode.REDUCED_3
    for _ in range(3):
        update_adaptive_mode(metrics, today_avg=80.0, topics_graded=3)
    assert metrics.current_topic_mode == TopicMode.NORMAL


def test_low_day_counter_resets_after_recovery():
    """Recovery day should reset low_day counter."""
    metrics = Metrics()
    metrics.consecutive_low_days = 4
    update_adaptive_mode(metrics, today_avg=80.0, topics_graded=2)
    assert metrics.consecutive_low_days == 0


def test_neutral_day_does_not_reset_consecutive_lows():
    """L2-05: Neutral day preserves consecutive_low_days."""
    metrics = Metrics()
    metrics.consecutive_low_days = 3
    update_adaptive_mode(metrics, today_avg=0.0, topics_graded=0)
    assert metrics.consecutive_low_days == 3  # Unchanged
