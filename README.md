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

## 📡 API 文档

### 上传并脱敏文件

```bash
POST /api/v1/mask
Content-Type: multipart/form-data
X-Session-ID: <your-session-id>

file: <file>
whitelist: localhost,127.0.0.1  # 可选
```

**响应：**
```json
{
  "task_id": "uuid",
  "session_id": "uuid",
  "status": "pending",
  "filename": "system.log",
  "message": "File uploaded successfully. Processing started."
}
```

### 查询任务状态

```bash
GET /api/v1/task/{task_id}
X-Session-ID: <your-session-id>
```

### 下载脱敏文件

```bash
GET /api/v1/download/{task_id}
X-Session-ID: <your-session-id>
```

### 获取脱敏报告

```bash
GET /api/v1/report/{task_id}
X-Session-ID: <your-session-id>
```

### 获取任务列表（仅当前用户）

```bash
GET /api/v1/tasks
X-Session-ID: <your-session-id>
```

### 系统状态

```bash
GET /api/v1/status
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
