"""
Rule Service — Business Logic + In-Memory Cache

Sits between API layer and Repository layer.
Loads rules from SQLite into memory on startup; masker.py reads from cache
with zero IO overhead at runtime.

Cache is invalidated on any write operation (create/update/delete/toggle).

Usage:
    from app.engine.rule_service import rule_service
    rules = rule_service.get_enabled_rules()   # fast, from cache
    rule_service.create_rule(data, "admin")     # writes DB + invalidates cache
"""
from __future__ import annotations
import re
import logging
import threading
from typing import TYPE_CHECKING, List, Optional, Dict
from dataclasses import dataclass

if TYPE_CHECKING:
    from app.engine.rules import MaskingRule, MaskStrategy

from app.engine.repository import (
    init_db,
    seed_builtin_rules,
    list_rules as repo_list_rules,
    get_rule as repo_get_rule,
    create_rule as repo_create_rule,
    update_rule as repo_update_rule,
    toggle_rule as repo_toggle_rule,
    delete_rule as repo_delete_rule,
    set_scope as repo_set_scope,
    set_visibility as repo_set_visibility,
    increment_use_count as repo_increment_use_count,
    list_orgs as repo_list_orgs,
    get_org as repo_get_org,
    create_org as repo_create_org,
    delete_org as repo_delete_org,
    set_org_invite_code as repo_set_org_invite_code,
    get_org_by_invite_code as repo_get_org_by_invite_code,
    export_rules as repo_export_rules,
    import_rules as repo_import_rules,
    fork_system_rules as repo_fork_system_rules,
    create_suggestion as repo_create_suggestion,
    list_suggestions as repo_list_suggestions,
    get_suggestion as repo_get_suggestion,
    review_suggestion as repo_review_suggestion,
    list_changelog as repo_list_changelog,
    _parse_flags,
)

logger = logging.getLogger(__name__)


# Re-use the same MaskingRule/MaskStrategy from rules.py to stay compatible
# (lazy import inside _db_row_to_masking_rule to avoid circular imports)


def _db_row_to_masking_rule(row: dict) -> "MaskingRule":
    """Convert a DB row dict into a MaskingRule dataclass (with compiled regex)."""
    from app.engine.rules import MaskingRule as _MaskingRule, MaskStrategy as _MaskStrategy  # lazy to break circular import
    flags = _parse_flags(row.get("flags", ""))
    pattern = re.compile(row["pattern"], flags)
    strategy = _MaskStrategy(row["strategy"])

    return _MaskingRule(
        id=row["id"],
        name=row["name"],
        pattern=pattern,
        strategy=strategy,
        placeholder=row["placeholder"],
        weight=row["weight"],
        enabled=bool(row["enabled"]),
    )


