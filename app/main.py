"""
app/main.py — FastAPI application entry point
TDD v2.0 §API Design (main.py)
PRD v2.0 §NFR-02, §NFR-04
FRD v2.0 §API Endpoints
Includes: lifespan management, CORS, rate limiting, security headers,
          startup validation, ping keep-alive endpoint (PRD FR-10.5).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import get_settings
from app.core.logging import setup_logging
from app.core.rate_limiter import limiter
from app.routers import api, dashboard, triggers

settings = get_settings()


# ──────────────────────────────────────────────────────────────────────────────
# Application Lifespan — TDD §Infrastructure Layer
# ──────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    FastAPI lifespan: startup → yield → shutdown.
    Startup: Initialize logging, sync orphaned /tmp/ files to Drive (L2-09),
             validate critical environment variables.
    """
    # Setup structured JSON logging
    setup_logging(settings.log_level)
    logger.info("AI PM Learning System starting up...")

    # Validate required env vars — fail loudly on startup
    _validate_env()

    # L2-09: Sync any orphaned /tmp/ files back to Drive (from prior crash)
    try:
        from app.clients.drive_client import startup_sync
        await startup_sync()
    except Exception as exc:
        logger.error(f"Startup Drive sync failed (non-fatal): {exc}")

    logger.info("Startup complete.")
    yield
    logger.info("Shutting down AI PM Learning System.")


def _validate_env() -> None:
    """
    Validate that all critical env vars are set.
    PRD NFR-02: Fail fast on missing secrets.
    """
    required = [
        ("gemini_api_key", "GEMINI_API_KEY"),
        ("google_client_id", "GOOGLE_CLIENT_ID"),
        ("google_client_secret", "GOOGLE_CLIENT_SECRET"),
        ("google_refresh_token", "GOOGLE_REFRESH_TOKEN"),
        ("api_key", "API_KEY"),
        ("cron_secret", "CRON_SECRET"),
        ("dashboard_user", "DASHBOARD_USER"),
        ("dashboard_pass", "DASHBOARD_PASS"),
        ("csrf_secret", "CSRF_SECRET"),
        ("sender_email", "SENDER_EMAIL"),
        ("recipient_email", "RECIPIENT_EMAIL"),
    ]
    missing = []
    for attr, env_name in required:
        val = getattr(settings, attr, None)
        if not val or val in ("change-me-immediately", "your-api-key-here"):
            missing.append(env_name)

    if missing:
        msg = f"Missing or placeholder env vars: {', '.join(missing)}"
        logger.critical(msg)
        if settings.environment == "production":
            raise RuntimeError(msg)
        logger.warning("Continuing in development mode despite missing env vars.")


# ──────────────────────────────────────────────────────────────────────────────
# FastAPI App
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI PM Autonomous Learning & Intelligence System",
    description=(
        "Autonomous daily learning system for AI Product Managers. "
        "Curates, summarizes, and tests AI PM knowledge from 42 RSS feeds."
    ),
    version="2.0.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

# ── Rate limiting — fastapi/slowapi ───────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda req, exc: JSONResponse(
        status_code=429,
        content={"error": "Rate limit exceeded. Slow down."},
    ),
)
app.add_middleware(SlowAPIMiddleware)

# ── CORS — PRD NFR-02 ─────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Security headers middleware — PRD NFR-02 ──────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(triggers.router, prefix="/trigger", tags=["triggers"])
app.include_router(api.router, prefix="/api", tags=["api"])
app.include_router(dashboard.router, tags=["dashboard"])


# ── Ping keep-alive endpoint — PRD FR-10.5 ────────────────────────────────────
@app.get("/api/ping", tags=["health"])
async def ping():
    """
    Cron-job.org pings this every 14 minutes to prevent Render cold starts.
    PRD FR-10.5: Keep-alive cron job (5th scheduled job on free tier).
    Does NOT call any external services.
    """
    return {"status": "ok", "version": "2.0.0"}


# ── Root redirect to dashboard ────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard", status_code=302)
