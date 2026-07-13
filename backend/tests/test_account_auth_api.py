import pytest


@pytest.fixture(autouse=True)
def enable_auth(monkeypatch):
    import app.core.auth as auth_mod
    import app.core.permissions as permissions_mod

    monkeypatch.setattr(auth_mod, "AUTH_ENABLED", True)
    monkeypatch.setattr(permissions_mod, "AUTH_ENABLED", True)


@pytest.fixture
def sent_email_tokens(monkeypatch):
    import app.core.account_service as account_service
    from app.core.email_service import EmailDeliveryResult

    tokens = {"verify": [], "reset": []}

    def fake_verify_email(email: str, token: str):
        tokens["verify"].append(token)
        return EmailDeliveryResult(sent=True, detail="Activation email sent")

    def fake_reset_email(email: str, token: str):
        tokens["reset"].append(token)
        return EmailDeliveryResult(sent=True, detail="Password reset email sent")

    monkeypatch.setattr(account_service, "smtp_configuration_error", lambda: None)
    monkeypatch.setattr(account_service, "send_email_verification_email", fake_verify_email)
    monkeypatch.setattr(account_service, "send_password_reset_email", fake_reset_email)
    return tokens


async def _register_and_verify(client, sent_email_tokens, email: str, password: str = "StrongPass123", name: str = "User"):
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": name},
    )
    assert register.status_code == 200
    assert "verify_token" not in register.json()
    assert sent_email_tokens["verify"][-1].startswith("dms_verify_")

    verified = await client.post(
        "/api/v1/auth/verify-email",
        json={"token": sent_email_tokens["verify"][-1]},
    )
    assert verified.status_code == 200
    return verified.json()["token"]


@pytest.mark.asyncio
async def test_register_requires_email_activation_before_login(client, sent_email_tokens):
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": "Alice@Example.com", "password": "StrongPass123", "name": "Alice"},
    )
    assert register.status_code == 200
    data = register.json()
    assert data["user"]["email"] == "alice@example.com"
    assert data["user"]["email_verified"] is False

    login_before_verify = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "StrongPass123"},
    )
    assert login_before_verify.status_code == 403

    assert "verify_token" not in data
    verified = await client.post("/api/v1/auth/verify-email", json={"token": sent_email_tokens["verify"][-1]})
    assert verified.status_code == 200
    assert verified.json()["token"].startswith("dms_sess_")


@pytest.mark.asyncio
async def test_verified_user_can_create_multiple_account_tokens(client, sent_email_tokens):
    session_token = await _register_and_verify(client, sent_email_tokens, "api-owner@example.com", name="API Owner")

    me = await client.get("/api/v1/auth/me", headers={"X-Session-Token": session_token})
    assert me.status_code == 200
    assert me.json()["user"]["name"] == "API Owner"

    token = await client.post(
        "/api/v1/account/tokens",
        headers={"X-Session-Token": session_token},
        json={"name": "ci-token", "expires_days": 30},
    )
    assert token.status_code == 200
    api_key = token.json()["key"]
    assert api_key.startswith("dms_")

    key_me = await client.get("/api/v1/keys/me", headers={"X-API-Key": api_key})
    assert key_me.status_code == 200
    assert key_me.json()["name"] == "ci-token"

    second = await client.post(
        "/api/v1/account/tokens",
        headers={"X-Session-Token": session_token},
        json={"name": "second-token", "expires_days": 30},
    )
    assert second.status_code == 200

    listed = await client.get("/api/v1/account/tokens", headers={"X-Session-Token": session_token})
    assert listed.status_code == 200
    assert listed.json()["total"] == 2


@pytest.mark.asyncio
async def test_session_user_can_create_org_and_remain_owner(client, sent_email_tokens):
    session_token = await _register_and_verify(client, sent_email_tokens, "owner@example.com", name="Owner")

    created = await client.post(
        "/api/v1/orgs",
        headers={"X-Session-Token": session_token},
        json={"id": "team-a", "name": "Team A"},
    )
    assert created.status_code == 201
    assert created.json()["org"]["id"] == "team-a"

    mine = await client.get("/api/v1/orgs/mine", headers={"X-Session-Token": session_token})
    assert mine.status_code == 200
    assert mine.json()["id"] == "team-a"
    assert "user_" in mine.json()["owner_key_prefix"]


@pytest.mark.asyncio
async def test_forgot_and_reset_password(client, sent_email_tokens):
    await _register_and_verify(client, sent_email_tokens, "bob@example.com", password="OldPassword123", name="Bob")

    forgot = await client.post("/api/v1/auth/forgot-password", json={"email": "bob@example.com"})
    assert forgot.status_code == 200
    assert "reset_token" not in forgot.json()
    reset_token = sent_email_tokens["reset"][-1]
    assert reset_token.startswith("dms_reset_")

    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "NewPassword123"},
    )
    assert reset.status_code == 200

    old_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "OldPassword123"},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "NewPassword123"},
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_register_requires_smtp_configuration(client, monkeypatch):
    import app.core.account_service as account_service

    monkeypatch.setattr(account_service, "smtp_configuration_error", lambda: "DMS_SMTP_HOST is required")

    register = await client.post(
        "/api/v1/auth/register",
        json={"email": "smtp-missing@example.com", "password": "StrongPass123", "name": "SMTP Missing"},
    )
    assert register.status_code == 503
    assert "Email delivery is not configured" in register.json()["detail"]

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "smtp-missing@example.com", "password": "StrongPass123"},
    )
    assert login.status_code == 401
