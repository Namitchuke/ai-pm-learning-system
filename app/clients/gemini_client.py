"""
app/clients/gemini_client.py — Google Gemini API client
TDD v2.0 §Infrastructure Layer (gemini_client.py)
PRD v2.0 §NFR-01 Cost Control, §NFR-02 (L2-08 RPD tracking, L2-17 deprecation)
FRD v2.0 §INT-01 Gemini API, §FS-12.2 RPD Tracking
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

import google.generativeai as genai
from google.api_core.exceptions import (
    NotFound,
    ResourceExhausted,
    ServiceUnavailable,
)
from loguru import logger

from app.config import get_settings
from app.core import logging as app_logging
from app.core.cost_tracker import calculate_cost, increment_rpd

settings = get_settings()

# Global flag: if grade model is deprecated, all grade calls → bulk
_grade_model_deprecated: bool = False


def _configure_genai() -> None:
    """Configure Gemini SDK with API key from env."""
    genai.configure(api_key=settings.gemini_api_key)


_configure_genai()


# ──────────────────────────────────────────────────────────────────────────────
# Core Gemini call with retry and fallback — L2-17 fix
# ──────────────────────────────────────────────────────────────────────────────

class GeminiModelDeprecatedError(Exception):
    """Raised when a Gemini model is deprecated / not found."""


def call_gemini(
    model: str,
    prompt: str,
    max_output_tokens: int,
    temperature: float = 0.0,
    daily_rpd: Optional[dict[str, int]] = None,
    operation: str = "unknown",
    metrics: Optional[Any] = None,
) -> dict[str, Any]:
    """
    Core Gemini API call with:
    - RPD tracking (L2-08)
    - Model deprecation handling (L2-17)
    - Cost logging (FRD FS-12.1)
    - Retry on transient errors

    Returns dict with 'text' and 'usage' keys.
    Raises GeminiModelDeprecatedError on 404 / model-not-found.
    Raises RuntimeError on persistent API failures.
    """
    global _grade_model_deprecated

    start_time = time.monotonic()

    # Increment RPD counter before each call
    if daily_rpd is not None:
        increment_rpd(daily_rpd, model)

    last_exc: Optional[Exception] = None

    for attempt in range(3):
        try:
            gen_model = genai.GenerativeModel(
                model,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
            )
            response = gen_model.generate_content(prompt)
            latency_ms = (time.monotonic() - start_time) * 1000

            # Extract token counts
            usage = response.usage_metadata if hasattr(response, "usage_metadata") else None
            input_tokens = usage.prompt_token_count if usage else 0
            output_tokens = usage.candidates_token_count if usage else 0
            cost = calculate_cost(model, input_tokens, output_tokens)

            # Log the call — PRD NFR-04
            rpd_count = daily_rpd.get(model, 0) if daily_rpd else 0
            app_logging.log_gemini_call(
                model=model,
                operation=operation,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
                tier_used="free",
                rpd_count=rpd_count,
            )

            # Log to metrics cost tracker
            if metrics is not None:
                from app.core.cost_tracker import log_api_call
                log_api_call(
                    metrics=metrics,
                    model=model,
                    operation=operation,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

            text = response.text.strip() if response.text else ""
            return {"text": text, "input_tokens": input_tokens, "output_tokens": output_tokens, "cost_usd": cost}

        except (NotFound, Exception) as exc:
            exc_str = str(exc).lower()
            # Detect model deprecation — L2-17 fix
            if "not found" in exc_str or "model" in exc_str and "not found" in exc_str:
                raise GeminiModelDeprecatedError(
                    f"Model '{model}' not found (possibly deprecated): {exc}"
                ) from exc

            if isinstance(exc, ResourceExhausted):
                # 429 — exponential backoff
                wait = (2 ** attempt)
                logger.warning(f"Gemini 429 rate limit on attempt {attempt+1}. Waiting {wait}s.")
                time.sleep(wait)
                last_exc = exc
                continue

            if isinstance(exc, ServiceUnavailable):
                # 5xx — retry once
                if attempt < 2:
                    time.sleep(1)
                    last_exc = exc
                    continue

            last_exc = exc
            logger.error(f"Gemini call failed (attempt {attempt+1}): {exc}")
            if attempt < 2:
                time.sleep(1)

    raise RuntimeError(
        f"Gemini call failed after 3 attempts for model '{model}': {last_exc}"
    )


def call_gemini_with_fallback(
    model_env_var: str,
    prompt: str,
    max_output_tokens: int,
    temperature: float = 0.0,
    daily_rpd: Optional[dict[str, int]] = None,
    operation: str = "unknown",
    metrics: Optional[Any] = None,
    alert_on_deprecation: bool = True,
) -> dict[str, Any]:
    """
    L2-17 fix: Call Gemini with automatic fallback to bulk model on deprecation.
    On 'model not found':
    1. Log CRITICAL error
    2. Queue alert email to user
    3. Fall back to GEMINI_BULK_MODEL for this and all subsequent calls
    FRD FS-06.6, TDD §Loophole Fix Summary L2-17.
    """
    global _grade_model_deprecated

    model = os.getenv(model_env_var, settings.gemini_bulk_model)
    bulk_model = settings.gemini_bulk_model

    # If grade model already known deprecated, skip directly to bulk
    if model_env_var == "GEMINI_GRADE_MODEL" and _grade_model_deprecated:
        model = bulk_model

    try:
        return call_gemini(
            model=model,
            prompt=prompt,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            daily_rpd=daily_rpd,
            operation=operation,
            metrics=metrics,
        )
    except GeminiModelDeprecatedError as dep_exc:
        # L2-17: Mark model as deprecated system-wide
        if model_env_var == "GEMINI_GRADE_MODEL":
            _grade_model_deprecated = True

        logger.critical(
            f"CRITICAL: Model '{model}' is deprecated. Falling back to '{bulk_model}'. "
            f"Please update {model_env_var} env var. Error: {dep_exc}"
        )

        # Queue alert email (non-blocking — handled by caller or next task)
        # The alert is queued via a flag checked in the morning trigger
        if alert_on_deprecation:
            _schedule_deprecation_alert(model, model_env_var)

        # Fall back to bulk model
        return call_gemini(
            model=bulk_model,
            prompt=prompt,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            daily_rpd=daily_rpd,
            operation=operation,
            metrics=metrics,
        )


# Alert queue for model deprecation — written to errors.json by pipeline
_pending_deprecation_alerts: list[dict] = []


def _schedule_deprecation_alert(model: str, env_var: str) -> None:
    """Queue a deprecation alert. Consumed by the email service on next run."""
    _pending_deprecation_alerts.append({
        "model": model,
        "env_var": env_var,
        "detected_at": time.time(),
    })


def get_pending_deprecation_alerts() -> list[dict]:
    """Return and clear pending deprecation alerts."""
    alerts = list(_pending_deprecation_alerts)
    _pending_deprecation_alerts.clear()
    return alerts


# ──────────────────────────────────────────────────────────────────────────────
# JSON extraction helper
# ──────────────────────────────────────────────────────────────────────────────

def extract_json_from_response(text: str) -> dict[str, Any]:
    """
    Safely extract JSON from a Gemini response text.
    Handles markdown code fences (```json ... ```) or raw JSON.
    Returns empty dict on parse failure.
    """
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence line
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find the first `{` and parse from there
        start = text.find("{")
        if start != -1:
            try:
                return json.loads(text[start:])
            except json.JSONDecodeError:
                pass
    return {}
