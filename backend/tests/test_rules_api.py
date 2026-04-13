"""
test_rules_api.py — Tests for Rules Management API (/api/v1/rules/...).

Covers:
  1. List rules (public)
  2. Get single rule
  3. Create / Update / Delete (admin CRUD)
  4. Toggle enable/disable
  5. Import / Export
  6. Suggestions workflow (create → list → approve/reject)
  7. Changelog
  8. Error handling & validation
"""
import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 1. List Rules (public)
# ═══════════════════════════════════════════════════════════════════════════════

class TestListRules:

    @pytest.mark.asyncio
    async def test_list_all_rules(self, client):
        resp = await client.get("/api/v1/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert data["total"] >= 80
        assert isinstance(data["rules"], list)

    @pytest.mark.asyncio
    async def test_filter_by_category(self, client):
        resp = await client.get("/api/v1/rules?category=suse")
        assert resp.status_code == 200
        data = resp.json()
        for rule in data["rules"]:
            assert rule["category"] == "suse"

    @pytest.mark.asyncio
    async def test_filter_enabled_only(self, client):
        resp = await client.get("/api/v1/rules?enabled_only=true")
        assert resp.status_code == 200
        for rule in resp.json()["rules"]:
            assert rule["enabled"] == True


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Get Single Rule
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetRule:

    @pytest.mark.asyncio
    async def test_get_existing_rule(self, client):
        resp = await client.get("/api/v1/rules/ipv4")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "ipv4"
        assert data["name"] == "IPv4 Address"
        assert data["category"] == "network"

    @pytest.mark.asyncio
    async def test_get_nonexistent_rule(self, client):
        resp = await client.get("/api/v1/rules/nonexistent_xyz")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CRUD Operations
# ═══════════════════════════════════════════════════════════════════════════════

class TestRuleCRUD:

    NEW_RULE = {
        "id": "test_custom_rule",
        "name": "Test Custom Rule",
        "category": "custom",
        "pattern": r"\bTEST_SECRET_\d+\b",
        "flags": "",
        "strategy": "placeholder",
        "placeholder": "[TEST]",
        "weight": 5,
        "enabled": True,
    }

    @pytest.mark.asyncio
    async def test_create_rule(self, client):
        resp = await client.post("/api/v1/rules", json=self.NEW_RULE)
        assert resp.status_code == 201
        data = resp.json()
        assert data["rule"]["id"] == "test_custom_rule"

    @pytest.mark.asyncio
    async def test_create_duplicate_fails(self, client):
        await client.post("/api/v1/rules", json=self.NEW_RULE)
        resp = await client.post("/api/v1/rules", json=self.NEW_RULE)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_with_bad_regex_fails(self, client):
        bad = {**self.NEW_RULE, "id": "bad_regex", "pattern": "[invalid("}
        resp = await client.post("/api/v1/rules", json=bad)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_update_rule(self, client):
        await client.post("/api/v1/rules", json=self.NEW_RULE)
        resp = await client.put("/api/v1/rules/test_custom_rule", json={
            "name": "Updated Name",
            "weight": 8,
        })
        assert resp.status_code == 200
        assert resp.json()["rule"]["name"] == "Updated Name"
        assert resp.json()["rule"]["weight"] == 8

    @pytest.mark.asyncio
    async def test_update_nonexistent_fails(self, client):
        resp = await client.put("/api/v1/rules/nonexistent_xyz", json={"name": "x"})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_custom_rule(self, client):
        await client.post("/api/v1/rules", json=self.NEW_RULE)
        resp = await client.delete("/api/v1/rules/test_custom_rule")
        assert resp.status_code == 200
        # Should be gone
        resp2 = await client.get("/api/v1/rules/test_custom_rule")
        assert resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_builtin_fails(self, client):
        resp = await client.delete("/api/v1/rules/ipv4")
        assert resp.status_code == 400  # Built-in rules can't be deleted


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Toggle
# ═══════════════════════════════════════════════════════════════════════════════

class TestToggle:

    @pytest.mark.asyncio
    async def test_toggle_disables_and_enables(self, client):
        # First toggle → disable
        resp1 = await client.patch("/api/v1/rules/ipv4/toggle")
        assert resp1.status_code == 200
        assert resp1.json()["rule"]["enabled"] == False

        # Second toggle → re-enable
        resp2 = await client.patch("/api/v1/rules/ipv4/toggle")
        assert resp2.status_code == 200
        assert resp2.json()["rule"]["enabled"] == True


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Import / Export
# ═══════════════════════════════════════════════════════════════════════════════

class TestImportExport:

    @pytest.mark.asyncio
    async def test_export_returns_rules(self, client):
        resp = await client.get("/api/v1/rules-export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 80
        assert isinstance(data["rules"], list)

    @pytest.mark.asyncio
    async def test_import_creates_new_rules(self, client):
        new_rules = [
            {
                "id": "import_test_1",
                "name": "Imported Rule 1",
                "category": "custom",
                "pattern": r"\bIMPORT1\b",
                "strategy": "placeholder",
                "placeholder": "[IMP1]",
                "weight": 3,
            },
            {
                "id": "import_test_2",
                "name": "Imported Rule 2",
                "category": "custom",
                "pattern": r"\bIMPORT2\b",
                "strategy": "placeholder",
                "placeholder": "[IMP2]",
                "weight": 4,
            },
        ]
        resp = await client.post("/api/v1/rules-import", json={"rules": new_rules})
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] == 2

        # Verify they exist
        resp2 = await client.get("/api/v1/rules/import_test_1")
        assert resp2.status_code == 200

    @pytest.mark.asyncio
    async def test_import_empty_fails(self, client):
        resp = await client.post("/api/v1/rules-import", json={"rules": []})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_roundtrip_export_import(self, client):
        """Export → re-import should not fail."""
        exp = await client.get("/api/v1/rules-export")
        rules = exp.json()["rules"]
        # Import them back (all existing → updated, 0 created)
        resp = await client.post("/api/v1/rules-import", json={"rules": rules})
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] == 0
        assert data["updated"] >= 80


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Suggestions
# ═══════════════════════════════════════════════════════════════════════════════

