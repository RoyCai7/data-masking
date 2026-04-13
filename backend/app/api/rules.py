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
    id: str = Field(..., min_length=1, max_length=64, description="Unique rule identifier, e.g. 'ipv4_cidr'")
    name: str = Field(..., min_length=1, max_length=128)
    category: str = Field(default="custom", max_length=32)
    pattern: str = Field(..., min_length=1, description="Regex pattern string")
    flags: str = Field(default="", description="Regex flags: IGNORECASE, MULTILINE, etc.")
    strategy: str = Field(default="placeholder", description="asterisk | placeholder | partial | hash")
    placeholder: str = Field(default="[MASKED]")
    weight: int = Field(default=5, ge=0, le=100)
    enabled: bool = True


class RuleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    category: Optional[str] = Field(default=None, max_length=32)
    pattern: Optional[str] = None
    flags: Optional[str] = None
    strategy: Optional[str] = None
    placeholder: Optional[str] = None
    weight: Optional[int] = Field(default=None, ge=0, le=100)
    enabled: Optional[bool] = None


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


def _get_user_name(request: Request) -> str:
    """Extract user name from request (for audit logging)."""
    auth_user = getattr(request.state, "auth_user", None)
    if auth_user:
        return auth_user.get("name", "unknown")
    return "anonymous"


# ─── Public: List Rules ───────────────────────────────────────────────────────

@router.get("/rules", summary="List all rules")
async def list_rules(
    category: Optional[str] = Query(default=None, description="Filter by category"),
    enabled_only: bool = Query(default=False, description="Only return enabled rules"),
):
    """
    List masking rules. Public endpoint — no authentication required.
    Returns full metadata for each rule.
    """
    rules = rule_service.list_rules_detailed(category=category, enabled_only=enabled_only)
    return {
        "total": len(rules),
        "rules": rules,
    }


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
    """Create a new masking rule. Requires admin role."""
    _require_admin(request)
    try:
        rule = rule_service.create_rule(body.model_dump(), created_by=_get_user_name(request))
        return {"message": "Rule created", "rule": rule}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/rules/{rule_id}", summary="Update a rule")
async def update_rule(rule_id: str, body: RuleUpdate, request: Request):
    """Update an existing rule. Requires admin role."""
    _require_admin(request)
    # Only send non-None fields
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        rule = rule_service.update_rule(rule_id, data, changed_by=_get_user_name(request))
        return {"message": "Rule updated", "rule": rule}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/rules/{rule_id}", summary="Delete a rule")
async def delete_rule(rule_id: str, request: Request):
    """
    Delete a custom rule. Built-in rules cannot be deleted (use toggle).
    Requires admin role.
    """
    _require_admin(request)
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
