"""
Rules Management API

Provides endpoints for:
  - Admin: Full CRUD on masking rules, import/export, approve suggestions
  - User: Submit rule suggestions (feedback channel)
  - Public: List active rules (for UI display)

Role-based access:
  - GET /rules            → public (no auth)
  - POST/PUT/DELETE/PATCH → admin only
  - POST suggestions      → any authenticated user
  - PATCH suggestions     → admin only (approve/reject)
"""
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field

from app.engine.rule_service import rule_service

router = APIRouter()


# ─── Request / Response Models ─────────────────────────────────────────────────

class RuleCreate(BaseModel):
    id: Optional[str] = Field(default=None, max_length=64, description="Rule ID (auto-UUID for org/private rules)")
    name: str = Field(..., min_length=1, max_length=128)
    category: str = Field(default="custom", max_length=32)
    pattern: str = Field(..., min_length=1, description="Regex pattern string")
    flags: str = Field(default="", description="Regex flags: IGNORECASE, MULTILINE, etc.")
    strategy: str = Field(default="placeholder", description="asterisk | placeholder | partial | hash")
    placeholder: str = Field(default="[MASKED]")
    weight: int = Field(default=5, ge=0, le=100)
    enabled: bool = True
    scope: str = Field(default="private", description="'private' (owner only), 'org' (org members), 'system' (admin only)")


class RuleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    category: Optional[str] = Field(default=None, max_length=32)
    pattern: Optional[str] = None
    flags: Optional[str] = None
    strategy: Optional[str] = None
    placeholder: Optional[str] = None
    weight: Optional[int] = Field(default=None, ge=0, le=100)
    enabled: Optional[bool] = None
    scope: Optional[str] = Field(default=None, description="'private', 'org', or 'system' (admin only)")


class PromoteRequest(BaseModel):
    scope: str = Field(..., description="Target scope: 'org' or 'system'")
    org_id: Optional[str] = Field(default=None, description="Target org ID (required when scope='org')")


class OrgCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=64, description="Unique org identifier")
    name: str = Field(..., min_length=1, max_length=128)


class SuggestionCreate(BaseModel):
    rule_id: Optional[str] = Field(default=None, description="Target rule ID (null for new rule suggestion)")
    action: str = Field(..., description="create | modify | disable")
    name: Optional[str] = None
    category: Optional[str] = None
    pattern: Optional[str] = None
    flags: Optional[str] = None
    strategy: Optional[str] = None
    placeholder: Optional[str] = None
    weight: Optional[int] = None
    reason: str = Field(default="", description="Why this change is needed")


class SuggestionReview(BaseModel):
    action: str = Field(..., description="approve | reject")


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _require_admin(request: Request):
    """Raise 403 if the request is not from an admin."""
    from app.core.auth import AUTH_ENABLED
    if not AUTH_ENABLED:
        return  # Dev mode — skip
    auth_user = getattr(request.state, "auth_user", None)
    if not auth_user or auth_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")


def _get_auth_context(request: Request) -> dict:
    """Returns dict with role, name, org_id, key_prefix from request auth state."""
    from app.core.auth import AUTH_ENABLED
    auth_user = getattr(request.state, "auth_user", None)
    if not AUTH_ENABLED:
        return {"role": "admin", "name": "dev", "org_id": "default", "key_prefix": "dev_____"}
    if auth_user:
        return {
            "role": auth_user.get("role", "user"),
            "name": auth_user.get("name", "unknown"),
            "org_id": auth_user.get("org_id") or "default",
            "key_prefix": auth_user.get("key_prefix", ""),
        }
    return {"role": "anonymous", "name": "anonymous", "org_id": None, "key_prefix": ""}


def _is_org_owner_check(org_id: str, key_prefix: str) -> bool:
    """Return True if key_prefix is an owner of the given org."""
    from app.engine.repository import is_org_owner
    return is_org_owner(org_id, key_prefix)


def _require_rule_write_access(request: Request, rule: dict):
    """
    Enforce write access for self-service model:
      system rule  → admin only
      org rule     → org owner of that org, or admin
      private rule → creator (by creator_key_prefix), or admin
    Raises HTTPException(403) on failure.
    """
    from app.core.auth import AUTH_ENABLED
    if not AUTH_ENABLED:
        return
    ctx = _get_auth_context(request)
    if ctx["role"] == "admin":
        return  # admin can do anything

    scope = rule.get("scope", "private")
    if scope == "system":
        raise HTTPException(status_code=403, detail="Only admins can modify system rules")

    if scope == "org":
        org_id = rule.get("org_id")
        if not org_id or not _is_org_owner_check(org_id, ctx["key_prefix"]):
            raise HTTPException(status_code=403,
                                detail="Only an org owner can modify org-scoped rules")
        return

    # private rule — only the creator may modify it
    if scope == "private":
        creator_prefix = rule.get("creator_key_prefix")
        if not creator_prefix or ctx["key_prefix"] != creator_prefix:
            raise HTTPException(status_code=403,
                                detail="Only the rule creator can modify their private rules")
        return

    raise HTTPException(status_code=403, detail="Cannot determine rule ownership")


