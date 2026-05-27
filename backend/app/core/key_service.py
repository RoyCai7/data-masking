"""
key_service.py — API key business logic (create, rotate, update, disable).

This is the single source of truth for key lifecycle operations.
auth.py keeps re-exports for backward compatibility but delegates here.

Design:
  - No FastAPI/HTTP concerns — pure Python functions returning dicts
  - All heavy lifting delegated to repo_keys (DB layer)
  - Hashing logic centralised via _hash_key (imported from auth)
"""
import logging
from datetime import date, timedelta
from typing import Optional, Dict, Any

from app.core.auth import _hash_key, generate_api_key
from app.engine.repo_keys import (
    db_add_key,
    db_get_key_by_hash,
    db_get_all_keys,
    db_update_key,
    db_update_key_by_id,
    db_disable_key,
    db_disable_key_by_id,
    db_get_key_plain_by_id,
)

logger = logging.getLogger(__name__)


def add_key(name: str, role: str = "user", expires_days: int = 365,
            org_id: str = "default") -> dict:
    """
    Create a new API key.
    Stores only the SHA-256 hash; returns the plaintext key ONCE.
    """
    raw_key = generate_api_key()
    key_hash = _hash_key(raw_key)
    key_prefix = raw_key[:8]
    expires_at = (date.today() + timedelta(days=expires_days)).isoformat()
    row = db_add_key(
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=name,
        role=role,
        org_id=org_id,
        expires_at=expires_at,
        key_plain=raw_key,
    )
    logger.info(f"API key created for '{name}' (role={role}, org={org_id})")
    return {
        "id": row.get("id"),
        "key": raw_key,
        "key_prefix": key_prefix,
        "name": name,
        "role": role,
        "org_id": org_id,
        "created_at": date.today().isoformat(),
        "expires_at": expires_at,
        "enabled": True,
    }


def rotate_key(old_api_key: str) -> Optional[dict]:
    """
    Disable the old key and issue a new one with the same name/role/org.
    Preserves remaining expiry days.  Returns new key data, or None if not found.
    """
    old_hash = _hash_key(old_api_key)
    old_entry = db_get_key_by_hash(old_hash)
    if not old_entry:
        return None
    db_disable_key(old_hash)

    expires_days = 365  # fallback
    expires_at_str = old_entry.get("expires_at")
    if expires_at_str:
        try:
            remaining = (date.fromisoformat(expires_at_str) - date.today()).days
            expires_days = max(remaining, 1)
        except ValueError:
            pass

    new_key_data = add_key(
        name=old_entry["name"],
        role=old_entry.get("role", "user"),
        org_id=old_entry.get("org_id", "default"),
        expires_days=expires_days,
    )
    logger.info(f"API key rotated for '{old_entry['name']}'")
    return new_key_data


def update_key(api_key: str, org_id: Optional[str] = None,
               role: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Update org_id / role of an existing key identified by plaintext."""
    return db_update_key(_hash_key(api_key), org_id=org_id, role=role)


def disable_key(api_key: str) -> bool:
    """Disable a key by its plaintext value."""
    return db_disable_key(_hash_key(api_key))


def list_keys() -> list:
    """Return all keys (no hashes, no plaintext)."""
    return db_get_all_keys()


# Re-export lower-level by-id helpers so callers only need one import
update_key_by_id = db_update_key_by_id
disable_key_by_id = db_disable_key_by_id
get_key_plain_by_id = db_get_key_plain_by_id
