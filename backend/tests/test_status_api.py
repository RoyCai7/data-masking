"""
test_status_api.py — Tests for Status & Session endpoints.

Covers:
  1. GET /status → health check
  2. POST /session → create new session
"""
import pytest


class TestStatusAPI:

    @pytest.mark.asyncio
    async def test_health_status(self, client):
        resp = await client.get("/api/v1/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "SUSE Data Masking Service"
        assert "executor" in data

    @pytest.mark.asyncio
    async def test_executor_info(self, client):
        resp = await client.get("/api/v1/status")
        executor = resp.json()["executor"]
        assert "max_workers" in executor
        assert "active_tasks" in executor
        assert "available_slots" in executor


class TestSessionAPI:

    @pytest.mark.asyncio
    async def test_create_session(self, client):
        resp = await client.post("/api/v1/session")
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert len(data["session_id"]) > 10

    @pytest.mark.asyncio
    async def test_sessions_are_unique(self, client):
        r1 = await client.post("/api/v1/session")
        r2 = await client.post("/api/v1/session")
        assert r1.json()["session_id"] != r2.json()["session_id"]
