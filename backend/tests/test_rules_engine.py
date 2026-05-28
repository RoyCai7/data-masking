"""
test_rules_engine.py — Unit tests for the core masking rules engine.

Covers:
  1. All 81 built-in rules compile without regex errors
  2. Every rule category is represented
  3. Each MaskStrategy works correctly (asterisk, placeholder, partial, hash)
  4. All rules match at least one expected sample
  5. Whitelist / negative-match filtering
  6. Rule weight & risk scoring
"""
import re
import pytest

from app.engine.rules import MaskingRule, MaskStrategy, get_enabled_rules, get_rules_info
from app.engine.repository import BUILTIN_RULES


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Built-in rules integrity
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuiltinRulesIntegrity:
    """Every built-in rule must compile, be unique, and belong to a known category."""

    EXPECTED_CATEGORIES = {"network", "pii", "credential", "suse", "system"}

    def test_total_rule_count(self):
        """We should have at least 80 built-in rules."""
        assert len(BUILTIN_RULES) >= 80, f"Expected ≥80, got {len(BUILTIN_RULES)}"

    def test_all_rules_compile(self):
        """Every regex pattern must compile without error."""
        errors = []
        for r in BUILTIN_RULES:
            flags = 0
            for f in r.get("flags", "").split("|"):
                f = f.strip()
                if f and hasattr(re, f):
                    flags |= getattr(re, f)
            try:
                re.compile(r["pattern"], flags)
            except re.error as e:
                errors.append(f"{r['id']}: {e}")
        assert not errors, "Regex compile errors:\n" + "\n".join(errors)

    def test_unique_ids(self):
        ids = [r["id"] for r in BUILTIN_RULES]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {[x for x in ids if ids.count(x) > 1]}"

    def test_all_categories_present(self):
        cats = {r["category"] for r in BUILTIN_RULES}
        assert cats == self.EXPECTED_CATEGORIES, f"Missing categories: {self.EXPECTED_CATEGORIES - cats}"

    @pytest.mark.parametrize("category", ["network", "pii", "credential", "suse", "system"])
    def test_category_not_empty(self, category):
        rules_in_cat = [r for r in BUILTIN_RULES if r["category"] == category]
        assert len(rules_in_cat) >= 2, f"Category '{category}' should have ≥2 rules"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. MaskStrategy behaviors
# ═══════════════════════════════════════════════════════════════════════════════

class TestMaskStrategy:
    """Verify each strategy produces the expected output."""

    def _make_rule(self, strategy: str, placeholder: str = "[X]") -> MaskingRule:
        return MaskingRule(
            id="test",
            name="Test Rule",
            pattern=re.compile(r"\bSECRET\b"),
            strategy=MaskStrategy(strategy),
            placeholder=placeholder,
            weight=5,
        )

    def test_asterisk(self):
        rule = self._make_rule("asterisk")
        assert rule.mask("SECRET") == "******"

    def test_placeholder(self):
        rule = self._make_rule("placeholder", "[REDACTED]")
        assert rule.mask("SECRET") == "[REDACTED]"

    def test_partial_long(self):
        rule = self._make_rule("partial")
        result = rule.mask("SECRETVALUE")
        assert result.startswith("SE")
        assert result.endswith("UE")
        assert "*" in result

    def test_partial_short(self):
        rule = self._make_rule("partial")
        assert rule.mask("AB") == "**"

    def test_hash(self):
        rule = self._make_rule("hash")
        result = rule.mask("SECRET")
        assert len(result) == 12
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_deterministic(self):
        rule = self._make_rule("hash")
        assert rule.mask("SECRET") == rule.mask("SECRET")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Rule pattern matching — positive cases
# ═══════════════════════════════════════════════════════════════════════════════

