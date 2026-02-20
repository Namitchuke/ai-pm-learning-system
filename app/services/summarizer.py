"""
app/services/summarizer.py — 3-step anti-hallucination summarization pipeline
TDD v2.0 §Core Services (summarizer.py)
PRD v2.0 §FR-03 Summary Generation (3-step anti-hallucination)
FRD v2.0 §FS-03 Summarization Service
Steps: 1) Extractive sentence selection, 2) Fuzzy verify ≥85%, 3) Abstractive summarize
Cache key = SHA256(url + extraction_method) — L2-20 fix
Faithfulness scoring: flag if < 7 — FRD FS-03.5
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from app.clients.gemini_client import call_gemini_with_fallback, extract_json_from_response
from app.config import get_settings
from app.core import cache_manager
from app.models import CacheData, Metrics, ScoredArticle, SummarizedArticle, TopicSummary
from app.utils.validators import extract_float_from_dict

settings = get_settings()
PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"

_extractive_prompt_cache: Optional[str] = None
_summarization_prompt_cache: Optional[str] = None
_faithfulness_prompt_cache: Optional[str] = None


def _load_prompt(filename: str, fallback: str) -> str:
    """Load a prompt file from prompts/, fall back to inline string."""
    try:
        return (PROMPTS_DIR / filename).read_text(encoding="utf-8")
    except FileNotFoundError:
        return fallback


# ──────────────────────────────────────────────────────────────────────────────
# Step 1: Extractive sentence selection — FRD FS-03.1
# ──────────────────────────────────────────────────────────────────────────────

_EXTRACTIVE_PROMPT_FALLBACK = """
You are an expert technical content analyst.

Your task: Extract exactly 5 key sentences from the article that best capture:
1. Why the topic matters for AI product managers
2. The core technical mechanism
3. Product/business applications
4. Risks or limitations
5. A memorable key takeaway

Rules:
- Copy sentences VERBATIM from the article — do not paraphrase
- Return as JSON: {"sentences": ["sent1", "sent2", "sent3", "sent4", "sent5"]}
- Maximum input considered: {max_words} words

ARTICLE:
---
{content}
---
"""

def _step1_extract_sentences(
    article_text: str,
    daily_rpd: Optional[dict[str, int]],
    metrics: Optional[Metrics],
) -> Optional[list[str]]:
    """
    Step 1: Ask Gemini to extract exactly 5 verbatim key sentences.
    FRD FS-03.1.
    """
    prompt_template = _load_prompt("extraction.txt", _EXTRACTIVE_PROMPT_FALLBACK)
    # Truncate input
    words = article_text.split()
    content_preview = " ".join(words[: settings.input_limits["extractive"]])

    prompt = prompt_template.format(
        max_words=settings.input_limits["extractive"],
        content=content_preview,
    )

    try:
        result = call_gemini_with_fallback(
            model_env_var="GEMINI_BULK_MODEL",
            prompt=prompt,
            max_output_tokens=settings.token_limits["extractive"],
            temperature=0.0,
            daily_rpd=daily_rpd,
            operation="extractive",
            metrics=metrics,
        )
        parsed = extract_json_from_response(result.get("text", ""))
        sentences = parsed.get("sentences", [])
        if isinstance(sentences, list) and len(sentences) >= 3:
            return [str(s).strip() for s in sentences[:5]]
        return None
    except Exception as exc:
        logger.error(f"Step 1 extraction failed: {exc}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Fuzzy verification ≥85% — FRD FS-03.2
# ──────────────────────────────────────────────────────────────────────────────

def _step2_verify_sentences(
    extracted_sentences: list[str],
    original_text: str,
    min_similarity: int = 85,
) -> list[str]:
    """
    Step 2: Verify each extracted sentence exists verbatim (≥85% similarity)
    in the original article text. FRD FS-03.2.
    Verified sentences only are passed to Step 3.
    """
    from fuzzywuzzy import fuzz
    verified: list[str] = []

    # Split original into sentence-like chunks for comparison
    original_chunks = re.split(r"[.!?]\s+", original_text)
    original_chunks = [c.strip() for c in original_chunks if len(c.strip()) > 20]

    for sentence in extracted_sentences:
        best_score = 0
        for chunk in original_chunks:
            score = fuzz.partial_ratio(sentence.lower(), chunk.lower())
            if score > best_score:
                best_score = score

        if best_score >= min_similarity:
            verified.append(sentence)
        else:
            logger.debug(
                f"Sentence failed verification ({best_score}% < {min_similarity}%): "
                f"{sentence[:60]!r}"
            )

    return verified


# ──────────────────────────────────────────────────────────────────────────────
# Step 3: Abstractive summarization from verified sentences only — FRD FS-03.3
# ──────────────────────────────────────────────────────────────────────────────

_SUMMARIZATION_PROMPT_FALLBACK = """
You are an expert AI product manager educator. Create a structured summary for a learner using ONLY the verified sentences provided.

