"""
Masking Rules Engine
Defines core data types (MaskingRule, MaskStrategy) and public accessor functions.

Rules are now stored in SQLite and managed through RuleService.
This module remains the public interface that masker.py imports from —
keeping backward compatibility while switching the backing store.
"""
import re
from dataclasses import dataclass
from typing import List, Pattern, Optional
from enum import Enum


class MaskStrategy(Enum):
    """Masking strategy types"""
    ASTERISK = "asterisk"      # Replace with asterisks
    PLACEHOLDER = "placeholder" # Replace with placeholder text
    PARTIAL = "partial"        # Partial masking (keep some chars)
    HASH = "hash"              # Replace with hash


@dataclass
class MaskingRule:
    """Definition of a masking rule"""
    id: str
    name: str
    pattern: Pattern
    strategy: MaskStrategy
    placeholder: str
    weight: int  # Risk weight for scoring
    enabled: bool = True

    def mask(self, text: str) -> str:
        """Apply masking to matched text"""
        if self.strategy == MaskStrategy.ASTERISK:
            return '*' * len(text)
        elif self.strategy == MaskStrategy.PLACEHOLDER:
            return self.placeholder
        elif self.strategy == MaskStrategy.PARTIAL:
            if len(text) <= 4:
                return '*' * len(text)
            return text[:2] + '*' * (len(text) - 4) + text[-2:]
        elif self.strategy == MaskStrategy.HASH:
            import hashlib
            return hashlib.md5(text.encode()).hexdigest()[:8]
        return self.placeholder


# ─── Public API (delegates to RuleService singleton) ───────────────────────────

def _service():
    """Lazy import to avoid circular dependency at module load time."""
    from app.engine.rule_service import rule_service
    return rule_service


def get_enabled_rules() -> List[MaskingRule]:
    """Get all enabled masking rules (from in-memory cache)."""
    return _service().get_enabled_rules()


def get_rule_by_id(rule_id: str) -> Optional[MaskingRule]:
    """Get a rule by its ID (from in-memory cache)."""
    return _service().get_rule_by_id(rule_id)


def get_rules_info() -> List[dict]:
    """Get rule summary dicts for API responses."""
    return _service().get_rules_info()
