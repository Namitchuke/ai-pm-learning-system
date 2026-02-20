"""
app/services/grading.py — Answer grading engine with reteaching support
TDD v2.0 §Core Services (grading.py)
PRD v2.0 §FR-06 Check-Your-Understanding & Mastery Tracking
FRD v2.0 §FS-06 Grading Engine
L2-03 fix: Cache hit returns display-only — NO state transitions.
L2-08 fix: RPD-aware model selection with fallback to bulk.
L2-14 fix: Reteaching entries auto-revert after 14 days.
L2-15 fix: mastery_score = latest grade score; daily avg includes ALL grades.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from app.clients.gemini_client import call_gemini_with_fallback, extract_json_from_response
from app.config import get_settings
from app.core import cache_manager, logging as app_logging
from app.core.cost_tracker import get_grading_model
from app.models import (
    CacheData,
    GradeBreakdown,
    GradeResponse,
    GradingDecision,
    HistoryEntry,
    Metrics,
    PipelineState,
    ReteachContent,
    Topic,
    TopicStatus,
    TopicsFile,
)
from app.utils.validators import extract_float_from_dict

settings = get_settings()
PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"

# ── Rubric weight distribution (must sum to 100) — FRD FS-06.3 ────────────────
RUBRIC_WEIGHTS = {
    "concept_clarity": 25,
    "technical_correctness": 25,
    "application_thinking": 25,
    "ai_pm_relevance": 25,
}

_GRADING_PROMPT_FALLBACK = """
You are an expert AI PM educator grading a student answer.

TOPIC: {topic_name}
DEPTH LEVEL: {depth}/5

TOPIC CONTEXT (from summary):
{context}

STUDENT ANSWER:
{answer}

Grade on a 4-dimension rubric (0-25 points each, total 100):

1. concept_clarity (0-25): Does the student clearly understand and explain the core concept?
2. technical_correctness (0-25): Are the technical details accurate and precise?
3. application_thinking (0-25): Does the student demonstrate how to apply this in product work?
4. ai_pm_relevance (0-25): Is the response relevant to the work of an AI PM?

DECISION RULES:
- Score ≥ 70: ADVANCE to depth {next_depth}
- Score 40-69 with retries remaining (retries_used < {max_retries}): RETRY at same depth
- Score 40-69 with no retries left: RETEACH (full re-engagement)
- Score < 40: RETEACH immediately

Respond ONLY with JSON:
{{
  "concept_clarity": <0-25>,
  "technical_correctness": <0-25>,
  "application_thinking": <0-25>,
  "ai_pm_relevance": <0-25>,
  "feedback": "<1-2 sentences of specific, constructive feedback>",
  "decision": "advance|retry|reteach"
}}
"""

_RETEACH_PROMPT_FALLBACK = """
You are an AI PM educator. A student has failed to master a topic at depth {depth}.
Break it down into simpler sub-concepts to help them re-engage.

TOPIC: {topic_name}
DEPTH: {depth}/5

ORIGINAL SUMMARY:
{context}

Produce a reteaching plan:
{{
  "sub_concepts": [
    {{"name": "<concept>", "explanation": "<simple explanation in 2-3 sentences>"}},
    ...
  ],
  "reteach_question": "<A simpler question to help the student engage with the fundamentals>"
}}

