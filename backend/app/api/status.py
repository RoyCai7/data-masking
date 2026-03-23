"""
Status API endpoints
System status, health monitoring, and API key management
"""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.core.executor import get_executor_status
from app.core.session import create_session
from app.core.auth import (
    add_key, load_keys, disable_key, rotate_key, _load_keys_file,
    AUTH_ENABLED
)

router = APIRouter()


@router.get("/status", summary="Get service status")
async def get_status():
    """Returns service health and executor status"""
    executor_status = get_executor_status()
    
    return {
        "service": "SUSE Data Masking Service",
        "version": "1.0.0",
        "status": "healthy",
        "auth_enabled": AUTH_ENABLED,
        "executor": executor_status
    }


@router.post("/session", summary="Create new session")
async def new_session():
    """Creates a new session for file isolation"""
    session_id = create_session()
    return {
        "session_id": session_id,
        "message": "Session created successfully"
    }


# --- API Key Management (admin only) ---

class CreateKeyRequest(BaseModel):
    name: str
    role: str = "user"
    expires_days: int = 365


@router.post("/keys", summary="Create API key", tags=["Auth"])
async def create_api_key(body: CreateKeyRequest, request: Request):
    """Create a new API key. Requires admin role."""
    # Check admin permission (if auth is enabled)
    if AUTH_ENABLED:
        auth_user = getattr(request.state, "auth_user", None)
        if not auth_user or auth_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin role required")

    key_data = add_key(
        name=body.name,
        role=body.role,
        expires_days=body.expires_days,
    )
    return {
        "message": "API key created successfully",
        "key": key_data["key"],
        "name": key_data["name"],
        "role": key_data["role"],
        "created_at": key_data["created_at"],
        "expires_at": key_data["expires_at"],
    }


@router.get("/keys", summary="List API keys", tags=["Auth"])
async def list_api_keys(request: Request):
    """List all API keys (key values are partially hidden). Requires admin role."""
    if AUTH_ENABLED:
        auth_user = getattr(request.state, "auth_user", None)
        if not auth_user or auth_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin role required")

    data = _load_keys_file()
    keys = []
    for k in data.get("keys", []):
        keys.append({
            "name": k["name"],
            "role": k.get("role", "user"),
            "enabled": k.get("enabled", True),
            "created_at": k["created_at"],
            "expires_at": k.get("expires_at"),
            "key_preview": k["key"][:8] + "..." + k["key"][-4:],
        })

    return {"total": len(keys), "keys": keys}


class DisableKeyRequest(BaseModel):
    key: str


@router.post("/keys/disable", summary="Disable API key", tags=["Auth"])
async def disable_api_key(body: DisableKeyRequest, request: Request):
    """Disable an API key. Requires admin role."""
    if AUTH_ENABLED:
        auth_user = getattr(request.state, "auth_user", None)
        if not auth_user or auth_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin role required")

    if disable_key(body.key):
        return {"message": "API key disabled successfully"}
    else:
        raise HTTPException(status_code=404, detail="API key not found")


# --- User self-service endpoints ---

@router.get("/keys/me", summary="View my key info", tags=["Auth"])
async def get_my_key(request: Request):
    """Get the current user's key information (any authenticated user)."""
    auth_user = getattr(request.state, "auth_user", None)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    return {
        "name": auth_user.get("name"),
        "role": auth_user.get("role", "user"),
        "created_at": auth_user.get("created_at"),
        "expires_at": auth_user.get("expires_at"),
        "key_preview": auth_user["key"][:8] + "..." + auth_user["key"][-4:],
    }


@router.post("/keys/rotate", summary="Rotate my API key", tags=["Auth"])
async def rotate_my_key(request: Request):
    """
    Rotate the current user's API key.
    The old key is disabled and a new key is generated with the same name/role.
    Any authenticated user can rotate their own key.
    """
    auth_user = getattr(request.state, "auth_user", None)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    old_key = auth_user["key"]
    new_key_data = rotate_key(old_key)

    if not new_key_data:
        raise HTTPException(status_code=404, detail="Key not found")

    return {
        "message": "API key rotated successfully. Update your client with the new key.",
        "new_key": new_key_data["key"],
        "name": new_key_data["name"],
        "role": new_key_data["role"],
        "created_at": new_key_data["created_at"],
        "expires_at": new_key_data["expires_at"],
        "warning": "The old key has been disabled. Save the new key now!"
    }
