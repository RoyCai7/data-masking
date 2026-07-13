"""
repo_keys.py — API key CRUD against the api_keys table.
"""
import logging
from typing import List, Optional, Dict, Any

from app.engine.db import _get_conn

logger = logging.getLogger(__name__)


def db_add_key(key_hash: str, key_prefix: str, name: str, role: str = "user",
               org_id: str = "default", expires_at: Optional[str] = None,
               key_plain: Optional[str] = None,
               email: Optional[str] = None) -> Dict[str, Any]:
    """Insert a new hashed API key into the DB and return its record."""
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO api_keys (key_hash, key_prefix, key_plain, email, name, role, org_id, enabled, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (key_hash, key_prefix, key_plain, email, name, role, org_id, expires_at),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)
    ).fetchone()
    return dict(row)


def db_get_key_plain_by_id(key_id: int) -> Optional[str]:
    """Return the plaintext key for a given DB row id, or None if not stored."""
    conn = _get_conn()
    row = conn.execute("SELECT key_plain FROM api_keys WHERE id = ?", (key_id,)).fetchone()
    return row["key_plain"] if row else None


def db_get_key_by_hash(key_hash: str) -> Optional[Dict[str, Any]]:
    """Retrieve a key record by its SHA-256 hash."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)
    ).fetchone()
    return dict(row) if row else None


def db_get_key_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Retrieve a key record by normalized email."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM api_keys WHERE email = ?", (email,)
    ).fetchone()
    return dict(row) if row else None


def db_get_org_by_key_prefix(key_prefix: str) -> Optional[str]:
    """Return the org_id for a key identified by its prefix, or None."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT org_id FROM api_keys WHERE key_prefix = ?", (key_prefix,)
    ).fetchone()
    return row["org_id"] if row else None


def db_get_all_keys() -> List[Dict[str, Any]]:
    """Return all API key records (without hash), including DB id."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, key_prefix, email, name, role, org_id, enabled, created_at, expires_at FROM api_keys ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def db_update_key_by_id(key_id: int, org_id: Optional[str] = None,
                        role: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Update mutable fields of a key identified by DB id."""
    conn = _get_conn()
    if org_id is not None:
        conn.execute("UPDATE api_keys SET org_id = ? WHERE id = ?", (org_id, key_id))
    if role is not None:
        conn.execute("UPDATE api_keys SET role = ? WHERE id = ?", (role, key_id))
    conn.commit()
    row = conn.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone()
    return dict(row) if row else None


def db_update_key(key_hash: str, org_id: Optional[str] = None,
                  role: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Update mutable fields of a key identified by its SHA-256 hash."""
    conn = _get_conn()
    if org_id is not None:
        conn.execute("UPDATE api_keys SET org_id = ? WHERE key_hash = ?", (org_id, key_hash))
    if role is not None:
        conn.execute("UPDATE api_keys SET role = ? WHERE key_hash = ?", (role, key_hash))
    conn.commit()
    row = conn.execute("SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)).fetchone()
    return dict(row) if row else None


def db_clear_key_email(key_hash: str) -> None:
    """Remove email binding from a key row, used when rotating email-bound keys."""
    conn = _get_conn()
    conn.execute("UPDATE api_keys SET email = NULL WHERE key_hash = ?", (key_hash,))
    conn.commit()


def db_disable_key_by_id(key_id: int) -> bool:
    """Disable a key by its DB id. Returns True if a row was updated."""
    conn = _get_conn()
    cur = conn.execute("UPDATE api_keys SET enabled = 0 WHERE id = ?", (key_id,))
    conn.commit()
    return cur.rowcount > 0


def db_disable_key(key_hash: str) -> bool:
    """Disable a key by its hash. Returns True if a row was updated."""
    conn = _get_conn()
    cur = conn.execute("UPDATE api_keys SET enabled = 0 WHERE key_hash = ?", (key_hash,))
    conn.commit()
    return cur.rowcount > 0
