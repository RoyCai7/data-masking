#!/usr/bin/env python3
"""Run end-to-end API scenarios for regular users and administrators.

This script is intended for tester-facing validation against a live deployment.
It uses only the Python standard library and prints a markdown-style result table.

Typical usage:
  DMS_USER_API_KEY=... DMS_ADMIN_API_KEY=... python api_scenario_test.py

Safe-by-default behavior:
  - Public and regular-user scenarios run automatically when `DMS_USER_API_KEY`
    or `--user-key` is provided.
  - Read-only admin scenarios run automatically when `DMS_ADMIN_API_KEY` or
    `--admin-key` is provided.
  - Destructive admin write scenarios require `--full-admin`.
"""
from __future__ import annotations

import argparse
import io
import json
import mimetypes
import os
import sys
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional
from urllib import error, parse, request


DEFAULT_BASE_URL = os.getenv("DMS_BASE_URL", "http://10.146.15.188:8080/api/v1")
DEFAULT_TIMEOUT = 30.0
POLL_INTERVAL = 1.0
POLL_TIMEOUT = 120.0

SAMPLE_TEXT = """# API scenario sample
server_ip = 192.168.1.100
email = john.doe@example.com
password = SuperSecret123!
api_key = sk_live_4eC39HqLyjWDarjtT1zdp7dc
aws_key = AKIAIOSFODNN7EXAMPLE
"""


@dataclass
class Response:
    status_code: int
    headers: Dict[str, str]
    body: bytes

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        if not self.body:
            return None
        return json.loads(self.text())


@dataclass
class ScenarioResult:
    role: str
    name: str
    status: str
    detail: str
    duration_ms: int


class APIClient:
    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        form_fields: Optional[Dict[str, str]] = None,
        files: Optional[Dict[str, tuple[str, bytes, Optional[str]]]] = None,
    ) -> Response:
        url = self.base_url + path
        if params:
            query = parse.urlencode(params)
            url = f"{url}?{query}"

        req_headers = {"Accept": "application/json", **(headers or {})}
        data: Optional[bytes] = None

        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        elif files:
            boundary = f"----DMSBoundary{uuid.uuid4().hex}"
            data = self._encode_multipart(boundary, form_fields or {}, files)
            req_headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif form_fields:
            data = parse.urlencode(form_fields).encode("utf-8")
            req_headers["Content-Type"] = "application/x-www-form-urlencoded"

        req = request.Request(url, data=data, method=method.upper(), headers=req_headers)
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                return Response(
                    status_code=resp.status,
                    headers=dict(resp.headers.items()),
                    body=resp.read(),
                )
        except error.HTTPError as exc:
            return Response(
                status_code=exc.code,
                headers=dict(exc.headers.items()),
                body=exc.read(),
            )

    @staticmethod
    def _encode_multipart(
        boundary: str,
        fields: Dict[str, str],
        files: Dict[str, tuple[str, bytes, Optional[str]]],
    ) -> bytes:
        buffer = io.BytesIO()
        boundary_bytes = boundary.encode("utf-8")

        for key, value in fields.items():
            buffer.write(b"--" + boundary_bytes + b"\r\n")
            buffer.write(
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8")
            )
            buffer.write(str(value).encode("utf-8"))
            buffer.write(b"\r\n")

        for key, (filename, content, content_type) in files.items():
            guessed = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
            buffer.write(b"--" + boundary_bytes + b"\r\n")
            buffer.write(
                (
                    f'Content-Disposition: form-data; name="{key}"; '
                    f'filename="{filename}"\r\n'
                ).encode("utf-8")
            )
            buffer.write(f"Content-Type: {guessed}\r\n\r\n".encode("utf-8"))
            buffer.write(content)
            buffer.write(b"\r\n")

        buffer.write(b"--" + boundary_bytes + b"--\r\n")
        return buffer.getvalue()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def short_detail(value: Any, limit: int = 120) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


