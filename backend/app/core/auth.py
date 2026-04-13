"""
API Key Authentication Module
Provides middleware and utilities for API Key based authentication.

Usage:
  - Set AUTH_ENABLED=true (default) to enforce API Key auth
  - Set AUTH_ENABLED=false for development mode (no auth)
  - Public endpoints (/status, /rules, /docs) are always accessible
  - Protected endpoints require X-API-Key header
"""
import json
import os
import secrets
import logging
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

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

# Configuration
KEYS_FILE = Path(os.getenv("API_KEYS_FILE", str(Path(__file__).parent.parent.parent / "keys.json")))
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() == "true"

# In-memory key cache
_keys_cache: Optional[Dict[str, dict]] = None
_keys_mtime: float = 0.0

# Paths that don't require authentication (but optionally accept credentials)
PUBLIC_PATHS = frozenset({
    "/api/v1/status",
    "/api/v1/rules",
    "/api/v1/session",
    "/api/v1/rules-export",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
})

# Path prefixes that don't require authentication
PUBLIC_PREFIXES = (
    "/assets/",
)


def generate_api_key() -> str:
    """Generate a new API key with dms_ prefix"""
    return f"dms_{secrets.token_hex(16)}"


def _load_keys_file() -> dict:
    """Load keys from JSON file"""
    if not KEYS_FILE.exists():
        return {"keys": []}
    try:
        with open(KEYS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load keys file {KEYS_FILE}: {e}")
        return {"keys": []}


def _save_keys_file(data: dict):
    """Save keys to JSON file atomically (write-to-temp then rename)"""
    global _keys_cache, _keys_mtime
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(KEYS_FILE.parent), suffix=".tmp"
        )
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, str(KEYS_FILE))
        # Invalidate cache so next read picks up changes
        _keys_cache = None
        _keys_mtime = 0.0
    except Exception as e:
        logger.error(f"Failed to save keys file: {e}")
        # Clean up temp file if rename failed
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


def load_keys() -> Dict[str, dict]:
    """Load all API keys as a dict keyed by the key string (cached)"""
    global _keys_cache, _keys_mtime
    try:
        mtime = KEYS_FILE.stat().st_mtime if KEYS_FILE.exists() else 0.0
    except OSError:
        mtime = 0.0
    if _keys_cache is not None and mtime == _keys_mtime:
        return _keys_cache
    data = _load_keys_file()
    _keys_cache = {k["key"]: k for k in data.get("keys", [])}
    _keys_mtime = mtime
    return _keys_cache


def add_key(name: str, role: str = "user", expires_days: int = 365) -> dict:
    """Add a new API key and save to file"""
    data = _load_keys_file()
    new_key = {
        "key": generate_api_key(),
        "name": name,
        "role": role,
        "created_at": date.today().isoformat(),
        "expires_at": (date.today() + timedelta(days=expires_days)).isoformat(),
        "enabled": True,
    }
    data.setdefault("keys", []).append(new_key)
    _save_keys_file(data)
    logger.info(f"API key created for '{name}' (role={role})")
    return new_key


def disable_key(api_key: str) -> bool:
    """Disable an API key"""
    data = _load_keys_file()
    for k in data.get("keys", []):
        if k["key"] == api_key:
            k["enabled"] = False
            _save_keys_file(data)
            logger.info(f"API key disabled for '{k.get('name')}'")
            return True
    return False


def rotate_key(old_api_key: str) -> Optional[dict]:
    """
    Rotate an API key: disable the old one, create a new one with same name/role.
    Returns the new key data, or None if old key not found.
    """
    data = _load_keys_file()
    old_entry = None
    for k in data.get("keys", []):
        if k["key"] == old_api_key:
            old_entry = k
            break

    if not old_entry:
        return None

    # Disable old key
    old_entry["enabled"] = False

    # Create new key inheriting name and role
    new_key = {
        "key": generate_api_key(),
        "name": old_entry["name"],
        "role": old_entry.get("role", "user"),
        "created_at": date.today().isoformat(),
        "expires_at": (date.today() + timedelta(days=365)).isoformat(),
        "enabled": True,
    }
    data["keys"].append(new_key)
    _save_keys_file(data)
    logger.info(f"API key rotated for '{old_entry['name']}'")
    return new_key


def validate_key(api_key: str) -> dict:
    """
    Validate an API key.
    Returns the key data dict if valid, raises HTTPException otherwise.
    """
    keys = load_keys()
    key_data = keys.get(api_key)

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
            pass  # Invalid date format, skip expiry check

    return key_data


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

        if _is_public_path(path):
            # Public paths: optionally validate credentials if provided
            if api_key:
                try:
                    key_data = validate_key(api_key)
                    request.state.auth_user = key_data
                except HTTPException:
                    pass  # Optional auth — don't block on invalid key
            return await call_next(request)

        # Protected path — require valid key
        if not api_key:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Authentication required. Provide X-API-Key header.",
                    "docs": "See /api/v1/status for service info. Use generate_key.py to create an API key."
                }
            )

        try:
            key_data = validate_key(api_key)
            # Inject authenticated user info into request state
            request.state.auth_user = key_data
        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )

        return await call_next(request)
