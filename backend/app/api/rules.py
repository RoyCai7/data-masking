"""
Rules Management API

Provides endpoints for:
  - Admin: Full CRUD on masking rules, import/export, approve suggestions
  - Org owner: Self-service CRUD on org-scoped rules, approve suggestions targeting their org
  - User: Submit rule suggestions (feedback channel), manage own private rules
  - Public: List active rules (for UI display)

Role-based access:
  - GET /rules              → public (no auth)
  - POST rules (system)     → admin only
  - POST rules (org/private)→ org owner or admin
  - PUT/DELETE              → rule write access (admin / org owner / creator)
  - PATCH toggle            → rule write access
  - POST suggestions        → any authenticated user
  - PATCH suggestions/{id}  → org owner of targeted rule's org, or admin
  - GET suggestions         → admin sees all; org owner sees their org's
  - GET changelog           → admin sees all; org owner sees their org's
  - GET/POST rules-export/import → admin (all); org owner (their org only)
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
    """Raise 403 if not admin. Reserved for system-level operations only."""
    from app.core.auth import AUTH_ENABLED
    if not AUTH_ENABLED:
        return  # Dev mode — skip
    auth_user = getattr(request.state, "auth_user", None)
    if not auth_user or auth_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")


def _require_admin_or_org_owner(request: Request, org_id: Optional[str] = None):
    """
    Self-service gate: passes if caller is admin OR is an owner of the specified org.
    org_id MUST be provided explicitly — this function never falls back to the caller's
    own org_id to avoid fail-open privilege escalation.
    Raises 403 if org_id is not supplied and caller is not admin.
    """
    from app.core.auth import AUTH_ENABLED
    if not AUTH_ENABLED:
        return
    ctx = _get_auth_context(request)
    if ctx["role"] == "admin":
        return
    # Fail closed: require explicit org_id — never infer from caller context
    if not org_id:
        raise HTTPException(status_code=403, detail="Org owner or admin role required")
    if _is_org_owner_check(org_id, ctx["key_prefix"]):
        return
    raise HTTPException(status_code=403, detail="Org owner or admin role required")


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
    List suggestions.
    - Admin: sees all.
    - Org owner: sees suggestions they submitted + suggestions targeting their org's rules.
    - Regular user: sees only their own submissions.
    """
    from app.core.auth import AUTH_ENABLED
    ctx = _get_auth_context(request)
    auth_user = getattr(request.state, "auth_user", None)

    submitted_by = None
    org_id = None

    if AUTH_ENABLED and ctx["role"] != "admin":
        submitted_by = ctx["name"]
        # Org owner also sees suggestions targeting their org's rules
        if ctx.get("org_id") and _is_org_owner_check(ctx["org_id"], ctx["key_prefix"]):
            org_id = ctx["org_id"]

    suggestions = rule_service.list_suggestions(
        status=status, submitted_by=submitted_by, org_id=org_id
    )
    return {"total": len(suggestions), "suggestions": suggestions}


