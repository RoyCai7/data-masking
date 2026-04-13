"""
test_masking_api.py — Tests for the Masking API (/api/v1/mask, /task, /download...).

Covers:
  1. Upload text file → mask → poll status → download
  2. Upload archive (tar.gz) → mask → download
  3. Upload archive (zip) → mask → download
  4. Whitelist parameter
  5. Unsupported file type → 400
  6. Task listing
  7. Report endpoint
  8. Session isolation
  9. Error cases (missing session, wrong task ID, ...)
"""
import io
import time
import asyncio
import pytest


async def _wait_for_task(client, session_id: str, task_id: str, timeout: float = 15.0):
    """Poll task status until completed/failed or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        resp = await client.get(
            f"/api/v1/task/{task_id}",
            headers={"X-Session-ID": session_id},
        )
        data = resp.json()
        if data["status"] in ("completed", "failed"):
            return data
        await asyncio.sleep(0.3)
    raise TimeoutError(f"Task {task_id} did not complete in {timeout}s")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Text file upload → mask → download (full E2E)
# ═══════════════════════════════════════════════════════════════════════════════

class TestTextFileMasking:

    @pytest.mark.asyncio
    async def test_upload_and_mask_text(self, client, sample_text):
        # Upload
        files = {"file": ("sample.log", io.BytesIO(sample_text.encode()), "text/plain")}
        resp = await client.post("/api/v1/mask", files=files)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "pending"
        session_id = body["session_id"]
        task_id = body["task_id"]

        # Wait for completion
        task = await _wait_for_task(client, session_id, task_id)
        assert task["status"] == "completed"
        assert task["report"]["summary"]["total_matches"] > 0

    @pytest.mark.asyncio
    async def test_download_masked_file(self, client, sample_text):
        files = {"file": ("test.log", io.BytesIO(sample_text.encode()), "text/plain")}
        resp = await client.post("/api/v1/mask", files=files)
        body = resp.json()
        session_id, task_id = body["session_id"], body["task_id"]

        await _wait_for_task(client, session_id, task_id)

        # Download
        dl = await client.get(
            f"/api/v1/download/{task_id}",
            headers={"X-Session-ID": session_id},
        )
        assert dl.status_code == 200
        content = dl.text
        # Verify sensitive data is masked
        assert "192.168.1.100" not in content
        assert "SuperSecret123" not in content
        assert "john.doe@example.com" not in content

    @pytest.mark.asyncio
    async def test_report_endpoint(self, client, sample_text):
        files = {"file": ("r.log", io.BytesIO(sample_text.encode()), "text/plain")}
        resp = await client.post("/api/v1/mask", files=files)
        body = resp.json()
        session_id, task_id = body["session_id"], body["task_id"]
        await _wait_for_task(client, session_id, task_id)

        rpt = await client.get(
            f"/api/v1/report/{task_id}",
            headers={"X-Session-ID": session_id},
        )
        assert rpt.status_code == 200
        report = rpt.json()
        assert "summary" in report
        assert "breakdown" in report
        assert report["summary"]["total_matches"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Archive file masking
# ═══════════════════════════════════════════════════════════════════════════════

class TestArchiveMasking:

    @pytest.mark.asyncio
    async def test_tar_gz_upload(self, client, sample_tar_gz):
        data = sample_tar_gz.read_bytes()
        files = {"file": ("bundle.tar.gz", io.BytesIO(data), "application/gzip")}
        resp = await client.post("/api/v1/mask", files=files)
        assert resp.status_code == 200
        body = resp.json()
        session_id, task_id = body["session_id"], body["task_id"]

        task = await _wait_for_task(client, session_id, task_id)
        assert task["status"] == "completed"
        assert task["report"]["file_info"]["is_archive"] is True
        assert task["report"]["summary"]["total_matches"] > 0

    @pytest.mark.asyncio
    async def test_zip_upload(self, client, sample_zip):
        data = sample_zip.read_bytes()
        files = {"file": ("bundle.zip", io.BytesIO(data), "application/zip")}
        resp = await client.post("/api/v1/mask", files=files)
        assert resp.status_code == 200
        body = resp.json()
        session_id, task_id = body["session_id"], body["task_id"]

        task = await _wait_for_task(client, session_id, task_id)
        assert task["status"] == "completed"
        assert task["report"]["file_info"]["is_archive"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Whitelist via form field
# ═══════════════════════════════════════════════════════════════════════════════

class TestWhitelistAPI:

    @pytest.mark.asyncio
    async def test_whitelist_preserves_ip(self, client):
        text = "server ip=192.168.1.100\n"
        files = {"file": ("wl.log", io.BytesIO(text.encode()), "text/plain")}
        resp = await client.post(
            "/api/v1/mask",
            files=files,
            data={"whitelist": "192.168.1.100"},
        )
        body = resp.json()
        session_id, task_id = body["session_id"], body["task_id"]

        await _wait_for_task(client, session_id, task_id)

        dl = await client.get(
            f"/api/v1/download/{task_id}",
            headers={"X-Session-ID": session_id},
        )
        assert "192.168.1.100" in dl.text


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Error handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestMaskingErrors:

    @pytest.mark.asyncio
    async def test_unsupported_file_type(self, client):
        files = {"file": ("photo.png", io.BytesIO(b"\x89PNG"), "image/png")}
        resp = await client.post("/api/v1/mask", files=files)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_task_not_found(self, client):
        resp = await client.get(
            "/api/v1/task/nonexistent-id",
            headers={"X-Session-ID": "fake-session"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_download_without_session(self, client):
        resp = await client.get("/api/v1/download/some-task-id")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_report_before_completion(self, client, sample_text):
        files = {"file": ("slow.log", io.BytesIO(sample_text.encode()), "text/plain")}
        resp = await client.post("/api/v1/mask", files=files)
        body = resp.json()
        # Immediately try to get report (may still be pending)
        rpt = await client.get(
            f"/api/v1/report/{body['task_id']}",
            headers={"X-Session-ID": body["session_id"]},
        )
        # Either 400 (not completed) or 200 (if it was fast enough)
        assert rpt.status_code in (200, 400)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Task listing
# ═══════════════════════════════════════════════════════════════════════════════

class TestTaskListing:

    @pytest.mark.asyncio
    async def test_list_tasks(self, client, sample_text):
        # Upload a file
        files = {"file": ("a.log", io.BytesIO(sample_text.encode()), "text/plain")}
        resp = await client.post("/api/v1/mask", files=files)
        body = resp.json()
        session_id = body["session_id"]

        # Wait for task to complete
        await _wait_for_task(client, session_id, body["task_id"])

        # List tasks
        resp2 = await client.get("/api/v1/tasks", headers={"X-Session-ID": session_id})
        assert resp2.status_code == 200
        tasks = resp2.json()["tasks"]
        assert len(tasks) >= 1
        assert tasks[0]["task_id"] == body["task_id"]

    @pytest.mark.asyncio
    async def test_list_tasks_no_session(self, client):
        resp = await client.get("/api/v1/tasks")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Session isolation
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionIsolation:

    @pytest.mark.asyncio
    async def test_different_sessions_isolated(self, client, sample_text):
        # Upload from "session A"
        files1 = {"file": ("a.log", io.BytesIO(sample_text.encode()), "text/plain")}
        resp1 = await client.post("/api/v1/mask", files=files1)
        body1 = resp1.json()

        # Try to access task from a different session
        resp2 = await client.get(
            f"/api/v1/task/{body1['task_id']}",
            headers={"X-Session-ID": "other-session-id"},
        )
        assert resp2.status_code == 404
