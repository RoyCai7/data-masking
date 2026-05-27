"""
permissions.py — Centralized permission guards.

All auth checks in API handlers should use these helpers instead of
repeating the same if-AUTH_ENABLED / role-check pattern inline.

Usage:
    from app.core.permissions import require_admin, require_auth, get_auth_user

    @router.post("/something")
    async def endpoint(request: Request):
        require_admin(request)          # raises 403 if not admin
        user = get_auth_user(request)   # returns dict or None
"""
from typing import Optional
from fastapi import Request, HTTPException

from app.core.auth import AUTH_ENABLED


def get_auth_user(request: Request) -> Optional[dict]:
    """Return the authenticated user dict from request.state, or None."""
    return getattr(request.state, "auth_user", None)


def require_auth(request: Request) -> dict:
    """
    Raise HTTP 401 if the request has no authenticated user.
    Returns the auth_user dict when auth is enabled and user is present.
    When AUTH_ENABLED=false returns an empty dict (dev mode).
    """
    if not AUTH_ENABLED:
        return {}
    auth_user = get_auth_user(request)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return auth_user


def require_admin(request: Request) -> dict:
    """
    Raise HTTP 403 if the authenticated user is not an admin.
    When AUTH_ENABLED=false, silently passes (dev mode).
    Returns the auth_user dict on success.
    """
    if not AUTH_ENABLED:
        return {}
    auth_user = get_auth_user(request)
    if not auth_user or auth_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return auth_user


def require_role(request: Request, role: str) -> dict:
    """
    Generic role check.  require_role(request, 'admin') is equivalent
    to require_admin(request).
    """
    if not AUTH_ENABLED:
        return {}
    auth_user = get_auth_user(request)
    if not auth_user or auth_user.get("role") != role:
        raise HTTPException(status_code=403, detail=f"'{role}' role required")
    return auth_user
