"""
Rule Repository — SQLite Data Access Layer

Manages persistent storage of masking rules using SQLite (Python built-in).
Provides CRUD operations, user suggestions, and changelog tracking.

Design:
  - Zero external dependencies (sqlite3 is in Python stdlib)
  - Thread-safe with WAL mode for concurrent reads
  - Startup: seeds built-in rules if DB is empty
  - All writes are logged to rule_changelog for audit trail
"""
import sqlite3
import json
import os
import logging
import threading
from datetime import datetime
from typing import List, Optional, Dict, Any
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
"""


def init_db():
    """Create tables if they don't exist."""
    conn = _get_conn()
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    logger.info(f"Rules database initialized at {DB_PATH}")


# ─── Built-in Rules Seed Data ─────────────────────────────────────────────────

BUILTIN_RULES: List[Dict[str, Any]] = [
    # ── Network ──
    {
        "id": "ipv4",
        "name": "IPv4 Address",
        "category": "network",
        "pattern": r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[IPv4]",
        "weight": 3,
    },
    {
        "id": "ipv4_cidr",
        "name": "IPv4 CIDR",
        "category": "network",
        "pattern": r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)/(?:3[0-2]|[12]?[0-9])\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[IPv4_CIDR]",
        "weight": 3,
    },
    {
        "id": "ipv6",
        "name": "IPv6 Address",
        "category": "network",
        "pattern": r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b|\b(?:[0-9a-fA-F]{1,4}:){1,7}:|\b(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[IPv6]",
        "weight": 3,
    },
    {
        "id": "mac",
        "name": "MAC Address",
        "category": "network",
        "pattern": r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[MAC]",
        "weight": 3,
    },
    {
        "id": "url",
        "name": "URL",
        "category": "network",
        "pattern": r"https?://[^\s\"'<>\)]+",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[URL]",
        "weight": 2,
    },
    {
        "id": "hostname",
        "name": "Hostname",
        "category": "network",
        "pattern": r"\b(?:sles?|suse|linux|server|host|node|vm|container)[-_]?[a-zA-Z0-9]+[-_]?[a-zA-Z0-9]*\b",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[HOSTNAME]",
        "weight": 2,
    },
    # ── PII ──
    {
        "id": "email",
        "name": "Email Address",
        "category": "pii",
        "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[EMAIL]",
        "weight": 5,
    },
    {
        "id": "phone",
        "name": "Phone Number",
        "category": "pii",
        "pattern": r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[PHONE]",
        "weight": 5,
    },
    {
        "id": "id_card",
        "name": "ID Card (China)",
        "category": "pii",
        "pattern": r"\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b",
        "flags": "",
        "strategy": "partial",
        "placeholder": "[ID_CARD]",
        "weight": 10,
    },
    {
        "id": "credit_card",
        "name": "Credit Card Number",
        "category": "pii",
        "pattern": r"\b(?:4\d{3}|5[1-5]\d{2}|6011|3[47]\d{2})[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
        "flags": "",
        "strategy": "partial",
        "placeholder": "[CREDIT_CARD]",
        "weight": 10,
    },
    {
        "id": "path_user",
        "name": "Path Username",
        "category": "pii",
        "pattern": r"/home/([a-zA-Z0-9_-]+)",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "/home/[USER]",
        "weight": 2,
    },
    {
        "id": "username",
        "name": "Username Pattern",
        "category": "pii",
        "pattern": r"\b(?:user|admin|root|operator)[=:\s]+([a-zA-Z0-9_-]+)\b",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[USERNAME]",
        "weight": 4,
    },
    # ── Credentials ──
    {
        "id": "password",
        "name": "Password Field",
        "category": "credential",
        "pattern": r"(?i)(?:password|passwd|pwd|pass)\s*[=:]\s*\S+",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[PASSWORD]",
        "weight": 10,
    },
    {
        "id": "api_key_pattern",
        "name": "API Key / Token",
        "category": "credential",
        "pattern": r"(?i)(?:api[_-]?key|token|secret|access[_-]?key)\s*[=:]\s*['\"]?\S{8,}['\"]?",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[API_KEY]",
        "weight": 10,
    },
    {
        "id": "private_key",
        "name": "Private Key Block",
        "category": "credential",
        "pattern": r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[PRIVATE_KEY]",
        "weight": 10,
    },
    {
        "id": "jwt",
        "name": "JWT Token",
        "category": "credential",
        "pattern": r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[JWT]",
        "weight": 8,
    },
    {
        "id": "ssh_pub_key",
        "name": "SSH Public Key",
        "category": "credential",
        "pattern": r"ssh-(?:rsa|ed25519|dss|ecdsa)\s+AAAA[A-Za-z0-9+/=]{20,}",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[SSH_KEY]",
        "weight": 7,
    },
    {
        "id": "bearer_token",
        "name": "Bearer Token",
        "category": "credential",
        "pattern": r"Bearer\s+[A-Za-z0-9_\-.~+/]+=*",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[BEARER_TOKEN]",
        "weight": 9,
    },
    {
        "id": "license",
        "name": "License Key",
        "category": "credential",
        "pattern": r"\b[A-Z0-9]{4,5}(?:-[A-Z0-9]{4,5}){2,}\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[LICENSE]",
        "weight": 10,
    },
    # ── SUSE-specific ──
    {
        "id": "bsc_number",
        "name": "Bugzilla BSC#",
        "category": "suse",
        "pattern": r"\b(?:bsc|boo|bnc|fate)#\d{5,}\b",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[BSC]",
        "weight": 1,
    },
    {
        "id": "scc_regcode",
        "name": "SCC Registration Code",
        "category": "suse",
        "pattern": r"(?:regcode|registration\s*code|scc)\s*[=:]\s*[A-Za-z0-9-]{10,}",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[SCC_REGCODE]",
        "weight": 8,
    },
    {
        "id": "zypper_repo_url",
        "name": "Zypper Repo URL with Credentials",
        "category": "suse",
        "pattern": r"https?://[^:/?#\s]+:[^@\s]+@[^\s\"'<>]+",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[REPO_URL_AUTH]",
        "weight": 9,
    },
    {
        "id": "smt_rmt_url",
        "name": "SMT/RMT Server URL",
        "category": "suse",
        "pattern": r"https?://(?:smt|rmt|scc|suseconnect|updates?)[.\-][^\s\"'<>]+",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[SMT_URL]",
        "weight": 4,
    },
    {
        "id": "suse_connect_key",
        "name": "SUSEConnect Activation Key",
        "category": "suse",
        "pattern": r"(?:activate|registration_key|addon_key)\s*[=:]\s*[A-Za-z0-9_-]{10,}",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[ACTIVATION_KEY]",
        "weight": 8,
    },
    {
        "id": "autoyast_password",
        "name": "AutoYaST Password Hash",
        "category": "suse",
        "pattern": r"<user_password[^>]*>[^<]+</user_password>",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "<user_password>[HASH]</user_password>",
        "weight": 10,
    },
    {
        "id": "autoyast_encrypted",
        "name": "AutoYaST Encrypted Field",
        "category": "suse",
        "pattern": r"<encrypted[^>]*>[^<]+</encrypted>",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "<encrypted>[MASKED]</encrypted>",
        "weight": 10,
    },
    {
        "id": "salt_master_key",
        "name": "Salt Master/Minion Key",
        "category": "suse",
        "pattern": r"-----BEGIN RSA (?:PUBLIC|PRIVATE) KEY-----[\s\S]{20,}?-----END RSA (?:PUBLIC|PRIVATE) KEY-----",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[SALT_KEY]",
        "weight": 10,
    },
    {
        "id": "suma_api_token",
        "name": "SUSE Manager API Session Key",
        "category": "suse",
        "pattern": r"(?:session_key|sessionkey|SUMA[_-]?API[_-]?KEY)\s*[=:]\s*[A-Za-z0-9]{16,}",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[SUMA_TOKEN]",
        "weight": 9,
    },
    {
        "id": "supportconfig_filename",
        "name": "Supportconfig Filename (contains hostname)",
        "category": "suse",
        "pattern": r"\bnts_[a-zA-Z0-9._-]+_\d{6}_\d{4}(?:\.txz|\.tgz|\.tar\.xz|\.tar\.gz)?\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[SUPPORTCONFIG_FILE]",
        "weight": 3,
    },
    {
        "id": "zypper_cookie",
        "name": "Zypper Anonymous ID / Cookie",
        "category": "suse",
        "pattern": r"(?:AnonymousUniqueId|zypp\.conf\.credentials)\s*[=:]\s*\S+",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[ZYPPER_ID]",
        "weight": 4,
    },
    # ── Linux System / supportconfig patterns ──
    {
        "id": "fqdn",
        "name": "Fully Qualified Domain Name",
        "category": "network",
        "pattern": r"(?<!iqn\.\d{4}-\d{2}\.)\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.){2,}(?:com|net|org|io|de|cn|local|internal|intranet|corp|lan)\b",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[FQDN]",
        "weight": 3,
    },
    {
        "id": "nfs_mount",
        "name": "NFS Mount (server:/path)",
        "category": "network",
        "pattern": r"\b[a-zA-Z0-9._-]+:/(?:[a-zA-Z0-9._/-]+){2,}",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[NFS_MOUNT]",
        "weight": 3,
    },
    {
        "id": "iscsi_iqn",
        "name": "iSCSI IQN",
        "category": "network",
        "pattern": r"\biqn\.\d{4}-\d{2}\.[a-zA-Z0-9._:-]+\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[ISCSI_IQN]",
        "weight": 4,
    },
    {
        "id": "proxy_auth_url",
        "name": "Proxy URL with Credentials",
        "category": "credential",
        "pattern": r"(?:https?|socks[45])://[^:/?#\s]+:[^@\s]+@[^\s\"'<>]+",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[PROXY_AUTH_URL]",
        "weight": 10,
    },
    {
        "id": "shadow_hash",
        "name": "/etc/shadow Password Hash",
        "category": "credential",
        "pattern": r"\$(?:1|2[aby]?|5|6|y)\$[A-Za-z0-9./+$]{8,}",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[SHADOW_HASH]",
        "weight": 10,
    },
    {
        "id": "ldap_bind_dn",
        "name": "LDAP Bind DN",
        "category": "credential",
        "pattern": r"(?:bind_?dn|rootdn|binddn)\s*[=:]\s*\S+",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[LDAP_BIND_DN]",
        "weight": 6,
    },
    {
        "id": "ldap_bind_pw",
        "name": "LDAP Bind Password",
        "category": "credential",
        "pattern": r"(?:bind_?pw|rootpw|bindpw|ldap_password)\s*[=:]\s*\S+",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[LDAP_PASSWORD]",
        "weight": 10,
    },
    {
        "id": "db_connection_string",
        "name": "Database Connection String",
        "category": "credential",
        "pattern": r"(?:mysql|postgresql|postgres|mongodb|mariadb|mssql)://[^\s\"'<>]+",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[DB_CONN]",
        "weight": 10,
    },
    {
        "id": "snmp_community",
        "name": "SNMP Community String",
        "category": "credential",
        "pattern": r"(?:community|rocommunity|rwcommunity)\s+\S+",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[SNMP_COMMUNITY]",
        "weight": 8,
    },
    {
        "id": "wifi_psk",
        "name": "WiFi / WPA PSK",
        "category": "credential",
        "pattern": r"(?:wpa[_-]?passphrase|psk|pre[_-]?shared[_-]?key)\s*[=:]\s*\S+",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[WIFI_PSK]",
        "weight": 9,
    },
    {
        "id": "kerberos_principal",
        "name": "Kerberos Principal",
        "category": "credential",
        "pattern": r"\b[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+@[A-Z0-9._-]+\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[KRB_PRINCIPAL]",
        "weight": 5,
    },
    {
        "id": "aws_access_key",
        "name": "AWS Access Key ID",
        "category": "credential",
        "pattern": r"\bAKIA[0-9A-Z]{16}\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[AWS_KEY]",
        "weight": 10,
    },
    {
        "id": "aws_secret_key",
        "name": "AWS Secret Access Key",
        "category": "credential",
        "pattern": r"(?:aws_secret_access_key|AWS_SECRET)\s*[=:]\s*[A-Za-z0-9/+=]{40}",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[AWS_SECRET]",
        "weight": 10,
    },
    {
        "id": "uuid",
        "name": "UUID (System/Device Identifier)",
        "category": "system",
        "pattern": r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[UUID]",
        "weight": 2,
    },
    {
        "id": "serial_number",
        "name": "Hardware Serial Number",
        "category": "system",
        "pattern": r"(?:serial\s*(?:number)?|S/N|SN|DMI[:\s])\s*[=:]\s*[A-Za-z0-9-]{6,}",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[SERIAL]",
        "weight": 4,
    },
    {
        "id": "bios_uuid",
        "name": "BIOS/DMI UUID",
        "category": "system",
        "pattern": r"(?:BIOS|DMI|Product|System)\s*UUID\s*[=:]\s*[0-9A-Fa-f-]{36}",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[BIOS_UUID]",
        "weight": 4,
    },
    {
        "id": "wwn",
        "name": "World Wide Name (SAN/FC)",
        "category": "system",
        "pattern": r"(?:wwn|wwpn|wwnn|target_naa|naa)[=:\s]+(?:0x)?[0-9a-fA-F]{16}\b",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[WWN]",
        "weight": 3,
    },
    {
        "id": "docker_registry_auth",
        "name": "Docker Registry Auth",
        "category": "credential",
        "pattern": r'"auth"\s*:\s*"[A-Za-z0-9+/=]{20,}"',
        "flags": "",
        "strategy": "placeholder",
        "placeholder": '"auth":"[DOCKER_AUTH]"',
        "weight": 9,
    },
    {
        "id": "k8s_secret_data",
        "name": "Kubernetes Secret Data (base64)",
        "category": "credential",
        "pattern": r"(?:^|\s)(?:data|stringData):\s*\n(?:\s+[a-zA-Z0-9._-]+:\s*[A-Za-z0-9+/=]{16,}\s*\n?)+",
        "flags": "MULTILINE",
        "strategy": "placeholder",
        "placeholder": "[K8S_SECRET]",
        "weight": 10,
    },
    {
        "id": "k8s_service_token",
        "name": "Kubernetes Service Account Token",
        "category": "credential",
        "pattern": r"/var/run/secrets/kubernetes\.io/serviceaccount/token",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[K8S_TOKEN_PATH]",
        "weight": 5,
    },
    {
        "id": "ssl_cert_fingerprint",
        "name": "SSL Certificate Fingerprint",
        "category": "system",
        "pattern": r"(?:SHA[\-]?(?:1|256|384|512)?\s*(?:Fingerprint|Digest))\s*[=:]\s*(?:[0-9A-Fa-f]{2}:){15,}[0-9A-Fa-f]{2}",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[CERT_FINGERPRINT]",
        "weight": 4,
    },
    {
        "id": "gpg_key_id",
        "name": "GPG Key ID",
        "category": "system",
        "pattern": r"\b(?:0x)?[0-9A-Fa-f]{8,16}\b(?=.*(?:gpg|GPG|PGP|key|KEY))",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[GPG_KEY]",
        "weight": 3,
    },
    {
        "id": "env_secret",
        "name": "Environment Variable Secret",
        "category": "credential",
        "pattern": r"(?:export\s+)?[A-Z_]*(?:SECRET|PASSWORD|TOKEN|APIKEY|API_KEY|CREDENTIALS?|AUTH)[A-Z_]*\s*=\s*['\"]?[^\s'\"]{4,}['\"]?",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[ENV_SECRET]",
        "weight": 9,
    },
    {
        "id": "connection_auth",
        "name": "Generic Connection Auth (user:pass@host)",
        "category": "credential",
        "pattern": r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^:/?#\s]+:[^@/?#\s]+@[^\s\"'<>]+",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[CONN_AUTH]",
        "weight": 10,
    },
    # ── Cloud Provider Tokens (from supportutils-scrub) ──
    {
        "id": "aws_temp_key",
        "name": "AWS Temporary Access Key (ASIA)",
        "category": "credential",
        "pattern": r"\bASIA[0-9A-Z]{16}\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[AWS_TEMP_KEY]",
        "weight": 10,
    },
    {
        "id": "aws_session_token",
        "name": "AWS Session Token / Secret Value",
        "category": "credential",
        "pattern": r"(?i)(?:aws_session_token|SessionToken|aws_secret_access_key|SecretAccessKey)\s*[=:]\s*[\"']?([A-Za-z0-9+/=_-]{20,})",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[AWS_SESSION]",
        "weight": 10,
    },
    {
        "id": "azure_account_key",
        "name": "Azure Storage Account Key",
        "category": "credential",
        "pattern": r"(?i)AccountKey\s*=\s*[A-Za-z0-9+/=]{20,}",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[AZURE_KEY]",
        "weight": 10,
    },
    {
        "id": "azure_sas_token",
        "name": "Azure SAS Token Parameters",
        "category": "credential",
        "pattern": r"[?&](?:sig|sv|se|sp|spr|srt|ss)=[A-Za-z0-9%+/=]{20,}",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[AZURE_SAS]",
        "weight": 9,
    },
    {
        "id": "azure_connection_string",
        "name": "Azure Connection String",
        "category": "credential",
        "pattern": r"(?i)(?:DefaultEndpointsProtocol|AccountName|AccountKey|EndpointSuffix)\s*=[^\s;]{4,}(?:;(?:DefaultEndpointsProtocol|AccountName|AccountKey|EndpointSuffix)\s*=[^\s;]{4,})+",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[AZURE_CONN_STR]",
        "weight": 10,
    },
    {
        "id": "gcp_private_key_json",
        "name": "GCP Service Account Private Key (JSON)",
        "category": "credential",
        "pattern": r'"private_key"\s*:\s*"-----BEGIN[^"]+-----"',
        "flags": "",
        "strategy": "placeholder",
        "placeholder": '"private_key":"[GCP_PRIVATE_KEY]"',
        "weight": 10,
    },
    {
        "id": "gcp_service_account",
        "name": "GCP Service Account Email",
        "category": "credential",
        "pattern": r"\b[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.iam\.gserviceaccount\.com\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[GCP_SA]",
        "weight": 7,
    },
    {
        "id": "x_auth_token",
        "name": "X-Auth-Token / Authorization Header",
        "category": "credential",
        "pattern": r"(?i)(?:X-Auth-Token|Authorization)\s*[:=]\s*(?:Bearer\s+)?[\"']?[A-Za-z0-9._+/=-]{40,}",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[AUTH_TOKEN]",
        "weight": 9,
    },
    {
        "id": "identity_tag",
        "name": "Identity Tag with Token",
        "category": "credential",
        "pattern": r"(?:<identity>|identity:\s*)eyJ[A-Za-z0-9_+/=-]{20,}",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[IDENTITY_TOKEN]",
        "weight": 8,
    },
    # ── LDAP / Directory (from supportutils-scrub) ──
    {
        "id": "ldap_dn_dc",
        "name": "LDAP Distinguished Name (DC= format)",
        "category": "credential",
        "pattern": r"DC=[A-Za-z0-9-]+(?:,DC=[A-Za-z0-9-]+)+",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[LDAP_DN]",
        "weight": 5,
    },
    {
        "id": "ldap_dn_full",
        "name": "LDAP Full DN (CN=...,OU=...,DC=...)",
        "category": "credential",
        "pattern": r"(?:CN|OU|UID)=[^,\s]+(?:,(?:CN|OU|DC|O|L|ST|C)=[^,\s]+){2,}",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[LDAP_FULL_DN]",
        "weight": 5,
    },
    # ── Certificate / Key Blocks ──
    {
        "id": "certificate_block",
        "name": "X.509 Certificate Block",
        "category": "credential",
        "pattern": r"-----BEGIN CERTIFICATE-----[\s\S]{20,}?-----END CERTIFICATE-----",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[CERTIFICATE]",
        "weight": 8,
    },
    {
        "id": "private_key_block",
        "name": "Private Key Block (full PEM)",
        "category": "credential",
        "pattern": r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----[\s\S]{20,}?-----END (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[PRIVATE_KEY_BLOCK]",
        "weight": 10,
    },
    # ── Hardware / dmidecode (from supportutils-scrub serial_scrubber) ──
    {
        "id": "asset_tag",
        "name": "Asset Tag (dmidecode)",
        "category": "system",
        "pattern": r"(?i)Asset\s+Tag\s*:\s*(?!Not Specified|Not Present|Unknown|N/A|None|No Asset)\S[^\n]*",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "Asset Tag: [ASSET_TAG]",
        "weight": 4,
    },
    {
        "id": "part_number",
        "name": "Part Number (dmidecode)",
        "category": "system",
        "pattern": r"(?i)Part\s+Number\s*:\s*(?!Not Specified|Not Present|Unknown|N/A|None)\S[^\n]*",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "Part Number: [PART_NUMBER]",
        "weight": 3,
    },
    {
        "id": "product_serial",
        "name": "Product/Chassis Serial (dmidecode)",
        "category": "system",
        "pattern": r"(?i)(?:Chassis|System|Base\s+Board)\s+Serial\s+Number\s*:\s*(?!Not Specified|Not Present|Unknown|N/A|None)\S[^\n]*",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[PRODUCT_SERIAL]",
        "weight": 5,
    },
    # ── SUSE Ecosystem (Rancher / Longhorn / Corosync / SAP) ──
    {
        "id": "rancher_token",
        "name": "Rancher API / Bearer Token",
        "category": "suse",
        "pattern": r"token-[a-z0-9]{5}:[a-z0-9]{20,}",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[RANCHER_TOKEN]",
        "weight": 10,
    },
    {
        "id": "rancher_cluster_reg",
        "name": "Rancher Cluster Registration Token",
        "category": "suse",
        "pattern": r"(?:clusterregistrationtoken|cluster-registration-token|CATTLE_TOKEN)\s*[=:]\s*\S{10,}",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[RANCHER_REG_TOKEN]",
        "weight": 9,
    },
    {
        "id": "corosync_authkey",
        "name": "Corosync / Pacemaker Authkey",
        "category": "suse",
        "pattern": r"(?:/etc/corosync/authkey|corosync-keygen|COROSYNC_AUTHKEY)\b[^\n]*",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[COROSYNC_AUTH]",
        "weight": 7,
    },
    {
        "id": "drbd_shared_secret",
        "name": "DRBD Shared Secret",
        "category": "suse",
        "pattern": r"(?i)shared-secret\s+\"[^\"]+\"",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": 'shared-secret "[DRBD_SECRET]"',
        "weight": 9,
    },
    {
        "id": "sap_hana_credential",
        "name": "SAP HANA / NetWeaver Credential",
        "category": "suse",
        "pattern": r"(?i)(?:HANA_?PASSWORD|SAP_?PASSWORD|MASTER_?PASSWORD|SYSTEM_?PASSWORD|SAPDBHOST_?PASSWORD)\s*[=:]\s*\S+",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[SAP_PASSWORD]",
        "weight": 10,
    },
    {
        "id": "sap_sid",
        "name": "SAP System ID + Instance Number",
        "category": "suse",
        "pattern": r"\b(?:SID|sap_sid|SAPSYSTEMNAME)\s*[=:]\s*[A-Z][A-Z0-9]{2}\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[SAP_SID]",
        "weight": 4,
    },
    {
        "id": "supportconfig_removed",
        "name": "Supportconfig REMOVED marker",
        "category": "suse",
        "pattern": r"\*REMOVED BY SUPPORTCONFIG\*",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[ALREADY_MASKED]",
        "weight": 0,
        "enabled": False,
    },
    {
        "id": "kube_config_token",
        "name": "Kubeconfig Token / Client Certificate Data",
        "category": "credential",
        "pattern": r"(?i)(?:client-certificate-data|client-key-data|token)\s*:\s*[A-Za-z0-9+/=_-]{40,}",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[KUBE_TOKEN]",
        "weight": 10,
    },
    {
        "id": "helm_secret",
        "name": "Helm / Chart Secret Value",
        "category": "credential",
        "pattern": r"(?i)(?:helm\.sh/release\.v1|release-secret)\s*[=:]\s*[A-Za-z0-9+/=]{20,}",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[HELM_SECRET]",
        "weight": 8,
    },
    {
        "id": "github_token",
        "name": "GitHub Personal Access Token",
        "category": "credential",
        "pattern": r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[GITHUB_TOKEN]",
        "weight": 10,
    },
    {
        "id": "generic_secret_header",
        "name": "Generic Secret in Config Header",
        "category": "credential",
        "pattern": r"(?i)(?:secret_key|client_secret|shared_secret|encryption_key|signing_key|hmac_key)\s*[=:]\s*[\"']?[A-Za-z0-9+/=_-]{8,}[\"']?",
        "flags": "IGNORECASE",
        "strategy": "placeholder",
        "placeholder": "[SECRET_KEY]",
        "weight": 9,
    },
]


def seed_builtin_rules():
    """
    Insert built-in rules into DB if they don't already exist.
    Existing rules are NOT overwritten — admin edits are preserved.
    """
    conn = _get_conn()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()

    inserted = 0
    for rule in BUILTIN_RULES:
        cursor.execute("SELECT id FROM rules WHERE id = ?", (rule["id"],))
        if cursor.fetchone() is None:
            cursor.execute(
                """INSERT INTO rules
                   (id, name, category, pattern, flags, strategy, placeholder,
                    weight, enabled, is_builtin, version, created_at, updated_at, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 1, ?, ?, 'system')""",
                (
                    rule["id"], rule["name"], rule["category"],
                    rule["pattern"], rule.get("flags", ""),
                    rule["strategy"], rule["placeholder"],
                    rule["weight"], now, now
                )
            )
            inserted += 1

    conn.commit()
    logger.info(f"Seeded {inserted} built-in rules (total built-in: {len(BUILTIN_RULES)})")


# ─── Rule CRUD ─────────────────────────────────────────────────────────────────

def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert sqlite3.Row to plain dict."""
    return dict(row)


def list_rules(
    category: Optional[str] = None,
    enabled_only: bool = False
) -> List[dict]:
    """List rules, optionally filtered by category or enabled status."""
    conn = _get_conn()
    sql = "SELECT * FROM rules WHERE 1=1"
    params: list = []

    if category:
        sql += " AND category = ?"
        params.append(category)
    if enabled_only:
        sql += " AND enabled = 1"

    sql += " ORDER BY category, weight DESC, id"
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_rule(rule_id: str) -> Optional[dict]:
    """Get a single rule by ID."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
    return _row_to_dict(row) if row else None


def create_rule(data: dict, created_by: str = "admin") -> dict:
    """
    Insert a new rule. Raises ValueError on duplicate ID or invalid regex.
    """
    import re as _re

    rule_id = data["id"]
    # Validate ID uniqueness
    if get_rule(rule_id):
        raise ValueError(f"Rule '{rule_id}' already exists")

    # Validate regex
    try:
        flags = _parse_flags(data.get("flags", ""))
        _re.compile(data["pattern"], flags)
    except _re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}")

    conn = _get_conn()
    now = datetime.utcnow().isoformat()
    conn.execute(
        """INSERT INTO rules
           (id, name, category, pattern, flags, strategy, placeholder,
            weight, enabled, is_builtin, version, created_at, updated_at, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?, ?)""",
        (
            rule_id, data["name"], data.get("category", "custom"),
            data["pattern"], data.get("flags", ""),
            data.get("strategy", "placeholder"),
            data.get("placeholder", "[MASKED]"),
            data.get("weight", 5),
            1 if data.get("enabled", True) else 0,
            now, now, created_by
        )
    )
    conn.commit()

    rule = get_rule(rule_id)
    _log_change(rule_id, "create", None, rule, created_by)
    return rule


