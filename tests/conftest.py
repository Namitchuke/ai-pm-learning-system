"""
tests/conftest.py — Shared pytest fixtures
"""
from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.models import (
    CacheData,
    Category,
    DiscardedFile,
    Metrics,
    PipelineState,
    Topic,
    TopicStatus,
    TopicSummary,
    TopicsFile,
    TopicMode,
)


@pytest.fixture
def sample_topic() -> Topic:
    return Topic(
        topic_name="Attention Mechanisms in Transformers",
        category=Category.ML_ENGINEERING,
        current_depth=1,
        mastery_score=0.0,
        status=TopicStatus.ACTIVE,
        source_url="https://example.com/attention",
        source_title="Attention Is All You Need",
        source_tier=1,
        credibility_score=8.5,
        faithfulness_score=9.0,
        summary=TopicSummary(
            why_it_matters="Attention mechanisms are the core of modern LLMs.",
            core_mechanism="Each token attends to all other tokens via Q/K/V matrices.",
            product_applications="Understanding attention helps PMs reason about context window costs.",
            risks_limitations="Quadratic scaling with sequence length increases latency and cost.",
            key_takeaways=["Attention is what enables LLMs to understand context."],
            tldr="Attention mechanisms let transformers understand context dynamically.",
            keywords_glossary={"attention": "A mechanism that weighs token relevance"},
        ),
    )


@pytest.fixture
def empty_cache() -> CacheData:
    return CacheData()


@pytest.fixture
def empty_metrics() -> Metrics:
    return Metrics()


@pytest.fixture
def empty_pipeline_state() -> PipelineState:
    return PipelineState(date=datetime.utcnow().strftime("%Y-%m-%d"))


@pytest.fixture
def topics_file(sample_topic) -> TopicsFile:
    return TopicsFile(topics=[sample_topic])


@pytest.fixture
def discarded_file() -> DiscardedFile:
    return DiscardedFile()
