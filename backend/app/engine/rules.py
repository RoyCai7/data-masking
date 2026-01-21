"""
Masking Rules Engine
Defines all sensitive data patterns and masking strategies
"""
import re
from dataclasses import dataclass
from typing import List, Pattern, Callable
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
    name_zh: str
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


# Define all masking rules
MASKING_RULES: List[MaskingRule] = [
    MaskingRule(
        id="ipv4",
        name="IPv4 Address",
        name_zh="IPv4 地址",
        pattern=re.compile(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'),
        strategy=MaskStrategy.PLACEHOLDER,
        placeholder="[IPv4]",
        weight=3
    ),
    MaskingRule(
        id="ipv6",
        name="IPv6 Address",
        name_zh="IPv6 地址",
        pattern=re.compile(r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b|\b(?:[0-9a-fA-F]{1,4}:){1,7}:|\b(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}\b'),
        strategy=MaskStrategy.PLACEHOLDER,
        placeholder="[IPv6]",
        weight=3
    ),
    MaskingRule(
        id="mac",
        name="MAC Address",
        name_zh="MAC 地址",
        pattern=re.compile(r'\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b'),
        strategy=MaskStrategy.PLACEHOLDER,
        placeholder="[MAC]",
        weight=3
    ),
    MaskingRule(
        id="email",
        name="Email Address",
        name_zh="邮箱地址",
        pattern=re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        strategy=MaskStrategy.PLACEHOLDER,
        placeholder="[EMAIL]",
        weight=5
    ),
    MaskingRule(
        id="path_user",
        name="Path Username",
        name_zh="路径用户名",
        pattern=re.compile(r'/home/([a-zA-Z0-9_-]+)'),
        strategy=MaskStrategy.PLACEHOLDER,
        placeholder="/home/[USER]",
        weight=2
    ),
    MaskingRule(
        id="license",
        name="License Key",
        name_zh="License Key",
        pattern=re.compile(r'\b[A-Z0-9]{4,5}(?:-[A-Z0-9]{4,5}){2,}\b'),
        strategy=MaskStrategy.PLACEHOLDER,
        placeholder="[LICENSE]",
        weight=10
    ),
    MaskingRule(
        id="hostname",
        name="Hostname",
        name_zh="主机名",
        pattern=re.compile(r'\b(?:sles?|suse|linux|server|host|node|vm|container)[-_]?[a-zA-Z0-9]+[-_]?[a-zA-Z0-9]*\b', re.IGNORECASE),
        strategy=MaskStrategy.PLACEHOLDER,
        placeholder="[HOSTNAME]",
        weight=2
    ),
    MaskingRule(
        id="username",
        name="Username Pattern",
        name_zh="用户名",
        pattern=re.compile(r'\b(?:user|admin|root|operator)[=:\s]+([a-zA-Z0-9_-]+)\b', re.IGNORECASE),
        strategy=MaskStrategy.PLACEHOLDER,
        placeholder="[USERNAME]",
        weight=4
    ),
]


def get_enabled_rules() -> List[MaskingRule]:
    """Get all enabled masking rules"""
    return [rule for rule in MASKING_RULES if rule.enabled]


def get_rule_by_id(rule_id: str) -> MaskingRule:
    """Get a rule by its ID"""
    for rule in MASKING_RULES:
        if rule.id == rule_id:
            return rule
    return None


def get_rules_info() -> List[dict]:
    """Get rule information for API response"""
    return [
        {
            "id": rule.id,
            "name": rule.name,
            "name_zh": rule.name_zh,
            "enabled": rule.enabled,
            "weight": rule.weight
        }
        for rule in MASKING_RULES
    ]
