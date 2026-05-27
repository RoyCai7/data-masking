"""
keys.py — API key management endpoints.

Extracted from status.py so it owns a single concern: key lifecycle.

Admin routes:    POST/GET /keys, PUT /keys/update, POST /keys/disable,
                 GET /keys/{id}/reveal
Self-service:    GET /keys/me, POST /keys/rotate
"""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.core.permissions import require_admin, require_auth
from app.core.key_service import (
    add_key,
    rotate_key,
    list_keys,
    update_key_by_id,
    disable_key_by_id,
    get_key_plain_by_id,
)

router = APIRouter()


# ─── Request models ───────────────────────────────────────────────────────────

class CreateKeyRequest(BaseModel):
    name: str
    role: str = "user"
    expires_days: int = 365
    org_id: str = "default"


class UpdateKeyRequest(BaseModel):
    key_id: int
    org_id: Optional[str] = None
    role: Optional[str] = None


class DisableKeyRequest(BaseModel):
    key_id: int


# ─── Admin routes ─────────────────────────────────────────────────────────────

@router.post("/keys", summary="Create API key", tags=["Keys"])
async def create_api_key(body: CreateKeyRequest, request: Request):
    """Create a new API key. Requires admin role."""
    require_admin(request)
    key_data = add_key(name=body.name, role=body.role,
                       expires_days=body.expires_days, org_id=body.org_id)
    return {
        "message": "API key created successfully",
        "id": key_data.get("id"),
        "key": key_data["key"],
        "name": key_data["name"],
        "role": key_data["role"],
        "org_id": key_data["org_id"],
        "created_at": key_data["created_at"],
        "expires_at": key_data["expires_at"],
    }


@router.get("/keys", summary="List API keys", tags=["Keys"])
async def list_api_keys(request: Request):
    """List all API keys (values partially hidden). Requires admin role."""
    require_admin(request)
    rows = list_keys()
    keys = [
        {
            "id": k["id"],
            "name": k["name"],
            "role": k.get("role", "user"),
            "org_id": k.get("org_id", "default"),
            "enabled": bool(k.get("enabled", True)),
            "created_at": k["created_at"],
            "expires_at": k.get("expires_at"),
            "key_preview": k.get("key_prefix", "") + "...",
        }
        for k in rows
    ]
    return {"total": len(keys), "keys": keys}


@router.put("/keys/update", summary="Update API key org/role", tags=["Keys"])
async def update_api_key(body: UpdateKeyRequest, request: Request):
    """Update mutable fields (org_id, role) of an existing key. Requires admin role."""
    require_admin(request)
    result = update_key_by_id(body.key_id, org_id=body.org_id, role=body.role)
    if not result:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"message": "API key updated",
            "name": result["name"], "org_id": result["org_id"], "role": result["role"]}


@router.post("/keys/disable", summary="Disable API key", tags=["Keys"])
async def disable_api_key(body: DisableKeyRequest, request: Request):
    """Disable an API key. Requires admin role."""
    require_admin(request)
    if disable_key_by_id(body.key_id):
        return {"message": "API key disabled successfully"}
    raise HTTPException(status_code=404, detail="API key not found")


@router.get("/keys/{key_id}/reveal", summary="Reveal full API key value", tags=["Keys"])
async def reveal_api_key(key_id: int, request: Request):
    """Return the plaintext API key for a given key ID. Requires admin role."""
    require_admin(request)
    plain = get_key_plain_by_id(key_id)
    if plain is None:
        raise HTTPException(status_code=404, detail="Key not found or plaintext not available")
    return {"key": plain}


# ─── Self-service routes ──────────────────────────────────────────────────────

@router.get("/keys/me", summary="View my key info", tags=["Keys"])
async def get_my_key(request: Request):
    """Get the current user's key information (any authenticated user)."""
    auth_user = require_auth(request)
    return {
        "name": auth_user.get("name"),
        "role": auth_user.get("role", "user"),
        "org_id": auth_user.get("org_id", "default"),
        "created_at": auth_user.get("created_at"),
        "expires_at": auth_user.get("expires_at"),
        "key_preview": auth_user.get("key_prefix", "") + "...",
    }


@router.post("/keys/rotate", summary="Rotate my API key", tags=["Keys"])
async def rotate_my_key(request: Request):
    """
    Rotate the current user's API key.
    Disables the old key and issues a new one with the same name/role.
    Any authenticated user can rotate their own key.
    """
    require_auth(request)
    old_key = request.headers.get("X-API-Key", "")
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
        "warning": "The old key has been disabled. Save the new key now!",
    }
