"""
Email delivery for account activation and password recovery.

SMTP is required for account activation and password recovery in production.
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


def smtp_configuration_error() -> str | None:
    """Return a human-readable SMTP configuration problem, or None when usable."""
    host = os.getenv("DMS_SMTP_HOST", "").strip()
    if not host:
        return "DMS_SMTP_HOST is required"
    sender = os.getenv("DMS_SMTP_FROM", os.getenv("DMS_SMTP_USER", "")).strip()
    if not sender:
        return "DMS_SMTP_FROM or DMS_SMTP_USER is required"
    return None


def send_password_reset_email(email: str, reset_token: str) -> EmailDeliveryResult:
    """Send a password reset token or link through SMTP."""
    config_error = smtp_configuration_error()
    if config_error:
        logger.warning("SMTP is not configured; password reset email for %s was not sent", email)
        return EmailDeliveryResult(sent=False, detail=config_error)

    host = os.getenv("DMS_SMTP_HOST", "").strip()
    port = int(os.getenv("DMS_SMTP_PORT", "587"))
    sender = os.getenv("DMS_SMTP_FROM", os.getenv("DMS_SMTP_USER", "")).strip()
    username = os.getenv("DMS_SMTP_USER", "").strip()
    password = os.getenv("DMS_SMTP_PASSWORD", "")
    use_tls = _env_bool("DMS_SMTP_TLS", True)
    base_url = os.getenv("DMS_PUBLIC_BASE_URL", "").rstrip("/")
    reset_line = reset_token
    if base_url:
        reset_line = f"{base_url}/?reset_token={reset_token}"

    message = EmailMessage()
    message["From"] = sender
    message["To"] = email
    message["Subject"] = "Reset your Data Masking Service password"
    message.set_content(
        "\n".join([
            "Data Masking Service password reset",
            "",
            "Use the following reset link or token within 2 hours.",
            "",
            reset_line,
            "",
            "If you did not request this, ignore this email.",
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
        logger.warning("Failed to send password reset email to %s: %s", email, exc)
        return EmailDeliveryResult(sent=False, detail="Failed to send email")

    return EmailDeliveryResult(sent=True, detail="Password reset email sent")


def send_email_verification_email(email: str, verification_token: str) -> EmailDeliveryResult:
    """Send account activation email through SMTP."""
    config_error = smtp_configuration_error()
    if config_error:
        logger.warning("SMTP is not configured; activation email for %s was not sent", email)
        return EmailDeliveryResult(sent=False, detail=config_error)

    host = os.getenv("DMS_SMTP_HOST", "").strip()
    port = int(os.getenv("DMS_SMTP_PORT", "587"))
    sender = os.getenv("DMS_SMTP_FROM", os.getenv("DMS_SMTP_USER", "")).strip()
    username = os.getenv("DMS_SMTP_USER", "").strip()
    password = os.getenv("DMS_SMTP_PASSWORD", "")
    use_tls = _env_bool("DMS_SMTP_TLS", True)
    base_url = os.getenv("DMS_PUBLIC_BASE_URL", "").rstrip("/")
    activation_line = verification_token
    if base_url:
        activation_line = f"{base_url}/?verify_token={verification_token}"

    message = EmailMessage()
    message["From"] = sender
    message["To"] = email
    message["Subject"] = "Activate your Data Masking Service account"
    message.set_content(
        "\n".join([
            "Data Masking Service account activation",
            "",
            "Open the following link to activate your account.",
            "",
            activation_line,
            "",
            "If you did not create this account, ignore this email.",
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
        logger.warning("Failed to send activation email to %s: %s", email, exc)
        return EmailDeliveryResult(sent=False, detail="Failed to send email")

    return EmailDeliveryResult(sent=True, detail="Activation email sent")
