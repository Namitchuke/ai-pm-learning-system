"""
app/services/scoring.py — Combined Gemini relevance + credibility scoring
TDD v2.0 §Core Services (scoring.py)
PRD v2.0 §FR-02 AI Pre-Filtering & Scoring
FRD v2.0 §FS-02 Scoring Service (single API call — L2-12 fix)
Combined single Gemini call: 5 relevance dimensions + credibility + promotional flag.
Few-shot calibration examples from prompts/scoring_examples.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from app.clients.gemini_client import call_gemini_with_fallback, extract_json_from_response
from app.config import get_settings
from app.models import (
    CacheData,
    DiscardedEntry,
    DiscardedFile,
    ExtractedArticle,
    Metrics,
    ScoredArticle,
)
from app.utils.validators import extract_float_from_dict

settings = get_settings()

# Path to prompt templates
PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
_scoring_prompt_cache: Optional[str] = None
_scoring_examples_cache: Optional[str] = None


def _load_scoring_prompt() -> str:
    """Load scoring prompt template from prompts/scoring.txt."""
    global _scoring_prompt_cache
    if _scoring_prompt_cache is None:
        try:
            _scoring_prompt_cache = (PROMPTS_DIR / "scoring.txt").read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("scoring.txt not found. Using inline prompt.")
            _scoring_prompt_cache = _INLINE_SCORING_PROMPT
    return _scoring_prompt_cache


def _load_scoring_examples() -> str:
    """Load few-shot examples from prompts/scoring_examples.json."""
    global _scoring_examples_cache
    if _scoring_examples_cache is None:
        try:
            examples = json.loads((PROMPTS_DIR / "scoring_examples.json").read_text(encoding="utf-8"))
            _scoring_examples_cache = json.dumps(examples, indent=2)
        except FileNotFoundError:
            _scoring_examples_cache = "[]"
    return _scoring_examples_cache


# Inline prompt fallback (in case prompts/ not found)
_INLINE_SCORING_PROMPT = """
You are an expert AI product manager content curator. Your task is to score an article on its relevance and credibility.

SCORING DIMENSIONS (1-10 each):
1. relevance_to_ai_pm: How relevant is this to an AI Product Manager's daily work?
2. technical_depth: Appropriate technical depth (avoids both oversimplification and excessive academic jargon)?
3. actionability: Does it provide actionable insights or frameworks?
4. novelty: Does it present new ideas or perspectives (not just rehashing basics)?
5. recency_relevance: Is the topic current and relevant to 2025-2026 AI landscape?
6. credibility: Is the source and content credible? (Author expertise, sourcing, methodology)
7. is_promotional: Is this primarily marketing/promotional content? (true/false)

Respond ONLY with valid JSON matching this schema:
{
  "relevance_to_ai_pm": <1-10>,
  "technical_depth": <1-10>,
  "actionability": <1-10>,
  "novelty": <1-10>,
  "recency_relevance": <1-10>,
  "credibility": <1-10>,
  "is_promotional": <true|false>,
  "rejection_reason": "<reason if score too low, else null>"
}

FEW-SHOT EXAMPLES:
{examples}

