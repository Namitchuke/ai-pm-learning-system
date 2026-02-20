"""
tests/test_grading.py — Unit tests for grading engine
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from app.core.cache_manager import (
    get_cached_grade,
    set_cached_grade,
    hash_grading_key,
)
from app.models import CacheData, GradingDecision


def test_grading_cache_hit_returns_entry(empty_cache):
    """Cache stores and retrieves a grading result."""
    set_cached_grade(
        cache=empty_cache,
        topic_id="topic-1",
        depth=1,
        answer_text="My answer",
        score=75.0,
        breakdown={"concept_clarity": 20, "technical_correctness": 20,
                   "application_thinking": 18, "ai_pm_relevance": 17},
        feedback="Good answer.",
        decision=GradingDecision.ADVANCE.value,
        model_used="gemini-2.5-flash",
    )
    entry = get_cached_grade(empty_cache, "topic-1", 1, "My answer")
    assert entry is not None
    assert entry.result.score == 75.0
    assert entry.result.decision == GradingDecision.ADVANCE


def test_grading_cache_miss_returns_none(empty_cache):
    """Cache miss returns None."""
    result = get_cached_grade(empty_cache, "nonexistent-topic", 1, "Any answer")
    assert result is None


def test_submission_count_increments(empty_cache):
    """Submission count increments on each set."""
    for i in range(3):
        set_cached_grade(
            empty_cache, "topic-2", 1, "Same answer",
            score=50.0, breakdown={}, feedback="Retry.",
            decision=GradingDecision.RETRY.value, model_used="gemini-2.0-flash-lite",
        )
    entry = get_cached_grade(empty_cache, "topic-2", 1, "Same answer")
    assert entry.submission_count == 3


def test_different_answers_produce_different_cache_keys():
    """Different answer texts should have different cache keys."""
    k1 = hash_grading_key("topic-1", 1, "Answer A")
    k2 = hash_grading_key("topic-1", 1, "Answer B")
    assert k1 != k2
