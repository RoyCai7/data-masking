"""
repository.py — Thin re-export facade.

All implementation has been split into domain-specific modules:
  - app.engine.db          → connection, schema, init_db, migrations
  - app.engine.repo_rules  → rules CRUD, suggestions, changelog, import/export, seed
  - app.engine.repo_keys   → api_keys CRUD
  - app.engine.repo_orgs   → organizations + org_owners CRUD

This module re-exports everything so existing consumers continue to work
without any import changes.
"""

# Infrastructure
from app.engine.db import (  # noqa: F401
    DB_PATH,
    _get_conn,
    _local,
    init_db,
    _load_keys_json,
    _migrate_keys_json_to_db,
    _backfill_key_plain_from_json,
)

# Rules domain
from app.engine.repo_rules import *  # noqa: F401, F403
from app.engine.repo_rules import (  # noqa: F401  (explicit for type checkers)
    BUILTIN_RULES,
    seed_builtin_rules,
    list_rules,
    list_rules_detailed,
    get_rule,
    create_rule,
    update_rule,
    toggle_rule,
    set_scope,
    set_visibility,
    increment_use_count,
    delete_rule,
    create_suggestion,
    get_suggestion,
    list_suggestions,
    review_suggestion,
    export_rules,
    import_rules,
    fork_system_rules,
    list_changelog,
    _parse_flags,
    _validate_org_id,
    _log_change,
    _row_to_dict,
)

# Keys domain
from app.engine.repo_keys import *  # noqa: F401, F403
from app.engine.repo_keys import (  # noqa: F401
    db_add_key,
    db_get_key_plain_by_id,
    db_get_key_by_hash,
    db_get_key_by_email,
    db_get_all_keys,
    db_update_key_by_id,
    db_update_key,
    db_disable_key_by_id,
    db_disable_key,
)

# Orgs domain
from app.engine.repo_orgs import *  # noqa: F401, F403
from app.engine.repo_orgs import (  # noqa: F401
    list_orgs,
    get_org,
    create_org,
    get_org_owners,
    is_org_owner,
    add_org_owner,
    remove_org_owner,
    set_org_invite_code,
    get_org_by_invite_code,
    delete_org,
)
