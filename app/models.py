"""
app/models.py — All Pydantic data schemas
TDD v2.0 §Data Model / Complete JSON Schemas
FRD v2.0 §FS-11.4 (pipeline_state, topics, metrics, cache, errors)
PRD v2.0 §FR-12 (Pipeline State Schema), §FR-13 (Topic Data Schema)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────────────────────────────────────
# Enumerations
# ──────────────────────────────────────────────────────────────────────────────

class SlotStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    FETCHING = "FETCHING"
    SCORING = "SCORING"
    SUMMARIZING = "SUMMARIZING"
    SELECTING = "SELECTING"
    DONE = "DONE"
    FAILED = "FAILED"


class TopicStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    RETEACHING = "reteaching"


class GradingDecision(str, Enum):
    ADVANCE = "advance"
    RETRY = "retry"
    RETEACH = "reteach"


class ExtractionMethod(str, Enum):
    TRAFILATURA = "trafilatura"
    READABILITY = "readability"
    NEWSPAPER3K = "newspaper3k"
    RSS_DESCRIPTION = "rss_description"


class Category(str, Enum):
    ML_ENGINEERING = "ml_engineering"
    PRODUCT_STRATEGY = "product_strategy"
    MLOPS = "mlops"
    AI_ETHICS = "ai_ethics"
    INFRASTRUCTURE = "infrastructure"


class TopicMode(str, Enum):
    NORMAL = "normal"
    REDUCED_3 = "reduced_3"
    REDUCED_2 = "reduced_2"
    MINIMAL = "minimal"


# ──────────────────────────────────────────────────────────────────────────────
# RSS Source — FRD FS-01.1
# ──────────────────────────────────────────────────────────────────────────────

class RSSSource(BaseModel):
    source_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    feed_url: str
    tier: int = Field(ge=1, le=6)
    category_bias: Category
    enabled: bool = True
    consecutive_failures: int = 0
    last_success: Optional[datetime] = None
    added_at: datetime = Field(default_factory=datetime.utcnow)


class RSSSourcesFile(BaseModel):
    schema_version: str = "2.0"
    sources: list[RSSSource]
    blocked_domains: list[str] = []
    blocked_patterns: list[str] = []


# ──────────────────────────────────────────────────────────────────────────────
# Article (in-flight, not persisted) — FRD FS-01.3 / FS-01.4
# ──────────────────────────────────────────────────────────────────────────────

class CandidateArticle(BaseModel):
    url: str
    url_hash: str
    title: str
    source_name: str
    source_tier: int
    category_bias: Category
    published_date: Optional[datetime] = None
    rss_description: str = ""


class ExtractedArticle(CandidateArticle):
    extracted_text: str
    word_count: int
    extraction_method: ExtractionMethod
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class ScoredArticle(ExtractedArticle):
    scores: dict[str, float]  # 5 relevance dimensions
    avg_score: float
    credibility: float
    is_promotional: bool
    rejection_reason: Optional[str] = None


class SummarizedArticle(ScoredArticle):
    summary: "TopicSummary"
    faithfulness_score: float
    low_confidence: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# Topic Summary — FRD FS-11.4 / PRD FR-13
# ──────────────────────────────────────────────────────────────────────────────

class TopicSummary(BaseModel):
    why_it_matters: str = ""
    core_mechanism: str = ""
    product_applications: str = ""
    risks_limitations: str = ""
    key_takeaways: list[str] = []
    tldr: str = ""
    keywords_glossary: dict[str, str] = {}


# ──────────────────────────────────────────────────────────────────────────────
# Grading History Entry — FRD FS-11.4 / PRD FR-13
# ──────────────────────────────────────────────────────────────────────────────

class HistoryEntry(BaseModel):
    date: datetime = Field(default_factory=datetime.utcnow)
    depth: int
    score: float
    answer_hash: str
    decision: GradingDecision
    feedback: str
    model_used: str
    cached: bool = False
    reteach_content: Optional[dict] = None


# ──────────────────────────────────────────────────────────────────────────────
# Topic — PRD FR-13 / FRD FS-11.4 topics.json
# ──────────────────────────────────────────────────────────────────────────────

class Topic(BaseModel):
    schema_version: str = "2.0"
    topic_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic_name: str
    category: Category
    current_depth: int = Field(default=1, ge=1, le=5)
    mastery_score: float = Field(default=0.0, ge=0.0, le=100.0)
    status: TopicStatus = TopicStatus.ACTIVE
    retries_used: int = Field(default=0, ge=0, le=2)
    source_url: str
    source_title: str
    source_tier: int = Field(ge=1, le=6)
    credibility_score: float = 0.0
    faithfulness_score: float = 0.0
    extraction_method: ExtractionMethod = ExtractionMethod.TRAFILATURA
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    reteaching_entered_at: Optional[datetime] = None
    summary: TopicSummary = Field(default_factory=TopicSummary)
    history: list[HistoryEntry] = []


class TopicsFile(BaseModel):
    schema_version: str = "2.0"
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    topics: list[Topic] = []


class ArchivedTopicsFile(BaseModel):
    schema_version: str = "2.0"
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    topics: list[Topic] = []


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline State — PRD FR-12 / FRD FS-11.4 pipeline_state.json
# ──────────────────────────────────────────────────────────────────────────────

class SlotState(BaseModel):
    run_id: Optional[str] = None
    status: SlotStatus = SlotStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    articles_fetched: int = 0
    articles_new: int = 0
    articles_scored: int = 0
    articles_passed: int = 0
    articles_summarized: int = 0
    topics_selected: int = 0
    errors: list[dict] = []
    cleanup_ran: bool = False
    backup_ran: bool = False
    quarterly_ran: bool = False


class QueuedArticle(BaseModel):
    """Evening carry-over article — L2-06 fix."""
    url: str
    url_hash: str
    title: str
    source_name: str
    source_tier: int
    category_bias: Category
    summary: dict = {}
    scores: dict = {}
    added_at: datetime = Field(default_factory=datetime.utcnow)


class PipelineState(BaseModel):
    schema_version: str = "2.0"
    date: str = Field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d"))  # ISO date YYYY-MM-DD
    slots: dict[str, SlotState] = Field(
        default_factory=lambda: {
            "morning": SlotState(),
            "midday": SlotState(),
            "evening": SlotState(),
        }
    )
    email_sent: bool = False
    next_day_priority_queue: list[QueuedArticle] = []
    daily_rpd: dict[str, int] = {}  # model_id → request count


# ──────────────────────────────────────────────────────────────────────────────
# Metrics — FRD FS-11.4 metrics.json / FS-05.3
# ──────────────────────────────────────────────────────────────────────────────

class DailyMasteryEntry(BaseModel):
    date: str  # YYYY-MM-DD
    avg_mastery: float
    topics_graded: int


class ModeHistoryEntry(BaseModel):
    date: str
    from_mode: str
    to_mode: str
    reason: str


class MonthlyCostEntry(BaseModel):
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    calls_by_operation: dict[str, dict[str, Any]] = {}


class Metrics(BaseModel):
    schema_version: str = "2.0"
    streak_count: int = 0
    streak_start_date: Optional[str] = None
    longest_streak: int = 0
    current_topic_mode: TopicMode = TopicMode.NORMAL
    consecutive_low_days: int = 0
    consecutive_recovery_days: int = 0
    consecutive_neutral_days: int = 0
    daily_mastery_averages: list[DailyMasteryEntry] = []
    weekly_category_distribution: dict[str, dict[str, int]] = {}
    category_drought_counter: dict[str, int] = {}
    topic_reduction_history: list[ModeHistoryEntry] = []
    monthly_cost_tracker: dict[str, MonthlyCostEntry] = {}


# ──────────────────────────────────────────────────────────────────────────────
# Cache — FRD FS-11.4 cache.json / L2-20
# ──────────────────────────────────────────────────────────────────────────────

class ProcessedURLEntry(BaseModel):
    url: str
    title: str
    added_at: datetime
    ttl_days: int = 30


class GradingCacheResult(BaseModel):
    score: float
    breakdown: dict[str, float]
    feedback: str
    decision: GradingDecision
    model_used: str


class GradingCacheEntry(BaseModel):
    added_at: datetime
    ttl_days: int = 30
    submission_count: int = 1
    result: GradingCacheResult


class SummaryCacheEntry(BaseModel):
    added_at: datetime
    ttl_days: int = 90
    extraction_method: ExtractionMethod
    summary: TopicSummary


class EmailCacheEntry(BaseModel):
    sent: bool
    generated_at: datetime
    topics_count: int


class CacheData(BaseModel):
    schema_version: str = "2.0"
    last_cleanup: Optional[datetime] = None
    processed_urls: dict[str, ProcessedURLEntry] = {}      # sha256 → entry
    grading_cache: dict[str, GradingCacheEntry] = {}       # sha256 → entry
    email_cache: dict[str, EmailCacheEntry] = {}           # YYYY-MM-DD → entry
    summary_cache: dict[str, SummaryCacheEntry] = {}       # sha256 → entry


# ──────────────────────────────────────────────────────────────────────────────
# Discarded Articles — FRD FS-02.2
# ──────────────────────────────────────────────────────────────────────────────

class DiscardedEntry(BaseModel):
    url: str
    title: str
    source_name: str
    source_tier: int
    avg_score: Optional[float] = None
    credibility: Optional[float] = None
    is_promotional: bool = False
    rejection_reason: str
    scores_detail: dict[str, float] = {}
    discarded_at: datetime = Field(default_factory=datetime.utcnow)


class DiscardedFile(BaseModel):
    schema_version: str = "2.0"
    max_entries: int = 500
    entries: list[DiscardedEntry] = []


# ──────────────────────────────────────────────────────────────────────────────
# Errors — FRD FS-11.4 errors.json
# ──────────────────────────────────────────────────────────────────────────────

class ErrorEntry(BaseModel):
    error_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    component: str
    operation: str
    error_type: str
    error_message: str
    stack_trace: str = ""
    context: dict = {}
    resolved: bool = False


class ErrorsFile(BaseModel):
    schema_version: str = "2.0"
    max_entries: int = 200
    errors: list[ErrorEntry] = []


# ──────────────────────────────────────────────────────────────────────────────
# Quarterly Report — FRD FS-09.1
# ──────────────────────────────────────────────────────────────────────────────

class QuarterlyReport(BaseModel):
    quarter: str  # e.g. "Q1 2026"
    period_start: str
    period_end: str
    topics_covered: int
    topics_completed: int
    topics_attempted: int
    avg_mastery_overall: float
    avg_mastery_by_category: dict[str, float]
    depth_progression: dict[str, int]
    weakest_categories: list[str]
    strongest_categories: list[str]
    learning_velocity: float  # topics_advanced / topics_attempted
    streak_max: int
    topic_reduction_days: int
    reteach_count: int
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class QuarterlyReportsFile(BaseModel):
    schema_version: str = "2.0"
    year: int = Field(default_factory=lambda: datetime.utcnow().year)
    reports: list[QuarterlyReport] = []


# ──────────────────────────────────────────────────────────────────────────────
# API Request / Response models — TDD §API Contracts
# ──────────────────────────────────────────────────────────────────────────────

class GradeRequest(BaseModel):
    """POST /api/grade request body — FRD FS-06.1"""
    topic_id: str
    answer_text: str = Field(min_length=1, max_length=5000)
    csrf_token: Optional[str] = None  # Required for Basic Auth path

    @field_validator("answer_text")
    @classmethod
    def validate_word_count(cls, v: str) -> str:
        words = v.strip().split()
        if len(words) < 50:
            raise ValueError(
                "Please provide a more detailed answer (minimum 50 words)"
            )
        return v.strip()


class GradeBreakdown(BaseModel):
    concept_clarity: float
    technical_correctness: float
    application_thinking: float
    ai_pm_relevance: float


class GradeResponse(BaseModel):
    """POST /api/grade response — FRD FS-06.4"""
    success: bool = True
    topic_id: str
    topic_name: str
    depth: int
    score: float
    breakdown: GradeBreakdown
    feedback: str
    decision: GradingDecision
    new_depth: Optional[int] = None
    retries_remaining: int
    model_used: str
    quality_warning: Optional[str] = None
    cached: bool = False
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """GET /health response — PRD NFR-04 / TDD §API Contracts"""
    status: str  # healthy | degraded | unhealthy
    last_rss_fetch: dict[str, Optional[str]]
    last_email_sent: Optional[str]
    oauth_token_valid: bool
    daily_token_usage: dict[str, Any]
    monthly_token_usage: dict[str, Any]
    daily_rpd: dict[str, int]
    errors_last_24h: int
    pipeline_state: dict[str, str]
    adaptive_mode: str
    streak: int
    active_feeds: int
    disabled_feeds: int


class TriggerResponse(BaseModel):
    """GET /api/trigger/rss-fetch response — TDD §API Contracts"""
    status: str
    slot: str
    run_id: Optional[str] = None
    message: str
    duration_seconds: Optional[float] = None
    cleanup_ran: bool = False
    backup_ran: bool = False
    quarterly_ran: bool = False


class DailyLog(BaseModel):
    schema_version: str = "2.0"
    date: str
    slot: str
    run_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: SlotStatus
    articles_fetched: int
    articles_new: int
    articles_scored: int
    articles_passed: int
    articles_summarized: int
    topics_selected: int
    topic_ids_selected: list[str] = []
    errors_count: int = 0


class DailyLogsFile(BaseModel):
    schema_version: str = "2.0"
    month: str  # YYYY-MM
    logs: list[DailyLog] = []


# Reteaching content returned from Gemini
class ReteachContent(BaseModel):
    sub_concepts: list[dict[str, str]]  # [{name, explanation}]
    reteach_question: str
