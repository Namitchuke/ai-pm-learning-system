"""
app/core/logging.py — loguru structured JSON logging setup
TDD v2.0 §Error Logging
PRD v2.0 §NFR-04 Logging & Observability (Loophole #15 fix)
FRD v2.0 §NFR-04
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime
from typing import Any, Optional

from loguru import logger


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure loguru for structured JSON output to stdout.
    Render captures stdout and displays in its dashboard.
    PRD NFR-04: Log to stdout + monthly system_logs_{YYYY_MM}.json on Drive.
    """
    # Remove default loguru handler
    logger.remove()

    # Add structured JSON handler to stdout
    logger.add(
        sys.stdout,
        level=log_level.upper(),
        format="{message}",  # Raw message (we format as JSON ourselves)
        serialize=True,       # loguru built-in JSON serialization
        backtrace=True,
        diagnose=False,       # Disable in production for safety
        colorize=False,
    )


def _build_log_record(
    component: str,
    operation: str,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build a base structured log record."""
    record: dict[str, Any] = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "component": component,
        "operation": operation,
    }
    if extra:
        record.update(extra)
    return record


# ──────────────────────────────────────────────────────────────────────────────
# Mandatory log event helpers — PRD NFR-04 §Mandatory log events
# ──────────────────────────────────────────────────────────────────────────────

def log_gemini_call(
    model: str,
    operation: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: float,
    tier_used: str,
    rpd_count: int,
) -> None:
    """PRD NFR-04: Every Gemini API call must be logged."""
    record = _build_log_record("gemini_client", "api_call", {
        "model": model,
        "operation": operation,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_usd, 8),
        "latency_ms": round(latency_ms, 2),
        "tier_used": tier_used,
        "rpd_count": rpd_count,
    })
    logger.info(json.dumps(record))


def log_drive_operation(
    filename: str,
    operation: str,  # read | write | backup | restore
    success: bool,
    latency_ms: float,
    etag_used: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """PRD NFR-04: Every Google Drive read/write must be logged."""
    record = _build_log_record("drive_client", operation, {
        "filename": filename,
        "success": success,
        "latency_ms": round(latency_ms, 2),
        "etag_used": etag_used,
        "error": error,
    })
    logger.info(json.dumps(record))


def log_rss_fetch(
    source_url: str,
    source_tier: int,
    articles_found: int,
    articles_new: int,
    slot: str,
    error: Optional[str] = None,
) -> None:
    """PRD NFR-04: Every RSS fetch must be logged."""
    record = _build_log_record("rss_pipeline", "rss_fetch", {
        "source_url": source_url,
        "source_tier": source_tier,
        "articles_found": articles_found,
        "articles_new": articles_new,
        "slot": slot,
        "error": error,
    })
    logger.info(json.dumps(record))


def log_email_send(
    topics_count: int,
    success: bool,
    streak_count: int,
    error: Optional[str] = None,
) -> None:
    """PRD NFR-04: Every email send must be logged."""
    record = _build_log_record("email_service", "email_send", {
        "topics_count": topics_count,
        "success": success,
        "streak_count": streak_count,
        "error": error,
    })
    logger.info(json.dumps(record))


def log_grading(
    topic_id: str,
    depth: int,
    score: float,
    decision: str,
    model_used: str,
    cached: bool,
    error: Optional[str] = None,
) -> None:
    """PRD NFR-04: Every grading submission must be logged."""
    record = _build_log_record("grading_engine", "grade_answer", {
        "topic_id": topic_id,
        "depth": depth,
        "score": score,
        "decision": decision,
        "model_used": model_used,
        "cached": cached,
        "error": error,
    })
    logger.info(json.dumps(record))


def log_error(
    component: str,
    operation: str,
    error: Exception,
    context: Optional[dict[str, Any]] = None,
) -> None:
    """PRD NFR-04: Every error must be logged with full context."""
    tb = traceback.format_exc()
    record = _build_log_record(component, operation, {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "stack_trace": tb[:2000] if tb else "",
        "context": context or {},
    })
    logger.error(json.dumps(record))


def log_slot_transition(
    slot: str,
    old_status: str,
    new_status: str,
) -> None:
    """PRD NFR-04: Every slot status transition must be logged."""
    record = _build_log_record("pipeline", "slot_transition", {
        "slot": slot,
        "old_status": old_status,
        "new_status": new_status,
    })
    logger.info(json.dumps(record))


def log_mode_transition(
    old_mode: str,
    new_mode: str,
    trigger_reason: str,
) -> None:
    """PRD NFR-04: Every adaptive mode transition must be logged."""
    record = _build_log_record("adaptive_mode", "mode_transition", {
        "old_mode": old_mode,
        "new_mode": new_mode,
        "trigger_reason": trigger_reason,
    })
    logger.info(json.dumps(record))