@router.patch("/rules/suggestions/{suggestion_id}", summary="Review a suggestion")
async def review_suggestion(suggestion_id: int, body: SuggestionReview, request: Request):
    """
    Approve or reject a suggestion.
    - Admin: can review all suggestions.
    - Org owner: can review suggestions targeting their org's rules.
    """
    from app.core.auth import AUTH_ENABLED
    ctx = _get_auth_context(request)

    if AUTH_ENABLED and ctx["role"] != "admin":
        # Org owner: verify the suggestion's target rule belongs to their org
        suggestion = rule_service.get_suggestion(suggestion_id)
        if not suggestion:
            raise HTTPException(status_code=404, detail=f"Suggestion {suggestion_id} not found")
        target_rule_id = suggestion.get("rule_id")
        if not target_rule_id:
            raise HTTPException(status_code=403, detail="Only admins can review suggestions for new rules")
        target_rule = rule_service.get_rule_detail(target_rule_id)
        if not target_rule or target_rule.get("org_id") != ctx.get("org_id"):
            raise HTTPException(status_code=403, detail="You can only review suggestions for rules in your org")
        if not _is_org_owner_check(ctx["org_id"], ctx["key_prefix"]):
            raise HTTPException(status_code=403, detail="Org owner role required to review suggestions")

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
    """
    View audit trail of rule changes.
    - Admin: sees all changes.
    - Org owner: sees changes on their org's rules only.
    """
    from app.core.auth import AUTH_ENABLED
    ctx = _get_auth_context(request)

    org_id = None
    if AUTH_ENABLED and ctx["role"] != "admin":
        if ctx.get("org_id") and _is_org_owner_check(ctx["org_id"], ctx["key_prefix"]):
            org_id = ctx["org_id"]
        else:
            raise HTTPException(status_code=403, detail="Org owner or admin role required")

    entries = rule_service.list_changelog(rule_id=rule_id, limit=limit, org_id=org_id)
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
    Create a new masking rule — self-service model:
    - Admin: any scope (private / org / system).
    - Org owner: private or org scope within their own org.
    - Regular user: private scope only.
    """
    from app.core.auth import AUTH_ENABLED
    ctx = _get_auth_context(request)
    is_admin = ctx["role"] == "admin"

    if AUTH_ENABLED and not is_admin:
        auth_user = getattr(request.state, "auth_user", None)
        if not auth_user:
            raise HTTPException(status_code=401, detail="Authentication required")

    data = body.model_dump()
    requested_scope = data.get("scope", "private")

    if not is_admin:
        is_org_owner = (
            ctx.get("org_id")
            and _is_org_owner_check(ctx["org_id"], ctx["key_prefix"])
        )
        # Block system-scope creation for non-admins
        if requested_scope == "system":
            raise HTTPException(status_code=403, detail="Only admins can create system-scoped rules")
        # Block org-scope if not an org owner
        if requested_scope == "org" and not is_org_owner:
            raise HTTPException(status_code=403, detail="Only org owners can create org-scoped rules")
        # Force to caller's own org
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
    """
    Toggle a rule between enabled and disabled — self-service model:
    - system rule → admin only.
    - org rule    → org owner or admin.
    - private rule → creator or admin.
    """
    existing = rule_service.get_rule_detail(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    _require_rule_write_access(request, existing)
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
    """
    Export rules as a JSON array.
    - Admin: exports all rules.
    - Org owner: exports only their org's rules.
    """
    from app.core.auth import AUTH_ENABLED
    ctx = _get_auth_context(request)

    org_id = None
    if AUTH_ENABLED and ctx["role"] != "admin":
        if ctx.get("org_id") and _is_org_owner_check(ctx["org_id"], ctx["key_prefix"]):
            org_id = ctx["org_id"]
        else:
            raise HTTPException(status_code=403, detail="Org owner or admin role required")

    rules = rule_service.export_rules(org_id=org_id)
    return {"total": len(rules), "rules": rules}


@router.post("/rules-import", summary="Import rules from JSON")
async def import_rules(request: Request):
    """
    Bulk import rules from a JSON body.
    Body should be: {"rules": [{...}, {...}, ...]}
    - Admin: imports at any scope; existing IDs → updated, new IDs → created.
    - Org owner: imports rules forced to org scope within their own org.
    """
    from app.core.auth import AUTH_ENABLED
    ctx = _get_auth_context(request)
    is_admin = ctx["role"] == "admin"

    if AUTH_ENABLED and not is_admin:
        if not (ctx.get("org_id") and _is_org_owner_check(ctx["org_id"], ctx["key_prefix"])):
            raise HTTPException(status_code=403, detail="Org owner or admin role required")

    body = await request.json()
    rules_data = body.get("rules", [])
    if not rules_data:
        raise HTTPException(status_code=400, detail="No rules in body. Expected {\"rules\": [...]}")

    # Non-admin org owner: force all imported rules to their org scope
    if not is_admin:
        for item in rules_data:
            item["scope"] = "org"
            item["org_id"] = ctx["org_id"]

    result = rule_service.import_rules(rules_data, imported_by=_get_user_name(request))
    return {
        "message": f"Import complete: {result['created']} created, {result['updated']} updated",
        **result,
    }
