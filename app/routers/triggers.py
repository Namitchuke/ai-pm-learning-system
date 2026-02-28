"""
app/routers/triggers.py — Cron-triggered pipeline endpoints
TDD v2.0 §API Design (cron endpoints)
PRD v2.0 §FR-10 Cron Jobs (4 triggers + ping keep-alive)
FRD v2.0 §FS-01, §FS-07, §FS-08, §FS-09, §FS-10, §FS-12
Trigger endpoints: /trigger/rss, /trigger/email, /trigger/grade-check, /trigger/weekly
All protected by X-Cron-Secret header.
"""

from datetime import datetime
import threading
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from loguru import logger

from app.clients import drive_client
from app.clients.gmail_client import send_alert_email
from app.core.auth import verify_cron_secret
from app.models import (
    ArchivedTopicsFile,
    CacheData,
    DiscardedFile,
    ErrorsFile,
    Metrics,
    PipelineState,
    QuarterlyReportsFile,
    SlotStatus,
    TopicsFile,
)
from app.services import (
    adaptive_mode as adaptive_mode_service,
    cleanup,
    email_service,
    quarterly_report as quarterly_report_service,
    rss_pipeline,
    scoring,
    summarizer,
    topic_selector,
)
from app.utils.timezone import (
    get_current_slot,
    is_sunday,
    today_ist_str,
    is_first_day_of_quarter,
)

router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────────
# Drive I/O helpers — load all state, batch write at end
# PRD Design Decision: batch writes to reduce Drive API calls (~6 per slot)
# ──────────────────────────────────────────────────────────────────────────────

def _load_all_state() -> dict[str, Any]:
    """Load all required JSON files from Drive in parallel (sequential fallback)."""
    state: dict[str, Any] = {}

    def _read(filename: str, model_class):
        data = drive_client.read_json_file(filename)
        if data:
            try:
                return model_class(**data)
            except Exception as exc:
                logger.warning(f"Schema parse error for {filename}: {exc}")
        return model_class()

    state["pipeline_state"] = _read("pipeline_state.json", PipelineState)
    state["topics_file"] = _read("topics.json", TopicsFile)
    state["archived_file"] = _read("archived_topics.json", ArchivedTopicsFile)
    state["metrics"] = _read("metrics.json", Metrics)
    state["cache"] = _read("cache.json", CacheData)
    state["discarded_file"] = _read("discarded.json", DiscardedFile)
    state["errors_file"] = _read("errors.json", ErrorsFile)
    sources_data = drive_client.read_json_file("rss_sources.json")
    state["sources_data"] = sources_data or rss_pipeline.build_default_sources_json()

    return state


def _save_all_state(state: dict[str, Any]) -> None:
    """Batch write all state files back to Drive."""
    for filename, obj in [
        ("pipeline_state.json", state["pipeline_state"]),
        ("topics.json", state["topics_file"]),
        ("archived_topics.json", state["archived_file"]),
        ("metrics.json", state["metrics"]),
        ("cache.json", state["cache"]),
        ("discarded.json", state["discarded_file"]),
        ("errors.json", state["errors_file"]),
        ("rss_sources.json", state["sources_data"]),
    ]:
        try:
            if isinstance(obj, dict):
                drive_client.write_json_file(filename, obj)
            else:
                drive_client.write_json_file(filename, obj.model_dump(mode="json"))
        except Exception as exc:
            logger.error(f"Failed to write {filename}: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# Trigger 1: RSS Content Pipeline — PRD FR-01 / FRD FS-01
# Cron: 07:55 (morning) / 11:55 (midday) / 16:55 (evening) IST
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/rss")
async def trigger_rss(
    request: Request,
    background_tasks: BackgroundTasks,
    force_slot: str | None = None,
    force_sync: str | None = None,
    force_reset: str | None = None,
    _auth: bool = Depends(verify_cron_secret),
) -> dict[str, Any]:
    """
    RSS content pipeline trigger.
    Runs the full pipeline: fetch → dedup → extract → score → summarize → select → email.
    Uses a daemon=False thread so the pipeline survives Render worker recycling.
    """
    if force_sync:
        try:
            _run_rss_pipeline(force_slot, force_reset=bool(force_reset))
            return {"status": "success", "message": "Pipeline ran synchronously"}
        except Exception as e:
            import traceback
            return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}
    else:
        t = threading.Thread(
            target=_run_rss_pipeline,
            args=(force_slot, bool(force_reset)),
            daemon=False,  # NOT a daemon — survives beyond request lifetime
            name=f"rss-pipeline-{force_slot or 'auto'}",
        )
        t.start()
        return {"status": "accepted", "message": f"RSS pipeline started (forced {force_slot}, reset={force_reset})" if force_slot else "RSS pipeline started"}


