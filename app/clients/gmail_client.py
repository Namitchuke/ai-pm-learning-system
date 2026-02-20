"""
app/clients/gmail_client.py — Gmail API client
TDD v2.0 §Infrastructure Layer (gmail_client.py)
PRD v2.0 §FR-07 Daily Email Digest
FRD v2.0 §INT-03 Gmail API
"""
from __future__ import annotations

import base64
import email.mime.multipart
import email.mime.text
import time
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from loguru import logger

from app.config import get_settings
from app.clients.drive_client import SCOPES, _build_credentials

settings = get_settings()


def _get_gmail_service():
    """Build authenticated Gmail API service."""
    creds = _build_credentials()
    if not creds.valid or creds.expired:
        creds.refresh(GoogleRequest())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def send_email(
    subject: str,
    html_body: str,
    plain_body: str,
    to_address: Optional[str] = None,
    from_address: Optional[str] = None,
) -> bool:
    """
    Send an email via Gmail API.
    PRD FR-07: Sent via Gmail API to configured recipient.
    FRD FS-07.4: multipart/alternative (HTML + plain-text).
    Returns True on success, False on failure.
    """
    to_address = to_address or settings.recipient_email
    from_address = from_address or settings.sender_email

    # Build multipart message — FRD FS-07.2: multipart/alternative
    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_address
    msg["To"] = to_address

    # Plain-text part first (fallback for basic clients)
    part_plain = email.mime.text.MIMEText(plain_body, "plain", "utf-8")
    # HTML part second (preferred)
    part_html = email.mime.text.MIMEText(html_body, "html", "utf-8")

    msg.attach(part_plain)
    msg.attach(part_html)

    # Encode to base64 for Gmail API
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    for attempt in range(3):
        try:
            service = _get_gmail_service()
            service.users().messages().send(
                userId="me",
                body={"raw": raw},
            ).execute()
            logger.info(f"Email sent successfully to {to_address}: {subject}")
            return True

        except Exception as exc:
            logger.error(f"Gmail send attempt {attempt+1} failed: {exc}")
            if attempt < 2:
                time.sleep(2 ** attempt)

    return False


def send_alert_email(subject: str, body: str) -> bool:
    """
    Send a critical alert email.
    PRD NFR-04: On critical failures (OAuth invalid, budget exceeded,
    3+ consecutive pipeline failures, model deprecation).
    """
    plain_body = body
    html_body = f"<pre>{body}</pre>"
    return send_email(
        subject=f"[AI PM SYSTEM ALERT] {subject}",
        html_body=html_body,
        plain_body=plain_body,
    )
