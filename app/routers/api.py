"""
app/routers/api.py — Programmatic API endpoints
TDD v2.0 §API Design
PRD v2.0 §FR-06 Answer Grading, §NFR-02 Auth, §NFR-03 Health
FRD v2.0 §FS-06 Grading Engine, §FS-08 API Endpoints
Endpoints: /api/grade, /api/health, /api/dashboard-data
Dual auth: API Key OR Basic Auth (L2-13, L2-19 fixes).
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger

from app.clients import drive_client
from app.clients.drive_client import check_oauth_valid
from app.core.auth import dual_auth, verify_api_key
from app.core.rate_limiter import limiter, RATE_LIMITS
from app.models import (
    CacheData,
    ErrorsFile,
    GradeRequest,
    GradeResponse,
    GradingDecision,
    Metrics,
    PipelineState,
    TopicStatus,
    TopicsFile,
)
from app.services import grading as grading_service
from app.utils.timezone import today_ist_str

router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────────
# POST /api/grade — FRD FS-06.1 / L2-13 dual auth
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/grade", response_model=GradeResponse)
@limiter.limit(RATE_LIMITS["grading"])
async def grade_answer(
    request: Request,
    body: GradeRequest,
    _auth: bool = Depends(dual_auth),
) -> GradeResponse:
    """
    Submit an answer for a topic and receive grading.
    Dual auth: X-API-Key header OR HTTP Basic Auth (L2-13 fix).
    L2-03: Cache hit = display-only (no state transitions).
    L2-08: Model downgrade warning included in response.
    FRD BR-05: Reject if answer length < 50 chars.
    FRD BR-05c: Reject if same answer hash submitted ≥ 3 times.
    """
    if len(body.answer_text.strip()) < 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Answer must be at least 50 characters.",
        )

    try:
        # Load required state from Drive
        topics_data = drive_client.read_json_file("topics.json")
        cache_data = drive_client.read_json_file("cache.json")
        pipeline_data = drive_client.read_json_file("pipeline_state.json")
        metrics_data = drive_client.read_json_file("metrics.json")

        topics_file = TopicsFile(**(topics_data or {}))
        cache = CacheData(**(cache_data or {}))
        pipeline_state = PipelineState(**(pipeline_data or {}))
        metrics = Metrics(**(metrics_data or {}))

        # Find topic
        topic = next(
            (t for t in topics_file.topics if t.topic_id == body.topic_id),
            None,
        )
        if topic is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Topic {body.topic_id!r} not found.",
            )

        if topic.status == TopicStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Topic is already completed.",
            )

        if topic.status == TopicStatus.ARCHIVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Topic is archived. Archive topics cannot be graded.",
            )

        # FRD BR-05c: Check same-answer repeat limit (3x max)
        from app.core.cache_manager import get_answer_submission_count
        submission_count = get_answer_submission_count(
            cache, body.topic_id, topic.current_depth, body.answer_text
        )
        if submission_count >= 3:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "This exact answer has been submitted 3+ times. "
                    "Please modify your answer to receive a fresh evaluation."
                ),
            )

        # Grade the answer
        result = grading_service.grade_answer(
            topic=topic,
            answer_text=body.answer_text,
            cache=cache,
            pipeline_state=pipeline_state,
            metrics=metrics,
        )

        # Persist updated state (only if not cached — L2-03)
        if not result.cached:
            drive_client.write_json_file(
                "topics.json", topics_file.model_dump(mode="json")
            )
            drive_client.write_json_file(
                "cache.json", cache.model_dump(mode="json")
            )
            drive_client.write_json_file(
                "pipeline_state.json", pipeline_state.model_dump(mode="json")
            )
            drive_client.write_json_file(
                "metrics.json", metrics.model_dump(mode="json")
            )

        return result

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Grade endpoint error for topic {body.topic_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Grading failed: {str(exc)}",
        )


# ──────────────────────────────────────────────────────────────────────────────
# GET /api/health — PRD NFR-03 / TDD §Health Check
# Public endpoint — no auth required
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/health")
@limiter.limit(RATE_LIMITS["health"])
async def health_check(request: Request) -> dict[str, Any]:
    """
    System health check.
    PRD NFR-03: Check Google OAuth, Drive connectivity, Gemini API key presence.
    Returns HTTP 200 if healthy, 503 if degraded.
    """
    checks: dict[str, Any] = {}
    healthy = True

    # OAuth token valid?
    try:
        checks["google_oauth"] = check_oauth_valid()
        if not checks["google_oauth"]:
            healthy = False
    except Exception as exc:
        checks["google_oauth"] = False
        checks["google_oauth_error"] = str(exc)
        healthy = False

    # Drive connectivity: can we list the folder?
    try:
        folder_id = drive_client.get_or_create_folder()
        checks["drive_connected"] = bool(folder_id)
        if not checks["drive_connected"]:
            healthy = False
    except Exception as exc:
        checks["drive_connected"] = False
        checks["drive_error"] = str(exc)
        healthy = False

    # Gemini API key present?
    from app.config import get_settings
    s = get_settings()
    checks["gemini_api_key_set"] = bool(s.gemini_api_key and s.gemini_api_key != "sk-...")

    # Budget status
    try:
        metrics_data = drive_client.read_json_file("metrics.json")
        metrics = Metrics(**(metrics_data or {}))
        from app.core.cost_tracker import get_budget_status, BudgetStatus
        budget_status = get_budget_status(metrics)
        checks["budget_status"] = budget_status
        if budget_status == BudgetStatus.RED:
            healthy = False
    except Exception:
        checks["budget_status"] = "unknown"

    status_code = 200 if healthy else 503
    return {
        "status": "healthy" if healthy else "degraded",
        "checks": checks,
        "timestamp": today_ist_str(),
    }


# ──────────────────────────────────────────────────────────────────────────────
# GET /api/dashboard-data — L2-19 fix: dual auth for JSON data
# FRD FS-08.3
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard-data")
@limiter.limit(RATE_LIMITS["dashboard"])
async def dashboard_data(
    request: Request,
    _auth: bool = Depends(dual_auth),
) -> dict[str, Any]:
    """
    JSON API returning dashboard-ready data.
    L2-19 fix: Accepts both API Key and Basic Auth (same as /api/grade).
    FRD FS-08.3.
    """
    try:
        topics_data = drive_client.read_json_file("topics.json")
        metrics_data = drive_client.read_json_file("metrics.json")
        pipeline_data = drive_client.read_json_file("pipeline_state.json")
        discarded_data = drive_client.read_json_file("discarded.json")

        topics_file = TopicsFile(**(topics_data or {}))
        metrics = Metrics(**(metrics_data or {}))
        pipeline_state = PipelineState(**(pipeline_data or {}))

        from app.core.cost_tracker import get_budget_status, get_daily_cost
        budget_status = get_budget_status(metrics)
        daily_cost = get_daily_cost(metrics)

        active_topics = [
            {
                "topic_id": t.topic_id,
                "topic_name": t.topic_name,
                "category": t.category.value,
                "current_depth": t.current_depth,
                "mastery_score": round(t.mastery_score, 1),
                "status": t.status.value,
                "retries_used": t.retries_used,
                "source_tier": t.source_tier,
                "tldr": t.summary.tldr if t.summary else "",
            }
            for t in topics_file.topics
            if t.status.value != "archived"
        ]

        return {
            "active_topics": active_topics,
            "topic_count": len(active_topics),
            "streak": metrics.streak_count,
            "longest_streak": metrics.longest_streak,
            "current_mode": metrics.current_topic_mode.value,
            "budget_status": budget_status,
            "daily_cost_usd": round(daily_cost, 4),
            "pipeline_state_date": pipeline_state.date,
            "slot_statuses": {
                slot: s.status.value
                for slot, s in pipeline_state.slots.items()
            },
        }

    except Exception as exc:
        logger.error(f"Dashboard-data endpoint error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Dashboard data unavailable: {str(exc)}",
        )
