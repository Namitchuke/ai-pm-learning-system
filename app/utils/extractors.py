"""
app/utils/extractors.py — Layered content extraction chain
TDD v2.0 §Utilities (extractors.py)
PRD v2.0 §FR-01 RSS Content Pipeline - Content Extraction
FRD v2.0 §FS-01.4 Content Extraction Pipeline, §FS-01.5 Content Validation
L2-18 fix: Separate BLOCKED_DOMAINS list + BLOCKED_URL_PATTERNS regex list
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Optional

import requests
import trafilatura
from loguru import logger
from readability import Document

from app.config import get_settings
from app.models import ExtractionMethod

settings = get_settings()

# ── Request headers to mimic a browser ──────────────────────────────────────
_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AI-PM-Learning-Bot/2.0; "
        "+https://github.com/ai-pm-learning)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
_FETCH_TIMEOUT = 10  # seconds


# ──────────────────────────────────────────────────────────────────────────────
# URL Blocking — L2-18 fix: separate domain + pattern blocklists
# ──────────────────────────────────────────────────────────────────────────────

def is_url_blocked(url: str) -> tuple[bool, str]:
    """
    L2-18 fix: Check URL against BLOCKED_DOMAINS (exact) + BLOCKED_URL_PATTERNS (regex).
    Returns (is_blocked, reason).
    """
    try:
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
    except Exception:
        return True, "invalid_url"

    # Check blocked domains (exact match)
    for blocked_domain in settings.blocked_domains:
        if domain == blocked_domain.lower():
            return True, f"blocked_domain:{blocked_domain}"

    # Check blocked URL patterns (regex)
    for pattern in settings.blocked_url_patterns:
        try:
            if re.search(pattern, url, re.IGNORECASE):
                return True, f"blocked_pattern:{pattern}"
        except re.error:
            pass

    return False, ""


# ──────────────────────────────────────────────────────────────────────────────
# arXiv keyword pre-filter — PRD FR-01 / FRD FS-01.2
# ──────────────────────────────────────────────────────────────────────────────

def passes_arxiv_filter(title: str, abstract: str) -> bool:
    """
    PRD FR-01: arXiv articles must pass keyword relevance pre-filter.
    At least one keyword must appear in title OR abstract.
    FRD FS-01.2.
    """
    combined = (title + " " + abstract).lower()
    return any(kw.lower() in combined for kw in settings.arxiv_keywords)


# ──────────────────────────────────────────────────────────────────────────────
# Layered extraction chain — FRD FS-01.4
# Order: trafilatura → readability-lxml → newspaper3k → rss_description (fallback)
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_html(url: str) -> Optional[str]:
    """Fetch raw HTML content from a URL with timeout + error handling."""
    try:
        response = requests.get(
            url, headers=_REQUEST_HEADERS, timeout=_FETCH_TIMEOUT, allow_redirects=True
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.Timeout:
        logger.debug(f"Timeout fetching {url}")
    except requests.exceptions.TooManyRedirects:
        logger.debug(f"Too many redirects for {url}")
    except requests.exceptions.RequestException as exc:
        logger.debug(f"Request failed for {url}: {exc}")
    return None


def _extract_with_trafilatura(html: str, url: str) -> Optional[str]:
    """
    Primary: trafilatura extraction.
    FRD FS-01.4 Chain Step 1.
    """
    try:
        text = trafilatura.extract(
            html,
            url=url,
            include_tables=False,
            include_images=False,
            include_links=False,
            favor_precision=True,
            no_fallback=True,
        )
        return text if text and len(text.strip()) >= 100 else None
    except Exception as exc:
        logger.debug(f"Trafilatura failed for {url}: {exc}")
        return None


def _extract_with_readability(html: str, url: str) -> Optional[str]:
    """
    Secondary: readability-lxml extraction.
    FRD FS-01.4 Chain Step 2.
    """
    try:
        doc = Document(html)
        content = doc.summary(html_partial=False)
        # Strip HTML tags
        clean = re.sub(r"<[^>]+>", " ", content)
        clean = re.sub(r"\s{2,}", " ", clean).strip()
        return clean if len(clean) >= 100 else None
    except Exception as exc:
        logger.debug(f"Readability failed for {url}: {exc}")
        return None


def _extract_with_newspaper3k(url: str) -> Optional[str]:
    """
    Tertiary: newspaper3k extraction.
    FRD FS-01.4 Chain Step 3.
    """
    try:
        from newspaper import Article
        article = Article(url)
        article.download()
        article.parse()
        text = article.text
        return text if text and len(text.strip()) >= 100 else None
    except Exception as exc:
        logger.debug(f"Newspaper3k failed for {url}: {exc}")
        return None


def extract_article_content(
    url: str,
    rss_description: str = "",
) -> tuple[str, ExtractionMethod]:
    """
    Execute the layered extraction chain.
    FRD FS-01.4: trafilatura → readability → newspaper3k → rss_description.
    Returns (extracted_text, extraction_method_used).
    PRD FR-01: Reject if < MIN_WORD_COUNT after extraction.
    """
    # Check URL blocklist first — L2-18
    is_blocked, reason = is_url_blocked(url)
    if is_blocked:
        logger.debug(f"URL blocked ({reason}): {url}")
        # Return RSS description as lowest-fidelity fallback
        if rss_description:
            return rss_description, ExtractionMethod.RSS_DESCRIPTION
        return "", ExtractionMethod.RSS_DESCRIPTION

    html = _fetch_html(url)
    if html:
        # Step 1: trafilatura
        text = _extract_with_trafilatura(html, url)
        if text:
            return text, ExtractionMethod.TRAFILATURA

        # Step 2: readability-lxml
        text = _extract_with_readability(html, url)
        if text:
            return text, ExtractionMethod.READABILITY

    # Step 3: newspaper3k (fetches its own)
    text = _extract_with_newspaper3k(url)
    if text:
        return text, ExtractionMethod.NEWSPAPER3K

    # Step 4: Fallback to RSS description
    logger.debug(f"All extractors failed for {url}. Using RSS description.")
    return rss_description, ExtractionMethod.RSS_DESCRIPTION


# ──────────────────────────────────────────────────────────────────────────────
# Content validation — FRD FS-01.5
# ──────────────────────────────────────────────────────────────────────────────

def count_words(text: str) -> int:
    """Count words in extracted text."""
    return len(text.split()) if text else 0


def validate_and_truncate(
    text: str,
) -> tuple[bool, str, str]:
    """
    FRD FS-01.5 Content Validation:
    - Reject if < MIN_ARTICLE_WORDS (200)
    - Truncate if > TRUNCATE_ARTICLE_WORDS (3000)
    Returns (is_valid, processed_text, rejection_reason).
    """
    word_count = count_words(text)

    if word_count < settings.min_article_words:
        return (
            False,
            "",
            f"too_short:{word_count}_words_min_{settings.min_article_words}",
        )

    if word_count > settings.truncate_article_words:
        # Truncate to max words
        words = text.split()
        text = " ".join(words[: settings.truncate_article_words])
        logger.debug(f"Truncated article from {word_count} to {settings.truncate_article_words} words.")

    return True, text, ""
