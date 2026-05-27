"""
Organization Management API — Self-Service Model

Any authenticated user can:
  - Create their own org (they become owner, their key moves to this org)
  - View their own org (GET /orgs/mine)
  - Generate / refresh an invite code (owner only)
  - Join an org via invite code (POST /orgs/join)

Admins can additionally:
  - List all orgs (GET /orgs)
  - Delete any org (DELETE /orgs/{id})
"""
import secrets
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from app.engine.rule_service import rule_service
from app.engine.repository import is_org_owner, get_org_owners, add_org_owner, remove_org_owner, db_get_all_keys
from app.core.key_service import update_key
from app.core.permissions import require_admin, require_auth, get_auth_user

router = APIRouter()


# ─── Local aliases (thin wrappers kept for readability in this module) ────────

def _get_auth_user(request: Request, require: bool = True) -> Optional[dict]:
    return require_auth(request) if require else get_auth_user(request)


def _require_admin(request: Request):
    require_admin(request)


# ─── Models ───────────────────────────────────────────────────────────────────

class OrgCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=64,
                    description="Unique identifier, e.g. 'my-team'")
    name: str = Field(..., min_length=1, max_length=128)


class JoinOrgRequest(BaseModel):
    invite_code: str = Field(..., min_length=4)


class AddOwnerRequest(BaseModel):
    key_prefix: str = Field(..., min_length=4, description="Key prefix of the user to make owner")


# ─── Admin endpoints ──────────────────────────────────────────────────────────

@router.get("/orgs", summary="List all organizations (admin)")
async def list_orgs(request: Request):
    """List all organizations. Requires admin role."""
    _require_admin(request)
    orgs = rule_service.list_orgs()
    return {"total": len(orgs), "orgs": orgs}


