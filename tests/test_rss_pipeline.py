"""
tests/test_rss_pipeline.py — Unit tests for RSS pipeline utilities
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from app.utils.extractors import (
    is_url_blocked,
    passes_arxiv_filter,
    count_words,
    validate_and_truncate,
)
from app.core.cache_manager import (
    is_url_processed,
    mark_url_processed,
)
from app.models import CacheData


def test_url_not_blocked(empty_cache):
    blocked, _ = is_url_blocked("https://deepmind.google/blog/gemini")
    assert not blocked


def test_url_processed_check(empty_cache):
    assert not is_url_processed(empty_cache, "https://new-article.com/test")
    mark_url_processed(empty_cache, "https://new-article.com/test", "Test Article")
    assert is_url_processed(empty_cache, "https://new-article.com/test")


def test_url_not_reprocessed_after_mark(empty_cache):
    url = "https://example.com/article"
    mark_url_processed(empty_cache, url, "Article Title")
    # Should now be marked as processed
    assert is_url_processed(empty_cache, url)


def test_arxiv_filter_passes_relevant():
    assert passes_arxiv_filter(
        "LLM Reasoning with Chain-of-Thought",
        "We study how large language models reason step-by-step using chain-of-thought prompting."
    )


def test_arxiv_filter_rejects_irrelevant():
    assert not passes_arxiv_filter(
        "Quantum Entanglement in Photonic Systems",
        "We study quantum entanglement properties of photonic systems at low temperatures."
    )


def test_word_count():
    assert count_words("hello world foo bar") == 4
    assert count_words("") == 0


def test_validate_and_truncate_too_short():
    text = "short text " * 10  # 20 words
    valid, _, reason = validate_and_truncate(text)
    assert not valid
    assert "too_short" in reason


def test_validate_and_truncate_valid():
    text = "word " * 300  # 300 words
    valid, processed, _ = validate_and_truncate(text)
    assert valid
    assert len(processed.split()) == 300


def test_validate_and_truncate_truncates_long_text():
    text = "word " * 4000  # 4000 words
    valid, processed, _ = validate_and_truncate(text)
    assert valid
    assert len(processed.split()) == 3000  # Truncated to max
