"""
test_orgs_api.py — Tests for /api/v1/orgs endpoints.

AUTH_ENABLED is forced OFF in conftest.  With auth disabled:
  - require_admin / require_auth both return {} silently
  - get_auth_user returns None (no auth middleware injected auth_user)
  - AUTH_ENABLED is read at import time in permissions.py, but the conftest
    sets os.environ["AUTH_ENABLED"]="false" before import, so this is safe.
"""
import pytest


class TestListOrgs:
    @pytest.mark.asyncio
    async def test_list_orgs_returns_dict(self, client):
        resp = await client.get("/api/v1/orgs")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "orgs" in data
        assert isinstance(data["orgs"], list)


class TestCreateOrg:
    @pytest.mark.asyncio
    async def test_create_org_success(self, client):
        resp = await client.post("/api/v1/orgs", json={"id": "test-team", "name": "Test Team"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["org"]["id"] == "test-team"
        assert data["org"]["name"] == "Test Team"
        # invite code should be set
        assert data["org"].get("invite_code") is not None

    @pytest.mark.asyncio
    async def test_create_duplicate_org_fails(self, client):
        await client.post("/api/v1/orgs", json={"id": "dup-org", "name": "Dup Org"})
        resp = await client.post("/api/v1/orgs", json={"id": "dup-org", "name": "Dup Org Again"})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_org_appears_in_list(self, client):
        await client.post("/api/v1/orgs", json={"id": "visible-org", "name": "Visible"})
        resp = await client.get("/api/v1/orgs")
        ids = [o["id"] for o in resp.json()["orgs"]]
        assert "visible-org" in ids


class TestDeleteOrg:
    @pytest.mark.asyncio
    async def test_delete_org(self, client):
        await client.post("/api/v1/orgs", json={"id": "del-org", "name": "To Delete"})
        resp = await client.delete("/api/v1/orgs/del-org")
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_org(self, client):
        # rule_service.delete_org does not raise for nonexistent — returns success silently
        resp = await client.delete("/api/v1/orgs/no-such-org")
        assert resp.status_code == 200


class TestGetMineOrg:
    @pytest.mark.asyncio
    async def test_get_mine_returns_default_org(self, client):
        """With AUTH_ENABLED=false, org_id defaults to 'default' which exists by default."""
        resp = await client.get("/api/v1/orgs/mine")
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data


class TestRefreshInvite:
    @pytest.mark.asyncio
    async def test_refresh_invite_requires_ownership(self, client):
        """With empty key_prefix (dev mode), non-owner gets 403."""
        await client.post("/api/v1/orgs", json={"id": "inv-org", "name": "Invite Org"})
        resp = await client.post("/api/v1/orgs/inv-org/invite")
        # dev mode has empty key_prefix, not recorded as owner → 403
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_refresh_invite_nonexistent_org(self, client):
        resp = await client.post("/api/v1/orgs/nonexistent/invite")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_successive_refreshes_endpoint_exists(self, client):
        """Verify the endpoint is wired up (403 with no ownership is expected)."""
        await client.post("/api/v1/orgs", json={"id": "refresh-org", "name": "Refresh"})
        r1 = await client.post("/api/v1/orgs/refresh-org/invite")
        r2 = await client.post("/api/v1/orgs/refresh-org/invite")
        assert r1.status_code == r2.status_code == 403


class TestOrgOwners:
    @pytest.mark.asyncio
    async def test_list_owners_requires_membership(self, client):
        """With empty key_prefix, non-member / non-admin gets 403."""
        await client.post("/api/v1/orgs", json={"id": "owner-org", "name": "Owner Org"})
        resp = await client.get("/api/v1/orgs/owner-org/owners")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_list_owners_nonexistent_org(self, client):
        resp = await client.get("/api/v1/orgs/ghost-org/owners")
        assert resp.status_code == 404
