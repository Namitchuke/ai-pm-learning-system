"""
app/main.py — FastAPI application entry point
TDD v2.0 §API Design (main.py)
PRD v2.0 §NFR-02, §NFR-04
FRD v2.0 §API Endpoints
Includes: lifespan management, CORS, rate limiting, security headers,
          startup validation, ping keep-alive endpoint (PRD FR-10.5).
"""

from contextlib import asynccontextmanager
import os
import threading
import time
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
# Self-Ping Keep-Alive — prevents Render free-tier cold starts
# Pings /api/ping every 8 minutes from a daemon thread launched at startup.
# No external cron service needed. daemon=True means thread auto-dies with app.
# ──────────────────────────────────────────────────────────────────────────────

_PING_INTERVAL_SECONDS = 8 * 60  # 8 minutes


def _self_ping_worker(base_url: str) -> None:
    """Background daemon thread: ping own health endpoint every 8 minutes."""
    import httpx
    time.sleep(60)  # Wait 1 minute after startup before first ping
    while True:
        try:
            httpx.get(f"{base_url}/api/ping", timeout=10)
            logger.debug("Self-ping OK.")
        except Exception as exc:
            logger.warning(f"Self-ping failed (non-fatal): {exc}")
        time.sleep(_PING_INTERVAL_SECONDS)


def _start_self_ping() -> None:
    """Launch the self-ping keep-alive daemon thread."""
    # Derive our own public URL from Render's env var, or use a sensible default
    base_url = os.environ.get(
        "RENDER_EXTERNAL_URL",
        "https://ai-pm-learning-system.onrender.com",
    ).rstrip("/")
    thread = threading.Thread(
        target=_self_ping_worker,
        args=(base_url,),
        daemon=True,
        name="self-ping-keepalive",
    )
    thread.start()
    logger.info(f"Self-ping keep-alive started. Pinging {base_url}/api/ping every {_PING_INTERVAL_SECONDS // 60}m.")


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

    # Self-ping keep-alive — prevents Render free-tier from spinning down
    # Fires every 8 minutes in a background daemon thread (no external cron needed)
    if settings.environment == "production":
        _start_self_ping()

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
        logger.warning("App will start but affected features will be unavailable until credentials are set.")



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





@app.get("/api/debug-clear", tags=["health"])
async def debug_clear():
    import traceback
    try:
        from app.clients import drive_client
        cache = drive_client.read_json_file("cache.json")
        count = len(cache.get("processed_urls", {}))
        cache["processed_urls"] = {}
        drive_client.write_json_file("cache.json", cache)
        return {"status": "cleared", "urls_removed": count}
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


@app.get("/api/debug-reset-state", tags=["health"])
async def debug_reset_state():
    """Directly write a fresh PipelineState for today to Drive (bypasses pipeline)."""
    import traceback
    try:
        from app.clients import drive_client
        from app.models import PipelineState
        from app.utils.timezone import today_ist_str
        today = today_ist_str()
        fresh_state = PipelineState(date=today)
        drive_client.write_json_file("pipeline_state.json", fresh_state.model_dump(mode="json"))
        return {"status": "reset", "date": today, "note": "Pipeline state reset to fresh for today. All slots PENDING."}
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}



@app.get("/api/debug", tags=["health"])
async def debug_state():
    import traceback
    try:
        from app.clients import drive_client
        state = drive_client.read_json_file("pipeline_state.json")
        sources = drive_client.read_json_file("rss_sources.json")
        errors = drive_client.read_json_file("errors.json")
        topics = drive_client.read_json_file("topics.json")
        dbg_drive = drive_client.read_json_file("_debug_pipeline.json")
        
        # Read local tmp fallback since Drive rate limits hide the real marker
        import json
        from pathlib import Path
        tmp_target = Path("/tmp/AI_PM_SYSTEM/_debug_pipeline.json")
        dbg_tmp = None
        if tmp_target.exists():
            try: dbg_tmp = json.loads(tmp_target.read_text())
            except: pass
            
        topic_count = len((topics or {}).get("topics", []))
        return {
            "pipeline": state, 
            "sources": sources, 
            "errors": errors, 
            "topic_count": topic_count, 
            "thread_marker": dbg_drive,
            "tmp_thread_marker": dbg_tmp
        }
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


@app.get("/api/debug-pipeline-run", tags=["health"])
async def debug_pipeline_run():
    """Step-by-step synchronous pipeline run to pinpoint where it fails."""
    import traceback as tb_mod
    result = {"steps": []}
    try:
        from app.clients import drive_client
        from app.models import PipelineState, TopicsFile, Metrics, CacheData, DiscardedFile
        from app.services import rss_pipeline
        from app.utils.timezone import today_ist_str

        today = today_ist_str()
        result["today"] = today

        # Step 1: Load state
        sources_data = drive_client.read_json_file("rss_sources.json") or rss_pipeline.build_default_sources_json()
        cache_data = drive_client.read_json_file("cache.json") or {}
        cache = CacheData(**cache_data) if cache_data else CacheData()
        pipeline_state = PipelineState(date=today)
        metrics = Metrics()
        result["steps"].append({"step": "load_state", "ok": True, "url_cache_size": len(cache.processed_urls)})

        # Step 2: Fetch feeds (just first 3 for speed)
        from app.services.rss_pipeline import load_rss_sources, fetch_feed_articles
        sources = load_rss_sources(sources_data)
        enabled = [s for s in sources if s.enabled][:3]
        arxiv_ref = [0]
        candidates = []
        for src in enabled:
            arts = fetch_feed_articles(src, arxiv_ref)
            candidates.extend(arts)
        result["steps"].append({"step": "fetch_3_feeds", "ok": True, "candidates": len(candidates)})

        # Step 3: Dedup
        from app.services.rss_pipeline import filter_duplicates
        new_arts, dups = filter_duplicates(candidates, cache, [])
        result["steps"].append({"step": "dedup", "ok": True, "new": len(new_arts), "dups": len(dups)})

        # Step 4: Extract first article
        if new_arts:
            from app.services.rss_pipeline import extract_article
            art = extract_article(new_arts[0])
            result["steps"].append({"step": "extract_first", "ok": art is not None, "url": new_arts[0].url, "words": art.word_count if art else 0})
        else:
            result["steps"].append({"step": "extract_first", "ok": False, "reason": "no new articles after dedup"})

        return result
    except Exception as e:
        result["error"] = str(e)
        result["traceback"] = tb_mod.format_exc()
        return result



# ── Root redirect to dashboard ────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard", status_code=302)
