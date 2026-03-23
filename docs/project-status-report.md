# DMS 项目状态与计划报告

> **报告日期**：2026-03-23（W4）  
> **项目周期**：2026-02-23 – 2027-02-22（52 周）  
> **团队**：Roy Cai, Richard Fan

---

## 一、模块完成状态总览

| 模组 | 计划目标 | 当前状态 | 完成度 |
|------|---------|---------|:------:|
| **Web UI（文件上传）** | 拖拽上传、实时进度、可视化风险报告 | ✅ 已实现 | **90%** |
| **REST API（系统集成）** | FastAPI 接口、CI/CD 集成 | ✅ 基础已实现，缺认证/限流 | **70%** |
| **Tampermonkey 脚本（浏览器助手）** | 实时监控 Bugzilla/ChatGPT 等页面 | ❌ 完全未开发 | **0%** |

---

## 二、已完成功能清单 ✅

| # | 功能模块 | 说明 | 代码位置 |
|---|---------|------|---------|
| 1 | FastAPI 框架 | CORS、路由注册、SPA 静态服务、OpenAPI 文档 | `backend/app/main.py` |
| 2 | 正则脱敏引擎 | 支持分块并行处理（chunk_size=5000行） | `backend/app/engine/masker.py` |
| 3 | 8 条脱敏规则 | IPv4, IPv6, MAC, Email, Path Username, License, Hostname, Username | `backend/app/engine/rules.py` |
| 4 | 4 种脱敏策略 | ASTERISK（星号）、PLACEHOLDER（占位符）、PARTIAL（部分隐藏）、HASH | `backend/app/engine/rules.py` |
| 5 | 压缩包处理 | .tar.gz / .tgz / .tar.bz2 / .tar.xz / .zip 解包→脱敏→重打包 | `backend/app/engine/archive.py` |
| 6 | 16 线程并发 | ThreadPoolExecutor + asyncio Semaphore 控制 | `backend/app/core/executor.py` |
| 7 | Session 隔离 | UUID Session、2小时过期、自动清理存储 | `backend/app/core/session.py` |
| 8 | 7 个 REST 端点 | `/mask`, `/task/{id}`, `/tasks`, `/download/{id}`, `/report/{id}`, `/rules`, `/status` | `backend/app/api/mask.py` |
| 9 | Web UI 上传 | react-dropzone 拖拽、白名单输入、500MB 限制 | `frontend/src/components/FileUpload.tsx` |
| 10 | 任务列表 & 进度 | 1s 轮询刷新、进度条动画、历史记录 | `frontend/src/components/TaskList.tsx` |
| 11 | 可视化报告 | 风险评分仪表盘、Recharts 柱状图、脱敏示例表格 | `frontend/src/components/ResultView.tsx` |
| 12 | 文件下载 | 脱敏后文件 + JSON 报告双下载 | `frontend/src/components/ResultView.tsx` |
| 13 | Docker 部署 | docker-compose 前后端容器化 | `docker-compose.yml` |
| 14 | API 文档 | README 含 7 个接口完整 curl 示例 | `README.md` |

---

## 三、未完成功能清单 ❌

### 🔴 高优先级

| # | 功能 | 计划阶段 | 详细说明 | 预估工时 |
|---|------|---------|---------|:--------:|
| 1 | **Tampermonkey 浏览器脚本** | Phase 2 (W9–W20) | 三大核心模组之一，需从零开发。包括：页面 DOM 监听、输入/粘贴事件拦截、正则匹配脱敏、多站点配置（Bugzilla, ChatGPT, Jira）、GM_xmlhttpRequest API 调用 | 3–4 周 |
| 2 | **API 认证机制** | Phase 2 (W9–W20) | 当前 X-Session-ID 可随意伪造，需引入 API Key / JWT Token 认证 | 1 周 |
| 3 | **API 速率限制** | Phase 2 (W9–W20) | 无 rate limiter，可被恶意刷接口。需引入 slowapi 或自定义限流中间件 | 0.5 周 |

### 🟡 中优先级

| # | 功能 | 计划阶段 | 详细说明 | 预估工时 |
|---|------|---------|---------|:--------:|
| 4 | **SQLite 规则库** | Phase 2 | 技术栈中计划使用 SQLite 持久化规则，当前规则硬编码在 Python 列表中 | 1 周 |
| 5 | **规则管理 CRUD API** | Phase 2 | `/rules` 仅 GET 只读，缺少 POST/PUT/DELETE 端点用于动态管理规则 | 1 周 |
| 6 | **规则扩充至 20+ 类型** | Phase 3 (W21–W36) | 当前 8 条，需补充：电话号码、身份证号、URL/域名、密码字段、API Key/Secret、信用卡号、CIDR 子网、证书序列号、SSH Key、AWS ARN 等 | 2 周 |
| 7 | **WebSocket 实时通信** | Phase 3 | 技术栈描述支持 WebSocket，当前前端用 1s 轮询。需引入 FastAPI WebSocket 端点推送进度 | 1.5 周 |
| 8 | **大文件流式处理** | Phase 3 | 当前 `file.read()` 全量读入内存，1GB 文件会 OOM。需改为流式分块读写 | 2 周 |
| 9 | **单元测试** | Phase 3 | 零测试文件，KPI 要求 ≥ 70% 覆盖率。需 pytest + coverage 配置 | 2–3 周 |
| 10 | **集成测试** | Phase 2 | 无端到端测试用例，QE 团队需参与 | 1–2 周 |
| 11 | **数据加密** | Phase 4 (W37–W52) | 传输层无 HTTPS；存储层 /tmp 明文。需 TLS + 文件加密 | 1 周 |
| 12 | **审计日志** | Phase 4 | 仅 console 输出，无持久化审计日志系统 | 1 周 |