def update_rule(rule_id: str, data: dict, changed_by: str = "admin") -> dict:
    """
    Update an existing rule. Returns updated dict.
    Raises ValueError if not found or invalid regex.
    """
    import re as _re

    old = get_rule(rule_id)
    if not old:
        raise ValueError(f"Rule '{rule_id}' not found")

    # Validate regex if pattern is being changed
    pattern = data.get("pattern", old["pattern"])
    flags_str = data.get("flags", old["flags"])
    try:
        flags = _parse_flags(flags_str)
        _re.compile(pattern, flags)
    except _re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}")

    conn = _get_conn()
    now = datetime.utcnow().isoformat()
    conn.execute(
        """UPDATE rules SET
            name = ?, category = ?, pattern = ?, flags = ?,
            strategy = ?, placeholder = ?, weight = ?, enabled = ?,
            version = version + 1, updated_at = ?
           WHERE id = ?""",
        (
            data.get("name", old["name"]),
            data.get("category", old["category"]),
            pattern, flags_str,
            data.get("strategy", old["strategy"]),
            data.get("placeholder", old["placeholder"]),
            data.get("weight", old["weight"]),
            1 if data.get("enabled", old["enabled"]) else 0,
            now, rule_id
        )
    )
    conn.commit()

    new = get_rule(rule_id)
    _log_change(rule_id, "update", old, new, changed_by)
    return new