class RuleService:
    """
    Singleton service managing the rule lifecycle.

    Thread-safe: a RLock guards cache reads/writes.
    Cache invalidation is automatic on any mutation.
    """

    def __init__(self):
        self._cache: List[MaskingRule] = []
        self._cache_map: Dict[str, MaskingRule] = {}
        self._lock = threading.RLock()
        self._initialized = False

    # ─── Initialization ────────────────────────────────────────────────────

    def initialize(self):
        """
        Called once at application startup.
        Creates tables, seeds built-in rules, and loads cache.
        """
        if self._initialized:
            return
        init_db()
        seed_builtin_rules()
        self._reload_cache()
        self._initialized = True
        logger.info(f"RuleService initialized — {len(self._cache)} rules loaded into cache")

    # ─── Cache Management ──────────────────────────────────────────────────

    def _reload_cache(self):
        """Reload all rules from DB into memory."""
        rows = repo_list_rules()
        rules = []
        rule_map = {}
        for row in rows:
            try:
                rule = _db_row_to_masking_rule(row)
                rules.append(rule)
                rule_map[rule.id] = rule
            except Exception as e:
                logger.warning(f"Skipping invalid rule '{row.get('id')}': {e}")
        with self._lock:
            self._cache = rules
            self._cache_map = rule_map

    def _invalidate(self):
        """Invalidate cache — force reload from DB."""
        self._reload_cache()

    # ─── Read (from cache — zero IO) ──────────────────────────────────────

    def get_all_rules(self) -> List[MaskingRule]:
        """All rules (enabled + disabled), from cache."""
        with self._lock:
            return list(self._cache)

    def get_enabled_rules(self) -> List[MaskingRule]:
        """Only enabled rules, from cache. Used by masker.py."""
        with self._lock:
            return [r for r in self._cache if r.enabled]

    def get_rule_by_id(self, rule_id: str) -> Optional[MaskingRule]:
        """Get a single rule from cache."""
        with self._lock:
            return self._cache_map.get(rule_id)

    def get_rules_info(self) -> List[dict]:
        """Summary dicts for API responses."""
        with self._lock:
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "enabled": r.enabled,
                    "weight": r.weight,
                }
                for r in self._cache
            ]

    # ─── Write (DB + invalidate cache) ────────────────────────────────────

    def create_rule(self, data: dict, created_by: str = "admin") -> dict:
        """Create a new rule → DB, then invalidate cache."""
        result = repo_create_rule(data, created_by)
        self._invalidate()
        return result

    def update_rule(self, rule_id: str, data: dict, changed_by: str = "admin") -> dict:
        """Update rule → DB, then invalidate cache."""
        result = repo_update_rule(rule_id, data, changed_by)
        self._invalidate()
        return result

    def toggle_rule(self, rule_id: str, changed_by: str = "admin") -> dict:
        """Toggle enabled → DB, then invalidate cache."""
        result = repo_toggle_rule(rule_id, changed_by)
        self._invalidate()
        return result

    def delete_rule(self, rule_id: str, changed_by: str = "admin") -> bool:
        """Delete custom rule → DB, then invalidate cache."""
        result = repo_delete_rule(rule_id, changed_by)
        self._invalidate()
        return result

    def set_scope(self, rule_id: str, scope: str, org_id: Optional[str] = None, changed_by: str = "admin") -> dict:
        """Change rule scope (private → org → system) → DB, then invalidate cache."""
        result = repo_set_scope(rule_id, scope, org_id=org_id, changed_by=changed_by)
        self._invalidate()
        return result

    def set_visibility(self, rule_id: str, visibility: str, changed_by: str = "admin") -> dict:
        """Legacy alias: public→org (default), private→private."""
        result = repo_set_visibility(rule_id, visibility, changed_by)
        self._invalidate()
        return result

    def increment_use_count(self, rule_ids: List[str]) -> None:
        """Bump use_count for given rules (call after mask job completes)."""
        repo_increment_use_count(rule_ids)

    # ─── Suggestions ──────────────────────────────────────────────────────

    def create_suggestion(self, data: dict, submitted_by: str = "anonymous") -> dict:
        return repo_create_suggestion(data, submitted_by)

    def list_suggestions(self, status: Optional[str] = None, submitted_by: Optional[str] = None, org_id: Optional[str] = None) -> List[dict]:
        return repo_list_suggestions(status, submitted_by, org_id=org_id)

    def get_suggestion(self, suggestion_id: int) -> Optional[dict]:
        return repo_get_suggestion(suggestion_id)

    def review_suggestion(self, suggestion_id: int, action: str, reviewed_by: str = "admin", org_id: Optional[str] = None) -> dict:
        """Approve/reject → if approved, DB is mutated → invalidate cache.

        org_id: when set (org owner review), create-type suggestions produce an org-scoped rule.
        """
        result = repo_review_suggestion(suggestion_id, action=action, reviewed_by=reviewed_by, org_id=org_id)
        if action == "approve":
            self._invalidate()
        return result

    # ─── Import / Export ──────────────────────────────────────────────────

    def export_rules(self, org_id: Optional[str] = None) -> List[dict]:
        return repo_export_rules(org_id=org_id)

    def fork_system_rules(self, org_id: str, forked_by: str = "system") -> int:
        """Copy all enabled system rules to org scope, then mark org as custom rule set."""
        from app.engine.repo_orgs import set_custom_rule_set
        count = repo_fork_system_rules(org_id, forked_by=forked_by)
        set_custom_rule_set(org_id, enabled=True)
        self._invalidate()
        return count

    def import_rules(self, rules_data: List[dict], imported_by: str = "admin") -> dict:
        result = repo_import_rules(rules_data, imported_by)
        self._invalidate()
        return result

    # ─── Changelog ────────────────────────────────────────────────────────

    def list_changelog(self, rule_id: Optional[str] = None, limit: int = 50, org_id: Optional[str] = None) -> List[dict]:
        return repo_list_changelog(rule_id, limit, org_id=org_id)

    # ─── DB-level queries (pass-through for API detail views) ─────────────

    def get_rule_detail(self, rule_id: str) -> Optional[dict]:
        """Full DB row for a rule (includes metadata like version, timestamps)."""
        return repo_get_rule(rule_id)

    def list_rules_detailed(
        self,
        category: Optional[str] = None,
        enabled_only: bool = False,
        owner: Optional[str] = None,
        org_id: Optional[str] = None,
        role: str = "user",
    ) -> List[dict]:
        """Full DB rows for listing, scope-aware."""
        return repo_list_rules(category, enabled_only, owner=owner, org_id=org_id, role=role)

    # ─── Organizations ──────────────────────────────────────────────────

    def list_orgs(self) -> List[dict]:
        return repo_list_orgs()

    def get_org(self, org_id: str) -> Optional[dict]:
        return repo_get_org(org_id)

    def create_org(self, org_id: str, name: str, owner: str = None, owner_key_prefix: str = None) -> dict:
        return repo_create_org(org_id, name, owner=owner, owner_key_prefix=owner_key_prefix)

    def delete_org(self, org_id: str) -> bool:
        return repo_delete_org(org_id)

    def set_org_invite_code(self, org_id: str, code: str, expires_days: int = 7) -> Optional[dict]:
        return repo_set_org_invite_code(org_id, code, expires_days=expires_days)

    def get_org_by_invite_code(self, code: str) -> Optional[dict]:
        return repo_get_org_by_invite_code(code)


# ─── Global Singleton ─────────────────────────────────────────────────────────

rule_service = RuleService()