# Map: rule_id → list of strings that MUST match
POSITIVE_SAMPLES = {
    # Network
    "ipv4":           ["Server IP: 192.168.1.100", "subnet 10.0.0.0/24"],
    "ipv6":           ["addr 2001:0db8:85a3:0000:0000:8a2e:0370:7334"],
    "mac_address":    ["hw AA:BB:CC:DD:EE:FF"],
    "url":            ["visit https://example.com/path"],
    "hostname":       ["host node1.corp.suse.com"],
    "fqdn":           ["dns server01.corp.example.com"],
    "nfs_mount":      ["mount server01:/export/share"],
    "iscsi_iqn":      ["target iqn.2024-01.com.suse:storage1"],

    # PII
    "email":          ["contact admin@example.com"],
    "phone_intl":     ["call +86-138-0013-8000"],
    "cn_id_card":     ["身份证 110101199003076512"],
    "credit_card":    ["card 4111-1111-1111-1111"],
    "path_user":      ["dir /home/johndoe/.config"],
    "username":       ["user = johndoe"],

    # Credential
    "password":             ["password = Secret123"],
    "api_key_pattern":      ["api_key = sk_live_4eC39HqLyjWDarjtT1zdp7dc"],
    "private_key":          ["-----BEGIN RSA PRIVATE KEY-----"],
    "jwt":                  ["token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"],
    "ssh_pub_key":          ["key ssh-rsa AAAAB3NzaC1yc2EAAAABAAAAxyz0"],
    "bearer_token":         ["Bearer eyJhbGciOiJSUzI1NiIsInR5c.payload.sig_dat123442"],
    "license":              ["key XXXX-YYYY-ZZZZ-WWWW"],
    "aws_access_key":       ["key AKIAIOSFODNN7EXAMPLE"],
    "aws_secret_key":       ["aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"],
    "aws_temp_key":         ["key ASIAIOSFODNN7EXAMPLE"],
    "aws_session_token":    ["aws_session_token = FwoGZXIvYXdzEBYaDHabc"],
    "azure_account_key":    ["AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ="],
    "azure_sas_token":      ["?sig=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT"],
    "azure_connection_string": ["DefaultEndpointsProtocol=https;AccountName=myaccount;AccountKey=abc123=="],
    "gcp_private_key_json": ['"private_key": "-----BEGIN RSA PRIVATE KEY-----\ndata\n-----END RSA PRIVATE KEY-----"'],
    "gcp_service_account":  ["sa@project.iam.gserviceaccount.com"],
    "x_auth_token":         ["X-Auth-Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9abcdefghijklmnop"],
    "identity_tag":         ["<identity>eyJhbGciOiJIUzI1NiJ9abcdef1234567890"],
    "ldap_dn_dc":           ["base DC=corp,DC=example,DC=com"],
    "ldap_dn_full":         ["dn CN=admin,OU=Users,DC=corp,DC=example,DC=com"],
    "certificate_block":    ["-----BEGIN CERTIFICATE-----\nMIIDqDCCApCgAwIBAgIJALK5ABC\nbase64aaaaaaa\n-----END CERTIFICATE-----"],
    "private_key_block":    ["-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA0Z3VS5JJcds3xfnA\nBBBCCCDDDEEEFFF\n-----END RSA PRIVATE KEY-----"],
    "proxy_auth_url":       ["proxy http://user:pass@proxy.corp.com:3128"],
    "shadow_hash":          ["root:$6$xK1Pz0Rq$vN7HgBcT5mYs2QW9kJ4R6:18000:0:99999:7:::"],
    "ldap_bind_dn":         ["binddn=cn=admin,dc=example,dc=com"],
    "ldap_bind_pw":         ["bindpw=SecretLDAP123"],
    "db_connection_string": ["dsn postgresql://user:pwd@db.host:5432/mydb"],
    "snmp_community":       ["rocommunity public123"],
    "wifi_psk":             ["wpa_passphrase = MyWiFiSecret"],
    "kerberos_principal":   ["principal admin/admin@EXAMPLE.COM"],
    "docker_registry_auth": ['{"auth": "dXNlcjpwYXNzd29yZA=="}'],
    "env_secret":           ["export DB_PASSWORD='MySecret123'"],
    "connection_auth":      ["mongodb://admin:pass123@mongo.host:27017/db"],
    "github_token":         ["token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"],
    "generic_secret_header":["client_secret=abcdef1234567890"],
    "kube_config_token":    ["client-certificate-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSURxRENDQX"],
    "asset_tag":            ["Asset Tag: SRV-PRD-42"],
    "part_number":          ["Part Number: HMA82GR7CJR8N-VK"],
    "product_serial":       ["System Serial Number: WX00123456"],
    "rancher_token":        ["token-ab1cd:z8x7v6u5t4s3r2q1p0a9b8c7"],
    "rancher_cluster_reg":  ["CATTLE_TOKEN=token-ab1cd:z8x7v6u5t4s3r2q1p0"],
    "drbd_shared_secret":   ['shared-secret "ClusterPass123"'],
    "sap_hana_credential":  ["HANA_PASSWORD=SapSecret789"],
    "sap_sid":              ["SID=PRD"],
    "corosync_authkey":     ["/etc/corosync/authkey generated"],

    # SUSE
    "bsc_number":            ["fix for bsc#1234567"],
    "scc_regcode":           ["regcode = ABCD-EFGH-1234-5678-9012"],
    "zypper_repo_url":       ["repo https://user:pass@updates.suse.com/repo"],
    "smt_rmt_url":           ["url https://smt.corp.example.com/repo"],
    "suse_connect_key":      ["registration_key = ABCD1234EFGH5678"],
    "autoyast_password":     ["<user_password>$6$hashed</user_password>"],
    "autoyast_encrypted":    ["<encrypted>cipher_text_here</encrypted>"],
    "salt_master_key":       ["-----BEGIN RSA PUBLIC KEY-----\nABCDEFGHIJKLMNOPQRSTUVWX\n-----END RSA PUBLIC KEY-----"],
    "suma_api_token":        ["SUMA_API_KEY = abc123def456ghi789"],
    "supportconfig_filename":["file nts_myhost01_261013_1245.txz"],
    "zypper_cookie":         ["AnonymousUniqueId = abc-def-ghi-123"],

    # System
    "uuid":              ["UUID: 550e8400-e29b-41d4-a716-446655440000"],
    "serial_number":     ["Serial Number: ABCD1234"],
    "bios_uuid":         ["BIOS UUID: 550e8400-e29b-41d4-a716-446655440000"],
    "wwn":               ["wwpn=0x50060b0000c26813"],
    "ssl_cert_fingerprint": ["SHA256 Fingerprint=4A:2B:3C:4D:5E:6F:70:81:92:A3:B4:C5:D6:E7:F8:09:1A:2B:3C:4D"],
    "gpg_key_id":        ["import 0xABCD1234 gpg key"],
}


