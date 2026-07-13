"""
Tests for email-based token registration and recovery.
"""
import pytest


@pytest.mark.asyncio
async def test_register_email_creates_user_token(monkeypatch, client):
    import app.core.auth as auth_mod
    import app.core.permissions as permissions_mod

    monkeypatch.setenv("DMS_EMAIL_DEBUG_RETURN_TOKEN", "true")
    monkeypatch.setattr(auth_mod, "AUTH_ENABLED", True)
    monkeypatch.setattr(permissions_mod, "AUTH_ENABLED", True)

    resp = await client.post("/api/v1/email-token/register", json={"email": "Alice@Example.COM"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "alice@example.com"
    assert data["created"] is True
    assert data["key"].startswith("dms_")
    assert data["email_sent"] is False

    me = await client.get("/api/v1/keys/me", headers={"X-API-Key": data["key"]})
    assert me.status_code == 200
    assert me.json()["role"] == "user"
    assert me.json()["name"] == "alice@example.com"


@pytest.mark.asyncio
async def test_recover_email_returns_same_token_in_debug(monkeypatch, client):
    monkeypatch.setenv("DMS_EMAIL_DEBUG_RETURN_TOKEN", "true")

    first = await client.post("/api/v1/email-token/register", json={"email": "bob@example.com"})
    assert first.status_code == 200
    first_key = first.json()["key"]

    second = await client.post("/api/v1/email-token/recover", json={"email": "bob@example.com"})
    assert second.status_code == 200
    data = second.json()
    assert data["created"] is False
    assert data["key"] == first_key


@pytest.mark.asyncio
async def test_email_token_does_not_return_key_without_debug(monkeypatch, client):
    monkeypatch.delenv("DMS_EMAIL_DEBUG_RETURN_TOKEN", raising=False)

    resp = await client.post("/api/v1/email-token/register", json={"email": "carol@example.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["key"] is None
    assert data["email_sent"] is False
    assert "SMTP" in data["delivery_detail"]


@pytest.mark.asyncio
async def test_email_token_rejects_invalid_email(client):
    resp = await client.post("/api/v1/email-token/register", json={"email": "not-an-email"})
    assert resp.status_code == 422
