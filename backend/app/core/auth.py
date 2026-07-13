"""
auth.py — Authentication middleware + low-level key validation.

Responsibilities (intentionally narrow):
  - Define AUTH_ENABLED flag and PUBLIC_PATHS
  - _hash_key / generate_api_key  (cryptographic primitives only)
  - validate_key                  (lookup + expiry check, no business logic)
  - APIKeyMiddleware               (inject auth_user into request.state)

Business operations (create/rotate/update/disable keys) live in:
  → core/key_service.py

Permission guards (require_admin, require_auth) live in:
  → core/permissions.py

Backward-compat re-exports for existing callers:
  add_key, rotate_key, update_key, disable_key
  (These will be removed in a future cleanup pass)
"""
import hashlib
import os
import secrets
import logging
from datetime import date
from typing import Optional, Any

try:
    from fastapi import Request, HTTPException
    from fastapi.responses import JSONResponse
    from starlette.middleware.base import BaseHTTPMiddleware
except ModuleNotFoundError:
    Request = Any

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class JSONResponse:
        def __init__(self, status_code: int, content: dict):
            self.status_code = status_code
            self.content = content

    class BaseHTTPMiddleware:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("FastAPI/Starlette is required to use APIKeyMiddleware")

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() == "true"

PUBLIC_PATHS = frozenset({
    "/api/v1/status",
    "/api/v1/rules",
    "/api/v1/session",
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/verify-email",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
})

PUBLIC_PREFIXES = (
    "/assets/",
)


# ── Cryptographic primitives ──────────────────────────────────────────────────

def _hash_key(api_key: str) -> str:
    """Return the SHA-256 hex digest of an API key."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def generate_api_key() -> str:
    """Generate a new API key with dms_ prefix."""
    return f"dms_{secrets.token_hex(16)}"


# ── Validation (read-only DB lookup) ─────────────────────────────────────────

def validate_key(api_key: str) -> dict:
    """
    Validate an API key by hashing and looking up in SQLite.
    Returns the key record dict if valid, raises HTTPException otherwise.
    """
    from app.engine.repository import db_get_key_by_hash  # lazy import
    key_data = db_get_key_by_hash(_hash_key(api_key))

    if not key_data:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    if not key_data.get("enabled", True):
        raise HTTPException(status_code=403, detail="API Key has been disabled")

    expires_at = key_data.get("expires_at")
    if expires_at:
        try:
            if date.fromisoformat(expires_at) < date.today():
                raise HTTPException(status_code=403, detail="API Key has expired")
        except ValueError:
            raise HTTPException(status_code=403, detail="API Key has invalid expiry date")

    # Inject a stable key_prefix so callers can generate previews without plaintext
    key_data.setdefault("key_prefix", api_key[:8])
    key_data.setdefault("auth_type", "api_key")
    return key_data


def _extract_session_token(request: Request) -> Optional[str]:
    token = request.headers.get("X-Session-Token")
    if token:
        return token
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def _is_public_path(path: str) -> bool:
    """Check if a path is public (no auth required)"""
    # Exact match
    if path in PUBLIC_PATHS:
        return True
    # Prefix match
    if any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return True
    # Non-API paths (frontend SPA)
    if not path.startswith("/api/"):
        return True
    return False


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces API Key authentication on protected endpoints.
    
    - Checks X-API-Key header
    - Injects user info into request.state.auth_user
    - Public paths: auth is optional (credentials accepted but not required)
    - Protected paths: auth is mandatory
    """

    async def dispatch(self, request: Request, call_next):
        # Skip auth if disabled
        if not AUTH_ENABLED:
            return await call_next(request)

        path = request.url.path

        # Extract API key (header only — never from query params for security)
        api_key = request.headers.get("X-API-Key")
        session_token = _extract_session_token(request)

        if _is_public_path(path):
            # Public paths: optionally validate credentials if provided
            if session_token:
                try:
                    from app.core.account_service import validate_session_token
                    request.state.auth_user = validate_session_token(session_token)
                except HTTPException:
                    pass
            if api_key:
                try:
                    key_data = validate_key(api_key)
                    request.state.auth_user = key_data
                except HTTPException:
                    pass  # Optional auth — don't block on invalid key
            return await call_next(request)

        # Protected path — require a valid web session or API key
        if not api_key and not session_token:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Authentication required. Sign in or provide X-API-Key header.",
                    "docs": "Use /api/v1/auth/login for web sessions or an API token for external calls."
                }
            )

        try:
            if session_token:
                from app.core.account_service import validate_session_token
                request.state.auth_user = validate_session_token(session_token)
            else:
                key_data = validate_key(api_key)
                request.state.auth_user = key_data
        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )

        return await call_next(request)


# ── Backward-compatible re-exports ────────────────────────────────────────────
# Callers that still import add_key / rotate_key / update_key from here will
# continue to work.  Prefer importing from core.key_service directly.
def add_key(name: str, role: str = "user", expires_days: int = 365,
            org_id: str = "default") -> dict:
    from app.core.key_service import add_key as _add_key
    return _add_key(name=name, role=role, expires_days=expires_days, org_id=org_id)


def rotate_key(old_api_key: str):
    from app.core.key_service import rotate_key as _rotate_key
    return _rotate_key(old_api_key)


def update_key(api_key: str, org_id=None, role=None):
    from app.core.key_service import update_key as _update_key
    return _update_key(api_key, org_id=org_id, role=role)


def disable_key(api_key: str) -> bool:
    from app.core.key_service import disable_key as _disable_key
    return _disable_key(api_key)
