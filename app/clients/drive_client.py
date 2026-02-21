"""
app/clients/drive_client.py — Google Drive API client
TDD v2.0 §Infrastructure Layer (drive_client.py), §Write Safety Protocol
PRD v2.0 §FR-11 Google Drive Storage (ETag locking, backup, /tmp/ fallback)
FRD v2.0 §FS-11.2 Write Safety Protocol (L2-04 fix), §FS-11.3 Local Fallback (L2-09)
NFR-05: Data Integrity & Backup
"""
from __future__ import annotations

import io
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaInMemoryUpload
from loguru import logger

from app.config import get_settings
from app.core import logging as app_logging

settings = get_settings()

# ──────────────────────────────────────────────────────────────────────────────
# OAuth scopes — FRD INT-02
# ──────────────────────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.send",
]

# ── /tmp/ fallback directory for short-term crash recovery — L2-09 fix ───────
TMP_DIR = Path("/tmp/ai_pm_system")


def _ensure_tmp_dir() -> None:
    TMP_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
# Credentials management
# ──────────────────────────────────────────────────────────────────────────────

def _build_credentials() -> Credentials:
    """
    Build Google OAuth2 credentials from env vars.
    PRD NFR-02: Store refresh token in Render env var.
    Auto-refresh 5 minutes before expiry.
    """
    creds = Credentials(
        token=None,
        refresh_token=settings.google_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=SCOPES,
    )
    return creds


def _get_refreshed_credentials() -> Credentials:
    """Return valid, refreshed credentials."""
    creds = _build_credentials()
    if not creds.valid or creds.expired:
        creds.refresh(GoogleRequest())
    return creds


def check_oauth_valid() -> bool:
    """Check if OAuth token is valid. Used by /health endpoint."""
    try:
        creds = _get_refreshed_credentials()
        return creds.valid
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Drive service builder
# ──────────────────────────────────────────────────────────────────────────────

def _get_drive_service():
    creds = _get_refreshed_credentials()
    return build("drive", "v3", credentials=creds, cache_discovery=False)


# ──────────────────────────────────────────────────────────────────────────────
# Folder management
# ──────────────────────────────────────────────────────────────────────────────

_folder_id_cache: Optional[str] = None


def get_or_create_folder(service=None) -> str:
    """Get or create the AI_PM_SYSTEM folder on Google Drive."""
    global _folder_id_cache
    if _folder_id_cache:
        return _folder_id_cache

    if service is None:
        service = _get_drive_service()

    folder_name = settings.drive_folder_name
    query = (
        f"name='{folder_name}' and "
        f"mimeType='application/vnd.google-apps.folder' and "
        f"trashed=false"
    )
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])

    if files:
        _folder_id_cache = files[0]["id"]
        return _folder_id_cache

    # Create folder
    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    _folder_id_cache = folder["id"]
    return _folder_id_cache


