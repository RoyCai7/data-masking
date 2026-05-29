# SUSE Data Masking Service

<p align="center">
  <img src="frontend/public/favicon.svg" width="80" height="80" alt="SUSE Logo">
</p>

<p align="center">
  <strong>Data Masking Service</strong><br>
  Web UI + REST API · 16-thread concurrent processing · On-premise LLM rule generation
</p>

---

## 📚 Documentation

- [User & Admin Operation Guide](docs/user-admin-operation-guide.md)

> For daily use, treat [docs/user-admin-operation-guide.md](docs/user-admin-operation-guide.md) as the single source of truth.

## ✨ Features

- 🔒 **Smart Masking** — Auto-detect 8+ sensitive data types: IP, MAC, Email, Username, License, AWS keys, passwords, JWT, etc.
- 🚀 **High Performance** — 16-thread concurrency, chunked processing, 1 GB file in under 30 seconds
- 🎨 **Modern UI** — SUSE brand style, drag-and-drop upload, real-time progress
- 📊 **Detailed Reports** — Risk score, per-rule match counts, original-vs-masked table with file/line references
- 🔐 **Multi-tenant** — Three-level permissions: Admin / Org Owner / User; API Key authentication
- 🤖 **AI Rule Generation** — Describe a pattern in plain English; local LLM (Ollama) generates and tests the regex

## 🚀 Running the Service

### Production server

The service runs on `<SERVER_IP>`.

| Component | Address | Details |
|-----------|---------|---------|
| Web UI + API | `http://<SERVER_IP>:8080` | nginx serves `frontend/dist/`, proxies `/api/` → uvicorn |
| Backend (internal) | `127.0.0.1:8000` | uvicorn, managed by systemd `data-masking.service` |
| LLM | `127.0.0.1:11434` | Ollama via SSH reverse tunnel from Mac |

```bash
# Check service health
curl -s http://<SERVER_IP>:8080/api/v1/status | python3 -m json.tool

# Verify systemd units
ssh root@<SERVER_IP> "systemctl is-active data-masking nginx"
```

### Local development

**Backend**
```bash
cd backend
source venv/bin/activate          # or: python -m venv venv && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev                       # Vite dev server at :5173, proxies /api → localhost:8000
```

**LLM tunnel (optional — needed only for AI rule generation)**
```bash
# Run on Mac, keep open while developing
ollama serve
ssh -R 11434:127.0.0.1:11434 root@<SERVER_IP> -N
```

### Deploy to server

```bash
# Full deploy (code + frontend rebuild)
git add -A && git commit -m "..." && git push
ssh root@<SERVER_IP> "
  cd /opt/data-masking && git fetch origin && git reset --hard origin/main
  cd frontend && npm install --silent && npm run build
  systemctl restart data-masking
"

# Backend-only deploy
git push
ssh root@<SERVER_IP> "cd /opt/data-masking && git reset --hard origin/main && systemctl restart data-masking"
```

## 📡 API Reference

**Base URL:** `http://<SERVER_IP>:8080/api/v1`

### Authentication

All protected endpoints require an API key in the request header:

```http
X-API-Key: dms_your_api_key_here
```

> Public endpoints (no key required): `GET /status`, `GET /rules`, `GET /session`
>
> Generate a key: `python generate_key.py` — or via Admin Console → Keys.

---

### 1. Upload and Mask File

```http
POST /mask
Content-Type: multipart/form-data
X-API-Key: <key>
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | file | ✅ | File to mask — plain text, logs, configs, or archives (`.tar.gz`, `.tgz`, `.zip`) |
| `whitelist` | string | ❌ | Comma-separated values to skip (e.g. `localhost,127.0.0.1`) |

```bash
curl -X POST "http://<SERVER_IP>:8080/api/v1/mask" \
  -H "X-API-Key: dms_your_key" \
  -F "file=@system.log" \
  -F "whitelist=localhost,127.0.0.1"
```

**Response** `200 OK`

```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "session_id": "...",
  "status": "pending",
  "filename": "system.log",
  "message": "File uploaded successfully. Processing started."
}
```

---

### 2. Get Task Status

```http
GET /task/{task_id}
X-API-Key: <key>
```

```bash
curl "http://<SERVER_IP>:8080/api/v1/task/a1b2c3d4-..." \
  -H "X-API-Key: dms_your_key"
```

```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "completed",
  "filename": "system.log",
  "progress": 100
}
```

| Status | Description |
|--------|-------------|
| `pending` | Queued, waiting for a worker slot |
| `processing` | Masking in progress |
| `completed` | Done, file and report ready |
| `failed` | Processing error |

---

### 3. Download Masked File

```http
GET /download/{task_id}
X-API-Key: <key>
```

```bash
curl -O "http://<SERVER_IP>:8080/api/v1/download/a1b2c3d4-..." \
  -H "X-API-Key: dms_your_key"
```

---

### 4. Get Masking Report

```http
GET /report/{task_id}
X-API-Key: <key>
```

```bash
curl "http://<SERVER_IP>:8080/api/v1/report/a1b2c3d4-..." \
  -H "X-API-Key: dms_your_key"
