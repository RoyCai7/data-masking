"""
db.py — SQLite connection, schema DDL, init_db, and migration helpers.

This module owns everything related to database connectivity and schema
lifecycle.  All other repository modules import _get_conn() from here.
"""
import sqlite3
import os
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Default DB path — overridable via env var
DB_PATH = Path(os.getenv(
    "RULES_DB_PATH",
    str(Path(__file__).parent.parent.parent / "rules.db")
))

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Get a thread-local SQLite connection (one per thread)."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_PATH), timeout=10)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


# ─── Schema Initialization ────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS organizations (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    owner                 TEXT,
    owner_key_prefix      TEXT,
    invite_code           TEXT,
    invite_code_expires_at TEXT,
    created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS org_owners (
    org_id     TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    added_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (org_id, key_prefix)
);

CREATE TABLE IF NOT EXISTS rules (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'general',
    pattern     TEXT NOT NULL,
    flags       TEXT NOT NULL DEFAULT '',
    strategy    TEXT NOT NULL DEFAULT 'placeholder',
    placeholder TEXT NOT NULL DEFAULT '[MASKED]',
    weight      INTEGER NOT NULL DEFAULT 5,
    enabled     INTEGER NOT NULL DEFAULT 1,
    is_builtin  INTEGER NOT NULL DEFAULT 0,
    scope       TEXT    NOT NULL DEFAULT 'private',
    org_id      TEXT,
    use_count   INTEGER NOT NULL DEFAULT 0,
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    created_by  TEXT NOT NULL DEFAULT 'system'
);

CREATE TABLE IF NOT EXISTS rule_suggestions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id      TEXT,
    action       TEXT NOT NULL CHECK(action IN ('create','modify','disable')),
    name         TEXT,
    category     TEXT,
    pattern      TEXT,
    flags        TEXT,
    strategy     TEXT,
    placeholder  TEXT,
    weight       INTEGER,
    reason       TEXT,
    status       TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
    submitted_by TEXT,
    submitted_at TEXT NOT NULL DEFAULT (datetime('now')),
    reviewed_by  TEXT,
    reviewed_at  TEXT
);

