# SUSE Data Masking Service

<p align="center">
  <img src="frontend/public/favicon.svg" width="80" height="80" alt="SUSE Logo">
</p>

<p align="center">
  <strong>一站式数据脱敏服务</strong><br>
  支持网页上传和 REST API，16 线程并发处理
</p>

---

## ✨ 功能特性

- 🔒 **智能脱敏** - 自动识别 IP、MAC、邮箱、用户名、License 等 8 种敏感数据
- 🚀 **高性能** - 16 线程并发，大文件分块处理，1GB 文件 30 秒内完成
- 🎨 **精美界面** - SUSE 品牌风格，响应式设计，流畅动效
- 📊 **详细报告** - 风险评分、分类统计、脱敏示例，支持 JSON 导出
- 🔐 **隐私保护** - Session 隔离，每个用户只能访问自己的数据
- 🐳 **容器化** - Docker 一键部署，开箱即用

## 🖥️ 界面预览

### 主页面
- 拖拽上传文件
- 实时处理进度
- 历史记录（仅显示当前用户）

### 结果页面
- 风险评分可视化
- 敏感字段分布图表
- 脱敏前后对比示例
- 一键下载脱敏文件和报告

## 🚀 快速开始

### 方式一：Docker Compose（推荐）

```bash
# 克隆项目
cd data-masking-service

# 启动服务
docker-compose up -d

# 访问
# 前端: http://localhost:3000
# API:  http://localhost:8000
```

### 方式二：本地开发

**后端**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**前端**
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
  "file_size": 1048576,
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
  "progress": 100,
  "report": {
    "total_matches": 156,
    "risk_score": 72,
    "risk_level": "HIGH",
    "categories": {
      "ipv4": {"count": 45, "examples": ["192.168.1.100 → [IPv4]"]},
      "email": {"count": 23, "examples": ["admin@suse.com → [EMAIL]"]},
      "mac": {"count": 12, "examples": ["aa:bb:cc:dd:ee:ff → [MAC]"]}
    },
    "processing_time": 2.34
  }
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

**Response** `200 OK`

Returns the masked file with `Content-Disposition` header.

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

**Response** `200 OK`

```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "filename": "system.log",
  "original_size": 1048576,
  "masked_size": 1045230,
  "processing_time": 2.34,
  "risk_score": 72,
  "risk_level": "HIGH",
  "summary": {
    "total_matches": 156,
    "unique_values": 89
  },
  "categories": {
    "ipv4": {"count": 45, "weight": 3, "risk_contribution": 27},
    "email": {"count": 23, "weight": 5, "risk_contribution": 23},
    "mac": {"count": 12, "weight": 3, "risk_contribution": 7}
  },
  "timestamp": "2026-01-21T14:30:00Z"
}
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

**Response** `200 OK`

```json
{
  "tasks": [
    {
      "task_id": "a1b2c3d4-...",
      "filename": "system.log",
      "status": "completed",
      "created_at": "2026-01-21T14:25:00Z"
    },
    {
      "task_id": "b2c3d4e5-...",
      "filename": "app.tar.gz",
      "status": "processing",
      "created_at": "2026-01-21T14:28:00Z"
    }
  ]
}
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

**Response** `200 OK`

```json
{
  "rules": [
    {"id": "ipv4", "name": "IPv4 Address", "enabled": true, "weight": 3},
    {"id": "ipv6", "name": "IPv6 Address", "enabled": true, "weight": 3},
    {"id": "mac", "name": "MAC Address", "enabled": true, "weight": 3},
    {"id": "email", "name": "Email Address", "enabled": true, "weight": 5},
    {"id": "path_user", "name": "Path Username", "enabled": true, "weight": 2},
    {"id": "license", "name": "License Key", "enabled": true, "weight": 4},
    {"id": "hostname", "name": "Hostname", "enabled": true, "weight": 2},
    {"id": "username", "name": "Username", "enabled": true, "weight": 3}
  ]
}
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

**Error Response Format**

```json
{
  "detail": "Error message description"
}
```

## 🔧 脱敏规则

| 规则 | 类型 | 示例 | 脱敏后 |
|------|------|------|--------|
| IPv4 地址 | 网络 | `192.168.1.100` | `[IPv4]` |
| IPv6 地址 | 网络 | `2001:db8::1` | `[IPv6]` |
| MAC 地址 | 设备 | `aa:bb:cc:dd:ee:ff` | `[MAC]` |
| 邮箱地址 | 个人 | `user@suse.com` | `[EMAIL]` |
| 路径用户名 | 系统 | `/home/john/` | `/home/[USER]` |
| License Key | 密钥 | `XXXX-YYYY-ZZZZ` | `[LICENSE]` |
| 主机名 | 系统 | `sles15-test-01` | `[HOSTNAME]` |
| 用户名 | 个人 | `user=admin` | `[USERNAME]` |

## 📊 风险评分

风险评分基于敏感数据的类型和数量计算：

| 等级 | 分数范围 | 说明 |
|------|----------|------|
| 🟢 LOW | 0-29 | 低风险，可安全共享 |
| 🟡 MEDIUM | 30-59 | 中风险，建议审查 |
| 🔴 HIGH | 60-100 | 高风险，需仔细检查 |

## 🏗️ 项目结构

```
data-masking-service/
├── backend/
│   ├── app/
│   │   ├── api/           # API 路由
│   │   │   ├── mask.py    # 脱敏接口
│   │   │   └── status.py  # 状态接口
│   │   ├── core/          # 核心模块
│   │   │   ├── executor.py # 线程池
│   │   │   └── session.py  # 会话管理
│   │   ├── engine/        # 脱敏引擎
│   │   │   ├── masker.py  # 脱敏处理
│   │   │   └── rules.py   # 规则定义
│   │   └── main.py        # 应用入口
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/    # React 组件
│   │   │   ├── Header.tsx
│   │   │   ├── FileUpload.tsx
│   │   │   ├── TaskList.tsx
│   │   │   └── ResultView.tsx
│   │   ├── services/      # API 服务
│   │   │   └── api.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
└── README.md
```

## 🔐 隐私设计

- **Session 隔离**：每个用户分配唯一 Session ID
- **数据隔离**：用户只能访问自己上传的文件和报告
- **自动清理**：Session 2 小时后自动过期，数据自动删除
- **内网部署**：全程本地处理，数据不出内网

## 🛠️ 技术栈

**后端**
- FastAPI - 高性能 Python Web 框架
- ThreadPoolExecutor - 16 线程并发处理
- uvicorn - ASGI 服务器

**前端**
- React 18 + TypeScript
- Tailwind CSS - SUSE 品牌配色
- Framer Motion - 流畅动效
- Recharts - 数据可视化
- react-dropzone - 文件上传

**部署**
- Docker + Docker Compose
- Nginx 反向代理

## 📝 License

MIT License

---

<p align="center">
  Made with 💚 by SUSE QE Team
</p>
