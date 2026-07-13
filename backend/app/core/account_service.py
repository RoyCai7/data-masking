"""
account_service.py - Email/password account auth and web session handling.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from app.engine.repo_users import (
    db_add_email_verification,
    db_add_password_reset,
    db_add_session,
    db_count_users,
    db_create_user,
    db_disable_session,
    db_disable_user_sessions,
    db_get_email_verification,
    db_get_password_reset,
    db_get_session_by_hash,
    db_get_user_by_email,
    db_mark_email_verification_used,
    db_mark_user_email_verified,
    db_mark_password_reset_used,
    db_update_user_password,
)
from app.core.email_service import (
    send_email_verification_email,
    send_password_reset_email,
    smtp_configuration_error,
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_MIN_LENGTH = 8
PBKDF2_ITERATIONS = 210_000


def normalize_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if not EMAIL_RE.match(normalized):
        raise HTTPException(status_code=400, detail="Valid email is required")
    return normalized


def validate_password(password: str) -> None:
    if len(password or "") < PASSWORD_MIN_LENGTH:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations, salt, digest = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(candidate, digest)
    except Exception:
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utc_date_after(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


def _utc_datetime_after(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(microsecond=0).isoformat()


def _session_token() -> str:
    return f"dms_sess_{secrets.token_urlsafe(32)}"


def _reset_token() -> str:
    return f"dms_reset_{secrets.token_urlsafe(32)}"


def _verification_token() -> str:
    return f"dms_verify_{secrets.token_urlsafe(32)}"


def _require_email_delivery() -> None:
    config_error = smtp_configuration_error()
    if config_error:
        raise HTTPException(status_code=503, detail=f"Email delivery is not configured: {config_error}")


def _session_auth_user(row: dict) -> dict:
    user_id = int(row["user_id"])
    return {
        "auth_type": "session",
        "user_id": user_id,
        "email": row["email"],
        "name": row["name"],
        "role": row.get("role", "user"),
        "org_id": row.get("org_id") or "default",
        "key_prefix": f"user_{user_id}",
        "created_at": row.get("user_created_at"),
        "expires_at": row.get("expires_at"),
    }


def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user.get("role", "user"),
        "org_id": user.get("org_id") or "default",
        "enabled": bool(user.get("enabled", True)),
        "email_verified": bool(user.get("email_verified", False)),
        "created_at": user.get("created_at"),
    }


def create_session_for_user(user: dict, days: int = 14) -> dict:
    token = _session_token()
    session = db_add_session(
        user_id=int(user["id"]),
        token_hash=_hash_token(token),
        expires_at=_utc_date_after(days),
    )
    return {
        "token": token,
        "expires_at": session.get("expires_at"),
        "user": public_user(user),
    }


def register_user(email: str, password: str, name: Optional[str] = None) -> dict:
    email = normalize_email(email)
    validate_password(password)
    _require_email_delivery()

    existing = db_get_user_by_email(email)
    if existing and existing.get("email_verified", False):
        raise HTTPException(status_code=409, detail="Email is already registered")

    if existing:
        db_update_user_password(int(existing["id"]), hash_password(password))
        user = db_get_user_by_email(email)
    else:
        first_user_admin = os.getenv("DMS_FIRST_USER_ADMIN", "true").lower() in {"1", "true", "yes", "on"}
        role = "admin" if first_user_admin and db_count_users() == 0 else "user"
        user = db_create_user(
            email=email,
            name=(name or email).strip() or email,
            password_hash=hash_password(password),
            role=role,
            org_id="default",
        )
    token = _verification_token()
    db_add_email_verification(
        user_id=int(user["id"]),
        token_hash=_hash_token(token),
        expires_at=_utc_datetime_after(24),
    )
    delivery = send_email_verification_email(email, token)
    if not delivery.sent:
        raise HTTPException(status_code=503, detail=f"Activation email was not sent: {delivery.detail}")

    response = {
        "message": "Check your email to activate your account before signing in.",
        "email": email,
        "email_sent": delivery.sent,
        "delivery_detail": delivery.detail,
        "user": public_user(user),
    }
    return response


def login_user(email: str, password: str) -> dict:
    email = normalize_email(email)
    user = db_get_user_by_email(email)
    if not user or not user.get("enabled", True) or not verify_password(password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("email_verified", False):
        raise HTTPException(status_code=403, detail="Email is not activated. Check your email for the activation link.")
    return create_session_for_user(user)


def verify_email(token: str) -> dict:
    row = db_get_email_verification(_hash_token(token or ""))
    if not row or row.get("used"):
        raise HTTPException(status_code=400, detail="Invalid or used activation link")
    try:
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Activation link has expired")
    except ValueError:
        raise HTTPException(status_code=400, detail="Activation link has invalid expiry")

    user_id = int(row["user_id"])
    db_mark_user_email_verified(user_id)
    db_mark_email_verification_used(_hash_token(token))
    user = db_get_user_by_email(row["email"])
    return create_session_for_user(user)


def validate_session_token(token: str) -> dict:
    row = db_get_session_by_hash(_hash_token(token))
    if not row or not row.get("enabled", True):
        raise HTTPException(status_code=401, detail="Invalid session")
    if not row.get("user_enabled", True):
        raise HTTPException(status_code=403, detail="User account is disabled")
    expires_at = row.get("expires_at")
    if expires_at:
        try:
            if datetime.fromisoformat(expires_at).date() < datetime.now(timezone.utc).date():
                raise HTTPException(status_code=403, detail="Session has expired")
        except ValueError:
            raise HTTPException(status_code=403, detail="Session has invalid expiry date")
    return _session_auth_user(row)


def logout_session(token: str) -> bool:
    return db_disable_session(_hash_token(token))


def create_password_reset(email: str) -> dict:
    email = normalize_email(email)
    _require_email_delivery()
    user = db_get_user_by_email(email)
    response = {
        "message": "If the email exists, a password reset link has been sent.",
        "email": email,
        "email_sent": False,
        "delivery_detail": "If the email exists, delivery was attempted.",
    }
    if not user or not user.get("enabled", True):
        return response
    token = _reset_token()
    db_add_password_reset(
        user_id=int(user["id"]),
        token_hash=_hash_token(token),
        expires_at=_utc_datetime_after(2),
    )
    delivery = send_password_reset_email(email, token)
    response["email_sent"] = delivery.sent
    response["delivery_detail"] = delivery.detail
    return response


def reset_password(token: str, new_password: str) -> dict:
    validate_password(new_password)
    row = db_get_password_reset(_hash_token(token or ""))
    if not row or row.get("used"):
        raise HTTPException(status_code=400, detail="Invalid or used reset token")
    try:
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Reset token has expired")
    except ValueError:
        raise HTTPException(status_code=400, detail="Reset token has invalid expiry")

    user_id = int(row["user_id"])
    db_update_user_password(user_id, hash_password(new_password))
    db_mark_password_reset_used(_hash_token(token))
    db_disable_user_sessions(user_id)
    return {"message": "Password reset successfully"}
