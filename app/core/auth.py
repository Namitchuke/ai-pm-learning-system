"""
app/core/auth.py — Authentication & Authorization
TDD v2.0 §Security / §Authentication
FRD v2.0 §FS-08.2 Authentication Flow
PRD v2.0 §NFR-02 Security (L2-13 dual-auth, L2-19 dashboard data auth)
"""
from __future__ import annotations

import base64
import os
import secrets
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import get_settings

security = HTTPBasic(auto_error=False)
settings = get_settings()


# ──────────────────────────────────────────────────────────────────────────────
# Cron Secret — PRD FR-10 / TDD §Cron Secret
# ──────────────────────────────────────────────────────────────────────────────

async def verify_cron_secret(
    x_cron_secret: Optional[str] = Header(None, alias="X-Cron-Secret"),
) -> bool:
    """Validate the X-Cron-Secret header on trigger endpoints."""
    if not x_cron_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Cron-Secret header required",
        )
    if not secrets.compare_digest(x_cron_secret, settings.cron_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cron secret",
        )
    return True


# ──────────────────────────────────────────────────────────────────────────────
# API Key — PRD NFR-02 / TDD §Primary: API Key
# ──────────────────────────────────────────────────────────────────────────────

async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> bool:
    """Validate X-API-Key header for programmatic access."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header required",
        )
    if not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return True


# ──────────────────────────────────────────────────────────────────────────────
# HTTP Basic Auth — PRD NFR-02 / TDD §Secondary: HTTP Basic Auth
# ──────────────────────────────────────────────────────────────────────────────

async def verify_basic_auth(
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
) -> bool:
    """Validate HTTP Basic Auth credentials for dashboard pages."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Basic Auth credentials required",
            headers={"WWW-Authenticate": "Basic"},
        )
    correct_username = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        settings.dashboard_user.encode("utf-8"),
    )
    correct_password = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        settings.dashboard_pass.encode("utf-8"),
    )
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


def _check_basic_auth_from_header(authorization: Optional[str]) -> bool:
    """Parse and validate Basic Auth from Authorization header string."""
    if not authorization or not authorization.startswith("Basic "):
        return False
    try:
        encoded = authorization[6:]
        decoded = base64.b64decode(encoded).decode("utf-8")
        username, _, password = decoded.partition(":")
        correct_username = secrets.compare_digest(
            username.encode("utf-8"),
            settings.dashboard_user.encode("utf-8"),
        )
        correct_password = secrets.compare_digest(
            password.encode("utf-8"),
            settings.dashboard_pass.encode("utf-8"),
        )
        return correct_username and correct_password
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Dual Auth — L2-13 + L2-19 fix
# Accepts: X-API-Key header OR HTTP Basic Auth
# Used by: POST /api/grade, GET /api/dashboard-data
# ──────────────────────────────────────────────────────────────────────────────

async def dual_auth(request: Request) -> bool:
    """
    L2-13/L2-19 fix: Accept either API key OR Basic Auth.
    HTML forms use Basic Auth + CSRF; programmatic access uses API key.
    FRD FS-08.2 / PRD NFR-02.
    """
    # Method 1: API Key in header
    api_key = request.headers.get("X-API-Key")
    if api_key and secrets.compare_digest(api_key, settings.api_key):
        return True

    # Method 2: HTTP Basic Auth
    authorization = request.headers.get("Authorization")
    if _check_basic_auth_from_header(authorization):
        return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide X-API-Key header or HTTP Basic Auth.",
        headers={"WWW-Authenticate": "Basic"},
    )


# ──────────────────────────────────────────────────────────────────────────────
# CSRF Verification helper — PRD NFR-02 / L2-13 fix
# Used internally by /api/grade when request is from Basic Auth path
# ──────────────────────────────────────────────────────────────────────────────

def is_api_key_request(request: Request) -> bool:
    """Returns True if the request was authenticated via API key (not Basic Auth)."""
    api_key = request.headers.get("X-API-Key")
    return bool(api_key and secrets.compare_digest(api_key, settings.api_key))
