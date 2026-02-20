"""
app/utils/timezone.py — IST timezone handling and slot detection
TDD v2.0 §Utilities (timezone.py)
PRD v2.0 §FR-10 Cron Schedule (IST-based triggers)
FRD v2.0 §FS-01.6 Slot Detection, §FS-07.6 Email Schedule
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Literal
import pytz

from app.config import get_settings

settings = get_settings()

IST = pytz.timezone("Asia/Kolkata")
UTC = pytz.utc

Slot = Literal["morning", "midday", "evening"]


def utc_now() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


def ist_now() -> datetime:
    """Return current IST datetime (timezone-aware)."""
    return datetime.now(IST)


def utc_to_ist(dt: datetime) -> datetime:
    """Convert a UTC datetime to IST."""
    if dt.tzinfo is None:
        dt = UTC.localize(dt)
    return dt.astimezone(IST)


def ist_to_utc(dt: datetime) -> datetime:
    """Convert an IST datetime to UTC."""
    if dt.tzinfo is None:
        dt = IST.localize(dt)
    return dt.astimezone(UTC)


def get_current_slot() -> Slot:
    """
    Determine the current slot based on IST hour.
    PRD FR-10 / FRD FS-01.6:
    - Morning:  06:00–09:59 IST (cron at 07:55)
    - Midday:   10:00–13:59 IST (cron at 11:55)
    - Evening:  14:00–18:59 IST (cron at 16:55)
    Default to "morning" outside of these windows (safe fallback).
    """
    hour = ist_now().hour

    if settings.slot_morning_start <= hour < settings.slot_morning_end:
        return "morning"
    elif settings.slot_midday_start <= hour < settings.slot_midday_end:
        return "midday"
    elif settings.slot_evening_start <= hour < settings.slot_evening_end:
        return "evening"
    else:
        # Triggered outside window (e.g., Render cold start delay, cron retry)
        # Assign based on closest upcoming slot
        if hour < settings.slot_morning_start:
            return "morning"
        elif hour < settings.slot_midday_start:
            return "morning"
        elif hour < settings.slot_evening_start:
            return "midday"
        else:
            return "evening"


def today_ist_str() -> str:
    """Return today's date string in IST as YYYY-MM-DD."""
    return ist_now().strftime("%Y-%m-%d")


def yesterday_ist_str() -> str:
    """Return yesterday's date string in IST as YYYY-MM-DD."""
    from datetime import timedelta
    return (ist_now() - timedelta(days=1)).strftime("%Y-%m-%d")


def get_iso_week_key() -> str:
    """Return ISO week key like '2026-W07' for the current IST week."""
    now = ist_now()
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def get_month_key() -> str:
    """Return current month key as YYYY-MM."""
    return ist_now().strftime("%Y-%m")


def get_year() -> int:
    """Return current year (IST)."""
    return ist_now().year


def get_quarter(dt: Optional[datetime] = None) -> str:
    """Return quarter label like 'Q1 2026' for a given or current datetime."""
    if dt is None:
        dt = ist_now()
    month = dt.month
    quarter = ((month - 1) // 3) + 1
    return f"Q{quarter} {dt.year}"


def is_sunday() -> bool:
    """Return True if today is Sunday (IST). Used for weekly backup trigger."""
    return ist_now().weekday() == 6  # Monday=0, Sunday=6


def is_first_day_of_quarter() -> bool:
    """
    Return True if today is the first day of a quarter (Jan 1, Apr 1, Jul 1, Oct 1).
    FRD FS-09.1: Quarterly report generated on Q start.
    """
    now = ist_now()
    return now.month in (1, 4, 7, 10) and now.day == 1


def is_within_date_gate(
    target_date_str: str,
    current_date_str: Optional[str] = None,
) -> bool:
    """
    Check if the pipeline state date matches today.
    FRD FS-01.1: Per-slot tracking prevents double-runs by comparing dates.
    """
    if current_date_str is None:
        current_date_str = today_ist_str()
    return target_date_str == current_date_str


# Optional import for type hints
from typing import Optional