### 🟠 低优先级

| # | 功能 | 计划阶段 | 详细说明 | 预估工时 |
|---|------|---------|---------|:--------:|
| 13 | **Kubernetes 部署** | Phase 4 | 无 K8s manifests / Helm chart，仅有 docker-compose | 1–2 周 |
| 14 | **安全审计** | Phase 4 | 未进行安全扫描（Bandit/Trivy）或渗透测试 | 1 周 |
| 15 | **用户培训文档** | Phase 4 | 仅有 README，缺少 User Guide、Quick Start、管理员手册 | 1–2 周 |
| 16 | **性能基准测试** | Phase 4 | 无 benchmark 脚本，无法量化处理速度达标情况 | 0.5 周 |

---

## 四、KPI 达标分析

| 指标 | 目标 | 当前实际 | 差距 |
|------|------|---------|------|
| 处理速度 | < 30 秒 / 100MB | ⚠️ 未基准测试，大文件全量读入内存有瓶颈 | 需流式处理 + benchmark 验证 |
| 检测准确率 | ≥ 95% | ⚠️ 8 条规则覆盖有限，未做误报/漏报测试 | 需规则扩充 + 精度评估数据集 |
| 并发能力 | ≥ 8 并行任务 | ✅ 16 Workers Semaphore 已支持 | 已达标 |
| 团队覆盖 | ≥ 2 个 QE 团队 | ❌ 0 个团队在用 | 需上线推广 |

---

## 五、按阶段推进计划

### Phase 1：核心基础（W1–W8）— 进度 100% ✅

```
[██████████████████░] 95%
```

| 任务 | 状态 |
|------|:----:|
| FastAPI 后端框架 | ✅ |
| 正则脱敏引擎 | ✅ |
| Web UI 基础上传 | ✅ |
| 压缩包支持 | ✅ |
| Hyperv 部署 | ✅ |

### Phase 2：功能完备（W9–W20）— 进度 10% 🔴

```
[██░░░░░░░░░░░░░░░░░] 10%
```

| 任务 | 状态 | 计划周 |
|------|:----:|--------|
| API 认证（JWT/API Key） | ❌ | W9–W10 |
| API 速率限制 | ❌ | W10 |
| SQLite 规则库 | ❌ | W11–W12 |
| 规则管理 CRUD API | ❌ | W12–W13 |
| Tampermonkey 脚本 v1 | ❌ | W13–W17 |
| 集成测试 (QE) | ❌ | W18–W20 |

### Phase 3：性能与规则增强（W21–W36）— 进度 0% ❌

```
[░░░░░░░░░░░░░░░░░░░] 0%
```

| 任务 | 状态 | 计划周 |
|------|:----:|--------|
| 规则扩充至 20+ 类型 | ❌ | W21–W23 |
| 大文件流式处理优化 | ❌ | W24–W26 |
| WebSocket 替换轮询 | ❌ | W27–W28 |
| 单元测试 ≥70% 覆盖率 | ❌ | W29–W32 |
| UI/UX 优化 | ❌ | W33–W35 |
| v1.0 发布 | ❌ | W36 |

### Phase 4：上线与交付（W37–W52）— 进度 0% ❌

```
[░░░░░░░░░░░░░░░░░░░] 0%
```

| 任务 | 状态 | 计划周 |
|------|:----:|--------|
| HTTPS / 数据加密 | ❌ | W37–W38 |
| 审计日志系统 | ❌ | W39–W40 |
| 安全审计 & 漏洞修复 | ❌ | W41–W43 |
| K8s 部署配置 | ❌ | W44–W46 |
| 用户培训文档 | ❌ | W47–W49 |
| 生产环境部署 & 培训 | ❌ | W50–W52 |

---

## 六、风险与建议

| 风险 | 影响 | 建议 |
|------|------|------|
| Tampermonkey 脚本零基础 | 三大模组缺一，影响项目完整度 | W5 起提前调研 GM API，W9 正式开发 |
| 大文件内存溢出 | 1GB 文件无法处理 | Phase 2 末期开始流式改造 |
| 无测试覆盖 | 质量无法保障，KPI 不达标 | 每个 Phase 补充对应测试 |
| 规则硬编码 | 无法动态管理，运维困难 | SQLite 迁移优先于规则扩充 |
| 安全认证缺失 | API 可被未授权访问 | Phase 2 首要任务 |

---

## 七、下一步行动（W5–W8）

1. ✅ 正式发布 v0.5 MVP tag
2. 🔨 调研 Tampermonkey GM API + 多站点注入方案
3. 🔨 引入 FastAPI 认证中间件（JWT 或 API Key）
4. 🔨 集成 slowapi 速率限制
5. 🔨 搭建 pytest 框架，编写引擎核心单元测试

---

*报告由项目代码全量分析自动生成 | DMS Project W4 Status Report*