ARTICLE TO SCORE:
Title: {title}
Source: {source_name} (Tier {tier})
Content (truncated to {max_words} words):
---
{content}
---
"""

SCORING_DIMENSIONS = [
    "relevance_to_ai_pm",
    "technical_depth",
    "actionability",
    "novelty",
    "recency_relevance",
]


def build_scoring_prompt(article: ExtractedArticle, examples_json: str) -> str:
    """
    Build the combined scoring prompt for a single Gemini call.
    L2-12 fix: One call covers 5 relevance dimensions + credibility + promotional flag.
    FRD FS-02.2.
    """
    prompt_template = _load_scoring_prompt()
    content_preview = " ".join(article.extracted_text.split()[:settings.input_limits["combined_scoring"]])

    return prompt_template.format(
        examples=examples_json,
        title=article.title,
        source_name=article.source_name,
        tier=article.source_tier,
        max_words=settings.input_limits["combined_scoring"],
        content=content_preview,
    )


def parse_scoring_response(
    response_text: str,
) -> Optional[dict[str, float]]:
    """
    Parse and validate Gemini scoring JSON response.
    FRD FS-02.3: Must contain all 7 score fields.
    Returns dict with scores or None on parse failure.
    """
    data = extract_json_from_response(response_text)
    if not data:
        return None

    required_fields = SCORING_DIMENSIONS + ["credibility", "is_promotional"]
    for field in required_fields:
        if field not in data:
            logger.warning(f"Scoring response missing field: {field!r}")
            return None

    return data


def should_reject_article(
    scores: dict[str, Any],
) -> tuple[bool, str]:
    """
    FRD FS-02.4 Rejection logic:
    1. Reject if avg_relevance_score < 6.5 (PRD FR-02)
    2. Reject if credibility < 6.0 (PRD FR-02)
    3. Reject if is_promotional = true
    Returns (should_reject, rejection_reason).
    """
    if scores.get("is_promotional", False):
        return True, "promotional_content"

    credibility = extract_float_from_dict(scores, "credibility", 0.0)
    if credibility < settings.min_credibility_score:
        return True, f"low_credibility:{credibility:.1f}"

    relevance_scores = [
        extract_float_from_dict(scores, dim, 0.0)
        for dim in SCORING_DIMENSIONS
    ]
    avg_score = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0

    if avg_score < settings.min_relevance_score:
        return True, f"low_relevance:{avg_score:.2f}"

    return False, ""


def score_article(
    article: ExtractedArticle,
    pipeline_state_daily_rpd: dict[str, int],
    metrics: Optional[Metrics] = None,
) -> Optional[ScoredArticle]:
    """
    Score a single article using a combined Gemini call.
    L2-12 fix: Single call for all 7 scoring dimensions.
    Returns ScoredArticle on success, None on Gemini failure.
    """
    from app.core.cost_tracker import is_gemini_allowed, BudgetStatus, get_budget_status

    if metrics and not is_gemini_allowed(metrics):
        logger.warning("Budget RED: skipping Gemini scoring. Rejecting article.")
        return None

    examples_json = _load_scoring_examples()
    prompt = build_scoring_prompt(article, examples_json)

    try:
        result = call_gemini_with_fallback(
            model_env_var="GEMINI_BULK_MODEL",
            prompt=prompt,
            max_output_tokens=settings.token_limits["combined_scoring"],
            temperature=0.0,
            daily_rpd=pipeline_state_daily_rpd,
            operation="combined_scoring",
            metrics=metrics,
        )

        scores_raw = parse_scoring_response(result.get("text", ""))
        if scores_raw is None:
            logger.warning(f"Failed to parse scoring response for: {article.title[:60]}")
            return None

        # Calculate average relevance score
        relevance_values = [
            extract_float_from_dict(scores_raw, dim, 0.0, 0.0, 10.0)
            for dim in SCORING_DIMENSIONS
        ]
        avg_score = sum(relevance_values) / len(relevance_values)

        credibility = extract_float_from_dict(scores_raw, "credibility", 0.0, 0.0, 10.0)
        is_promotional = bool(scores_raw.get("is_promotional", False))

        # Build scores dict
        scores_dict = {dim: extract_float_from_dict(scores_raw, dim, 0.0, 0.0, 10.0) for dim in SCORING_DIMENSIONS}
        scores_dict["credibility"] = credibility

        should_reject, rejection_reason = should_reject_article(scores_raw)

        return ScoredArticle(
            **article.model_dump(),
            scores=scores_dict,
            avg_score=round(avg_score, 2),
            credibility=credibility,
            is_promotional=is_promotional,
            rejection_reason=rejection_reason if should_reject else None,
        )

    except Exception as exc:
        logger.error(f"Scoring failed for {article.url}: {exc}")
        return None


def score_articles(
    articles: list[ExtractedArticle],
    pipeline_state_daily_rpd: dict[str, int],
    discarded_file: DiscardedFile,
    metrics: Optional[Metrics] = None,
) -> tuple[list[ScoredArticle], list[ScoredArticle]]:
    """
    Score all extracted articles.
    Returns (passed_articles, rejected_articles).
    Rejected articles are added to discarded_file.
    """
    passed: list[ScoredArticle] = []
    rejected: list[ScoredArticle] = []

    for article in articles:
        scored = score_article(article, pipeline_state_daily_rpd, metrics)
        if scored is None:
            # Treat Gemini failure as rejection
            continue

        if scored.rejection_reason:
            rejected.append(scored)
            # FRD FS-02.5: Add to discarded.json (capped at 500)
            _add_to_discarded(discarded_file, scored)
        else:
            passed.append(scored)

    logger.info(
        f"Scoring: {len(passed)} passed, {len(rejected)} rejected out of "
        f"{len(articles)} articles."
    )
    return passed, rejected


def _add_to_discarded(discarded_file: DiscardedFile, article: ScoredArticle) -> None:
    """Add rejected article to discarded.json. Cap at 500 entries. FRD FS-05.4."""
    entry = DiscardedEntry(
        url=article.url,
        title=article.title,
        source_name=article.source_name,
        source_tier=article.source_tier,
        avg_score=article.avg_score,
        credibility=article.credibility,
        is_promotional=article.is_promotional,
        rejection_reason=article.rejection_reason or "unknown",
        scores_detail=article.scores,
    )

    # Enforce cap
    if len(discarded_file.entries) >= discarded_file.max_entries:
        discarded_file.entries.pop(0)  # Remove oldest (FIFO)

    discarded_file.entries.append(entry)
