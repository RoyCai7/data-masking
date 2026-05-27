"""
test_permissions.py — Auth enforcement tests (401 / 403 responses).

These tests enable AUTH to verify that the API correctly rejects
unauthenticated and unauthorized requests.
"""
import pytest
import pytest_asyncio


@pytest.fixture(autouse=True)
def enable_auth(monkeypatch):
    """
    Activate authentication for the duration of each test in this module.
    We patch both the source module and all modules that imported the constant.
    """
    import app.core.auth as auth_mod
    import app.core.permissions as perms_mod

    monkeypatch.setattr(auth_mod, "AUTH_ENABLED", True)
    monkeypatch.setattr(perms_mod, "AUTH_ENABLED", True)
    yield


class TestUnauthenticated:
    """No X-API-Key header → 401 on protected routes."""

    @pytest.mark.asyncio
    async def test_create_key_requires_auth(self, client):
        resp = await client.post("/api/v1/keys", json={"name": "x", "role": "user"})
        assert resp.status_code == 401  # middleware rejects before endpoint

    @pytest.mark.asyncio
    async def test_list_keys_requires_auth(self, client):
        resp = await client.get("/api/v1/keys")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_orgs_requires_admin(self, client):
        resp = await client.get("/api/v1/orgs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_my_key_requires_auth(self, client):
        resp = await client.get("/api/v1/keys/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_rotate_key_requires_auth(self, client):
        resp = await client.post("/api/v1/keys/rotate")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_org_requires_auth(self, client):
        resp = await client.post("/api/v1/orgs", json={"id": "x", "name": "X"})
        assert resp.status_code == 401


class TestAuthorizedAdmin:
    """With a valid admin API key in middleware, all admin routes succeed."""

    @pytest.fixture(autouse=True)
    def inject_admin_user(self, monkeypatch):
        """
        Simulate the auth middleware injecting an admin user into request.state.
        Patch validate_key so any key value is accepted as admin.
        """
        import app.core.auth as auth_mod

        admin_user = {
            "name": "test-admin",
            "role": "admin",
            "org_id": "default",
            "key_prefix": "dms_test",
            "enabled": True,
        }

        monkeypatch.setattr(auth_mod, "validate_key", lambda key: admin_user)
        yield

    @pytest.mark.asyncio
    async def test_admin_can_list_keys(self, client):
        resp = await client.get("/api/v1/keys", headers={"X-API-Key": "dms_fake"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_list_orgs(self, client):
        resp = await client.get("/api/v1/orgs", headers={"X-API-Key": "dms_fake"})
        assert resp.status_code == 200


class TestForbiddenUser:
    """With a non-admin user, admin-only routes return 403."""

    @pytest.fixture(autouse=True)
    def inject_regular_user(self, monkeypatch):
        import app.core.auth as auth_mod

        regular_user = {
            "name": "regular",
            "role": "user",
            "org_id": "default",
            "key_prefix": "dms_user",
            "enabled": True,
        }
        monkeypatch.setattr(auth_mod, "validate_key", lambda key: regular_user)
        yield

    @pytest.mark.asyncio
    async def test_user_cannot_list_keys(self, client):
        resp = await client.get("/api/v1/keys", headers={"X-API-Key": "dms_user"})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_user_cannot_create_key(self, client):
        resp = await client.post(
            "/api/v1/keys",
            json={"name": "x", "role": "user"},
            headers={"X-API-Key": "dms_user"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_user_cannot_list_all_orgs(self, client):
        resp = await client.get("/api/v1/orgs", headers={"X-API-Key": "dms_user"})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_user_can_get_own_key(self, client):
        """Non-admin users are allowed to view their own key info."""
        resp = await client.get("/api/v1/keys/me", headers={"X-API-Key": "dms_user"})
        assert resp.status_code == 200