class ScenarioRunner:
    def __init__(
        self,
        client: APIClient,
        *,
        user_key: str = "",
        admin_key: str = "",
        full_admin: bool = False,
    ):
        self.client = client
        self.user_key = user_key
        self.admin_key = admin_key
        self.full_admin = full_admin
        self.results: list[ScenarioResult] = []
        self._temp_user_key: Optional[str] = None
        self._temp_user_name: Optional[str] = None

    def run_all(self) -> int:
        self._maybe_bootstrap_user_key()
        self._run_public_scenarios()
        self._run_user_scenarios()
        self._run_admin_scenarios()
        self._cleanup_temp_user_key()
        self._print_report()
        return 1 if any(item.status == "FAIL" for item in self.results) else 0

    def _record(self, role: str, name: str, status: str, detail: str, started_at: float) -> None:
        self.results.append(
            ScenarioResult(
                role=role,
                name=name,
                status=status,
                detail=detail,
                duration_ms=int((time.time() - started_at) * 1000),
            )
        )

    def _execute(self, role: str, name: str, fn: Callable[[], str], *, skip_if: Optional[str] = None) -> None:
        started_at = time.time()
        if skip_if:
            self._record(role, name, "SKIP", skip_if, started_at)
            return
        try:
            detail = fn()
            self._record(role, name, "PASS", detail, started_at)
        except Exception as exc:  # noqa: BLE001
            self._record(role, name, "FAIL", short_detail(exc), started_at)

    def _run_public_scenarios(self) -> None:
        self._execute("public", "status endpoint", self._scenario_status)
        self._execute("public", "public rule list", self._scenario_public_rules)
        self._execute("public", "create session", self._scenario_create_session)
        self._execute("public", "protected endpoint rejects anonymous", self._scenario_protected_anonymous)

    def _run_user_scenarios(self) -> None:
        skip = None if self.user_key else "Missing user API key"
        self._execute("user", "upload text and fetch report", self._scenario_user_text_masking, skip_if=skip)
        self._execute("user", "whitelist keeps allowed value", self._scenario_user_whitelist, skip_if=skip)
        self._execute("user", "unsupported file type rejected", self._scenario_user_bad_file, skip_if=skip)
        self._execute("user", "task list contains new task", self._scenario_user_task_list, skip_if=skip)
        self._execute("user", "session isolation enforced", self._scenario_user_session_isolation, skip_if=skip)
        self._execute("user", "single rule detail with key", self._scenario_user_rule_detail, skip_if=skip)
        self._execute("user", "submit and list suggestions", self._scenario_user_suggestions, skip_if=skip)
        self._execute("user", "zip archive masking", self._scenario_user_zip_masking, skip_if=skip)

    def _run_admin_scenarios(self) -> None:
        skip = None if self.admin_key else "Missing admin API key"
        self._execute("admin", "admin key info", self._scenario_admin_key_info, skip_if=skip)
        self._execute("admin", "list API keys", self._scenario_admin_list_keys, skip_if=skip)
        self._execute("admin", "export rules", self._scenario_admin_export_rules, skip_if=skip)
        self._execute("admin", "read rule changelog", self._scenario_admin_changelog, skip_if=skip)

        write_skip = skip or (None if self.full_admin else "Use --full-admin for write scenarios")
        self._execute("admin", "create/update/toggle/delete rule", self._scenario_admin_rule_crud, skip_if=write_skip)
        self._execute("admin", "create and disable temp API key", self._scenario_admin_key_lifecycle, skip_if=write_skip)
        self._execute("admin", "approve a user suggestion", self._scenario_admin_approve_suggestion, skip_if=write_skip or (None if self.user_key else "Need user API key for suggestion approval flow"))

    def _maybe_bootstrap_user_key(self) -> None:
        if self.user_key or not self.admin_key or not self.full_admin:
            return

        temp_name = f"Scenario User {uuid.uuid4().hex[:6]}"
        resp = self.client.request(
            "POST",
            "/keys",
            headers=self._auth_headers(api_key=self.admin_key),
            json_body={"name": temp_name, "role": "user", "expires_days": 1},
        )
        if resp.status_code != 200:
            return

        body = resp.json()
        self.user_key = body.get("key", "")
        self._temp_user_key = self.user_key or None
        self._temp_user_name = temp_name if self._temp_user_key else None

    def _cleanup_temp_user_key(self) -> None:
        if not self._temp_user_key or not self.admin_key:
            return

        self.client.request(
            "POST",
            "/keys/disable",
            headers=self._auth_headers(api_key=self.admin_key),
            json_body={"key": self._temp_user_key},
        )

    def _auth_headers(self, api_key: str = "", session_id: str = "") -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if api_key:
            headers["X-API-Key"] = api_key
        if session_id:
            headers["X-Session-ID"] = session_id
        return headers

    @staticmethod
    def _is_enabled(value: Any) -> bool:
        return bool(value)

    def _new_session(self) -> str:
        resp = self.client.request("POST", "/session")
        require(resp.status_code == 200, f"Expected 200, got {resp.status_code}")
        body = resp.json()
        require(body.get("session_id"), f"Missing session_id: {body}")
        return body["session_id"]

    def _upload_file(
        self,
        *,
        api_key: str,
        session_id: str,
        filename: str,
        content: bytes,
        content_type: Optional[str] = None,
        whitelist: str = "",
    ) -> Dict[str, Any]:
        last_resp: Optional[Response] = None
        for attempt in range(5):
            resp = self.client.request(
                "POST",
                "/mask",
                headers=self._auth_headers(api_key=api_key, session_id=session_id),
                form_fields={"whitelist": whitelist},
                files={"file": (filename, content, content_type)},
            )
            if resp.status_code == 200:
                return resp.json()
            last_resp = resp
            if resp.status_code != 503:
                break
            time.sleep(2.0 * (attempt + 1))

        require(last_resp is not None, "Upload request did not return a response")
        raise AssertionError(f"Upload failed: {last_resp.status_code} {last_resp.text()}")

    def _wait_for_task(self, *, api_key: str, session_id: str, task_id: str) -> Dict[str, Any]:
        start = time.time()
        while time.time() - start < POLL_TIMEOUT:
            resp = self.client.request(
                "GET",
                f"/task/{task_id}",
                headers=self._auth_headers(api_key=api_key, session_id=session_id),
            )
            require(resp.status_code == 200, f"Task query failed: {resp.status_code} {resp.text()}")
            body = resp.json()
            if body.get("status") in {"completed", "failed"}:
                return body
            time.sleep(POLL_INTERVAL)
        raise TimeoutError(f"Task {task_id} did not finish within {POLL_TIMEOUT}s")

    def _scenario_status(self) -> str:
        resp = self.client.request("GET", "/status")
        require(resp.status_code == 200, f"Expected 200, got {resp.status_code}")
        body = resp.json()
        require(body.get("status") == "healthy", f"Unexpected status body: {body}")
        return f"service={body.get('service')} auth_enabled={body.get('auth_enabled')}"

    def _scenario_public_rules(self) -> str:
        resp = self.client.request("GET", "/rules")
        require(resp.status_code == 200, f"Expected 200, got {resp.status_code}")
        body = resp.json()
        require(body.get("total", 0) > 0, f"Rule list empty: {body}")
        return f"rules={body.get('total')}"

    def _scenario_create_session(self) -> str:
        session_id = self._new_session()
        return f"session_id={session_id}"

    def _scenario_protected_anonymous(self) -> str:
        resp = self.client.request("GET", "/keys/me")
        require(resp.status_code == 401, f"Expected 401, got {resp.status_code}")
        return "GET /keys/me returned 401 without API key"

    def _scenario_user_text_masking(self) -> str:
        session_id = self._new_session()
        upload = self._upload_file(
            api_key=self.user_key,
            session_id=session_id,
            filename="sample.log",
            content=SAMPLE_TEXT.encode("utf-8"),
            content_type="text/plain",
        )
        task = self._wait_for_task(api_key=self.user_key, session_id=session_id, task_id=upload["task_id"])
        require(task.get("status") == "completed", f"Task not completed: {task}")

        report_resp = self.client.request(
            "GET",
            f"/report/{upload['task_id']}",
            headers=self._auth_headers(api_key=self.user_key, session_id=session_id),
        )
        require(report_resp.status_code == 200, f"Report failed: {report_resp.status_code}")
        report = report_resp.json()
        require(report["summary"]["total_matches"] > 0, f"No matches found: {report}")

        download_resp = self.client.request(
            "GET",
            f"/download/{upload['task_id']}",
            headers=self._auth_headers(api_key=self.user_key, session_id=session_id),
        )
        require(download_resp.status_code == 200, f"Download failed: {download_resp.status_code}")
        masked_text = download_resp.text()
        require("192.168.1.100" not in masked_text, "IP address was not masked")
        require("SuperSecret123!" not in masked_text, "Password was not masked")
        return f"task={upload['task_id']} matches={report['summary']['total_matches']}"

    def _scenario_user_whitelist(self) -> str:
        session_id = self._new_session()
        upload = self._upload_file(
            api_key=self.user_key,
            session_id=session_id,
            filename="whitelist.log",
            content=b"server ip=192.168.1.100\n",
            content_type="text/plain",
            whitelist="192.168.1.100",
        )
        task = self._wait_for_task(api_key=self.user_key, session_id=session_id, task_id=upload["task_id"])
        require(task.get("status") == "completed", f"Task not completed: {task}")
        download_resp = self.client.request(
            "GET",
            f"/download/{upload['task_id']}",
            headers=self._auth_headers(api_key=self.user_key, session_id=session_id),
        )
        require(download_resp.status_code == 200, f"Download failed: {download_resp.status_code}")
        require("192.168.1.100" in download_resp.text(), "Whitelist value should be preserved")
        return f"task={upload['task_id']} whitelist preserved"

    def _scenario_user_bad_file(self) -> str:
        session_id = self._new_session()
        resp = self.client.request(
            "POST",
            "/mask",
            headers=self._auth_headers(api_key=self.user_key, session_id=session_id),
            form_fields={"whitelist": ""},
            files={"file": ("photo.png", b"\x89PNG\r\n", "image/png")},
        )
        require(resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text()}")
        return "unsupported file type returned 400"

    def _scenario_user_task_list(self) -> str:
        session_id = self._new_session()
        upload = self._upload_file(
            api_key=self.user_key,
            session_id=session_id,
            filename="tasklist.log",
            content=SAMPLE_TEXT.encode("utf-8"),
            content_type="text/plain",
        )
        self._wait_for_task(api_key=self.user_key, session_id=session_id, task_id=upload["task_id"])
        resp = self.client.request(
            "GET",
            "/tasks",
            headers=self._auth_headers(api_key=self.user_key, session_id=session_id),
        )
        require(resp.status_code == 200, f"List tasks failed: {resp.status_code}")
        tasks = resp.json().get("tasks", [])
        require(any(item.get("task_id") == upload["task_id"] for item in tasks), "Uploaded task not found in list")
        return f"tasks={len(tasks)} includes={upload['task_id']}"

    def _scenario_user_session_isolation(self) -> str:
        owner_session = self._new_session()
        other_session = self._new_session()
        upload = self._upload_file(
            api_key=self.user_key,
            session_id=owner_session,
            filename="isolation.log",
            content=SAMPLE_TEXT.encode("utf-8"),
            content_type="text/plain",
        )
        resp = self.client.request(
            "GET",
            f"/task/{upload['task_id']}",
            headers=self._auth_headers(api_key=self.user_key, session_id=other_session),
        )
        require(resp.status_code == 404, f"Expected 404 from other session, got {resp.status_code}")
        return f"task hidden across sessions ({upload['task_id']})"

    def _scenario_user_rule_detail(self) -> str:
        resp = self.client.request(
            "GET",
            "/rules/ipv4",
            headers=self._auth_headers(api_key=self.user_key),
        )
        require(resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text()}")
        body = resp.json()
        require(body.get("id") == "ipv4", f"Unexpected rule body: {body}")
        return f"rule={body.get('id')} name={body.get('name')}"

    def _scenario_user_suggestions(self) -> str:
        suggestion_name = f"Scenario Suggestion {uuid.uuid4().hex[:8]}"
        resp = self.client.request(
            "POST",
            "/rules/suggestions",
            headers=self._auth_headers(api_key=self.user_key),
            json_body={
                "action": "create",
                "name": suggestion_name,
                "category": "custom",
                "pattern": r"\\bSCENARIO_SECRET_[A-Z0-9]{6}\\b",
                "strategy": "placeholder",
                "placeholder": "[SCENARIO_SECRET]",
                "weight": 6,
                "reason": "Automated scenario coverage",
            },
        )
        require(resp.status_code == 201, f"Suggestion create failed: {resp.status_code} {resp.text()}")
        created = resp.json()["suggestion"]

        listed = self.client.request(
            "GET",
            "/rules/suggestions",
            headers=self._auth_headers(api_key=self.user_key),
        )
        require(listed.status_code == 200, f"List suggestions failed: {listed.status_code}")
        suggestions = listed.json().get("suggestions", [])
        require(any(item.get("id") == created["id"] for item in suggestions), "Created suggestion not found")
        return f"suggestion_id={created['id']} status={created.get('status')}"

    def _scenario_user_zip_masking(self) -> str:
        session_id = self._new_session()
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        try:
            with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("sample.log", SAMPLE_TEXT)
            upload = self._upload_file(
                api_key=self.user_key,
                session_id=session_id,
                filename="bundle.zip",
                content=temp_path.read_bytes(),
                content_type="application/zip",
            )
            task = self._wait_for_task(api_key=self.user_key, session_id=session_id, task_id=upload["task_id"])
            require(task.get("status") == "completed", f"Archive task failed: {task}")
            file_info = task.get("report", {}).get("file_info", {})
            require(file_info.get("is_archive") is True, f"Expected archive report: {task}")
            return f"task={upload['task_id']} files_processed={file_info.get('files_processed')}"
        finally:
            temp_path.unlink(missing_ok=True)

    def _scenario_admin_key_info(self) -> str:
        resp = self.client.request("GET", "/keys/me", headers=self._auth_headers(api_key=self.admin_key))
        require(resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text()}")
        body = resp.json()
        require(body.get("role") == "admin", f"Current key is not admin: {body}")
        return f"name={body.get('name')} role={body.get('role')}"

    def _scenario_admin_list_keys(self) -> str:
        resp = self.client.request("GET", "/keys", headers=self._auth_headers(api_key=self.admin_key))
        require(resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text()}")
        body = resp.json()
        require(body.get("total", 0) >= 1, f"No keys returned: {body}")
        return f"keys={body.get('total')}"

    def _scenario_admin_export_rules(self) -> str:
        resp = self.client.request("GET", "/rules-export", headers=self._auth_headers(api_key=self.admin_key))
        require(resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text()}")
        body = resp.json()
        require(body.get("total", 0) > 0, f"No rules exported: {body}")
        return f"rules={body.get('total')}"

    def _scenario_admin_changelog(self) -> str:
        resp = self.client.request("GET", "/rules/changelog", headers=self._auth_headers(api_key=self.admin_key))
        require(resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text()}")
        body = resp.json()
        require("changelog" in body, f"Unexpected changelog body: {body}")
        return f"entries={body.get('total')}"

    def _scenario_admin_rule_crud(self) -> str:
        rule_id = f"scenario_rule_{uuid.uuid4().hex[:8]}"
        create_resp = self.client.request(
            "POST",
            "/rules",
            headers=self._auth_headers(api_key=self.admin_key),
            json_body={
                "id": rule_id,
                "name": "Scenario Rule",
                "category": "custom",
                "pattern": r"\\bSCENARIO_RULE_[A-Z0-9]{8}\\b",
                "flags": "",
                "strategy": "placeholder",
                "placeholder": "[SCENARIO_RULE]",
                "weight": 5,
                "enabled": True,
            },
        )
        require(create_resp.status_code == 201, f"Create rule failed: {create_resp.status_code} {create_resp.text()}")

        update_resp = self.client.request(
            "PUT",
            f"/rules/{rule_id}",
            headers=self._auth_headers(api_key=self.admin_key),
            json_body={"name": "Scenario Rule Updated", "weight": 9},
        )
        require(update_resp.status_code == 200, f"Update failed: {update_resp.status_code} {update_resp.text()}")

        toggle_resp = self.client.request(
            "PATCH",
            f"/rules/{rule_id}/toggle",
            headers=self._auth_headers(api_key=self.admin_key),
        )
        require(toggle_resp.status_code == 200, f"Toggle failed: {toggle_resp.status_code} {toggle_resp.text()}")

        detail_resp = self.client.request(
            "GET",
            f"/rules/{rule_id}",
            headers=self._auth_headers(api_key=self.admin_key),
        )
        require(detail_resp.status_code == 200, f"Detail failed: {detail_resp.status_code} {detail_resp.text()}")
        detail_body = detail_resp.json()
        require(not self._is_enabled(detail_body.get("enabled")), f"Rule should be disabled after toggle: {detail_body}")

        delete_resp = self.client.request(
            "DELETE",
            f"/rules/{rule_id}",
            headers=self._auth_headers(api_key=self.admin_key),
        )
        require(delete_resp.status_code == 200, f"Delete failed: {delete_resp.status_code} {delete_resp.text()}")
        return f"rule_id={rule_id} updated+toggled+deleted"

    def _scenario_admin_key_lifecycle(self) -> str:
        key_name = f"Scenario Temp Key {uuid.uuid4().hex[:6]}"
        create_resp = self.client.request(
            "POST",
            "/keys",
            headers=self._auth_headers(api_key=self.admin_key),
            json_body={"name": key_name, "role": "user", "expires_days": 7},
        )
        require(create_resp.status_code == 200, f"Create key failed: {create_resp.status_code} {create_resp.text()}")
        created = create_resp.json()

        disable_resp = self.client.request(
            "POST",
            "/keys/disable",
            headers=self._auth_headers(api_key=self.admin_key),
            json_body={"key": created["key"]},
        )
        require(disable_resp.status_code == 200, f"Disable key failed: {disable_resp.status_code} {disable_resp.text()}")
        return f"temp_key={created['name']} created+disabled"

    def _scenario_admin_approve_suggestion(self) -> str:
        rule_id = f"approval_rule_{uuid.uuid4().hex[:8]}"
        create_rule_resp = self.client.request(
            "POST",
            "/rules",
            headers=self._auth_headers(api_key=self.admin_key),
            json_body={
                "id": rule_id,
                "name": "Approval Scenario Rule",
                "category": "custom",
                "pattern": r"\\bAPPROVAL_SCENARIO_[A-Z0-9]{6}\\b",
                "flags": "",
                "strategy": "placeholder",
                "placeholder": "[APPROVAL_SCENARIO]",
                "weight": 5,
                "enabled": True,
            },
        )
        require(create_rule_resp.status_code == 201, f"Temp rule create failed: {create_rule_resp.status_code} {create_rule_resp.text()}")

        try:
            create_resp = self.client.request(
                "POST",
                "/rules/suggestions",
                headers=self._auth_headers(api_key=self.user_key),
                json_body={
                    "rule_id": rule_id,
                    "action": "disable",
                    "reason": "Admin approval scenario coverage",
                },
            )
            require(create_resp.status_code == 201, f"Suggestion create failed: {create_resp.status_code} {create_resp.text()}")
            suggestion = create_resp.json()["suggestion"]

            approve_resp = self.client.request(
                "PATCH",
                f"/rules/suggestions/{suggestion['id']}",
                headers=self._auth_headers(api_key=self.admin_key),
                json_body={"action": "approve"},
            )
            require(approve_resp.status_code == 200, f"Approve failed: {approve_resp.status_code} {approve_resp.text()}")
            approved = approve_resp.json()["suggestion"]
            require(approved.get("status") == "approved", f"Unexpected suggestion status: {approved}")

            detail_resp = self.client.request(
                "GET",
                f"/rules/{rule_id}",
                headers=self._auth_headers(api_key=self.admin_key),
            )
            require(detail_resp.status_code == 200, f"Temp rule detail failed: {detail_resp.status_code} {detail_resp.text()}")
            require(not self._is_enabled(detail_resp.json().get("enabled")), "Approved disable suggestion did not disable the rule")
            return f"suggestion_id={approved['id']} approved for {rule_id}"
        finally:
            self.client.request(
                "DELETE",
                f"/rules/{rule_id}",
                headers=self._auth_headers(api_key=self.admin_key),
            )

    def _print_report(self) -> None:
        total = len(self.results)
        passed = sum(item.status == "PASS" for item in self.results)
        failed = sum(item.status == "FAIL" for item in self.results)
        skipped = sum(item.status == "SKIP" for item in self.results)

        print("# API Scenario Test Report")
        print()
        print(f"- Base URL: `{self.client.base_url}`")
        print(f"- Generated At: `{time.strftime('%Y-%m-%d %H:%M:%S')}`")
        print(f"- Total: `{total}`  Passed: `{passed}`  Failed: `{failed}`  Skipped: `{skipped}`")
        print()
        print("| Role | Scenario | Result | Duration(ms) | Detail |")
        print("|------|----------|--------|--------------|--------|")
        for item in self.results:
            print(
                f"| {item.role} | {item.name} | {item.status} | "
                f"{item.duration_ms} | {item.detail.replace('|', '/')} |"
            )


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run comprehensive API scenarios for users and admins")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL, e.g. http://host:port/api/v1")
    parser.add_argument("--user-key", default=os.getenv("DMS_USER_API_KEY", ""), help="Regular user API key")
    parser.add_argument("--admin-key", default=os.getenv("DMS_ADMIN_API_KEY", ""), help="Administrator API key")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Per-request timeout in seconds")
    parser.add_argument("--full-admin", action="store_true", help="Enable admin write scenarios such as CRUD and key lifecycle")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    client = APIClient(args.base_url, timeout=args.timeout)
    runner = ScenarioRunner(
        client,
        user_key=args.user_key.strip(),
        admin_key=args.admin_key.strip(),
        full_admin=args.full_admin,
    )
    return runner.run_all()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