Verified source sentences (use ONLY these — do not add external knowledge):
{verified_sentences}

Generate a JSON summary with these exact fields:
{{
  "why_it_matters": "<2-3 sentences: Why this matters for an AI PM>",
  "core_mechanism": "<2-3 sentences: How it works technically>",
  "product_applications": "<2-3 sentences: How to apply this in product work>",
  "risks_limitations": "<1-2 sentences: Key risks or limitations>",
  "key_takeaways": ["<takeaway 1>", "<takeaway 2>", "<takeaway 3>"],
  "tldr": "<One memorable sentence summary>",
  "keywords_glossary": {{
    "<technical_term>": "<plain-English definition>"
  }}
}}

STRICT RULES:
- Only use information present in the verified sentences above
- Do NOT invent facts, statistics, or examples
- keywords_glossary: include 2-5 technical terms from the text
"""

def _step3_summarize(
    verified_sentences: list[str],
    daily_rpd: Optional[dict[str, int]],
    metrics: Optional[Metrics],
) -> Optional[TopicSummary]:
    """
    Step 3: Ask Gemini to write structured summary using ONLY verified sentences.
    FRD FS-03.3: Anti-hallucination — no external knowledge allowed.
    """
    prompt_template = _load_prompt("summarization.txt", _SUMMARIZATION_PROMPT_FALLBACK)
    sentences_text = "\n".join(f"- {s}" for s in verified_sentences)

    prompt = prompt_template.format(verified_sentences=sentences_text)

    try:
        result = call_gemini_with_fallback(
            model_env_var="GEMINI_BULK_MODEL",
            prompt=prompt,
            max_output_tokens=settings.token_limits["summarization"],
            temperature=0.3,  # Slight creativity for natural language
            daily_rpd=daily_rpd,
            operation="summarization",
            metrics=metrics,
        )
        parsed = extract_json_from_response(result.get("text", ""))
        if not parsed:
            return None

        return TopicSummary(
            why_it_matters=parsed.get("why_it_matters", ""),
            core_mechanism=parsed.get("core_mechanism", ""),
            product_applications=parsed.get("product_applications", ""),
            risks_limitations=parsed.get("risks_limitations", ""),
            key_takeaways=parsed.get("key_takeaways", []),
            tldr=parsed.get("tldr", ""),
            keywords_glossary=parsed.get("keywords_glossary", {}),
        )
    except Exception as exc:
        logger.error(f"Step 3 summarization failed: {exc}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Step 4: Faithfulness scoring — FRD FS-03.5 (conditional on budget)
# ──────────────────────────────────────────────────────────────────────────────

_FAITHFULNESS_PROMPT_FALLBACK = """
You are a fact-checking AI. Score how faithful the summary is to the source sentences on a scale 1-10.

Source sentences:
{source_sentences}

Generated summary:
{summary_text}

Score 10 = everything in summary is directly supported by source sentences.
Score 1 = summary contains many unsupported claims.