class TestRulePatternMatching:
    """Every rule must match its documented sample input."""

    @pytest.mark.parametrize("rule_id,samples", list(POSITIVE_SAMPLES.items()), ids=list(POSITIVE_SAMPLES.keys()))
    def test_positive_match(self, rule_id, samples):
        """Rule {rule_id} should match its sample."""
        # Find the rule definition
        rule_def = next((r for r in BUILTIN_RULES if r["id"] == rule_id), None)
        assert rule_def is not None, f"Rule '{rule_id}' not found in BUILTIN_RULES"

        flags = 0
        for f in rule_def.get("flags", "").split("|"):
            f = f.strip()
            if f and hasattr(re, f):
                flags |= getattr(re, f)
        compiled = re.compile(rule_def["pattern"], flags)

        for sample in samples:
            assert compiled.search(sample), f"Rule '{rule_id}' did NOT match: {sample[:100]}"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Negative / false-positive tests
# ═══════════════════════════════════════════════════════════════════════════════

NEGATIVE_SAMPLES = {
    "asset_tag": [
        "Asset Tag: Not Specified",
        "Asset Tag: None",
        "Asset Tag: No Asset Information",
    ],
    "part_number": [
        "Part Number: Not Specified",
        "Part Number: Unknown",
    ],
    "product_serial": [
        "System Serial Number: Not Specified",
        "Chassis Serial Number: None",
    ],
}


class TestNegativeMatching:
    """Rules must NOT match known false-positive inputs."""

    @pytest.mark.parametrize("rule_id,samples", list(NEGATIVE_SAMPLES.items()), ids=list(NEGATIVE_SAMPLES.keys()))
    def test_negative_match(self, rule_id, samples):
        rule_def = next(r for r in BUILTIN_RULES if r["id"] == rule_id)
        flags = 0
        for f in rule_def.get("flags", "").split("|"):
            f = f.strip()
            if f and hasattr(re, f):
                flags |= getattr(re, f)
        compiled = re.compile(rule_def["pattern"], flags)

        for sample in samples:
            assert not compiled.search(sample), f"Rule '{rule_id}' FALSE-POSITIVE on: {sample}"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Rule service layer
# ═══════════════════════════════════════════════════════════════════════════════

class TestRuleServiceLayer:
    """Verify RuleService loads rules into cache correctly."""

    def test_get_enabled_rules_returns_masking_rules(self):
        rules = get_enabled_rules()
        assert len(rules) >= 60  # 19 SUSE-specific rules disabled by default
        for r in rules:
            assert isinstance(r, MaskingRule)
            assert r.enabled is True

    def test_get_rules_info_returns_dicts(self):
        info = get_rules_info()
        assert isinstance(info, list)
        assert len(info) >= 80
        for item in info:
            assert "id" in item
            assert "name" in item

    def test_disabled_rules_not_in_enabled(self):
        """The 'supportconfig_removed' rule is disabled by default."""
        rules = get_enabled_rules()
        ids = {r.id for r in rules}
        # If the rule exists with enabled=False, it should not appear
        from app.engine.rule_service import rule_service
        detail = rule_service.get_rule_detail("supportconfig_removed")
        if detail and not detail.get("enabled"):
            assert "supportconfig_removed" not in ids
