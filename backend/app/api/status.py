"""
status.py — Service health and session management.

Intentionally minimal: two read-only concerns only.
  GET  /status   → health probe + executor stats
  POST /session  → create an anonymous upload session

All API key management (create/list/disable/rotate) has moved to api/keys.py.
"""
from fastapi import APIRouter

from app.core.executor import get_executor_status
from app.core.session import create_session
from app.core.auth import AUTH_ENABLED

router = APIRouter()


@router.get("/status", summary="Get service status")
async def get_status():
    """Returns service health and executor status."""
    return {
        "service": "SUSE Data Masking Service",
        "version": "1.0.0",
        "status": "healthy",
        "auth_enabled": AUTH_ENABLED,
        "executor": get_executor_status(),
    }


@router.post("/session", summary="Create new session")
async def new_session():
    """Creates a new session for file isolation."""
    session_id = create_session()
    return {
        "session_id": session_id,
        "message": "Session created successfully",
    }
