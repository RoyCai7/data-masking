"""
repo_users.py - User accounts, sessions, and password reset persistence.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.engine.db import _get_conn


def _dict(row) -> Optional[Dict[str, Any]]:
    return dict(row) if row else None


def db_count_users() -> int:
    conn = _get_conn()
    row = conn.execute("SELECT COUNT(*) AS total FROM users").fetchone()
    return int(row["total"])


def db_create_user(email: str, name: str, password_hash: str,
                   role: str = "user", org_id: str = "default") -> Dict[str, Any]:
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO users (email, name, password_hash, role, org_id, enabled)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        (email, name, password_hash, role, org_id),
    )
    conn.commit()
    return db_get_user_by_email(email)


def db_get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    return _dict(row)


def db_get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _dict(row)


def db_update_user_password(user_id: int, password_hash: str) -> bool:
    conn = _get_conn()
    cur = conn.execute(
        "UPDATE users SET password_hash = ?, updated_at = datetime('now') WHERE id = ?",
        (password_hash, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def db_mark_user_email_verified(user_id: int) -> bool:
    conn = _get_conn()
    cur = conn.execute(
        "UPDATE users SET email_verified = 1, updated_at = datetime('now') WHERE id = ?",
        (user_id,),
    )
    conn.commit()
    return cur.rowcount > 0


def db_update_user_org(user_id: int, org_id: str) -> bool:
    conn = _get_conn()
    cur = conn.execute(
        "UPDATE users SET org_id = ?, updated_at = datetime('now') WHERE id = ?",
        (org_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def db_add_session(user_id: int, token_hash: str, expires_at: str) -> Dict[str, Any]:
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO user_sessions (user_id, token_hash, enabled, expires_at)
        VALUES (?, ?, 1, ?)
        """,
        (user_id, token_hash, expires_at),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM user_sessions WHERE token_hash = ?", (token_hash,)).fetchone()
    return dict(row)


def db_get_session_by_hash(token_hash: str) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    row = conn.execute(
        """
        SELECT s.*, u.email, u.name, u.role, u.org_id, u.enabled AS user_enabled, u.created_at AS user_created_at
        FROM user_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = ?
        """,
        (token_hash,),
    ).fetchone()
    return _dict(row)


def db_disable_session(token_hash: str) -> bool:
    conn = _get_conn()
    cur = conn.execute("UPDATE user_sessions SET enabled = 0 WHERE token_hash = ?", (token_hash,))
    conn.commit()
    return cur.rowcount > 0


def db_disable_user_sessions(user_id: int) -> int:
    conn = _get_conn()
    cur = conn.execute("UPDATE user_sessions SET enabled = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    return cur.rowcount


def db_add_password_reset(user_id: int, token_hash: str, expires_at: str) -> Dict[str, Any]:
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO password_reset_tokens (user_id, token_hash, used, expires_at)
        VALUES (?, ?, 0, ?)
        """,
        (user_id, token_hash, expires_at),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM password_reset_tokens WHERE token_hash = ?", (token_hash,)).fetchone()
    return dict(row)


def db_add_email_verification(user_id: int, token_hash: str, expires_at: str) -> Dict[str, Any]:
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO email_verification_tokens (user_id, token_hash, used, expires_at)
        VALUES (?, ?, 0, ?)
        """,
        (user_id, token_hash, expires_at),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM email_verification_tokens WHERE token_hash = ?", (token_hash,)).fetchone()
    return dict(row)


def db_get_email_verification(token_hash: str) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    row = conn.execute(
        """
        SELECT v.*, u.email, u.name
        FROM email_verification_tokens v
        JOIN users u ON u.id = v.user_id
        WHERE v.token_hash = ?
        """,
        (token_hash,),
    ).fetchone()
    return _dict(row)


def db_mark_email_verification_used(token_hash: str) -> bool:
    conn = _get_conn()
    cur = conn.execute("UPDATE email_verification_tokens SET used = 1 WHERE token_hash = ?", (token_hash,))
    conn.commit()
    return cur.rowcount > 0


def db_get_password_reset(token_hash: str) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    row = conn.execute(
        """
        SELECT r.*, u.email, u.name
        FROM password_reset_tokens r
        JOIN users u ON u.id = r.user_id
        WHERE r.token_hash = ?
        """,
        (token_hash,),
    ).fetchone()
    return _dict(row)


def db_mark_password_reset_used(token_hash: str) -> bool:
    conn = _get_conn()
    cur = conn.execute("UPDATE password_reset_tokens SET used = 1 WHERE token_hash = ?", (token_hash,))
    conn.commit()
    return cur.rowcount > 0


def db_get_keys_by_user_id(user_id: int) -> List[Dict[str, Any]]:
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT id, key_prefix, email, name, role, org_id, enabled, created_at, expires_at
        FROM api_keys
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]