def toggle_rule(rule_id: str, changed_by: str = "admin") -> dict:
    """Toggle enabled/disabled. Returns updated rule."""
    old = get_rule(rule_id)
    if not old:
        raise ValueError(f"Rule '{rule_id}' not found")

    new_enabled = 0 if old["enabled"] else 1
    conn = _get_conn()
    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE rules SET enabled = ?, version = version + 1, updated_at = ? WHERE id = ?",
        (new_enabled, now, rule_id)
    )
    conn.commit()

    new = get_rule(rule_id)
    _log_change(rule_id, "toggle", old, new, changed_by)
    return new


def delete_rule(rule_id: str, changed_by: str = "admin") -> bool:
    """
    Delete a custom rule. Built-in rules cannot be deleted (use toggle instead).
    Returns True if deleted.
    """
    old = get_rule(rule_id)
    if not old:
        raise ValueError(f"Rule '{rule_id}' not found")
    if old["is_builtin"]:
        raise ValueError(f"Built-in rule '{rule_id}' cannot be deleted. Use toggle to disable it.")

    conn = _get_conn()
    conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
    conn.commit()

    _log_change(rule_id, "delete", old, None, changed_by)
    return True


# ─── Suggestions (User Feedback Channel) ──────────────────────────────────────

def create_suggestion(data: dict, submitted_by: str = "anonymous") -> dict:
    """Submit a rule suggestion from a user."""
    conn = _get_conn()
    cursor = conn.execute(
        """INSERT INTO rule_suggestions
           (rule_id, action, name, category, pattern, flags, strategy,
            placeholder, weight, reason, submitted_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("rule_id"),
            data["action"],
            data.get("name"),
            data.get("category"),
            data.get("pattern"),
            data.get("flags"),
            data.get("strategy"),
            data.get("placeholder"),
            data.get("weight"),
            data.get("reason", ""),
            submitted_by,
        )
    )
    conn.commit()
    return get_suggestion(cursor.lastrowid)


def get_suggestion(suggestion_id: int) -> Optional[dict]:
    """Get a suggestion by ID."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM rule_suggestions WHERE id = ?", (suggestion_id,)
    ).fetchone()
    return _row_to_dict(row) if row else None


