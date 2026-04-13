# SUSE Data Masking Service

<p align="center">
  <img src="frontend/public/favicon.svg" width="80" height="80" alt="SUSE Logo">
</p>

<p align="center">
  <strong>Data Masking Service</strong><br>
  Web upload and REST API with 16-thread concurrent processing
</p>

---

## 📚 Documentation Index

- [User & Admin Operation Guide](user-admin-operation-guide.md)
- [5-Minute Quick Start Guide](quick-start-guide.md)
- [Project Status Report](project-status-report.md)
- [Project Summary (EN)](project-summary-en.md)
- [Project Summary (ZH)](project-summary.md)

## ✨ Features

- 🔒 **Smart Masking** - Auto-detect 8 types of sensitive data: IP, MAC, Email, Username, License, etc.
- 🚀 **High Performance** - 16-thread concurrency, chunked processing, 1GB file in 30 seconds
- 🎨 **Modern UI** - SUSE brand style, responsive design, smooth animations
- 📊 **Detailed Reports** - Risk score, category stats, masking examples, JSON export
- 🔐 **Privacy** - Session isolation, users only access their own data
- 🐳 **Containerized** - Docker one-click deployment

## 🚀 Quick Start

### Option 1: Docker Compose (Recommended)

```bash
cd data-masking-service

# Start services
docker-compose up -d

# Access
# Frontend: http://localhost:3000
# API:      http://localhost:8000
```

### Option 2: Local Development

**Backend**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

## 📡 API Reference

Base URL: `http://your-server:8080/api/v1`

### Authentication

All API requests require a `X-Session-ID` header for user isolation:

```http
X-Session-ID: your-unique-session-id
```

> 💡 Session ID is auto-generated in the web interface. For API usage, generate a UUID or use any unique string.

---

### 1. Upload and Mask File

Upload a file for sensitive data masking.

**Request**

```http
POST /mask
Content-Type: multipart/form-data
X-Session-ID: <session-id>
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | file | ✅ | File to mask (text files, logs, archives: .tar.gz, .tgz, .zip) |
| `whitelist` | string | ❌ | Comma-separated values to exclude from masking |

**Example**

```bash
curl -X POST "http://10.146.15.188:8080/api/v1/mask" \
  -H "X-Session-ID: my-session-123" \
  -F "file=@/path/to/system.log" \
  -F "whitelist=localhost,127.0.0.1"
```

**Response** `200 OK`

```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "session_id": "my-session-123",
  "status": "pending",
  "filename": "system.log",
  "message": "File uploaded successfully. Processing started."
}
```

---

### 2. Get Task Status

Query the processing status and results of a masking task.

**Request**

```http
GET /task/{task_id}
X-Session-ID: <session-id>
```

**Example**

```bash
curl "http://10.146.15.188:8080/api/v1/task/a1b2c3d4-e5f6-7890-abcd-ef1234567890" \
  -H "X-Session-ID: my-session-123"
```

**Response** `200 OK`

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
| `pending` | Task queued, waiting for processing |
| `processing` | Masking in progress |
| `completed` | Done, results available |
| `failed` | Error occurred |

---

### 3. Download Masked File

Download the masked (sanitized) file.

**Request**

```http
GET /download/{task_id}
X-Session-ID: <session-id>
```

**Example**

```bash
curl -O "http://10.146.15.188:8080/api/v1/download/a1b2c3d4-e5f6-7890-abcd-ef1234567890" \
  -H "X-Session-ID: my-session-123"
```

---

### 4. Get Masking Report

Get detailed JSON report of the masking operation.

**Request**

```http
GET /report/{task_id}
X-Session-ID: <session-id>
```

**Example**

```bash
curl "http://10.146.15.188:8080/api/v1/report/a1b2c3d4-e5f6-7890-abcd-ef1234567890" \
  -H "X-Session-ID: my-session-123"
```

---

### 5. List My Tasks

Get all tasks for the current session.

**Request**

```http
GET /tasks
X-Session-ID: <session-id>
```

**Example**

```bash
curl "http://10.146.15.188:8080/api/v1/tasks" \
  -H "X-Session-ID: my-session-123"
```

---

### 6. Get Masking Rules

Get available masking rules and their configurations.

**Request**

```http
GET /rules
```

**Example**

```bash
curl "http://10.146.15.188:8080/api/v1/rules"
```

---

### 7. System Status

Check service health and worker status.

**Request**

```http
GET /status
```

**Example**

```bash
curl "http://10.146.15.188:8080/api/v1/status"
```

**Response** `200 OK`

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
| `400` | Bad Request - Invalid parameters |
| `403` | Forbidden - Session mismatch |
| `404` | Not Found - Task not found |
| `500` | Internal Server Error |

## 🔧 Masking Rules

| Rule | Type | Example | Masked |
|------|------|---------|--------|
| IPv4 Address | Network | `192.168.1.100` | `[IPv4]` |
| IPv6 Address | Network | `2001:db8::1` | `[IPv6]` |
| MAC Address | Device | `aa:bb:cc:dd:ee:ff` | `[MAC]` |
| Email Address | Personal | `user@suse.com` | `[EMAIL]` |
| Path Username | System | `/home/john/` | `/home/[USER]` |
| License Key | Secret | `XXXX-YYYY-ZZZZ` | `[LICENSE]` |
| Hostname | System | `sles15-test-01` | `[HOSTNAME]` |
| Username | Personal | `user=admin` | `[USERNAME]` |

## 📊 Risk Score

Risk score is calculated based on sensitive data types and counts:

| Level | Score Range | Description |
|-------|-------------|-------------|
| 🟢 LOW | 0-29 | Low risk, safe to share |
| 🟡 MEDIUM | 30-59 | Medium risk, review recommended |
| 🔴 HIGH | 60-100 | High risk, careful review needed |

## 🏗️ Project Structure

```
data-masking-service/
├── backend/
│   ├── app/
│   │   ├── api/           # API routes
│   │   │   ├── mask.py    # Masking endpoints
│   │   │   └── status.py  # Status endpoints
│   │   ├── core/          # Core modules
│   │   │   ├── executor.py # Thread pool
│   │   │   └── session.py  # Session management
│   │   ├── engine/        # Masking engine
│   │   │   ├── masker.py  # Masking processor
│   │   │   └── rules.py   # Rule definitions
│   │   └── main.py        # App entry
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/    # React components
│   │   ├── services/      # API services
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
└── README.md
```

## 🔐 Privacy Design

- **Session Isolation** - Each user gets unique Session ID
- **Data Isolation** - Users only access their own files and reports
- **Auto Cleanup** - Sessions expire after 2 hours, data auto-deleted
- **Local Processing** - All data processed locally, never leaves network

## 🛠️ Tech Stack

**Backend**
- FastAPI - High-performance Python web framework
- ThreadPoolExecutor - 16-thread concurrent processing
- uvicorn - ASGI server

**Frontend**
- React 18 + TypeScript
- Tailwind CSS - SUSE brand colors
- Framer Motion - Smooth animations
- Recharts - Data visualization
- react-dropzone - File upload

**Deployment**
- Docker + Docker Compose
- Nginx reverse proxy

## 📝 License

MIT License

---

<p align="center">
  Made with 💚 by SUSE QE Team
</p>
