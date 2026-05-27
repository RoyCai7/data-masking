"""
test_keys_api.py — Tests for POST/GET/PUT/DELETE /api/v1/keys endpoints.

AUTH_ENABLED is forced OFF in conftest, so all admin guards are bypassed.
"""
import pytest
import pytest_asyncio


class TestCreateKey:
    @pytest.mark.asyncio
    async def test_create_key_returns_token(self, client):
        resp = await client.post("/api/v1/keys", json={
            "name": "ci-bot", "role": "user", "expires_days": 30
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"].startswith("dms_")
        assert data["name"] == "ci-bot"
        assert data["role"] == "user"

    @pytest.mark.asyncio
    async def test_create_admin_key(self, client):
        resp = await client.post("/api/v1/keys", json={
            "name": "admin-key", "role": "admin", "expires_days": 365
        })
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"


class TestListKeys:
    @pytest.mark.asyncio
    async def test_list_keys_shape(self, client):
        # Seed two keys
        for name in ("key-a", "key-b"):
            await client.post("/api/v1/keys", json={"name": name, "role": "user"})

        resp = await client.get("/api/v1/keys")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "keys" in data
        assert data["total"] >= 2
        for k in data["keys"]:
            assert "id" in k
            assert "name" in k
            assert "enabled" in k

    @pytest.mark.asyncio
    async def test_list_keys_preview_hides_value(self, client):
        await client.post("/api/v1/keys", json={"name": "secret-key", "role": "user"})
        resp = await client.get("/api/v1/keys")
        for k in resp.json()["keys"]:
            assert k.get("key_preview", "").endswith("...")


class TestUpdateKey:
    @pytest.mark.asyncio
    async def test_update_key_role(self, client):
        create = await client.post("/api/v1/keys", json={"name": "upd-key", "role": "user"})
        key_id = create.json()["id"]

        resp = await client.put("/api/v1/keys/update", json={"key_id": key_id, "role": "admin"})
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    @pytest.mark.asyncio
    async def test_update_nonexistent_key(self, client):
        resp = await client.put("/api/v1/keys/update", json={"key_id": 999999})
        assert resp.status_code == 404


class TestDisableKey:
    @pytest.mark.asyncio
    async def test_disable_key(self, client):
        create = await client.post("/api/v1/keys", json={"name": "bye-key", "role": "user"})
        key_id = create.json()["id"]

        resp = await client.post("/api/v1/keys/disable", json={"key_id": key_id})
        assert resp.status_code == 200
        assert "disabled" in resp.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_disable_nonexistent_key(self, client):
        resp = await client.post("/api/v1/keys/disable", json={"key_id": 999999})
        assert resp.status_code == 404


class TestRevealKey:
    @pytest.mark.asyncio
    async def test_reveal_returns_plaintext(self, client):
        create = await client.post("/api/v1/keys", json={"name": "reveal-key", "role": "user"})
        data = create.json()
        key_id = data["id"]
        original_key = data["key"]

        resp = await client.get(f"/api/v1/keys/{key_id}/reveal")
        assert resp.status_code == 200
        assert resp.json()["key"] == original_key

    @pytest.mark.asyncio
    async def test_reveal_nonexistent(self, client):
        resp = await client.get("/api/v1/keys/999999/reveal")
        assert resp.status_code == 404


class TestMyKey:
    @pytest.mark.asyncio
    async def test_get_me_when_auth_disabled(self, client):
        """With AUTH_ENABLED=false, /keys/me returns empty-ish dict (no 401)."""
        resp = await client.get("/api/v1/keys/me")
        assert resp.status_code == 200
        # In dev mode require_auth returns {} so all fields are None/default
        data = resp.json()
        assert "role" in data


class TestRotateKey:
    @pytest.mark.asyncio
    async def test_rotate_with_valid_key(self, client):
        """Create a key then rotate it — new key returned, old is gone."""
        create = await client.post("/api/v1/keys", json={
            "name": "rotatable", "role": "user"
        })
        old_key = create.json()["key"]

        resp = await client.post(
            "/api/v1/keys/rotate",
            headers={"X-API-Key": old_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_key"].startswith("dms_")
        assert data["new_key"] != old_key
        assert "warning" in data

    @pytest.mark.asyncio
    async def test_rotate_without_key_returns_404(self, client):
        """No X-API-Key header → rotate_key('') returns None → 404."""
        resp = await client.post("/api/v1/keys/rotate")
        assert resp.status_code == 404