Respond ONLY with JSON: {{"faithfulness_score": <1-10>, "unsupported_claims": ["<claim>"]}}
"""

def _step4_faithfulness_check(
    verified_sentences: list[str],
    summary: TopicSummary,
    daily_rpd: Optional[dict[str, int]],
    metrics: Optional[Metrics],
) -> tuple[float, bool]:
    """
    Step 4 (optional — disabled on YELLOW budget): Faithfulness score 1-10.
    FRD FS-03.5: Flag if < 7. Returns (score, is_low_confidence).
    """
    from app.core.cost_tracker import is_faithfulness_allowed
    if metrics and not is_faithfulness_allowed(metrics):
        logger.debug("Budget YELLOW: skipping faithfulness check.")
        return settings.faithfulness_parse_error_default, False

    prompt_template = _load_prompt("faithfulness.txt", _FAITHFULNESS_PROMPT_FALLBACK)
    sentences_text = "\n".join(f"- {s}" for s in verified_sentences)
    summary_text = (
        f"{summary.why_it_matters} {summary.core_mechanism} "
        f"{summary.product_applications} {summary.risks_limitations}"
    )

    prompt = prompt_template.format(
        source_sentences=sentences_text,
        summary_text=summary_text,
    )

    try:
        result = call_gemini_with_fallback(
            model_env_var="GEMINI_BULK_MODEL",
            prompt=prompt,
            max_output_tokens=settings.token_limits["faithfulness"],
            temperature=0.0,
            daily_rpd=daily_rpd,
            operation="faithfulness",
            metrics=metrics,
        )
        parsed = extract_json_from_response(result.get("text", ""))
        if not parsed:
            return float(settings.faithfulness_parse_error_default), True

        score = extract_float_from_dict(parsed, "faithfulness_score", 5.0, 1.0, 10.0)
        is_low = score < settings.faithfulness_low_confidence_threshold
        if is_low:
            unsupported = parsed.get("unsupported_claims", [])
            logger.warning(
                f"Low faithfulness score {score}/10. "
                f"Unsupported claims: {unsupported}"
            )
        return score, is_low

    except Exception as exc:
        logger.error(f"Faithfulness check failed: {exc}")
        return float(settings.faithfulness_parse_error_default), True


# ──────────────────────────────────────────────────────────────────────────────
# Main summarize function — L2-20: cache by SHA256(url + extraction_method)
# ──────────────────────────────────────────────────────────────────────────────

def summarize_article(
    article: ScoredArticle,
    cache: CacheData,
    daily_rpd: Optional[dict[str, int]] = None,
    metrics: Optional[Metrics] = None,
) -> Optional[SummarizedArticle]:
    """
    Full 3-step anti-hallucination summarization pipeline.
    FRD FS-03: Extract → Verify → Summarize → Faithfulness check.
    L2-20 fix: Cache keyed by SHA256(url + extraction_method).
    Returns SummarizedArticle or None on failure.
    """
    from app.core.cost_tracker import is_gemini_allowed
    if metrics and not is_gemini_allowed(metrics):
        logger.warning("Budget RED: skipping summarization.")
        return None

    # Cache lookup — L2-20
    cached_summary = cache_manager.get_cached_summary(
        cache, article.url, article.extraction_method.value
    )
    if cached_summary:
        logger.debug(f"Summary cache hit for: {article.url[:60]}")
        return SummarizedArticle(
            **article.model_dump(),
            summary=cached_summary,
            faithfulness_score=10.0,  # Already verified in previous run
            low_confidence=False,
        )

    # Step 1: Extract verbatim sentences
    extracted_sentences = _step1_extract_sentences(
        article.extracted_text, daily_rpd, metrics
    )
    if not extracted_sentences:
        logger.warning(f"Step 1 failed: No sentences extracted for {article.url[:60]}")
        return None

    # Step 2: Verify sentences against source
    verified_sentences = _step2_verify_sentences(
        extracted_sentences, article.extracted_text
    )
    if len(verified_sentences) < settings.min_verified_sentences:
        logger.warning(
            f"Step 2: Only {len(verified_sentences)}/{len(extracted_sentences)} "
            f"sentences verified (min: {settings.min_verified_sentences}). "
            f"Rejecting article: {article.url[:60]}"
        )
        return None

    # Step 3: Summarize using ONLY verified sentences
    summary = _step3_summarize(verified_sentences, daily_rpd, metrics)
    if summary is None:
        logger.warning(f"Step 3 summarization failed for: {article.url[:60]}")
        return None

    # Step 4: Faithfulness check
    faith_score, is_low_confidence = _step4_faithfulness_check(
        verified_sentences, summary, daily_rpd, metrics
    )

    # Cache the result — L2-20
    cache_manager.set_cached_summary(
        cache, article.url, article.extraction_method.value, summary
    )

    return SummarizedArticle(
        **article.model_dump(),
        summary=summary,
        faithfulness_score=faith_score,
        low_confidence=is_low_confidence,
    )


def summarize_articles(
    articles: list[ScoredArticle],
    cache: CacheData,
    daily_rpd: Optional[dict[str, int]] = None,
    metrics: Optional[Metrics] = None,
) -> list[SummarizedArticle]:
    """Summarize a list of passed articles. Skips failures gracefully."""
    results: list[SummarizedArticle] = []
    for article in articles:
        summarized = summarize_article(article, cache, daily_rpd, metrics)
        if summarized:
            results.append(summarized)
    logger.info(f"Summarization: {len(results)}/{len(articles)} articles summarized.")
    return results