CREATE TABLE IF NOT EXISTS rule_changelog (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id    TEXT NOT NULL,
    action     TEXT NOT NULL,
    old_value  TEXT,
    new_value  TEXT,
    changed_by TEXT NOT NULL DEFAULT 'system',
    changed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS api_keys (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash   TEXT NOT NULL UNIQUE,
    key_prefix TEXT NOT NULL,
    key_plain  TEXT,
    name       TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'user',
    org_id     TEXT NOT NULL DEFAULT 'default',
    enabled    INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT
);
"""


def init_db():
    """Create tables if they don't exist, and run any pending migrations."""
    conn = _get_conn()
    conn.executescript(_SCHEMA_SQL)

    # ── Migrations (all idempotent) ──────────────────────────────────────────
    # 1. Legacy: rename visibility → scope
    try:
        conn.execute("ALTER TABLE rules ADD COLUMN visibility TEXT NOT NULL DEFAULT 'private'")
        conn.commit()
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE rules ADD COLUMN scope TEXT NOT NULL DEFAULT 'private'")
        conn.commit()
        logger.info("Migration: added 'scope' column to rules")
    except Exception:
        pass
    # Copy visibility → scope if scope is still all 'private' but visibility has data
    conn.execute("""
        UPDATE rules SET scope = CASE
            WHEN is_builtin = 1 THEN 'system'
            WHEN visibility = 'public' THEN 'org'
            ELSE 'private'
        END
        WHERE scope = 'private' AND visibility IS NOT NULL
    """)

    # 2. Add org_id column
    try:
        conn.execute("ALTER TABLE rules ADD COLUMN org_id TEXT")
        conn.commit()
        logger.info("Migration: added 'org_id' column to rules")
    except Exception:
        pass
    # system rules → org_id=NULL; former public non-builtin → org_id='default'
    conn.execute("UPDATE rules SET org_id = NULL WHERE scope = 'system'")
    conn.execute("UPDATE rules SET org_id = 'default' WHERE scope = 'org' AND org_id IS NULL")

    # 3. Add use_count column
    try:
        conn.execute("ALTER TABLE rules ADD COLUMN use_count INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        logger.info("Migration: added 'use_count' column to rules")
    except Exception:
        pass

    # 4. Ensure default org exists
    conn.execute("""
        INSERT OR IGNORE INTO organizations (id, name) VALUES ('default', 'Default Organization')
    """)
    conn.commit()

    # 5. Add owner and invite_code columns to organizations (migration)
    for col, definition in [("owner", "TEXT"), ("invite_code", "TEXT"),
                            ("owner_key_prefix", "TEXT"), ("invite_code_expires_at", "TEXT")]:
        try:
            conn.execute(f"ALTER TABLE organizations ADD COLUMN {col} {definition}")
            conn.commit()
            logger.info(f"Migration: added '{col}' column to organizations")
        except Exception:
            pass

    # 6. Migrate existing keys.json into api_keys table (one-time, idempotent)
    _migrate_keys_json_to_db(conn)

    # 7. Add key_plain column to api_keys (may not exist for older installs)
    try:
        conn.execute("ALTER TABLE api_keys ADD COLUMN key_plain TEXT")
        conn.commit()
        logger.info("Migration: added 'key_plain' column to api_keys")
    except Exception:
        pass
    # Back-fill key_plain from keys.json for rows that are missing it
    _backfill_key_plain_from_json(conn)

    # 8. Add creator_key_prefix to rules (tracks rule ownership for self-service model)
    try:
        conn.execute("ALTER TABLE rules ADD COLUMN creator_key_prefix TEXT")
        conn.commit()
        logger.info("Migration: added 'creator_key_prefix' column to rules")
    except Exception:
        pass

    # 9. Multi-owner support: migrate single owner_key_prefix → org_owners table
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS org_owners (
            org_id     TEXT NOT NULL,
            key_prefix TEXT NOT NULL,
            added_at   TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (org_id, key_prefix)
        );
    """)
    # Migrate any existing single-owner rows that haven't been copied yet
    conn.execute("""
        INSERT OR IGNORE INTO org_owners (org_id, key_prefix)
        SELECT id, owner_key_prefix
        FROM organizations
        WHERE owner_key_prefix IS NOT NULL AND owner_key_prefix != ''
    """)
    conn.commit()
    logger.info("Migration 9: org_owners table ready")

    # 10. Add custom_rule_set flag to organizations
    try:
        conn.execute("ALTER TABLE organizations ADD COLUMN custom_rule_set INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        logger.info("Migration 10: added 'custom_rule_set' column to organizations")
    except Exception:
        pass

    # 11. Add description column to rules and backfill builtin descriptions
    try:
        conn.execute("ALTER TABLE rules ADD COLUMN description TEXT")
        conn.commit()
        logger.info("Migration 11: added 'description' column to rules")
    except Exception:
        pass
    try:
        from app.engine.repo_rules import RULE_DESCRIPTIONS
        for rule_id, desc in RULE_DESCRIPTIONS.items():
            conn.execute(
                "UPDATE rules SET description = ? WHERE id = ? AND is_builtin = 1 AND (description IS NULL OR description = '')",
                (desc, rule_id)
            )
        conn.commit()
        logger.info(f"Migration 11: backfilled descriptions for {len(RULE_DESCRIPTIONS)} builtin rules")
    except Exception as e:
        logger.warning(f"Migration 11: description backfill failed: {e}")

    # 12. Backfill descriptions on forked org rules from their parent system rules
    try:
        conn.execute(
            """
            UPDATE rules SET description = (
                SELECT s.description FROM rules s
                WHERE s.id = SUBSTR(rules.id, INSTR(rules.id, '__') + 2)
                  AND s.scope = 'system'
            )
            WHERE scope = 'org'
              AND INSTR(id, '__') > 0
              AND (description IS NULL OR description = '')
            """
        )
        conn.commit()
        logger.info("Migration 12: backfilled descriptions on forked org rules")
    except Exception as e:
        logger.warning(f"Migration 12: forked rule description backfill failed: {e}")

    logger.info(f"Rules database initialized at {DB_PATH}")


# ─── Legacy keys.json migration helpers ──────────────────────────────────────

def _load_keys_json() -> list:
    """Load raw key records from keys.json, returns [] on any error."""
    import json as _json
    keys_file = Path(os.getenv("API_KEYS_FILE", str(Path(__file__).parent.parent.parent / "keys.json")))
    if not keys_file.exists():
        return []
    try:
        with open(keys_file, "r") as f:
            return _json.load(f).get("keys", [])
    except Exception:
        return []


def _migrate_keys_json_to_db(conn: sqlite3.Connection):
    """Import keys from legacy keys.json file into the api_keys table (one-time)."""
    import hashlib
    imported = 0
    for k in _load_keys_json():
        raw_key = k.get("key", "")
        if not raw_key:
            continue
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:8]
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO api_keys (key_hash, key_prefix, key_plain, name, role, org_id, enabled, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key_hash,
                    key_prefix,
                    raw_key,
                    k.get("name", "unknown"),
                    k.get("role", "user"),
                    k.get("org_id", "default"),
                    1 if k.get("enabled", True) else 0,
                    k.get("created_at", datetime.now(timezone.utc).date().isoformat()),
                    k.get("expires_at"),
                ),
            )
            imported += 1
        except Exception as e:
            logger.warning(f"Failed to migrate key '{k.get('name')}': {e}")
    conn.commit()
    if imported:
        logger.info(f"Migrated {imported} keys from keys.json into api_keys table")


def _backfill_key_plain_from_json(conn: sqlite3.Connection):
    """Fill key_plain for any rows that are missing it (e.g. migrated before this column existed)."""
    import hashlib
    rows_missing = conn.execute("SELECT id FROM api_keys WHERE key_plain IS NULL").fetchall()
    if not rows_missing:
        return
    json_keys = {hashlib.sha256(k["key"].encode()).hexdigest(): k["key"] for k in _load_keys_json() if k.get("key")}
    filled = 0
    for row in rows_missing:
        row_data = conn.execute("SELECT key_hash FROM api_keys WHERE id = ?", (row["id"],)).fetchone()
        plain = json_keys.get(row_data["key_hash"])
        if plain:
            conn.execute("UPDATE api_keys SET key_plain = ? WHERE id = ?", (plain, row["id"]))
            filled += 1
    if filled:
        conn.commit()
        logger.info(f"Back-filled key_plain for {filled} rows")
