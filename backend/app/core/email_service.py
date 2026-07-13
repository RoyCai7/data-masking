"""
Email delivery for account activation and password recovery.

SMTP is required for account activation and password recovery in production.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import socket
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailDeliveryResult:
    sent: bool
    detail: str


@dataclass(frozen=True)
class TokenEmailTemplate:
    purpose: str
    subject: str
    heading: str
    instruction: str
    token_param: str
    footer: str


PASSWORD_RESET_TEMPLATE = TokenEmailTemplate(
    purpose="Password reset",
    subject="Reset your Data Masking Service password",
    heading="Data Masking Service password reset",
    instruction="Use the following reset link or token within 2 hours.",
    token_param="reset_token",
    footer="If you did not request this, ignore this email.",
)

EMAIL_VERIFICATION_TEMPLATE = TokenEmailTemplate(
    purpose="Activation",
    subject="Activate your Data Masking Service account",
    heading="Data Masking Service account activation",
    instruction="Open the following link to activate your account.",
    token_param="verify_token",
    footer="If you did not create this account, ignore this email.",
)


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


def _smtp_timeout_seconds() -> int:
    try:
        return max(5, int(os.getenv("DMS_SMTP_TIMEOUT_SECONDS", "30")))
    except ValueError:
        return 30


def _email_failure_detail(exc: Exception) -> str:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "SMTP server timed out while sending email"
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "SMTP authentication failed"
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "Recipient email was refused"
    return "Failed to send email"


def _send_email_message(message: EmailMessage, recipient: str, purpose: str) -> EmailDeliveryResult:
    host = os.getenv("DMS_SMTP_HOST", "").strip()
    port = int(os.getenv("DMS_SMTP_PORT", "587"))
    username = os.getenv("DMS_SMTP_USER", "").strip()
    password = os.getenv("DMS_SMTP_PASSWORD", "")
    use_tls = _env_bool("DMS_SMTP_TLS", True)
    timeout = _smtp_timeout_seconds()
    last_exc: Exception | None = None

    for attempt in range(2):
        smtp = None
        try:
            smtp = smtplib.SMTP(host, port, timeout=timeout)
            if use_tls:
                smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
            try:
                smtp.quit()
            except Exception:
                logger.debug("SMTP quit failed after %s email was sent to %s", purpose, recipient, exc_info=True)
            return EmailDeliveryResult(sent=True, detail=f"{purpose} email sent")
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Failed to send %s email to %s on attempt %s: %s",
                purpose.lower(),
                recipient,
                attempt + 1,
                exc,
            )
            if smtp is not None:
                try:
                    smtp.close()
                except Exception:
                    pass
            if not isinstance(exc, (TimeoutError, socket.timeout)):
                break

    return EmailDeliveryResult(sent=False, detail=_email_failure_detail(last_exc or RuntimeError("unknown error")))


def _token_line(token_param: str, token: str) -> str:
    base_url = os.getenv("DMS_PUBLIC_BASE_URL", "").rstrip("/")
    if not base_url:
        return token
    return f"{base_url}/?{token_param}={token}"


def _send_token_email(email: str, token: str, template: TokenEmailTemplate) -> EmailDeliveryResult:
    config_error = smtp_configuration_error()
    if config_error:
        logger.warning("SMTP is not configured; %s email for %s was not sent", template.purpose.lower(), email)
        return EmailDeliveryResult(sent=False, detail=config_error)

    sender = os.getenv("DMS_SMTP_FROM", os.getenv("DMS_SMTP_USER", "")).strip()
    message = EmailMessage()
    message["From"] = sender
    message["To"] = email
    message["Subject"] = template.subject
    message.set_content(
        "\n".join([
            template.heading,
            "",
            template.instruction,
            "",
            _token_line(template.token_param, token),
            "",
            template.footer,
        ])
    )
    return _send_email_message(message, email, template.purpose)


def send_password_reset_email(email: str, reset_token: str) -> EmailDeliveryResult:
    """Send a password reset token or link through SMTP."""
    return _send_token_email(email, reset_token, PASSWORD_RESET_TEMPLATE)


def send_email_verification_email(email: str, verification_token: str) -> EmailDeliveryResult:
    """Send account activation email through SMTP."""
    return _send_token_email(email, verification_token, EMAIL_VERIFICATION_TEMPLATE)
