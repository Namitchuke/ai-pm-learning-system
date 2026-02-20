"""
tests/test_dedup.py — Unit tests for deduplication utilities
"""
from __future__ import annotations

import pytest
from app.utils.dedup import (
    compute_url_hash,
    get_fuzzy_similarity,
    check_title_phase1,
    DuplicateResult,
)


def test_url_hash_is_deterministic():
    url = "https://example.com/article"
    assert compute_url_hash(url) == compute_url_hash(url)


def test_url_hash_differs_for_different_urls():
    assert compute_url_hash("https://a.com") != compute_url_hash("https://b.com")


def test_fuzzy_similarity_identical():
    score = get_fuzzy_similarity("GPT-4 API Rate Limits", "GPT-4 API Rate Limits")
    assert score == 100


def test_fuzzy_similarity_different():
    score = get_fuzzy_similarity("Attention Mechanisms", "Python Deployment Patterns")
    assert score < 40


def test_phase1_definite_duplicate_at_85_plus():
    titles = ["GPT-4 Turbo API Rate Limits and Best Practices"]
    result, match, score = check_title_phase1(
        "GPT-4 Turbo Rate Limits API Best Practices", titles
    )
    assert result == DuplicateResult.DEFINITE_DUPLICATE
    assert score >= 85


def test_phase1_unique_below_60():
    titles = ["Kubernetes Deployment Strategies"]
    result, match, score = check_title_phase1(
        "Transformer Attention Mechanisms Explained", titles
    )
    assert result == DuplicateResult.UNIQUE


def test_phase1_ambiguous_in_60_to_85():
    titles = ["Building Scalable AI APIs"]
    result, match, score = check_title_phase1(
        "Scalable AI API Design Patterns", titles
    )
    # Score should be ambiguous (60-84)
    assert score >= 60