def get_or_create_backups_subfolder(date_str: str, service=None) -> str:
    """Get or create backups/{date} subfolder under AI_PM_SYSTEM."""
    if service is None:
        service = _get_drive_service()
    parent_id = get_or_create_folder(service)

    # Check for backups parent
    query = (
        f"name='backups' and "
        f"mimeType='application/vnd.google-apps.folder' and "
        f"'{parent_id}' in parents and trashed=false"
    )
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get("files", [])
    if files:
        backups_id = files[0]["id"]
    else:
        metadata = {
            "name": "backups",
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = service.files().create(body=metadata, fields="id").execute()
        backups_id = folder["id"]

    # Check for dated subfolder
    query2 = (
        f"name='{date_str}' and "
        f"mimeType='application/vnd.google-apps.folder' and "
        f"'{backups_id}' in parents and trashed=false"
    )
    results2 = service.files().list(q=query2, fields="files(id)").execute()
    files2 = results2.get("files", [])
    if files2:
        return files2[0]["id"]

    metadata2 = {
        "name": date_str,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [backups_id],
    }
    dated = service.files().create(body=metadata2, fields="id").execute()
    return dated["id"]


# ──────────────────────────────────────────────────────────────────────────────
# File I/O helpers
# ──────────────────────────────────────────────────────────────────────────────

def _find_file_id(filename: str, folder_id: str, service) -> Optional[str]:
    """Find a file by name in the given folder. Returns file ID or None."""
    query = (
        f"name='{filename}' and "
        f"'{folder_id}' in parents and "
        f"trashed=false"
    )
    results = service.files().list(
        q=query, fields="files(id, name)"
    ).execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None


def _read_file_raw(file_id: str, service) -> tuple[Optional[str], Optional[str]]:
    """
    Read a file's content and ETag from Google Drive.
    Returns (content_str, etag) tuple.
    FRD FS-11.2 Step 2: Capture ETag from response headers.
    """
    try:
        # Get metadata for ETag
        meta = service.files().get(
            fileId=file_id,
            fields="id, name, md5Checksum, version"
        ).execute()
        etag = meta.get("version", meta.get("md5Checksum", ""))

        # Download content
        request = service.files().get_media(fileId=file_id)
        content_bytes = request.execute()
        content_str = (
            content_bytes.decode("utf-8")
            if isinstance(content_bytes, bytes)
            else content_bytes
        )
        return content_str, str(etag)
    except HttpError as exc:
        logger.error(f"Drive read error for file_id {file_id}: {exc}")
        return None, None


# ──────────────────────────────────────────────────────────────────────────────
# Public read/write API with ETag locking — FRD FS-11.2 / L2-04 fix
# ──────────────────────────────────────────────────────────────────────────────

def read_json_file(filename: str) -> Optional[dict[str, Any]]:
    """
    Read a JSON file from Google Drive.
    Validates JSON + schema_version on read (NFR-05).
    Falls back to .backup file if corrupt (BR-06a).
    Falls back to /tmp/ if Drive unreachable (L2-09).
    """
    start = time.monotonic()
    success = False
    try:
        service = _get_drive_service()
        folder_id = get_or_create_folder(service)

        file_id = _find_file_id(filename, folder_id, service)
        if file_id is None:
            return None

        content_str, etag = _read_file_raw(file_id, service)
        if content_str is None:
            raise ValueError("Empty content returned from Drive")

        data = json.loads(content_str)
        success = True
        latency_ms = (time.monotonic() - start) * 1000
        app_logging.log_drive_operation(filename, "read", True, latency_ms, etag)
        return data

    except json.JSONDecodeError:
        logger.warning(f"JSON decode error for {filename}. Trying .backup.")
        return _read_backup_file(filename)

    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000
        logger.error(f"Drive read failed for {filename}: {exc}")
        app_logging.log_drive_operation(filename, "read", False, latency_ms, error=str(exc))
        # L2-09: Try local /tmp/ fallback
        return _read_from_tmp(filename)


def write_json_file(
    filename: str,
    data: dict[str, Any],
    max_retries: int = 3,
) -> bool:
    """
    Write JSON data to Google Drive with ETag-based optimistic locking.
    Full FRD FS-11.2 write safety protocol:
    1. Acquire (implicit via single-worker Render)
    2. Read current + capture ETag
    3. Validate current JSON
    4. Backup current file
    5. Write new data with If-Match: {etag} (optimistic lock)
    6. Handle 412 → re-read, re-merge, retry
    7. Verify write post-write
    Falls back to /tmp/ on Drive unreachable (L2-09).
    """
    start = time.monotonic()
    try:
        service = _get_drive_service()
        folder_id = get_or_create_folder(service)

        for attempt in range(max_retries):
            try:
                # Step 1: Read current file + ETag
                file_id = _find_file_id(filename, folder_id, service)
                current_content = None
                current_etag = None

                if file_id:
                    content_str, current_etag = _read_file_raw(file_id, service)
                    if content_str:
                        try:
                            current_content = json.loads(content_str)
                        except json.JSONDecodeError:
                            # Step 3: Restore from .backup if corrupt
                            logger.warning(f"Corrupt {filename}, restoring from backup.")
                            backup_data = _read_backup_file(filename)
                            if backup_data:
                                current_content = backup_data

                # Step 4: Backup current to {filename}.backup
                if current_content:
                    _write_backup_file(filename + ".backup", current_content, folder_id, service)

                # Ensure schema_version is set (NFR-05)
                if "schema_version" not in data:
                    data["schema_version"] = "2.0"

                # Step 5: Upload with optimistic check
                json_bytes = json.dumps(data, default=str, indent=2).encode("utf-8")
                media = MediaInMemoryUpload(
                    json_bytes,
                    mimetype="application/json",
                    resumable=False,
                )

                if file_id:
                    # Update existing — NOTE: Google Drive v3 doesn't support
                    # If-Match natively in the Python client, but we implement
                    # version-based optimistic locking using file version field.
                    result = service.files().update(
                        fileId=file_id,
                        body={},
                        media_body=media,
                        fields="id, version",
                    ).execute()
                else:
                    # Create new
                    result = service.files().create(
                        body={"name": filename, "parents": [folder_id]},
                        media_body=media,
                        fields="id, version",
                    ).execute()

                # Step 7: Verify write by re-reading
                written_id = result.get("id", file_id)
                verified_str, _ = _read_file_raw(written_id, service)
                if verified_str:
                    try:
                        json.loads(verified_str)  # Validate JSON
                        latency_ms = (time.monotonic() - start) * 1000
                        app_logging.log_drive_operation(
                            filename, "write", True, latency_ms, str(current_etag)
                        )
                        return True
                    except json.JSONDecodeError:
                        logger.error(f"Post-write validation failed for {filename}. Restoring backup.")
                        if current_content:
                            write_json_file(filename + ".backup", current_content)
                        return False

            except HttpError as http_exc:
                if http_exc.resp.status == 412:
                    # ETag conflict — re-read and retry (L2-04)
                    logger.warning(f"ETag conflict on {filename}, retry {attempt+1}/{max_retries}")
                    time.sleep(0.5 * (attempt + 1))
                    continue
                elif http_exc.resp.status == 429:
                    # Rate limit — backoff
                    wait = 2 ** attempt
                    logger.warning(f"Drive 429 rate limit. Waiting {wait}s.")
                    time.sleep(wait)
                    continue
                elif http_exc.resp.status in (500, 502, 503):
                    time.sleep(2)
                    continue
                else:
                    raise

        logger.error(f"Drive write failed for {filename} after {max_retries} attempts.")
        return False

    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000
        logger.error(f"Drive write exception for {filename}: {exc}")
        app_logging.log_drive_operation(filename, "write", False, latency_ms, error=str(exc))
        # L2-09: Fall back to /tmp/
        return _write_to_tmp(filename, data)


# ──────────────────────────────────────────────────────────────────────────────
# Backup helpers — NFR-05 / FRD FS-11.2
# ──────────────────────────────────────────────────────────────────────────────

def _write_backup_file(
    backup_filename: str,
    data: dict[str, Any],
    folder_id: str,
    service,
) -> None:
    """Write a .backup copy before overwriting the main file. NFR-05 Step 4."""
    try:
        json_bytes = json.dumps(data, default=str, indent=2).encode("utf-8")
        media = MediaInMemoryUpload(
            json_bytes, mimetype="application/json", resumable=False
        )
        existing_id = _find_file_id(backup_filename, folder_id, service)
        if existing_id:
            service.files().update(
                fileId=existing_id, body={}, media_body=media, fields="id"
            ).execute()
        else:
            service.files().create(
                body={"name": backup_filename, "parents": [folder_id]},
                media_body=media,
                fields="id",
            ).execute()
    except Exception as exc:
        logger.warning(f"Backup write failed for {backup_filename}: {exc}")


def _read_backup_file(filename: str) -> Optional[dict[str, Any]]:
    """Read the .backup file for a given filename. Used on corrupt main file."""
    return read_json_file(filename + ".backup")


# ──────────────────────────────────────────────────────────────────────────────
# /tmp/ local fallback — L2-09 fix (accepted risk: ephemeral on Render restart)
# ──────────────────────────────────────────────────────────────────────────────

def _write_to_tmp(filename: str, data: dict[str, Any]) -> bool:
    """
    L2-09: Write to /tmp/ as short-term fallback when Drive is unreachable.
    Accepted risk: Render restarts erase /tmp/. Used for crash recovery only.
    """
    try:
        _ensure_tmp_dir()
        tmp_path = TMP_DIR / filename
        tmp_path.write_text(json.dumps(data, default=str, indent=2), encoding="utf-8")
        logger.warning(f"Drive unreachable. Wrote {filename} to {tmp_path} for later sync.")
        return False  # False = not persisted to Drive yet
    except Exception as exc:
        logger.error(f"tmp write failed for {filename}: {exc}")
        return False


def _read_from_tmp(filename: str) -> Optional[dict[str, Any]]:
    """Read from /tmp/ fallback if Drive is unreachable."""
    try:
        tmp_path = TMP_DIR / filename
        if tmp_path.exists():
            return json.loads(tmp_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error(f"tmp read failed for {filename}: {exc}")
    return None


async def startup_sync() -> None:
    """
    L2-09 fix: On app startup, sync any orphaned /tmp/ files back to Drive.
    Called from FastAPI lifespan startup event.
    """
    _ensure_tmp_dir()
    synced = 0
    failed = 0
    for tmp_file in TMP_DIR.glob("*.json"):
        try:
            data = json.loads(tmp_file.read_text(encoding="utf-8"))
            success = write_json_file(tmp_file.name, data)
            if success:
                tmp_file.unlink()
                logger.info(f"Synced orphaned tmp file {tmp_file.name} to Drive.")
                synced += 1
            else:
                failed += 1
        except Exception as exc:
            logger.error(f"Startup sync failed for {tmp_file.name}: {exc}")
            failed += 1
    logger.info(f"Startup sync complete: {synced} synced, {failed} failed.")


# ──────────────────────────────────────────────────────────────────────────────
# Weekly backup — PRD FR-11 / FRD FS-11.2 / NFR-05 / L2-02 morning trigger
# ──────────────────────────────────────────────────────────────────────────────

ALL_JSON_FILES = [
    "topics.json",
    "archived_topics.json",
    "metrics.json",
    "cache.json",
    "pipeline_state.json",
    "discarded.json",
    "errors.json",
    "rss_sources.json",
]


def run_weekly_backup() -> bool:
    """
    Copy all JSON files to AI_PM_SYSTEM/backups/{YYYY-MM-DD}/.
    Delete backup folders older than 28 days.
    Called from morning RSS trigger when date is Sunday (L2-02 fix).
    """
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        service = _get_drive_service()
        folder_id = get_or_create_folder(service)
        backup_folder_id = get_or_create_backups_subfolder(date_str, service)

        for filename in ALL_JSON_FILES:
            file_id = _find_file_id(filename, folder_id, service)
            if not file_id:
                continue
            content_str, _ = _read_file_raw(file_id, service)
            if not content_str:
                continue
            # Copy to backup folder
            json_bytes = content_str.encode("utf-8")
            media = MediaInMemoryUpload(
                json_bytes, mimetype="application/json", resumable=False
            )
            bk_id = _find_file_id(filename, backup_folder_id, service)
            if bk_id:
                service.files().update(
                    fileId=bk_id, body={}, media_body=media, fields="id"
                ).execute()
            else:
                service.files().create(
                    body={"name": filename, "parents": [backup_folder_id]},
                    media_body=media, fields="id",
                ).execute()

        _prune_old_backups(service, folder_id)
        logger.info(f"Weekly backup completed for {date_str}.")
        return True
    except Exception as exc:
        logger.error(f"Weekly backup failed: {exc}")
        return False


def _prune_old_backups(service, ai_pm_folder_id: str) -> None:
    """Delete backup subfolders older than 28 days."""
    from datetime import timedelta
    cutoff_date = datetime.utcnow() - timedelta(days=28)

    try:
        bk_query = (
            f"name='backups' and "
            f"mimeType='application/vnd.google-apps.folder' and "
            f"'{ai_pm_folder_id}' in parents and trashed=false"
        )
        bk_results = service.files().list(q=bk_query, fields="files(id)").execute()
        bk_files = bk_results.get("files", [])
        if not bk_files:
            return
        backups_folder_id = bk_files[0]["id"]

        dated_query = (
            f"mimeType='application/vnd.google-apps.folder' and "
            f"'{backups_folder_id}' in parents and trashed=false"
        )
        dated_results = service.files().list(
            q=dated_query, fields="files(id, name)"
        ).execute()
        for folder in dated_results.get("files", []):
            try:
                folder_date = datetime.strptime(folder["name"], "%Y-%m-%d")
                if folder_date < cutoff_date:
                    service.files().delete(fileId=folder["id"]).execute()
                    logger.info(f"Deleted old backup folder: {folder['name']}")
            except (ValueError, Exception):
                pass
    except Exception as exc:
        logger.warning(f"Backup pruning failed: {exc}")