class TestSuggestions:

    @pytest.mark.asyncio
    async def test_create_suggestion(self, client):
        resp = await client.post("/api/v1/rules/suggestions", json={
            "action": "create",
            "name": "My Suggestion",
            "pattern": r"\bSUGGEST\b",
            "reason": "We need this pattern",
        })
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_list_suggestions(self, client):
        # Create one first
        await client.post("/api/v1/rules/suggestions", json={
            "action": "create",
            "name": "SugA",
            "pattern": r"\bAAA\b",
            "reason": "test",
        })
        resp = await client.get("/api/v1/rules/suggestions")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    @pytest.mark.asyncio
    async def test_approve_suggestion(self, client):
        # Create
        cr = await client.post("/api/v1/rules/suggestions", json={
            "action": "create",
            "name": "Approved Rule",
            "category": "custom",
            "pattern": r"\bAPPROVED_\d+\b",
            "strategy": "placeholder",
            "placeholder": "[APPROVED]",
            "weight": 5,
            "reason": "needed",
        })
        sug_id = cr.json()["suggestion"]["id"]

        # Approve
        resp = await client.patch(f"/api/v1/rules/suggestions/{sug_id}", json={"action": "approve"})
        assert resp.status_code == 200
        assert resp.json()["suggestion"]["status"] == "approved"

    @pytest.mark.asyncio
    async def test_reject_suggestion(self, client):
        cr = await client.post("/api/v1/rules/suggestions", json={
            "action": "create",
            "name": "Rejected Rule",
            "pattern": r"\bREJECTED\b",
            "reason": "not needed",
        })
        sug_id = cr.json()["suggestion"]["id"]

        resp = await client.patch(f"/api/v1/rules/suggestions/{sug_id}", json={"action": "reject"})
        assert resp.status_code == 200
        assert resp.json()["suggestion"]["status"] == "rejected"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Changelog
# ═══════════════════════════════════════════════════════════════════════════════

class TestChangelog:

    @pytest.mark.asyncio
    async def test_changelog_records_toggle(self, client):
        # Toggle a rule
        await client.patch("/api/v1/rules/ipv4/toggle")
        # Check changelog
        resp = await client.get("/api/v1/rules/changelog?rule_id=ipv4")
        assert resp.status_code == 200
        entries = resp.json()["changelog"]
        assert len(entries) >= 1
        assert entries[0]["rule_id"] == "ipv4"

    @pytest.mark.asyncio
    async def test_changelog_records_create(self, client):
        await client.post("/api/v1/rules", json={
            "id": "changelog_test",
            "name": "CL Test",
            "pattern": r"\bCLTEST\b",
        })
        resp = await client.get("/api/v1/rules/changelog?rule_id=changelog_test")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1