def list_suggestions(
    status: Optional[str] = None,
    submitted_by: Optional[str] = None
) -> List[dict]:
    """List suggestions with optional filters."""
    conn = _get_conn()
    sql = "SELECT * FROM rule_suggestions WHERE 1=1"
    params: list = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if submitted_by:
        sql += " AND submitted_by = ?"
        params.append(submitted_by)
    sql += " ORDER BY submitted_at DESC"
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def review_suggestion(
    suggestion_id: int,
    action: str,
    reviewed_by: str = "admin"
) -> dict:
    """
    Approve or reject a suggestion.
    If approved, the rule is created/modified/disabled accordingly.
    """
    suggestion = get_suggestion(suggestion_id)
    if not suggestion:
        raise ValueError(f"Suggestion {suggestion_id} not found")
    if suggestion["status"] != "pending":
        raise ValueError(f"Suggestion already {suggestion['status']}")

    conn = _get_conn()
    now = datetime.utcnow().isoformat()

    if action == "approve":
        # Apply the suggestion
        _apply_suggestion(suggestion, reviewed_by)
        conn.execute(
            "UPDATE rule_suggestions SET status='approved', reviewed_by=?, reviewed_at=? WHERE id=?",
            (reviewed_by, now, suggestion_id)
        )
    elif action == "reject":
        conn.execute(
            "UPDATE rule_suggestions SET status='rejected', reviewed_by=?, reviewed_at=? WHERE id=?",
            (reviewed_by, now, suggestion_id)
        )
    else:
        raise ValueError(f"Invalid action: {action}. Use 'approve' or 'reject'.")

    conn.commit()
    return get_suggestion(suggestion_id)