def _get_user_name(request: Request) -> str:
    return _get_auth_context(request)["name"]


# ─── Public: List Rules ────────────────────────────────────────────────

@router.get("/rules", summary="List all rules")
async def list_rules(
    request: Request,
    category: Optional[str] = Query(default=None, description="Filter by category"),
    enabled_only: bool = Query(default=False, description="Only return enabled rules"),
    scope: Optional[str] = Query(default=None, description="Filter by scope: system | org | private"),
):
    """
    List masking rules with scope-aware filtering.

    - Admin: sees all rules
    - Authenticated user: sees system rules + own org rules + own private rules
    - Anonymous: sees only system rules
    """
    ctx = _get_auth_context(request)
    rules = rule_service.list_rules_detailed(
        category=category,
        enabled_only=enabled_only,
        owner=ctx["name"] if ctx["role"] != "admin" else None,
        org_id=ctx["org_id"] if ctx["role"] != "admin" else None,
        role=ctx["role"],
    )

    if scope:
        rules = [r for r in rules if r.get("scope") == scope]

    return {"total": len(rules), "rules": rules}


# ─── User: Suggestions ───────────────────────────────────────────────────────
# NOTE: These MUST be defined before /rules/{rule_id} to avoid being caught
#       by the path-parameter route.

@router.post("/rules/suggestions", summary="Submit a rule suggestion", status_code=201)
async def create_suggestion(body: SuggestionCreate, request: Request):
    """
    Submit a suggestion for a new rule, modification, or disabling.
    Any authenticated user can submit.
    """
    suggestion = rule_service.create_suggestion(
        body.model_dump(),
        submitted_by=_get_user_name(request),
    )
    return {"message": "Suggestion submitted", "suggestion": suggestion}


@router.get("/rules/suggestions", summary="List suggestions")
async def list_suggestions(
    request: Request,
    status: Optional[str] = Query(default=None, description="Filter: pending|approved|rejected"),
):
    """
    List suggestions. Admin sees all; regular users see only their own.
    """
    from app.core.auth import AUTH_ENABLED
    user_name = _get_user_name(request)
    auth_user = getattr(request.state, "auth_user", None)

    # Admin sees all; others see only their own
    submitted_by = None
    if AUTH_ENABLED and (not auth_user or auth_user.get("role") != "admin"):
        submitted_by = user_name

    suggestions = rule_service.list_suggestions(status=status, submitted_by=submitted_by)
    return {"total": len(suggestions), "suggestions": suggestions}


@router.patch("/rules/suggestions/{suggestion_id}", summary="Review a suggestion")
async def review_suggestion(suggestion_id: int, body: SuggestionReview, request: Request):
    """
    Approve or reject a suggestion. Requires admin role.
    Approved suggestions are automatically applied to the rules.
    """
    _require_admin(request)
    try:
        suggestion = rule_service.review_suggestion(
            suggestion_id,
            action=body.action,
            reviewed_by=_get_user_name(request),
        )
        return {"message": f"Suggestion {body.action}d", "suggestion": suggestion}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Admin: Changelog ────────────────────────────────────────────────────────
# NOTE: Must also be before /rules/{rule_id}.

@router.get("/rules/changelog", summary="View rule change history")
async def list_changelog(
    request: Request,
    rule_id: Optional[str] = Query(default=None, description="Filter by rule ID"),
    limit: int = Query(default=50, ge=1, le=500),
):
    """View audit trail of all rule changes. Requires admin role."""
    _require_admin(request)
    entries = rule_service.list_changelog(rule_id=rule_id, limit=limit)
    return {"total": len(entries), "changelog": entries}


# ─── Public: Rule Detail ─────────────────────────────────────────────────────

