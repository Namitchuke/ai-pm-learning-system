"""
app/core/cost_tracker.py — Gemini API cost tracking and budget kill switch
TDD v2.0 §Cost Tracker
PRD v2.0 §NFR-01 Cost Control (Loophole #3 fix + L2-12 alignment)
FRD v2.0 §FS-12 Cost Tracking & Budget Control
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

from app.config import get_settings
from app.models import Metrics, MonthlyCostEntry

settings = get_settings()


# ──────────────────────────────────────────────────────────────────────────────
# Cost Calculation — FRD FS-12.3
# ──────────────────────────────────────────────────────────────────────────────

def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Calculate USD cost of a Gemini API call.
    FRD FS-12.3: Uses PRICING dict from config.
    Falls back to bulk model pricing for unknown models.
    """
    pricing = settings.gemini_pricing.get(
        model,
        settings.gemini_pricing.get(settings.gemini_bulk_model, {
            "input": 0.075 / 1_000_000,
            "output": 0.30 / 1_000_000,
        }),
    )
    return (input_tokens * pricing["input"]) + (output_tokens * pricing["output"])


# ──────────────────────────────────────────────────────────────────────────────
# Budget status — FRD FS-12.4
# ──────────────────────────────────────────────────────────────────────────────

class BudgetStatus:
    NORMAL = "normal"
    YELLOW = "yellow"   # ₹90 → disable faithfulness checks
    RED = "red"         # ₹95 → disable ALL Gemini


def get_budget_status(metrics: Metrics) -> str:
    """
    Return current budget status based on monthly spend.
    FRD FS-12.4 / PRD NFR-01:
    - YELLOW at ₹90 ($1.06): disable non-essential AI calls
    - RED at ₹95 ($1.12): disable everything + critical alert
    """
    month_key = datetime.utcnow().strftime("%Y-%m")
    monthly = metrics.monthly_cost_tracker.get(month_key)
    if monthly is None:
        return BudgetStatus.NORMAL

    cost = monthly.total_cost_usd
    if cost >= settings.monthly_budget_red_usd:
        return BudgetStatus.RED
    if cost >= settings.monthly_budget_yellow_usd:
        return BudgetStatus.YELLOW
    return BudgetStatus.NORMAL


def is_gemini_allowed(metrics: Metrics, operation: str = "") -> bool:
    """
    Return True if Gemini calls are permitted given current budget.
    RED → no Gemini calls at all.
    YELLOW → only grading and scoring; faithfulness disabled.
    """
    status = get_budget_status(metrics)
    if status == BudgetStatus.RED:
        return False
    return True


def is_faithfulness_allowed(metrics: Metrics) -> bool:
    """
    PRD NFR-01: At YELLOW budget, disable faithfulness checks (non-essential).
    """
    return get_budget_status(metrics) == BudgetStatus.NORMAL


def get_daily_cost(metrics: Metrics) -> float:
    """Return total cost for today from the monthly tracker."""
    month_key = datetime.utcnow().strftime("%Y-%m")
    monthly = metrics.monthly_cost_tracker.get(month_key)
    if monthly is None:
        return 0.0
    # NOTE: We approximate daily cost from monthly for budget alerts.
    # A dedicated daily_cost field could be added in v3.
    day_of_month = datetime.utcnow().day
    if day_of_month == 0:
        return 0.0
    return monthly.total_cost_usd / day_of_month  # rough daily average


# ──────────────────────────────────────────────────────────────────────────────
# Log API call — FRD FS-12.1
# ──────────────────────────────────────────────────────────────────────────────

def log_api_call(
    metrics: Metrics,
    model: str,
    operation: str,
    input_tokens: int,
    output_tokens: int,
    tier_used: str = "free",
) -> float:
    """
    Record a Gemini API call in metrics.monthly_cost_tracker.
    Returns the cost in USD.
    FRD FS-12.1: Log every API call with model, operation, tokens, cost.
    """
    cost = calculate_cost(model, input_tokens, output_tokens)
    month_key = datetime.utcnow().strftime("%Y-%m")

    if month_key not in metrics.monthly_cost_tracker:
        metrics.monthly_cost_tracker[month_key] = MonthlyCostEntry()

    entry = metrics.monthly_cost_tracker[month_key]
    entry.total_input_tokens += input_tokens
    entry.total_output_tokens += output_tokens
    entry.total_cost_usd = round(entry.total_cost_usd + cost, 8)

    # Track per-operation counts
    if operation not in entry.calls_by_operation:
        entry.calls_by_operation[operation] = {
            "count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }
    op = entry.calls_by_operation[operation]
    op["count"] += 1
    op["input_tokens"] += input_tokens
    op["output_tokens"] += output_tokens

    return cost


# ──────────────────────────────────────────────────────────────────────────────
# RPD (Requests Per Day) tracking — L2-08 fix
# ──────────────────────────────────────────────────────────────────────────────

def increment_rpd(pipeline_state_daily_rpd: dict[str, int], model: str) -> int:
    """
    Increment and return the daily request count for a model.
    FRD FS-12.2 / PRD NFR-01: Track RPD per model in pipeline_state.json.
    """
    current = pipeline_state_daily_rpd.get(model, 0)
    pipeline_state_daily_rpd[model] = current + 1
    return current + 1


def should_fallback_to_bulk(
    pipeline_state_daily_rpd: dict[str, int],
    grade_model: str,
) -> bool:
    """
    L2-08 fix: If grade model RPD ≥ 90, fall back to bulk model.
    FRD FS-12.2.
    """
    return pipeline_state_daily_rpd.get(grade_model, 0) >= settings.rpd_fallback_threshold


def get_grading_model(
    pipeline_state_daily_rpd: dict[str, int],
) -> tuple[str, Optional[str]]:
    """
    L2-08 fix: Return (model_id, quality_warning_message | None).
    FRD FS-06.3.
    """
    grade_model = settings.gemini_grade_model
    bulk_model = settings.gemini_bulk_model

    if should_fallback_to_bulk(pipeline_state_daily_rpd, grade_model):
        warning = (
            f"Graded with lighter model due to daily rate limit "
            f"({pipeline_state_daily_rpd.get(grade_model, 0)}/100 RPD reached)"
        )
        return bulk_model, warning

    return grade_model, None