@router.delete("/orgs/{org_id}", summary="Delete an organization (admin)")
async def delete_org(org_id: str, request: Request):
    """Delete an organization. Requires admin role."""
    _require_admin(request)
    try:
        rule_service.delete_org(org_id)
        return {"message": f"Organization '{org_id}' deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Self-service endpoints ───────────────────────────────────────────────────

@router.get("/orgs/mine", summary="Get my organization")
async def get_my_org(request: Request):
    """Return the organization the current user belongs to."""
    auth_user = _get_auth_user(request)
    org_id = (auth_user.get("org_id") or "default") if auth_user else "default"
    org = rule_service.get_org(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    # Only reveal invite_code to owners or admins
    is_admin = auth_user and auth_user.get("role") == "admin"
    caller_prefix = auth_user.get("key_prefix", "") if auth_user else ""
    caller_is_owner = is_org_owner(org_id, caller_prefix)
    if not (is_admin or caller_is_owner):
        org = {k: v for k, v in org.items() if k not in ("invite_code", "invite_code_expires_at")}
    # Attach owner list
    org["owners"] = get_org_owners(org_id)
    return org


@router.post("/orgs", summary="Create an organization", status_code=201)
async def create_org(body: OrgCreate, request: Request):
    """
    Create a new organization. Any authenticated user may call this.
    The caller becomes the owner and is automatically moved to this org.
    An invite code is generated immediately so the owner can share it.
    """
    auth_user = _get_auth_user(request)
    owner_name = auth_user.get("name") if auth_user else None
    owner_key_prefix = auth_user.get("key_prefix", "") if auth_user else None

    try:
        org = rule_service.create_org(body.id, body.name, owner=owner_name,
                                       owner_key_prefix=owner_key_prefix)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Move the creator's key into this new org
    if auth_user:
        caller_key = request.headers.get("X-API-Key", "")
        update_key(caller_key, org_id=body.id)

    # Auto-generate first invite code
    code = secrets.token_urlsafe(8)
    org = rule_service.set_org_invite_code(body.id, code)

    return {"message": "Organization created", "org": org}


@router.post("/orgs/{org_id}/invite", summary="Refresh invite code")
async def refresh_invite(org_id: str, request: Request):
    """
    Generate a new invite code. Old code is invalidated.
    Any org owner or admin can call this.
    """
    auth_user = _get_auth_user(request)
    org = rule_service.get_org(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    is_admin = auth_user and auth_user.get("role") == "admin"
    caller_prefix = auth_user.get("key_prefix", "") if auth_user else ""
    if not (is_admin or is_org_owner(org_id, caller_prefix)):
        raise HTTPException(status_code=403, detail="Only an org owner or admin can refresh the invite code")

    code = secrets.token_urlsafe(8)
    updated = rule_service.set_org_invite_code(org_id, code)
    return {"message": "Invite code refreshed (valid 7 days)", "invite_code": code, "org": updated}


# ─── Owner management ─────────────────────────────────────────────────────────

@router.get("/orgs/{org_id}/owners", summary="List org owners")
async def list_owners(org_id: str, request: Request):
    """List all owners of an org. Any org member or admin can view."""
    auth_user = _get_auth_user(request)
    org = rule_service.get_org(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    # Members of the org or admins may view owners
    is_admin = auth_user and auth_user.get("role") == "admin"
    caller_org = (auth_user.get("org_id") or "default") if auth_user else "default"
    if not (is_admin or caller_org == org_id):
        raise HTTPException(status_code=403, detail="Access denied")
    return {"org_id": org_id, "owners": get_org_owners(org_id)}


@router.post("/orgs/{org_id}/owners", summary="Add an owner to the org", status_code=201)
async def add_owner(org_id: str, body: AddOwnerRequest, request: Request):
    """
    Promote a member to org owner. Any existing owner or admin can do this.
    The target user must already be a member of this org (identified by key_prefix).
    """
    auth_user = _get_auth_user(request)
    org = rule_service.get_org(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    is_admin = auth_user and auth_user.get("role") == "admin"
    caller_prefix = auth_user.get("key_prefix", "") if auth_user else ""
    if not (is_admin or is_org_owner(org_id, caller_prefix)):
        raise HTTPException(status_code=403, detail="Only an existing owner or admin can add owners")

    # Verify the target key_prefix belongs to a member of this org
    all_keys = db_get_all_keys()
    target_keys = [k for k in all_keys if k.get("key_prefix") == body.key_prefix]
    if not target_keys:
        raise HTTPException(status_code=404, detail=f"No key found with prefix '{body.key_prefix}'")
    if not is_admin:
        # Enforce that target is already in this org
        target_org = target_keys[0].get("org_id", "default")
        if target_org != org_id:
            raise HTTPException(status_code=400,
                                detail="Target user must join the org before being made an owner")

    add_org_owner(org_id, body.key_prefix)
    return {"message": f"'{body.key_prefix}' is now an owner of '{org_id}'",
            "owners": get_org_owners(org_id)}


@router.delete("/orgs/{org_id}/owners/{key_prefix}", summary="Remove an owner from the org")
async def remove_owner(org_id: str, key_prefix: str, request: Request):
    """
    Remove an owner role. Any existing owner or admin can do this.
    Cannot remove the last owner.
    """
    auth_user = _get_auth_user(request)
    org = rule_service.get_org(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    is_admin = auth_user and auth_user.get("role") == "admin"
    caller_prefix = auth_user.get("key_prefix", "") if auth_user else ""
    if not (is_admin or is_org_owner(org_id, caller_prefix)):
        raise HTTPException(status_code=403, detail="Only an existing owner or admin can remove owners")

    try:
        remove_org_owner(org_id, key_prefix)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": f"'{key_prefix}' is no longer an owner of '{org_id}'",
            "owners": get_org_owners(org_id)}


@router.post("/orgs/join", summary="Join an org via invite code")
async def join_org(body: JoinOrgRequest, request: Request):
    """
    Join an organization using its invite code.
    The caller's API key is updated to belong to the matched org.
    """
    auth_user = _get_auth_user(request)
    org = rule_service.get_org_by_invite_code(body.invite_code)
    if not org:
        raise HTTPException(status_code=404, detail="Invalid or expired invite code")

    caller_key = request.headers.get("X-API-Key", "")
    update_key(caller_key, org_id=org["id"])
    return {"message": f"Welcome to '{org['name']}'!", "org_id": org["id"], "org_name": org["name"]}


@router.post("/orgs/leave", summary="Leave my current organization")
async def leave_org(request: Request):
    """
    Leave the current organization and return to the default org.
    If the caller is an owner, they must either:
      - have at least one other owner remaining (they can leave), or
      - they are the sole owner (blocked — add another owner first).
    """
    auth_user = _get_auth_user(request)
    current_org_id = (auth_user.get("org_id") or "default") if auth_user else "default"

    if current_org_id == "default":
        raise HTTPException(status_code=400, detail="You are not in any organization")

    caller_prefix = auth_user.get("key_prefix", "") if auth_user else ""
    if is_org_owner(current_org_id, caller_prefix):
        owners = get_org_owners(current_org_id)
        if len(owners) <= 1:
            raise HTTPException(
                status_code=400,
                detail="You are the only owner. Add another owner before leaving."
            )
        # Remove themselves from the owner list when they leave
        remove_org_owner(current_org_id, caller_prefix)

    caller_key = request.headers.get("X-API-Key", "")
    update_key(caller_key, org_id="default")
    return {"message": f"You have left '{current_org_id}' and returned to the default org."}