Include 3-5 sub-concepts. Plain English only.
"""


def _load_grading_prompt() -> str:
    try:
        return (PROMPTS_DIR / "grading.txt").read_text(encoding="utf-8")
    except FileNotFoundError:
        return _GRADING_PROMPT_FALLBACK


def _load_reteach_prompt() -> str:
    try:
        return (PROMPTS_DIR / "reteach.txt").read_text(encoding="utf-8")
    except FileNotFoundError:
        return _RETEACH_PROMPT_FALLBACK


def _build_context(topic: Topic) -> str:
    """Build grading context from topic summary."""
    s = topic.summary
    return (
        f"Why it matters: {s.why_it_matters}\n"
        f"Core mechanism: {s.core_mechanism}\n"
        f"Applications: {s.product_applications}\n"
        f"TL;DR: {s.tldr}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Grading logic — FRD FS-06.3
# ──────────────────────────────────────────────────────────────────────────────

def _determine_decision(
    score: float,
    retries_used: int,
) -> GradingDecision:
    """
    FRD FS-06.3 decision logic:
    ≥70 → ADVANCE
    40-69 + retries left → RETRY
    40-69 + no retries → RETEACH
    <40 → RETEACH
    """
    if score >= settings.mastery_advance_threshold:
        return GradingDecision.ADVANCE
    elif score < 40:
        return GradingDecision.RETEACH
    elif retries_used < settings.max_retries_per_depth:
        return GradingDecision.RETRY
    else:
        return GradingDecision.RETEACH


def _apply_decision(
    topic: Topic,
    decision: GradingDecision,
    score: float,
    answer_hash: str,
    feedback: str,
    breakdown: dict[str, float],
    model_used: str,
    reteach_content: Optional[dict] = None,
) -> None:
    """
    Apply grading decision to topic state.
    L2-15 fix: mastery_score = latest score (not average).
    L2-14 fix: Reteaching entered_at is tracked for auto-revert.
    """
    # L2-15: mastery_score is always the most recent grade score
    topic.mastery_score = score
    topic.last_active = datetime.utcnow()
    topic.last_updated = datetime.utcnow()

    entry = HistoryEntry(
        date=datetime.utcnow(),
        depth=topic.current_depth,
        score=score,
        answer_hash=answer_hash,
        decision=decision,
        feedback=feedback,
        model_used=model_used,
        cached=False,
        reteach_content=reteach_content,
    )
    topic.history.append(entry)

    if decision == GradingDecision.ADVANCE:
        topic.current_depth = min(topic.current_depth + 1, 5)
        topic.retries_used = 0
        if topic.current_depth > 5:
            topic.status = TopicStatus.COMPLETED
        if topic.status == TopicStatus.RETEACHING:
            topic.status = TopicStatus.ACTIVE  # Clear reteaching on advance

    elif decision == GradingDecision.RETRY:
        topic.retries_used += 1

    elif decision == GradingDecision.RETEACH:
        topic.retries_used = 0
        topic.status = TopicStatus.RETEACHING
        topic.reteaching_entered_at = datetime.utcnow()  # L2-14


# ──────────────────────────────────────────────────────────────────────────────
# Reteaching content generation — FRD FS-06.5
# ──────────────────────────────────────────────────────────────────────────────

def generate_reteach_content(
    topic: Topic,
    daily_rpd: dict[str, int],
    metrics: Optional[Metrics] = None,
) -> Optional[dict]:
    """Generate simplified sub-concept breakdown for reteaching. FRD FS-06.5."""
    prompt_template = _load_reteach_prompt()
    prompt = prompt_template.format(
        topic_name=topic.topic_name,
        depth=topic.current_depth,
        context=_build_context(topic),
    )
    try:
        result = call_gemini_with_fallback(
            model_env_var="GEMINI_BULK_MODEL",
            prompt=prompt,
            max_output_tokens=settings.token_limits["reteaching"],
            temperature=0.3,
            daily_rpd=daily_rpd,
            operation="reteaching",
            metrics=metrics,
        )
        return extract_json_from_response(result.get("text", ""))
    except Exception as exc:
        logger.error(f"Reteach generation failed for {topic.topic_name}: {exc}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Main grading function — FRD FS-06.1 / FS-06.2 / FS-06.3
# ──────────────────────────────────────────────────────────────────────────────

def grade_answer(
    topic: Topic,
    answer_text: str,
    cache: CacheData,
    pipeline_state: PipelineState,
    metrics: Optional[Metrics] = None,
) -> GradeResponse:
    """
    Grade a student's answer for a topic.

    L2-03 fix: If cache hit, return display-only result — do NOT advance topic state.
    L2-08 fix: Use get_grading_model() which respects RPD and falls back gracefully.
    L2-15 fix: mastery_score = latest score (applied in _apply_decision).
    """
    daily_rpd = pipeline_state.daily_rpd
    answer_hash = cache_manager.hash_answer(answer_text)

    # ── L2-03: Check grading cache FIRST ──────────────────────────────────────
    cache_entry = cache_manager.get_cached_grade(
        cache, topic.topic_id, topic.current_depth, answer_text
    )
    if cache_entry:
        result = cache_entry.result
        app_logging.log_grading(
            topic_id=topic.topic_id,
            depth=topic.current_depth,
            score=result.score,
            decision=result.decision.value,
            model_used=result.model_used,
            cached=True,
        )
        return GradeResponse(
            success=True,
            topic_id=topic.topic_id,
            topic_name=topic.topic_name,
            depth=topic.current_depth,
            score=result.score,
            breakdown=GradeBreakdown(**result.breakdown),
            feedback=result.feedback,
            decision=result.decision,
            new_depth=topic.current_depth,  # No advancement on cache hit
            retries_remaining=max(0, settings.max_retries_per_depth - topic.retries_used),
            model_used=result.model_used,
            cached=True,
            message="Cached result — no progress changes applied. Modify your answer for fresh evaluation.",
        )

    # ── L2-08: Select grading model with RPD-aware fallback ───────────────────
    model_id, quality_warning = get_grading_model(daily_rpd)

    # ── Build and send grading prompt ─────────────────────────────────────────
    prompt_template = _load_grading_prompt()
    import json
    examples_json = "{}"
    try:
        examples_json = (PROMPTS_DIR / "grading_examples.json").read_text(encoding="utf-8")
    except FileNotFoundError:
        pass

    import os
    model_env_var = (
        "GEMINI_GRADE_MODEL"
        if model_id == settings.gemini_grade_model
        else "GEMINI_BULK_MODEL"
    )

    prompt = prompt_template.format(
        topic_name=topic.topic_name,
        depth=topic.current_depth,
        context=_build_context(topic),
        answer=answer_text[:800],  # Truncate long answers
        next_depth=min(topic.current_depth + 1, 5),
        max_retries=settings.max_retries_per_depth,
        examples=examples_json,
    )

    result_data = call_gemini_with_fallback(
        model_env_var=model_env_var,
        prompt=prompt,
        max_output_tokens=settings.token_limits["grading"],
        temperature=0.0,
        daily_rpd=daily_rpd,
        operation="grading",
        metrics=metrics,
    )

    parsed = extract_json_from_response(result_data.get("text", ""))
    if not parsed:
        raise ValueError("Failed to parse grading response from Gemini.")

    # Extract scores
    breakdown = {
        dim: extract_float_from_dict(parsed, dim, 0.0, 0.0, 25.0)
        for dim in RUBRIC_WEIGHTS
    }
    score = sum(breakdown.values())
    feedback = parsed.get("feedback", "No feedback available.")
    raw_decision = parsed.get("decision", "retry")

    # Map decision (Gemini may say "advance", "retry", "reteach")
    decision = _determine_decision(score, topic.retries_used)

    # Cache the result BEFORE applying state — so cache stores pre-advance depth
    cache_manager.set_cached_grade(
        cache=cache,
        topic_id=topic.topic_id,
        depth=topic.current_depth,
        answer_text=answer_text,
        score=score,
        breakdown=breakdown,
        feedback=feedback,
        decision=decision.value,
        model_used=model_id,
    )

    # Generate reteach content if needed
    reteach_content = None
    if decision == GradingDecision.RETEACH:
        reteach_content = generate_reteach_content(topic, daily_rpd, metrics)

    # Capture pre-advance depth for response
    pre_advance_depth = topic.current_depth

    # Apply decision to topic (mutates topic in place)
    _apply_decision(
        topic=topic,
        decision=decision,
        score=score,
        answer_hash=answer_hash,
        feedback=feedback,
        breakdown=breakdown,
        model_used=model_id,
        reteach_content=reteach_content,
    )

    # Determine new_depth
    new_depth = topic.current_depth if decision == GradingDecision.ADVANCE else pre_advance_depth

    app_logging.log_grading(
        topic_id=topic.topic_id,
        depth=pre_advance_depth,
        score=score,
        decision=decision.value,
        model_used=model_id,
        cached=False,
    )

    return GradeResponse(
        success=True,
        topic_id=topic.topic_id,
        topic_name=topic.topic_name,
        depth=pre_advance_depth,
        score=round(score, 1),
        breakdown=GradeBreakdown(**breakdown),
        feedback=feedback,
        decision=decision,
        new_depth=new_depth,
        retries_remaining=max(0, settings.max_retries_per_depth - topic.retries_used),
        model_used=model_id,
        quality_warning=quality_warning,
        cached=False,
    )
