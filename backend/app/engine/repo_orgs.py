"""
repo_orgs.py — Organization and org_owners CRUD.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from app.engine.db import _get_conn

logger = logging.getLogger(__name__)


def list_orgs() -> List[dict]:
    """List all organizations."""
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM organizations ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_org(org_id: str) -> Optional[dict]:
    """Get org by id."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM organizations WHERE id = ?", (org_id,)).fetchone()
    return dict(row) if row else None


def create_org(org_id: str, name: str, owner: str = None,
               owner_key_prefix: str = None) -> dict:
    """Create a new organization. Raises ValueError if id already exists."""
    if get_org(org_id):
        raise ValueError(f"Organization '{org_id}' already exists")
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO organizations (id, name, owner, owner_key_prefix, created_at) VALUES (?, ?, ?, ?, ?)",
        (org_id, name, owner, owner_key_prefix, now)
    )
    # Also write the founder into org_owners table
    if owner_key_prefix:
        conn.execute(
            "INSERT OR IGNORE INTO org_owners (org_id, key_prefix, added_at) VALUES (?, ?, ?)",
            (org_id, owner_key_prefix, now)
        )
    conn.commit()
    return get_org(org_id)


def get_org_owners(org_id: str) -> List[str]:
    """Return list of key_prefixes that are owners of this org."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT key_prefix FROM org_owners WHERE org_id = ? ORDER BY added_at", (org_id,)
    ).fetchall()
    return [r["key_prefix"] for r in rows]


def is_org_owner(org_id: str, key_prefix: str) -> bool:
    """Return True if key_prefix is an owner of org_id."""
    if not key_prefix:
        return False
    conn = _get_conn()
    row = conn.execute(
        "SELECT 1 FROM org_owners WHERE org_id = ? AND key_prefix = ?", (org_id, key_prefix)
    ).fetchone()
    return row is not None


def add_org_owner(org_id: str, key_prefix: str) -> None:
    """Add a new owner to an org."""
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO org_owners (org_id, key_prefix, added_at) VALUES (?, ?, ?)",
        (org_id, key_prefix, now)
    )
    conn.commit()


def remove_org_owner(org_id: str, key_prefix: str) -> None:
    """Remove an owner from an org. Raises ValueError if they are the last owner."""
    owners = get_org_owners(org_id)
    if key_prefix not in owners:
        raise ValueError(f"'{key_prefix}' is not an owner of org '{org_id}'")
    if len(owners) <= 1:
        raise ValueError("Cannot remove the last owner. Add another owner first.")
    conn = _get_conn()
    conn.execute("DELETE FROM org_owners WHERE org_id = ? AND key_prefix = ?", (org_id, key_prefix))
    conn.commit()


def set_org_invite_code(org_id: str, code: str, expires_days: int = 7) -> Optional[dict]:
    """Set invite code on an org with an expiry. Returns updated org or None."""
    conn = _get_conn()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat()
    conn.execute(
        "UPDATE organizations SET invite_code = ?, invite_code_expires_at = ? WHERE id = ?",
        (code, expires_at, org_id)
    )
    conn.commit()
    return get_org(org_id)


def get_org_by_invite_code(code: str) -> Optional[dict]:
    """Find an org by its invite code. Returns None if not found or expired."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM organizations WHERE invite_code = ?", (code,)).fetchone()
    if not row:
        return None
    org = dict(row)
    expires_at = org.get("invite_code_expires_at")
    if expires_at:
        try:
            if datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
                return None  # expired
        except ValueError:
            pass
    return org


def set_custom_rule_set(org_id: str, enabled: bool = True) -> None:
    """Mark an org as having a custom (forked) rule set.
    When True, the masking engine no longer injects system rules for this org."""
    conn = _get_conn()
    conn.execute(
        "UPDATE organizations SET custom_rule_set = ? WHERE id = ?",
        (1 if enabled else 0, org_id)
    )
    conn.commit()


def delete_org(org_id: str) -> bool:
    """Delete an org. Cannot delete 'default'.
    All keys belonging to this org are moved back to 'default'."""
    if org_id == "default":
        raise ValueError("Cannot delete the default organization")
    conn = _get_conn()
    # Reset member keys to default org before deleting
    conn.execute(
        "UPDATE api_keys SET org_id = 'default' WHERE org_id = ?",
        (org_id,),
    )
    conn.execute("DELETE FROM organizations WHERE id = ?", (org_id,))
    conn.execute("DELETE FROM org_owners WHERE org_id = ?", (org_id,))
    conn.commit()
    return True
