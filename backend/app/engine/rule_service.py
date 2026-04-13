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
import re
import logging
import threading
from typing import List, Optional, Dict
from dataclasses import dataclass

from app.engine.repository import (
    init_db,
    seed_builtin_rules,
    list_rules as repo_list_rules,
    get_rule as repo_get_rule,
    create_rule as repo_create_rule,
    update_rule as repo_update_rule,
    toggle_rule as repo_toggle_rule,
    delete_rule as repo_delete_rule,
    export_rules as repo_export_rules,
    import_rules as repo_import_rules,
    create_suggestion as repo_create_suggestion,
    list_suggestions as repo_list_suggestions,
    get_suggestion as repo_get_suggestion,
    review_suggestion as repo_review_suggestion,
    list_changelog as repo_list_changelog,
    _parse_flags,
)

logger = logging.getLogger(__name__)


# Re-use the same MaskingRule/MaskStrategy from rules.py to stay compatible
from app.engine.rules import MaskingRule, MaskStrategy


def _db_row_to_masking_rule(row: dict) -> MaskingRule:
    """Convert a DB row dict into a MaskingRule dataclass (with compiled regex)."""
    flags = _parse_flags(row.get("flags", ""))
    pattern = re.compile(row["pattern"], flags)
    strategy = MaskStrategy(row["strategy"])

    return MaskingRule(
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

    # ─── Suggestions ──────────────────────────────────────────────────────

    def create_suggestion(self, data: dict, submitted_by: str = "anonymous") -> dict:
        return repo_create_suggestion(data, submitted_by)

    def list_suggestions(self, status: Optional[str] = None, submitted_by: Optional[str] = None) -> List[dict]:
        return repo_list_suggestions(status, submitted_by)

    def get_suggestion(self, suggestion_id: int) -> Optional[dict]:
        return repo_get_suggestion(suggestion_id)

    def review_suggestion(self, suggestion_id: int, action: str, reviewed_by: str = "admin") -> dict:
        """Approve/reject → if approved, DB is mutated → invalidate cache."""
        result = repo_review_suggestion(suggestion_id, action, reviewed_by)
        if action == "approve":
            self._invalidate()
        return result

    # ─── Import / Export ──────────────────────────────────────────────────

    def export_rules(self) -> List[dict]:
        return repo_export_rules()

    def import_rules(self, rules_data: List[dict], imported_by: str = "admin") -> dict:
        result = repo_import_rules(rules_data, imported_by)
        self._invalidate()
        return result

    # ─── Changelog ────────────────────────────────────────────────────────

    def list_changelog(self, rule_id: Optional[str] = None, limit: int = 50) -> List[dict]:
        return repo_list_changelog(rule_id, limit)

    # ─── DB-level queries (pass-through for API detail views) ─────────────

    def get_rule_detail(self, rule_id: str) -> Optional[dict]:
        """Full DB row for a rule (includes metadata like version, timestamps)."""
        return repo_get_rule(rule_id)

    def list_rules_detailed(self, category: Optional[str] = None, enabled_only: bool = False) -> List[dict]:
        """Full DB rows for listing (includes all metadata)."""
        return repo_list_rules(category, enabled_only)


# ─── Global Singleton ─────────────────────────────────────────────────────────

rule_service = RuleService()
