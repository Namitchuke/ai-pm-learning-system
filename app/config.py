"""
app/config.py — Pydantic BaseSettings configuration
TDD v2.0 §Component Diagram (config.py)
FRD §Constraints & Assumptions
PRD §NFR-02 Security, NFR-01 Cost Control
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────────
    environment: str = "development"
    log_level: str = "INFO"
    port: int = 8000

    # ── Authentication — PRD NFR-02 / TDD §Security ───────────────────────────
    api_key: str
    cron_secret: str
    dashboard_user: str
    dashboard_pass: str
    csrf_secret: str

    # ── Google Gemini — PRD NFR-01 / L2-17 env var fix ────────────────────────
    gemini_api_key: str
    gemini_bulk_model: str = "gemini-2.0-flash-lite"
    gemini_grade_model: str = "gemini-2.5-flash"

    # ── Google OAuth / Drive / Gmail — PRD FR-11, FRD INT-02, INT-03 ──────────
    google_client_id: str
    google_client_secret: str
    google_refresh_token: str
    drive_folder_name: str = "AI_PM_SYSTEM"

    # ── Email — PRD FR-07 ──────────────────────────────────────────────────────
    sender_email: str
    recipient_email: str

    # ── Cost Control — PRD NFR-01 / FRD FS-12.4 ───────────────────────────────
    # Daily budget threshold for WARNING alert (₹3 = ~$0.035)
    daily_budget_alert_usd: float = 0.035
    # Monthly YELLOW ALERT — disable faithfulness checks (₹90 = ~$1.06)
    monthly_budget_yellow_usd: float = 1.06
    # Monthly RED ALERT — disable ALL Gemini calls (₹95 = ~$1.12)
    monthly_budget_red_usd: float = 1.12

    # ── Content Limits — PRD FR-01 ────────────────────────────────────────────
    min_article_words: int = 200
    max_article_words: int = 5000
    truncate_article_words: int = 3000
    max_arxiv_per_cycle: int = 10  # Joint cap across cs.AI + cs.LG

    # ── Scoring thresholds — PRD FR-02 ────────────────────────────────────────
    min_relevance_score: float = 6.5
    min_credibility_score: float = 6.0

    # ── Caching — PRD FR-11 / FRD FS-03.4 ────────────────────────────────────
    url_dedup_ttl_days: int = 2190
    grading_cache_ttl_days: int = 30
    summary_cache_ttl_days: int = 90
    max_cache_entries: int = 1000

    # ── Mastery thresholds — PRD FR-05 ────────────────────────────────────────
    mastery_advance_threshold: float = 70.0
    mastery_recovery_threshold: float = 75.0
    max_retries_per_depth: int = 2

    # ── Adaptive mode thresholds — PRD FR-05 / FRD FS-05.3 ───────────────────
    mode_low_days_reduced_3: int = 5
    mode_low_days_reduced_2: int = 10
    mode_low_days_minimal: int = 15
    mode_recovery_days: int = 3
    mode_pause_neutral_days: int = 7

    # ── Reteaching — L2-14 fix ────────────────────────────────────────────────
    reteaching_timeout_days: int = 14

    # ── Topic archival — PRD FR-04 ────────────────────────────────────────────
    topic_archive_inactive_days: int = 90

    # ── Feed health — PRD FR-01 ───────────────────────────────────────────────
    feed_auto_disable_failures: int = 5

    # ── RPD limits — PRD NFR-01 / L2-08 fix ──────────────────────────────────
    rpd_fallback_threshold: int = 90  # Fallback to bulk model at 90 RPD

    # ── Dedup thresholds — PRD FR-01 / L2-11 fix ─────────────────────────────
    dedup_definite_threshold: int = 85   # Above this → definite duplicate
    dedup_ambiguous_lower: int = 60      # 60-85 → ask Gemini to confirm

    # ── Per-domain rate limit — PRD FR-01 ────────────────────────────────────
    domain_requests_per_minute: int = 3

    # ── Scheduled slot windows (IST hour ranges) — PRD FR-10 ─────────────────
    slot_morning_start: int = 6
    slot_morning_end: int = 10
    slot_midday_start: int = 10
    slot_midday_end: int = 14
    slot_evening_start: int = 14
    slot_evening_end: int = 19

    # ── File retention caps — PRD FR-11 / FRD FS-11.1 ────────────────────────
    discarded_max_entries: int = 500
    errors_max_entries: int = 200

    # ── Faithfulness confidence — FRD FS-03.3 ────────────────────────────────
    faithfulness_low_confidence_threshold: int = 7
    faithfulness_parse_error_default: int = 5
    min_verified_sentences: int = 3

    # ── arXiv relevance keyword pre-filter — PRD FR-01 ───────────────────────
    arxiv_keywords: list[str] = [
        "product", "deployment", "production", "recommendation",
        "ranking", "serving", "inference", "optimization",
        "fine-tuning", "RLHF", "alignment", "evaluation", "benchmark",
    ]

    # ── Blocked domains (exact match) — L2-18 fix ────────────────────────────
    blocked_domains: list[str] = [
        "paywall-site.com",
        "premium-only.com",
    ]

    # ── Blocked URL patterns (regex) — L2-18 fix ─────────────────────────────
    blocked_url_patterns: list[str] = [
        r"medium\.com/.*/membership",
        r"towardsdatascience\.com/.*/membership",
        r"/premium/",
        r"/subscribe-to-unlock/",
    ]

    # ── Token limits per operation — PRD NFR-01 §Hard token limits ───────────
    token_limits: dict[str, int] = {
        "combined_scoring": 200,
        "title_dedup": 50,
        "extractive": 400,
        "summarization": 600,
        "faithfulness": 150,
        "grading": 400,
        "reteaching": 500,
        "quarterly_report": 800,
    }

    # ── Input truncation limits (tokens) ──────────────────────────────────────
    input_limits: dict[str, int] = {
        "combined_scoring": 1500,
        "title_dedup": 200,
        "extractive": 2000,
        "summarization": 800,
        "faithfulness": 1000,
        "grading": 800,
        "reteaching": 500,
        "quarterly_report": 2000,
    }

    # ── Gemini pricing (USD per token) — FRD FS-12.3 ─────────────────────────
    gemini_pricing: dict[str, dict[str, float]] = {
        "gemini-2.0-flash-lite": {
            "input": 0.075 / 1_000_000,
            "output": 0.30 / 1_000_000,
        },
        "gemini-2.5-flash": {
            "input": 0.30 / 1_000_000,
            "output": 2.50 / 1_000_000,
        },
    }

    @field_validator("environment")
    @classmethod
    def validate_env(cls, v: str) -> str:
        allowed = {"development", "production", "testing"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings instance. Use this everywhere."""
    return Settings()
