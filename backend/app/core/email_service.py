"""
Email delivery for self-service API token registration and recovery.

SMTP is optional at runtime. When it is not configured, callers get a clear
delivery status instead of a false success.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailDeliveryResult:
    sent: bool
    detail: str


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def email_debug_return_token_enabled() -> bool:
    """Allow tests/local demos to return the token in the API response."""
    return _env_bool("DMS_EMAIL_DEBUG_RETURN_TOKEN", False)


def send_token_email(email: str, token: str, purpose: str) -> EmailDeliveryResult:
    """
    Send a token email through SMTP.

    Environment:
      DMS_SMTP_HOST, DMS_SMTP_PORT, DMS_SMTP_USER, DMS_SMTP_PASSWORD,
      DMS_SMTP_FROM, DMS_SMTP_TLS
    """
    host = os.getenv("DMS_SMTP_HOST", "").strip()
    if not host:
        logger.warning("SMTP is not configured; token email for %s was not sent", email)
        return EmailDeliveryResult(sent=False, detail="SMTP is not configured")

    port = int(os.getenv("DMS_SMTP_PORT", "587"))
    sender = os.getenv("DMS_SMTP_FROM", os.getenv("DMS_SMTP_USER", "")).strip()
    username = os.getenv("DMS_SMTP_USER", "").strip()
    password = os.getenv("DMS_SMTP_PASSWORD", "")
    use_tls = _env_bool("DMS_SMTP_TLS", True)
    if not sender:
        return EmailDeliveryResult(sent=False, detail="DMS_SMTP_FROM or DMS_SMTP_USER is required")

    subject = "Your Data Masking Service token"
    action = "registration" if purpose == "register" else "recovery"
    message = EmailMessage()
    message["From"] = sender
    message["To"] = email
    message["Subject"] = subject
    message.set_content(
        "\n".join([
            "Data Masking Service token",
            "",
            f"This token was requested for {action}.",
            "",
            token,
            "",
            "Keep this token private. Anyone with it can use your Data Masking Service account.",
        ])
    )

    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            if use_tls:
                smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
    except Exception as exc:
        logger.warning("Failed to send token email to %s: %s", email, exc)
        return EmailDeliveryResult(sent=False, detail="Failed to send email")

    return EmailDeliveryResult(sent=True, detail="Token email sent")