def _run_rss_pipeline(force_slot: str | None = None, force_reset: bool = False) -> None:
    """Full RSS pipeline execution (runs in background task)."""
    slot = force_slot or get_current_slot()
    today = today_ist_str()
    logger.info(f"RSS pipeline triggered. Slot: {slot}, Date: {today}")

    try:
        state = _load_all_state()
        pipeline_state: PipelineState = state["pipeline_state"]
        topics_file: TopicsFile = state["topics_file"]
        metrics: Metrics = state["metrics"]
        cache: CacheData = state["cache"]
        discarded_file: DiscardedFile = state["discarded_file"]

        # Date gate: reset pipeline state if it's a new day OR forced reset
        if pipeline_state.date != today or force_reset:
            pipeline_state = PipelineState(date=today)
            state["pipeline_state"] = pipeline_state
            logger.info(f"Pipeline state reset for {today}. (force_reset={force_reset})")

        slot_state = pipeline_state.slots.get(slot)
        if slot_state is None:
            logger.error(f"Unknown slot: {slot}")
            return

        # Idempotency: skip if slot already DONE
        if slot_state.status == SlotStatus.DONE:
            logger.info(f"Slot {slot} already DONE. Skipping.")
            return

        # Morning only: run cleanup first (L2-02)
        if slot == "morning":
            cleanup.run_morning_cleanup(
                topics_file=topics_file,
                archived_topics_file=state["archived_file"],
                cache=cache,
                errors_file=state["errors_file"],
            )
            # Run weekly backup on Sundays
            if is_sunday():
                logger.info("Sunday: running weekly backup.")
                drive_client.run_weekly_backup()

            # Run quarterly report on quarter start
            if is_first_day_of_quarter():
                report = quarterly_report_service.generate_quarterly_report(
                    topics_file, state["archived_file"], metrics
                )
                reports_file = QuarterlyReportsFile()
                quarterly_report_service.save_quarterly_report(report, reports_file)
                drive_client.write_json_file(
                    "quarterly_reports.json", reports_file.model_dump(mode="json")
                )

        # Mark slot as IN_PROGRESS
        slot_state.status = SlotStatus.IN_PROGRESS
        slot_state.started_at = datetime.utcnow()

        # Step 1-3: Fetch → Dedup → Extract
        existing_titles = [t.topic_name for t in topics_file.topics]
        extracted_articles, updated_sources = rss_pipeline.run_rss_pipeline(
            slot=slot,
            pipeline_state=pipeline_state,
            cache=cache,
            sources_data=state["sources_data"],
            existing_topic_titles=existing_titles,
            metrics=metrics,
        )
        state["sources_data"] = updated_sources

        if not extracted_articles:
            logger.info(f"[{slot}] No new articles after extraction. Marking slot DONE.")
            slot_state.status = SlotStatus.DONE
            slot_state.completed_at = datetime.utcnow()
            _save_all_state(state)
            return

        # Step 4: Score
        from app.core.cost_tracker import is_gemini_allowed
        if not is_gemini_allowed(metrics):
            logger.warning("Budget RED: skipping all Gemini calls (score/summarize).")
            slot_state.status = SlotStatus.DONE
            _save_all_state(state)
            return

        passed_articles, _ = scoring.score_articles(
            extracted_articles,
            pipeline_state.daily_rpd,
            discarded_file,
            metrics=metrics,
        )
        state["discarded_file"] = discarded_file

        if not passed_articles:
            logger.info(f"[{slot}] All articles rejected by scorer.")
            slot_state.status = SlotStatus.DONE
            slot_state.completed_at = datetime.utcnow()
            _save_all_state(state)
            return

        # Step 5: Summarize
        summarized = summarizer.summarize_articles(
            passed_articles, cache,
            daily_rpd=pipeline_state.daily_rpd,
            metrics=metrics,
        )
        state["cache"] = cache

        if not summarized:
            logger.info(f"[{slot}] Summarization yielded 0 articles.")
            slot_state.status = SlotStatus.DONE
            _save_all_state(state)
            return

        # Step 6: Select topics
        new_topics, _ = topic_selector.select_daily_topics(
            summarized_articles=summarized,
            existing_topics_file=topics_file,
            pipeline_state=pipeline_state,
            metrics=metrics,
            slot=slot,
        )
        topics_file.topics.extend(new_topics)
        topics_file.last_updated = datetime.utcnow()
        slot_state.topics_selected = len(new_topics)

        # Update adaptive mode daily counter (for evening slot — full day perspective)
        if slot == "evening":
            today_graded = [t for t in topics_file.topics
                            if any(h.date.strftime("%Y-%m-%d") == today for h in t.history)]
            today_scores = [h.score for t in today_graded for h in t.history
                           if h.date.strftime("%Y-%m-%d") == today]
            today_avg = sum(today_scores) / len(today_scores) if today_scores else 0.0
            topics_graded = len(today_graded)
            adaptive_mode_service.update_daily_mastery_average(metrics, today_avg, topics_graded)
            adaptive_mode_service.update_adaptive_mode(metrics, today_avg, topics_graded)

        slot_state.status = SlotStatus.DONE
        slot_state.completed_at = datetime.utcnow()
        logger.info(f"[{slot}] RSS pipeline complete. {len(new_topics)} topics added.")

        _save_all_state(state)

    except Exception as exc:
        import traceback as tb_module
        tb = tb_module.format_exc()
        logger.error(f"RSS pipeline failed for slot {slot}: {exc}\n{tb}")
        try:
            from app.models import ErrorEntry
            error_entry = ErrorEntry(
                component="rss_pipeline",
                operation=f"slot_{slot}",
                error_type=type(exc).__name__,
                error_message=str(exc),
                stack_trace=tb,
            )
            state["errors_file"].errors.append(error_entry)
            state["pipeline_state"].slots[slot].status = SlotStatus.FAILED
            _save_all_state(state)
        except Exception as save_exc:
            logger.error(f"Failed to save error state: {save_exc}")


