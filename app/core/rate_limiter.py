"""
app/core/rate_limiter.py — slowapi rate limiting configuration
TDD v2.0 §Rate Limiting
PRD v2.0 §NFR-02 Security (Loophole #22 fix)
FRD v2.0 §NFR-02
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Single shared limiter instance — imported by main.py and routers
limiter = Limiter(key_func=get_remote_address)

# ── Rate limits per endpoint category — PRD NFR-02 / TDD §Rate Limiting ──────
# These string values are used as decorators on individual route handlers.

RATE_LIMITS = {
    # Dashboard HTML pages: generous limit for normal browsing
    "dashboard": "60/minute",
    # Grading submission: restrictive to prevent abuse (5-second interval implied)
    "grading": "5/minute",
    # Cron trigger endpoints: moderate (external cron fires 3-4x/day max)
    "triggers": "10/minute",
    # Health check: moderate
    "health": "30/minute",
    # Ping keep-alive (reserved cron slot 5)
    "ping": "60/minute",
}