def _apply_suggestion(suggestion: dict, reviewed_by: str):
    """Apply an approved suggestion to the rules table."""
    if suggestion["action"] == "create":
        create_rule({
            "id": suggestion.get("rule_id") or f"custom_{suggestion['id']}",
            "name": suggestion["name"] or "Unnamed Rule",
            "category": suggestion.get("category") or "custom",
            "pattern": suggestion["pattern"],
            "flags": suggestion.get("flags") or "",
            "strategy": suggestion.get("strategy") or "placeholder",
            "placeholder": suggestion.get("placeholder") or "[MASKED]",
            "weight": suggestion.get("weight") or 5,
            "enabled": True,
        }, created_by=reviewed_by)
    elif suggestion["action"] == "modify" and suggestion["rule_id"]:
        # Only update fields that are provided
        update_data = {}
        for key in ("name", "category", "pattern", "flags", "strategy", "placeholder", "weight"):
            if suggestion.get(key) is not None:
                update_data[key] = suggestion[key]
        if update_data:
            update_rule(suggestion["rule_id"], update_data, changed_by=reviewed_by)
    elif suggestion["action"] == "disable" and suggestion["rule_id"]:
        rule = get_rule(suggestion["rule_id"])
        if rule and rule["enabled"]:
            toggle_rule(suggestion["rule_id"], changed_by=reviewed_by)