# ──────────────────────────────────────────────────────────────────────────────
# Trigger 2: Email Digest — PRD FR-07 / FRD FS-07
# Cron: 08:30 IST daily
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/email")
async def trigger_email(
    request: Request,
    background_tasks: BackgroundTasks,
    _auth: bool = Depends(verify_cron_secret),
) -> dict[str, Any]:
    """Send today's daily email digest."""
    background_tasks.add_task(_run_email_send)
    return {"status": "accepted", "message": "Email trigger accepted"}


def _run_email_send() -> None:
    """Email sending execution."""
    today = today_ist_str()
    logger.info(f"Email trigger fired for {today}.")
    try:
        state = _load_all_state()
        topics_file = state["topics_file"]
        metrics = state["metrics"]
        cache = state["cache"]
        pipeline_state = state["pipeline_state"]

        # Active topics only (not archived/completed)
        active_topics = [
            t for t in topics_file.topics
            if t.status.value in ("active", "reteaching")
        ]

        success = email_service.send_daily_email(
            topics=active_topics,
            metrics=metrics,
            cache=cache,
            pipeline_state=pipeline_state,
        )

        state["cache"] = cache
        state["pipeline_state"] = pipeline_state
        state["metrics"] = metrics
        _save_all_state(state)

        logger.info(f"Email trigger complete. Success: {success}")
    except Exception as exc:
        logger.error(f"Email trigger failed: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# Trigger 3: Weekly Backup & Adaptive Mode Check — PRD FR-11 / FRD FS-10
# Cron: Sunday 23:00 IST (also integrated into morning trigger in L2-02 fix)
# Left as separate endpoint for manual triggering / override.
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/weekly")
async def trigger_weekly(
    request: Request,
    background_tasks: BackgroundTasks,
    _auth: bool = Depends(verify_cron_secret),
) -> dict[str, Any]:
    """Run weekly backup and maintenance."""
    background_tasks.add_task(_run_weekly)
    return {"status": "accepted", "message": "Weekly trigger accepted"}


def _run_weekly() -> None:
    """Weekly backup + maintenance."""
    logger.info("Weekly trigger fired.")
    try:
        success = drive_client.run_weekly_backup()
        logger.info(f"Weekly backup: success={success}")
    except Exception as exc:
        logger.error(f"Weekly trigger failed: {exc}")
        send_alert_email("Weekly Backup Failed", str(exc))
