"""
tests/test_scoring.py — Unit tests for scoring service
"""
from __future__ import annotations

import pytest

from app.services.scoring import should_reject_article, parse_scoring_response


def test_reject_promotional():
    scores = {
        "relevance_to_ai_pm": 8, "technical_depth": 7,
        "actionability": 7, "novelty": 7, "recency_relevance": 8,
        "credibility": 8, "is_promotional": True,
    }
    reject, reason = should_reject_article(scores)
    assert reject
    assert "promotional" in reason


def test_reject_low_credibility():
    scores = {
        "relevance_to_ai_pm": 8, "technical_depth": 7,
        "actionability": 7, "novelty": 7, "recency_relevance": 8,
        "credibility": 4.0, "is_promotional": False,
    }
    reject, reason = should_reject_article(scores)
    assert reject
    assert "credibility" in reason


def test_reject_low_avg_score():
    scores = {
        "relevance_to_ai_pm": 4, "technical_depth": 5,
        "actionability": 4, "novelty": 4, "recency_relevance": 5,
        "credibility": 7.0, "is_promotional": False,
    }
    reject, reason = should_reject_article(scores)
    assert reject
    assert "relevance" in reason


def test_pass_good_article():
    scores = {
        "relevance_to_ai_pm": 9, "technical_depth": 8,
        "actionability": 9, "novelty": 7, "recency_relevance": 9,
        "credibility": 9.0, "is_promotional": False,
    }
    reject, _ = should_reject_article(scores)
    assert not reject


def test_parse_scoring_response_valid():
    text = '{"relevance_to_ai_pm": 8, "technical_depth": 7, "actionability": 8, "novelty": 7, "recency_relevance": 9, "credibility": 8, "is_promotional": false}'
    result = parse_scoring_response(text)
    assert result is not None
    assert result["relevance_to_ai_pm"] == 8


def test_parse_scoring_response_invalid():
    result = parse_scoring_response("not valid json")
    assert result is None