# ─── Import / Export ───────────────────────────────────────────────────────────

def export_rules() -> List[dict]:
    """Export all rules as a plain list of dicts (for JSON download)."""
    return list_rules()


def import_rules(rules_data: List[dict], imported_by: str = "admin") -> dict:
    """
    Bulk import rules from a JSON list.
    - Existing IDs → update
    - New IDs → create
    Returns summary: {created: N, updated: N, errors: [...]}
    """
    created = 0
    updated = 0
    errors = []

    for item in rules_data:
        try:
            rule_id = item.get("id")
            if not rule_id:
                errors.append({"item": item, "error": "Missing 'id' field"})
                continue
            existing = get_rule(rule_id)
            if existing:
                update_rule(rule_id, item, changed_by=imported_by)
                updated += 1
            else:
                create_rule(item, created_by=imported_by)
                created += 1
        except Exception as e:
            errors.append({"id": item.get("id"), "error": str(e)})

    return {"created": created, "updated": updated, "errors": errors}


# ─── Changelog ─────────────────────────────────────────────────────────────────

def list_changelog(rule_id: Optional[str] = None, limit: int = 50) -> List[dict]:
    """List recent changelog entries."""
    conn = _get_conn()
    sql = "SELECT * FROM rule_changelog"
    params: list = []
    if rule_id:
        sql += " WHERE rule_id = ?"
        params.append(rule_id)
    sql += " ORDER BY changed_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def _log_change(
    rule_id: str,
    action: str,
    old_value: Optional[dict],
    new_value: Optional[dict],
    changed_by: str
):
    """Write a changelog entry."""
    conn = _get_conn()
    conn.execute(
        """INSERT INTO rule_changelog (rule_id, action, old_value, new_value, changed_by)
           VALUES (?, ?, ?, ?, ?)""",
        (
            rule_id,
            action,
            json.dumps(old_value, ensure_ascii=False) if old_value else None,
            json.dumps(new_value, ensure_ascii=False) if new_value else None,
            changed_by,
        )
    )
    conn.commit()


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _parse_flags(flags_str: str) -> int:
    """Parse a flag string like 'IGNORECASE' into re flags integer."""
    import re as _re
    if not flags_str:
        return 0
    flag_map = {
        "IGNORECASE": _re.IGNORECASE,
        "MULTILINE": _re.MULTILINE,
        "DOTALL": _re.DOTALL,
        "VERBOSE": _re.VERBOSE,
    }
    result = 0
    for part in flags_str.upper().split("|"):
        part = part.strip()
        if part in flag_map:
            result |= flag_map[part]
    return result
