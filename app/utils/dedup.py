"""
app/utils/dedup.py — URL and title-based deduplication
TDD v2.0 §Utilities (dedup.py)
PRD v2.0 §FR-01 Content De-duplication
FRD v2.0 §FS-04.2 Title De-duplication (Two-Phase: L2-11 fix)
Two phases: 85% → definite duplicate; 60-85% → Gemini confirmation.
"""
from __future__ import annotations

import hashlib
from typing import Any, Optional

from fuzzywuzzy import fuzz
from loguru import logger

from app.config import get_settings

settings = get_settings()


# ──────────────────────────────────────────────────────────────────────────────
# URL dedup — PRD FR-01 / FRD FS-01.3
# ──────────────────────────────────────────────────────────────────────────────

def compute_url_hash(url: str) -> str:
    """SHA-256 hash of URL string. Used as key in processed_urls cache."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


# ──────────────────────────────────────────────────────────────────────────────
# Two-phase title deduplication — L2-11 fix
# Phase 1: fuzzywuzzy — ≥85% → definite duplicate (no Gemini)
# Phase 2: fuzzywuzzy — 60-84% → Gemini confirmation call
# ──────────────────────────────────────────────────────────────────────────────

def _normalize_title(title: str) -> str:
    """Normalize title for comparison: lowercase, strip punctuation."""
    import re
    title = title.lower().strip()
    title = re.sub(r"[^\w\s]", " ", title)
    title = re.sub(r"\s{2,}", " ", title)
    return title


def get_fuzzy_similarity(title_a: str, title_b: str) -> int:
    """
    Compute fuzzy similarity score between two titles.
    Uses token_set_ratio for robustness to word reordering.
    Returns score 0-100.
    """
    a = _normalize_title(title_a)
    b = _normalize_title(title_b)
    return fuzz.token_set_ratio(a, b)


class DuplicateResult:
    UNIQUE = "unique"
    DEFINITE_DUPLICATE = "definite_duplicate"
    AMBIGUOUS = "ambiguous"  # Needs Gemini confirmation


def check_title_phase1(
    new_title: str,
    existing_titles: list[str],
) -> tuple[str, Optional[str], int]:
    """
    Phase 1: fuzzywuzzy title dedup.
    FRD FS-04.2 Phase 1:
    - Score ≥ 85 → DuplicateResult.DEFINITE_DUPLICATE (no Gemini)
    - Score 60-84 → DuplicateResult.AMBIGUOUS (needs Gemini in Phase 2)
    - Score < 60 → DuplicateResult.UNIQUE

    Returns (result, matched_title_or_None, best_score).
    """
    best_score = 0
    best_match: Optional[str] = None

    for existing_title in existing_titles:
        score = get_fuzzy_similarity(new_title, existing_title)
        if score > best_score:
            best_score = score
            best_match = existing_title

    if best_score >= settings.dedup_definite_threshold:
        return DuplicateResult.DEFINITE_DUPLICATE, best_match, best_score
    elif best_score >= settings.dedup_ambiguous_lower:
        return DuplicateResult.AMBIGUOUS, best_match, best_score
    else:
        return DuplicateResult.UNIQUE, None, best_score


def check_title_phase2_gemini(
    new_title: str,
    candidate_title: str,
    daily_rpd: Optional[dict[str, int]] = None,
    metrics: Optional[Any] = None,
) -> bool:
    """
    Phase 2: Gemini confirmation for ambiguous 60-84% matches.
    FRD FS-04.2 Phase 2: A binary "Are these the same topic?" check.
    Returns True if Gemini confirms duplicate, False if distinct.
    Uses GEMINI_BULK_MODEL (low token count, cheap call).
    """
    from app.clients.gemini_client import call_gemini_with_fallback, extract_json_from_response

    prompt = (
        "You are a deduplication assistant for an article ingestion pipeline.\n\n"
        "Are these two article titles covering the SAME topic? "
        "Answer ONLY with JSON: {\"duplicate\": true} or {\"duplicate\": false}\n\n"
        f"Title A: {new_title}\n"
        f"Title B: {candidate_title}"
    )

    try:
        result = call_gemini_with_fallback(
            model_env_var="GEMINI_BULK_MODEL",
            prompt=prompt,
            max_output_tokens=50,  # Very short response expected
            temperature=0.0,
            daily_rpd=daily_rpd,
            operation="title_dedup",
            metrics=metrics,
            alert_on_deprecation=False,
        )
        parsed = extract_json_from_response(result.get("text", ""))
        return bool(parsed.get("duplicate", False))

    except Exception as exc:
        logger.warning(
            f"Gemini dedup Phase 2 failed for '{new_title}' vs '{candidate_title}': {exc}. "
            f"Treating as duplicate (conservative)."
        )
        # Conservative: if Gemini fails, treat 60-85% similarity as duplicate
        return True


def is_duplicate_title(
    new_title: str,
    existing_titles: list[str],
    daily_rpd: Optional[dict[str, int]] = None,
    metrics: Optional[Any] = None,
    use_gemini: bool = False, # HARD MITIGATION: Disabled to prevent 45-minute rate limit backup on first run of 6 years data
) -> tuple[bool, str, int]:
    """
    Full two-phase title dedup.
    FRD FS-04.2 L2-11 fix.
    Returns (is_duplicate, reason, best_score).
    """
    if not existing_titles:
        return False, "no_existing_titles", 0

    result, matched_title, best_score = check_title_phase1(new_title, existing_titles)

    if result == DuplicateResult.DEFINITE_DUPLICATE:
        return True, f"phase1_definite:{best_score}%_match_with_{matched_title}", best_score

    if result == DuplicateResult.AMBIGUOUS and use_gemini and matched_title:
        is_dup = check_title_phase2_gemini(
            new_title, matched_title, daily_rpd=daily_rpd, metrics=metrics
        )
        if is_dup:
            return True, f"phase2_gemini_confirmed_duplicate:{best_score}%_match", best_score
        else:
            return False, f"phase2_gemini_confirmed_distinct:{best_score}%_match", best_score

    return False, f"unique:{best_score}%_max_score", best_score
