"""
app/services/email_service.py — Daily email digest generation and sending
TDD v2.0 §Core Services (email_service.py)
PRD v2.0 §FR-07 Daily Email Digest, §FR-08 Streak Tracking
FRD v2.0 §FS-07 Email Service
L2-10 fix: Streak = consecutive days with email_sent == true (not grading streaks).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger

from app.clients.gmail_client import send_email
from app.config import get_settings
from app.core import cache_manager, logging as app_logging
from app.models import CacheData, Metrics, PipelineState, Topic, TopicMode, TopicStatus
from app.utils.timezone import today_ist_str, yesterday_ist_str

settings = get_settings()

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _get_jinja_env() -> Environment:
    """Build Jinja2 environment for email templates."""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Streak tracking — L2-10 fix
# PRD FR-08: Streak = consecutive days where email_sent == true in cache.
# ──────────────────────────────────────────────────────────────────────────────

def update_streak(
    metrics: Metrics,
    cache: CacheData,
) -> int:
    """
    L2-10 fix: Update streak counter based on consecutive email_sent == true days.
    PRD FR-08 / FRD FS-07.3: Streak increments only if yesterday also had email sent.
    Returns updated streak count.
    """
    today = today_ist_str()
    yesterday = yesterday_ist_str()

    # Check if yesterday's email was sent
    yesterday_sent = cache_manager.is_email_sent_today(cache, yesterday)

    if yesterday_sent:
        metrics.streak_count += 1
    else:
        # Streak broken — reset
        if metrics.streak_count > 0:
            logger.info(
                f"Streak broken! Was {metrics.streak_count} days. Resetting."
            )
        metrics.streak_count = 1  # Today starts a new streak
        metrics.streak_start_date = today

    # Update longest streak record
    if metrics.streak_count > metrics.longest_streak:
        metrics.longest_streak = metrics.streak_count

    return metrics.streak_count


# ──────────────────────────────────────────────────────────────────────────────
# Email generation — FRD FS-07.2
# ──────────────────────────────────────────────────────────────────────────────

def _get_mastery_level(score: float) -> str:
    """Return mastery level label for visual indicator."""
    if score >= 80:
        return "expert"
    elif score >= 60:
        return "proficient"
    elif score >= 40:
        return "developing"
    else:
        return "novice"


def _build_email_context(
    topics: list[Topic],
    metrics: Metrics,
    mode: TopicMode,
    streak: int,
) -> dict:
    """Build template context for Jinja2 email rendering."""
    topics_data = []
    for topic in topics:
        topics_data.append({
            "topic_id": topic.topic_id,
            "topic_name": topic.topic_name,
            "category": topic.category.value.replace("_", " ").title(),
            "depth": topic.current_depth,
            "mastery_score": round(topic.mastery_score, 1),
            "mastery_level": _get_mastery_level(topic.mastery_score),
            "status": topic.status.value,
            "why_it_matters": topic.summary.why_it_matters,
            "core_mechanism": topic.summary.core_mechanism,
            "product_applications": topic.summary.product_applications,
            "risks_limitations": topic.summary.risks_limitations,
            "key_takeaways": topic.summary.key_takeaways,
            "tldr": topic.summary.tldr,
            "keywords_glossary": topic.summary.keywords_glossary,
            "source_url": topic.source_url,
            "source_title": topic.source_title,
            "source_tier": topic.source_tier,
            "is_reteaching": topic.status == TopicStatus.RETEACHING,
        })

    # Build mode context for email subject
    mode_labels = {
        TopicMode.NORMAL: f"{len(topics)} topics today",
        TopicMode.REDUCED_3: f"{len(topics)} topics (reduced mode)",
        TopicMode.REDUCED_2: f"{len(topics)} topics (reduced mode)",
        TopicMode.MINIMAL: "1 topic (minimal mode — focus on recovery)",
    }

    return {
        "topics": topics_data,
        "topic_count": len(topics),
        "streak": streak,
        "mode": mode.value,
        "mode_label": mode_labels.get(mode, ""),
        "date": datetime.utcnow().strftime("%B %d, %Y"),
        "recipient_email": settings.recipient_email,
        "is_paused": False,
        "mode_friendly": mode.value.replace("_", " ").title(),
    }


def generate_email_html(context: dict) -> str:
    """Render the HTML email from Jinja2 template."""
    env = _get_jinja_env()
    try:
        template = env.get_template("email_html.html")
        return template.render(**context)
    except Exception as exc:
        logger.error(f"Email HTML template render failed: {exc}")
        # Minimal fallback HTML
        topics_html = ""
        for t in context.get("topics", []):
            topics_html += f"<h2>{t['topic_name']}</h2><p>{t['tldr']}</p>"
        return f"<html><body>{topics_html}</body></html>"


def generate_email_plain(context: dict) -> str:
    """Render the plain-text email from Jinja2 template."""
    env = _get_jinja_env()
    try:
        template = env.get_template("email_plain.txt")
        return template.render(**context)
    except Exception as exc:
        logger.error(f"Email plain template render failed: {exc}")
        # Minimal fallback text
        lines = [f"AI PM Daily Learning Digest — {context.get('date', '')}"]
        for t in context.get("topics", []):
            lines.append(f"\n{t['topic_name']}\n{t['tldr']}")
        return "\n".join(lines)


def build_email_subject(
    topic_count: int,
    streak: int,
    mode: TopicMode,
) -> str:
    """FRD FS-07.1: Build descriptive email subject."""
    streak_str = f" 🔥 {streak}d streak" if streak > 1 else ""
    if mode == TopicMode.MINIMAL:
        return f"💡 Your daily AI PM focus (minimal mode){streak_str}"
    elif mode in (TopicMode.REDUCED_2, TopicMode.REDUCED_3):
        return f"💡 {topic_count} AI PM topics for today{streak_str}"
    else:
        return f"💡 {topic_count} AI PM topics for today{streak_str}"


# ──────────────────────────────────────────────────────────────────────────────
# Main send function — FRD FS-07.4 / FS-07.5
# ──────────────────────────────────────────────────────────────────────────────

def send_daily_email(
    topics: list[Topic],
    metrics: Metrics,
    cache: CacheData,
    pipeline_state: PipelineState,
) -> bool:
    """
    Generate and send daily learning email.
    FRD FS-07: Idempotent — checks email_cache before sending.
    L2-10 fix: Updates streak based on email_sent cache (not grading).
    Returns True on success.
    """
    today = today_ist_str()

    # Idempotency check — PRD FR-07 / Loophole #25 fix
    if cache_manager.is_email_sent_today(cache, today):
        logger.info("Email already sent today. Skipping (idempotent).")
        return True

    if not topics:
        logger.warning("No topics to include in daily email. Skipping send.")
        return False

    # Update streak — L2-10
    streak = update_streak(metrics, cache)

    mode = metrics.current_topic_mode
    subject = build_email_subject(len(topics), streak, mode)
    context = _build_email_context(topics, metrics, mode, streak)

    html_body = generate_email_html(context)
    plain_body = generate_email_plain(context)

    success = send_email(
        subject=subject,
        html_body=html_body,
        plain_body=plain_body,
    )

    if success:
        # Mark as sent in cache
        cache_manager.mark_email_sent(cache, today, len(topics))
        pipeline_state.email_sent = True
        app_logging.log_email_send(
            topics_count=len(topics),
            success=True,
            streak_count=streak,
        )
        logger.info(f"Daily email sent: {len(topics)} topics, streak: {streak}")
    else:
        app_logging.log_email_send(
            topics_count=len(topics),
            success=False,
            streak_count=streak,
            error="Gmail API returned failure",
        )

    return success