```

Returns a JSON report with risk score, per-category match counts, and an original-vs-masked table with file path and line number for each finding.

---

### 5. List My Tasks

```http
GET /tasks
X-API-Key: <key>
```

```bash
curl "http://<SERVER_IP>:8080/api/v1/tasks" \
  -H "X-API-Key: dms_your_key"
```

---

### 6. Get Masking Rules

```http
GET /rules
```

No authentication required.

```bash
curl "http://<SERVER_IP>:8080/api/v1/rules"
```

---

### 7. System Status

```http
GET /status
```

No authentication required.

```bash
curl "http://<SERVER_IP>:8080/api/v1/status"
```

```json
{
  "service": "SUSE Data Masking Service",
  "version": "1.0.0",
  "status": "healthy",
  "executor": {
    "max_workers": 16,
    "active_tasks": 2,
    "available_slots": 14
  }
}
```

---

### Error Responses

| Code | Description |
|------|-------------|
| `400` | Bad request — invalid parameters |
| `401` | Missing or invalid `X-API-Key` |
| `403` | Key disabled, expired, or insufficient role |
| `404` | Task or resource not found |
| `500` | Internal server error |

---

### Full masking workflow (shell script)

```bash
SERVER="http://<SERVER_IP>:8080/api/v1"
KEY="dms_your_key"
FILE="system.log"

# 1. Upload
TASK_ID=$(curl -s -X POST "$SERVER/mask" \
  -H "X-API-Key: $KEY" -F "file=@$FILE" | jq -r .task_id)

# 2. Poll until done
while [[ $(curl -s "$SERVER/task/$TASK_ID" -H "X-API-Key: $KEY" | jq -r .status) != "completed" ]]; do
  sleep 2
done

# 3. Download
curl -s -O "$SERVER/download/$TASK_ID" -H "X-API-Key: $KEY"
echo "Done."
```

## 🔧 Masking Rules

| Rule | Category | Example | Masked As |
|------|----------|---------|-----------|
| IPv4 Address | Network | `192.168.1.100` | `[IP_ADDRESS]` |
| IPv6 Address | Network | `2001:db8::1` | `[IP_ADDRESS]` |
| MAC Address | Network | `aa:bb:cc:dd:ee:ff` | `[MAC_ADDRESS]` |
| Email Address | Identity | `user@suse.com` | `[EMAIL]` |
| Username | Identity | `user=admin` | `[USERNAME]` |
| Password field | Credential | `password=S3cr3t` | `[PASSWORD]` |
| SSH Private Key | Credential | `-----BEGIN RSA...` | `[SSH_PRIVATE_KEY]` |
| AWS Access Key | Cloud Key | `AKIAIOSFODNN7...` | `[AWS_ACCESS_KEY]` |
| JWT Token | Credential | `eyJhbGci...` | `[JWT_TOKEN]` |
| License Key | License | `Regcode-ABCDE` | `[LICENSE_KEY]` |
| Credit Card | Financial | `4111 1111 1111 1111` | `[CREDIT_CARD]` |

Custom rules can be added via Admin Console or generated using the AI assistant (`llm_add_rule.py`).

## 📊 Risk Score

| Level | Score | Description |
|-------|-------|-------------|
| 🟢 LOW | 0–29 | Low risk, generally safe to share |
| 🟡 MEDIUM | 30–59 | Review recommended before sharing |
| 🔴 HIGH | 60–100 | Contains highly sensitive data |

## 🏗️ Project Structure

```
backend/
  app/
    api/          # FastAPI routers: keys, llm, mask, orgs, rules, status
    core/         # auth, executor, key_service, permissions, session
    engine/       # db, masker, repo_*, rule_service, rules, archive
    main.py
  tests/          # pytest — 219 tests
  requirements.txt
frontend/
  src/
    components/   # AdminConsole, AiRegexPanel, FileUpload, Header, Modal,
                  # MyOrg, ResultView, RuleList, Settings, SuggestRule, TaskList
    hooks/        # useAiRegex, useModalA11y
    services/     # api.ts
  e2e/            # Playwright smoke tests — 39 tests
```

## 🔐 Permission Model

| Role | Capabilities |
|------|-------------|
| `admin` | Manage all keys, rules, orgs; approve AI suggestions |
| `org_owner` | Manage their org's rules and users |
| `user` | Upload files, view own tasks, submit AI rule suggestions |

## 🛠️ Tech Stack

**Backend:** FastAPI · SQLite · uvicorn · Python `ThreadPoolExecutor` (16 threads)

**Frontend:** React 18 + TypeScript · Vite · Tailwind CSS

**Infrastructure:** nginx (`:8080`) · systemd · Ollama (`qwen2.5-coder:7b`) via SSH tunnel

## 🧪 Testing

```bash
# Unit + integration tests
cd backend && python -m pytest tests/ -q    # 219 tests

# E2E tests (requires server at <SERVER_IP>:8080)
cd frontend && npx playwright test e2e/smoke.spec.ts --reporter=line   # 39 tests
```

## 📝 License

MIT License

---

<p align="center">
  Made with 💚 by SUSE QE Team
</p>
