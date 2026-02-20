"""
app/routers/dashboard.py — HTML dashboard routes
TDD v2.0 §API Design (dashboard endpoints)
PRD v2.0 §FR-08 Dashboard, §NFR-02 Auth
FRD v2.0 §FS-08.2 Dashboard Authentication
HTTP Basic Auth + CSRF protection for all dashboard HTML pages.
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from loguru import logger

from app.clients import drive_client
from app.core.auth import verify_basic_auth
from app.core.rate_limiter import limiter, RATE_LIMITS
from app.models import (
    ArchivedTopicsFile,
    DiscardedFile,
    ErrorsFile,
    Metrics,
    PipelineState,
    TopicsFile,
)

router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _load_dashboard_state() -> dict[str, Any]:
    """Load all state files needed for dashboard rendering. Returns empty defaults on Drive failure."""
    def _safe_read(filename: str, model_class):
        try:
            data = drive_client.read_json_file(filename)
            return model_class(**(data or {}))
        except Exception:
            return model_class()

    try:
        return {
            "topics_file": _safe_read("topics.json", TopicsFile),
            "archived_file": _safe_read("archived_topics.json", ArchivedTopicsFile),
            "metrics": _safe_read("metrics.json", Metrics),
            "pipeline_state": _safe_read("pipeline_state.json", PipelineState),
            "discarded_file": _safe_read("discarded.json", DiscardedFile),
            "errors_file": _safe_read("errors.json", ErrorsFile),
        }
    except Exception:
        # Fallback: return all empty defaults so dashboard always renders
        return {
            "topics_file": TopicsFile(),
            "archived_file": ArchivedTopicsFile(),
            "metrics": Metrics(),
            "pipeline_state": PipelineState(),
            "discarded_file": DiscardedFile(),
            "errors_file": ErrorsFile(),
        }


# ──────────────────────────────────────────────────────────────────────────────
# GET /dashboard — Main dashboard
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
@limiter.limit(RATE_LIMITS["dashboard"])
async def dashboard_home(
    request: Request,
    _auth: bool = Depends(verify_basic_auth),
) -> HTMLResponse:
    """Main dashboard: active topics, streak, mode, slot status."""
    state = _load_dashboard_state()
    topics_file: TopicsFile = state["topics_file"]
    metrics: Metrics = state["metrics"]
    pipeline_state: PipelineState = state["pipeline_state"]

    try:
        from app.core.cost_tracker import get_budget_status, get_daily_cost
        budget_status = get_budget_status(metrics)
        daily_cost = get_daily_cost(metrics)
    except Exception:
        budget_status = "unknown"
        daily_cost = 0.0

    active_topics = [
        t for t in topics_file.topics
        if t.status.value not in ("archived", "completed")
    ]

    context = {
        "request": request,
        "topics": active_topics,
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

    return templates.TemplateResponse("dashboard.html", context)


# ──────────────────────────────────────────────────────────────────────────────
# GET /dashboard/topic/{topic_id} — Topic detail with grading form
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard/topic/{topic_id}", response_class=HTMLResponse)
@limiter.limit(RATE_LIMITS["dashboard"])
async def topic_detail(
    request: Request,
    topic_id: str,
    _auth: bool = Depends(verify_basic_auth),
) -> HTMLResponse:
    """Individual topic detail view with grading form."""
    try:
        topics_data = drive_client.read_json_file("topics.json")
        topics_file = TopicsFile(**(topics_data or {}))

        topic = next(
            (t for t in topics_file.topics if t.topic_id == topic_id), None
        )
        if topic is None:
            raise HTTPException(status_code=404, detail="Topic not found.")

        context = {
            "request": request,
            "topic": topic,
            "grade_endpoint": f"/api/grade",
        }
        return templates.TemplateResponse("topic_detail.html", context)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Topic detail render error: {exc}")
        raise HTTPException(status_code=500, detail="Topic detail unavailable.")


# ──────────────────────────────────────────────────────────────────────────────
# GET /dashboard/discarded — Discarded articles view
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard/discarded", response_class=HTMLResponse)
@limiter.limit(RATE_LIMITS["dashboard"])
async def discarded_view(
    request: Request,
    _auth: bool = Depends(verify_basic_auth),
) -> HTMLResponse:
    """View discarded articles with rejection reasons."""
    try:
        discarded_data = drive_client.read_json_file("discarded.json")
        discarded_file = DiscardedFile(**(discarded_data or {}))

        context = {
            "request": request,
            "discarded": discarded_file.entries[-50:],  # Show last 50
            "total_count": len(discarded_file.entries),
        }
        return templates.TemplateResponse("discarded.html", context)
    except Exception as exc:
        logger.error(f"Discarded view error: {exc}")
        raise HTTPException(status_code=500, detail="Discarded view unavailable.")


# ──────────────────────────────────────────────────────────────────────────────
# GET /dashboard/errors — Error log view
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard/errors", response_class=HTMLResponse)
@limiter.limit(RATE_LIMITS["dashboard"])
async def errors_view(
    request: Request,
    _auth: bool = Depends(verify_basic_auth),
) -> HTMLResponse:
    """View recent system errors."""
    try:
        errors_data = drive_client.read_json_file("errors.json")
        errors_file = ErrorsFile(**(errors_data or {}))

        context = {
            "request": request,
            "errors": errors_file.errors[-30:],
        }
        return templates.TemplateResponse("health.html", context)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Error log unavailable.")