@router.get("/rules/{rule_id}", summary="Get rule detail")
async def get_rule(rule_id: str):
    """Get a single rule's full detail."""
    rule = rule_service.get_rule_detail(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    return rule


# ─── Admin: CRUD ──────────────────────────────────────────────────────────────

@router.post("/rules", summary="Create a new rule", status_code=201)
async def create_rule(body: RuleCreate, request: Request):
    """
    Create a new masking rule.
    - Admin: can create rules at any scope (private / org / system).
    - Authenticated user: can only create private rules within their own org.
    """
    from app.core.auth import AUTH_ENABLED
    ctx = _get_auth_context(request)
    is_admin = ctx["role"] == "admin"

    if AUTH_ENABLED and not is_admin:
        # Non-admin users are restricted to creating private rules in their own org
        auth_user = getattr(request.state, "auth_user", None)
        if not auth_user:
            raise HTTPException(status_code=401, detail="Authentication required")

    data = body.model_dump()

    if not is_admin:
        # Force private scope and caller's org — user cannot choose scope or org
        data["scope"] = "private"
        data["org_id"] = ctx["org_id"]
    else:
        # Admin: inject caller's org as default if scope != system
        if data.get("scope") != "system":
            data.setdefault("org_id", ctx["org_id"])

    # Track creator for private rules
    if data.get("scope") == "private":
        data["creator_key_prefix"] = ctx["key_prefix"]

    try:
        rule = rule_service.create_rule(data, created_by=ctx["name"])
        return {"message": "Rule created", "rule": rule}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/rules/{rule_id}", summary="Update a rule")
async def update_rule(rule_id: str, body: RuleUpdate, request: Request):
    """
    Update an existing rule.
    - Admin: can update any rule.
    - Org owner: can update org-scoped rules belonging to their org.
    - User: can only update their own private rules (by creator_key_prefix).
    """
    existing = rule_service.get_rule_detail(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    _require_rule_write_access(request, existing)

    # Only send non-None fields
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    ctx = _get_auth_context(request)
    # Non-admin cannot change scope / org_id via update
    if ctx["role"] != "admin":
        data.pop("scope", None)
        data.pop("org_id", None)

    try:
        rule = rule_service.update_rule(rule_id, data, changed_by=ctx["name"])
        return {"message": "Rule updated", "rule": rule}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/rules/{rule_id}", summary="Delete a rule")
async def delete_rule(rule_id: str, request: Request):
    """
    Delete a custom rule. Built-in rules cannot be deleted (use toggle).
    - Admin: can delete any rule.
    - Org owner: can delete org-scoped rules in their org.
    - User: can only delete their own private rules.
    """
    existing = rule_service.get_rule_detail(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    _require_rule_write_access(request, existing)
    try:
        rule_service.delete_rule(rule_id, changed_by=_get_user_name(request))
        return {"message": f"Rule '{rule_id}' deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/rules/{rule_id}/toggle", summary="Toggle rule enabled/disabled")
async def toggle_rule(rule_id: str, request: Request):
    """Toggle a rule between enabled and disabled. Requires admin role."""
    _require_admin(request)
    try:
        rule = rule_service.toggle_rule(rule_id, changed_by=_get_user_name(request))
        status_text = "enabled" if rule["enabled"] else "disabled"
        return {"message": f"Rule '{rule_id}' {status_text}", "rule": rule}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/rules/{rule_id}/promote", summary="Change rule scope (promote/demote)")
async def promote_rule(rule_id: str, body: PromoteRequest, request: Request):
    """
    Change rule scope — self-service model:
    - private → org : org owner (of the org the rule belongs to) or admin.
                      Ownership transfers to org (Plan B); original creator loses edit rights.
    - org → system  : admin only.
    - any → private : demote — admin, or org owner reverting their own org rule.
    """
    from app.core.auth import AUTH_ENABLED
    ctx = _get_auth_context(request)
    is_admin = ctx["role"] == "admin"

    existing = rule_service.get_rule_detail(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")

    current_scope = existing.get("scope", "private")
    target_scope  = body.scope

    if AUTH_ENABLED and not is_admin:
        if target_scope == "system":
            raise HTTPException(status_code=403,
                                detail="Only admins can promote rules to system scope")

        # Determine the org the rule currently belongs to (or the target org for private→org)
        relevant_org = body.org_id or existing.get("org_id") or ctx["org_id"]
        if not _is_org_owner_check(relevant_org, ctx["key_prefix"]):
            raise HTTPException(status_code=403,
                                detail="Only an org owner can promote/demote rules within their org")

        # Org owner may only act on rules that belong to their own org
        if current_scope in ("org", "private") and existing.get("org_id") not in (relevant_org, None, ctx["org_id"]):
            raise HTTPException(status_code=403,
                                detail="Cannot promote rules belonging to a different org")

    # Default target org to caller's org
    target_org = body.org_id or (None if target_scope == "system" else
                                  existing.get("org_id") or ctx["org_id"])
    try:
        rule = rule_service.set_scope(
            rule_id, target_scope,
            org_id=target_org,
            changed_by=ctx["name"]
        )
        return {"message": f"Rule '{rule_id}' scope changed to {target_scope}", "rule": rule}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Admin: Import / Export ───────────────────────────────────────────────────

@router.get("/rules-export", summary="Export all rules as JSON")
async def export_rules(request: Request):
    """Export all rules as a JSON array. Requires admin role."""
    _require_admin(request)
    rules = rule_service.export_rules()
    return {"total": len(rules), "rules": rules}


@router.post("/rules-import", summary="Import rules from JSON")
async def import_rules(request: Request):
    """
    Bulk import rules from a JSON body.
    Body should be: {"rules": [{...}, {...}, ...]}
    Existing rule IDs → updated; new IDs → created.
    Requires admin role.
    """
    _require_admin(request)
    body = await request.json()
    rules_data = body.get("rules", [])
    if not rules_data:
        raise HTTPException(status_code=400, detail="No rules in body. Expected {\"rules\": [...]}")
    result = rule_service.import_rules(rules_data, imported_by=_get_user_name(request))
    return {
        "message": f"Import complete: {result['created']} created, {result['updated']} updated",
        **result,
    }
