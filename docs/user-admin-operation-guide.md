# SUSE Data Masking Service 使用手册

## 1. 文档目标

本文档基于当前已部署的 SUSE Data Masking Service，说明两类角色的使用方法：

- 普通用户
- 管理员

覆盖内容包括：

- Web 界面操作
- API 调用方式
- API Key 使用
- 规则查看与更新
- 常见问题与排障

---

## 2. 系统访问地址

### 2.1 Web 入口

生产环境访问地址：

- `http://10.146.15.188:8080`

### 2.2 API 入口

API Base URL：

- `http://10.146.15.188:8080/api/v1`

### 2.3 Swagger 文档

交互式 API 文档：

- `http://10.146.15.188:8080/docs`

---

## 3. 角色说明

## 3.1 普通用户

普通用户可执行以下操作：

- 上传文件并脱敏
- 查看自己的任务列表
- 下载脱敏结果
- 下载 JSON 报告
- 查看自己的 API Key 信息
- 轮换自己的 API Key
- 提交规则建议
- 查看自己提交的建议

普通用户**不能**执行以下操作：

- 创建规则
- 修改规则
- 删除规则
- 启用/禁用规则
- 导入/导出规则
- 审批规则建议
- 管理其他人的 API Key

## 3.2 管理员

管理员拥有普通用户的全部能力，另外还可以：

- 创建 API Key
- 禁用 API Key
- 查看全部 API Key 列表
- 创建规则
- 修改规则
- 删除自定义规则
- 启用/禁用规则
- 导入/导出规则
- 查看规则变更历史
- 审批或拒绝规则建议

---

## 4. 认证与隔离机制

系统有两套机制：

### 4.1 Session 隔离

用于隔离每个用户自己的任务与文件。

- Web 页面会自动生成并保存 `X-Session-ID`
- API 调用时，如访问任务相关接口，需要带上 `X-Session-ID`

示例：

```http
X-Session-ID: 5f6fd5de-7d1f-4e6f-a9f5-8fa4a8bb4b2f
```

### 4.2 API Key 认证

用于权限控制。

- 公共接口：无需 API Key 也可访问
- 管理接口：必须携带 `X-API-Key`
- 个人密钥接口：必须携带 `X-API-Key`

示例：

```http
X-API-Key: dms_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 5. 普通用户操作手册

## 5.1 Web 方式：上传并脱敏文件

### 步骤 1：打开系统

访问：

- `http://10.146.15.188:8080`

### 步骤 2：上传文件

在首页上传区域可以：

- 拖拽文件到页面
- 点击选择文件

当前支持：

### 文本文件

- `.txt`
- `.log`
- `.csv`
- `.json`
- `.yaml`
- `.yml`
- `.ini`
- `.conf`

### 归档文件

- `.tar.gz`
- `.tgz`
- `.tar.bz2`
- `.tbz2`
- `.tar.xz`
- `.txz`
- `.tar`
- `.zip`

限制：

- 单文件最大 500 MB

### 步骤 3：设置白名单（可选）

白名单用于排除不希望被脱敏的关键词，例如：

```text
localhost,127.0.0.1,my-test-domain
```

### 步骤 4：开始处理

点击 `Start Masking`。

系统会：

1. 创建任务
2. 后台处理文件
3. 在任务列表中显示状态

### 步骤 5：查看结果

处理完成后，可查看：

- 风险分数
- 命中规则数量
- 每条规则的命中次数
- 示例替换结果
- 总行数 / 文件数
- 处理耗时

### 步骤 6：下载结果

在结果页可下载：

- 脱敏后的文件
- JSON 报告

---

## 5.2 Web 方式：设置自己的 API Key

页面右上角点击：

- `Key`

在弹窗中：

1. 粘贴 API Key
2. 点击 `Save`
3. 系统会自动保存到浏览器本地存储

说明：

- 输入框当前默认明文显示，便于粘贴和校验
- 可通过眼睛按钮切换显示/隐藏

---

## 5.3 Web 方式：查看自己的 Key 信息

保存 API Key 后，设置弹窗会显示：

- Owner
- Role
- Created
- Expires
- 当前 Key 的部分预览

如果 API Key 无效、已过期或已禁用，界面会报错。

---

## 5.4 Web 方式：轮换自己的 API Key

如果当前用户希望更换密钥：

1. 打开 `Key` 设置窗口
2. 点击 `Rotate`
3. 确认操作
4. 系统会生成一把新 key，并自动禁用旧 key

注意：

- 新 key 只会完整显示一次
- 必须及时复制保存
- 浏览器会自动更新为新 key

---

## 5.5 API 方式：上传文件并查看结果

### 5.5.1 创建会话（可选）

```bash
curl -X POST http://10.146.15.188:8080/api/v1/session
```

返回：

```json
{
  "session_id": "...",
  "message": "Session created successfully"
}
```

### 5.5.2 上传文件

```bash
curl -X POST http://10.146.15.188:8080/api/v1/mask \
  -H "X-Session-ID: <session_id>" \
  -F "file=@./sample.log" \
  -F "whitelist=localhost,127.0.0.1"
```

返回：

```json
{
  "task_id": "...",
  "session_id": "...",
  "status": "pending",
  "filename": "sample.log",
  "message": "File uploaded successfully. Processing started."
}
```

### 5.5.3 查询任务状态

```bash
curl http://10.146.15.188:8080/api/v1/task/<task_id> \
  -H "X-Session-ID: <session_id>"
```

### 5.5.4 列出当前会话全部任务

```bash
curl http://10.146.15.188:8080/api/v1/tasks \
  -H "X-Session-ID: <session_id>"
```

### 5.5.5 下载脱敏文件

```bash
curl http://10.146.15.188:8080/api/v1/download/<task_id> \
  -H "X-Session-ID: <session_id>" \
  -o masked_output.dat
```

### 5.5.6 获取 JSON 报告

```bash
curl http://10.146.15.188:8080/api/v1/report/<task_id> \
  -H "X-Session-ID: <session_id>"
```

---

## 5.6 普通用户可访问的公共接口

### 查看系统状态

```bash
curl http://10.146.15.188:8080/api/v1/status
```

### 查看规则列表

```bash
curl http://10.146.15.188:8080/api/v1/rules
```

### 查看单条规则详情

```bash
curl http://10.146.15.188:8080/api/v1/rules/ipv4
```

---

## 5.7 普通用户提交规则建议

如果发现漏脱敏或误脱敏，可以提交建议。

### 提交新规则建议

```bash
curl -X POST http://10.146.15.188:8080/api/v1/rules/suggestions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your_api_key>" \
  -d '{
    "action": "create",
    "name": "Kubernetes Token",
    "category": "secret",
    "pattern": "k8s_[A-Za-z0-9_-]{20,}",
    "flags": "",
    "strategy": "placeholder",
    "placeholder": "[K8S_TOKEN]",
    "weight": 8,
    "reason": "Need to mask k8s service tokens"
  }'
```

### 提交修改建议

```bash
curl -X POST http://10.146.15.188:8080/api/v1/rules/suggestions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your_api_key>" \
  -d '{
    "rule_id": "ipv4",
    "action": "modify",
    "pattern": "...",
    "reason": "Need broader IPv4 matching"
  }'
```

### 查看自己提交的建议

```bash
curl http://10.146.15.188:8080/api/v1/rules/suggestions \
  -H "X-API-Key: <your_api_key>"
```

说明：

- 普通用户只能看到自己提交的建议
- 管理员能看到全部建议

---

## 6. 管理员操作手册

## 6.1 获取管理员 API Key

管理员 key 可以由服务器侧 CLI 创建。

在服务器执行：

```bash
cd /opt/data-masking
python3.11 generate_key.py create --name "Admin User" --role admin
```

或使用虚拟环境：

```bash
cd /opt/data-masking
source backend/venv/bin/activate
python generate_key.py create --name "Admin User" --role admin
```

创建后请保存输出中的完整 key。

---

## 6.2 管理员 Web 使用方式

管理员在 Web 中主要用于：

- 设置自己的 API Key
- 访问 Swagger 文档测试管理接口
- 使用普通用户上传能力验证规则效果

当前前端主要提供文件脱敏与个人 key 管理；规则管理类操作更适合通过 Swagger 或 API 调用完成。

---

## 6.3 管理员 API：管理 API Key

### 创建新用户 key

```bash
curl -X POST http://10.146.15.188:8080/api/v1/keys \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <admin_api_key>" \
  -d '{
    "name": "Roy Cai",
    "role": "user",
    "expires_days": 365
  }'
```

### 创建新管理员 key

```bash
curl -X POST http://10.146.15.188:8080/api/v1/keys \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <admin_api_key>" \
  -d '{
    "name": "Ops Admin",
    "role": "admin",
    "expires_days": 365
  }'
```

### 查看所有 key

```bash
curl http://10.146.15.188:8080/api/v1/keys \
  -H "X-API-Key: <admin_api_key>"
```

### 禁用某个 key

```bash
curl -X POST http://10.146.15.188:8080/api/v1/keys/disable \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <admin_api_key>" \
  -d '{
    "key": "dms_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  }'
```

---

## 6.4 管理员 API：查看规则

### 查看全部规则

```bash
curl http://10.146.15.188:8080/api/v1/rules
```

### 只看启用规则

```bash
curl 'http://10.146.15.188:8080/api/v1/rules?enabled_only=true'
```

### 按分类查看

```bash
curl 'http://10.146.15.188:8080/api/v1/rules?category=network'
```

### 查看单条规则详情

```bash
curl http://10.146.15.188:8080/api/v1/rules/aws_access_key
```

---

## 6.5 管理员 API：创建规则

```bash
curl -X POST http://10.146.15.188:8080/api/v1/rules \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <admin_api_key>" \
  -d '{
    "id": "k8s_secret_token",
    "name": "Kubernetes Secret Token",
    "category": "secret",
    "pattern": "k8s_[A-Za-z0-9_-]{20,}",
    "flags": "",
    "strategy": "placeholder",
    "placeholder": "[K8S_SECRET_TOKEN]",
    "weight": 8,
    "enabled": true
  }'
```

字段说明：

- `id`：规则唯一标识
- `name`：显示名称
- `category`：分类
- `pattern`：正则表达式
- `flags`：如 `IGNORECASE`
- `strategy`：`asterisk | placeholder | partial | hash`
- `placeholder`：替换文本
- `weight`：风险权重
- `enabled`：是否启用

---

## 6.6 管理员 API：更新规则

```bash
curl -X PUT http://10.146.15.188:8080/api/v1/rules/k8s_secret_token \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <admin_api_key>" \
  -d '{
    "pattern": "k8s_[A-Za-z0-9_-]{16,}",
    "weight": 9,
    "placeholder": "[K8S_TOKEN]"
  }'
```

说明：

- 只需传需要修改的字段
- 更新后内存缓存会自动刷新

---

## 6.7 管理员 API：启用 / 禁用规则

```bash
curl -X PATCH http://10.146.15.188:8080/api/v1/rules/k8s_secret_token/toggle \
  -H "X-API-Key: <admin_api_key>"
```

说明：

- 该接口会在启用和禁用之间切换
- 适合临时关闭某条规则而不是删除它

---

## 6.8 管理员 API：删除规则

```bash
curl -X DELETE http://10.146.15.188:8080/api/v1/rules/k8s_secret_token \
  -H "X-API-Key: <admin_api_key>"
```

注意：

- 只能删除自定义规则
- 内置规则不能删除，只能 `toggle`

---

## 6.9 管理员 API：导出与导入规则

### 导出全部规则

```bash
curl http://10.146.15.188:8080/api/v1/rules-export \
  -H "X-API-Key: <admin_api_key>" \
  -o rules-export.json
```

### 导入规则

```bash
curl -X POST http://10.146.15.188:8080/api/v1/rules-import \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <admin_api_key>" \
  --data @rules-export.json
```

导入规则时：

- 已存在的 `id` 会更新
- 不存在的 `id` 会新建
- 导入后缓存自动刷新

---

## 6.10 管理员 API：审批建议

### 查看全部建议

```bash
curl http://10.146.15.188:8080/api/v1/rules/suggestions \
  -H "X-API-Key: <admin_api_key>"
```

### 只看待审批建议

```bash
curl 'http://10.146.15.188:8080/api/v1/rules/suggestions?status=pending' \
  -H "X-API-Key: <admin_api_key>"
```

### 审批通过

```bash
curl -X PATCH http://10.146.15.188:8080/api/v1/rules/suggestions/1 \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <admin_api_key>" \
  -d '{"action": "approve"}'
```

### 拒绝建议

```bash
curl -X PATCH http://10.146.15.188:8080/api/v1/rules/suggestions/1 \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <admin_api_key>" \
  -d '{"action": "reject"}'
```

说明：

- `approve` 后，建议会自动应用到规则库
- 应用成功后缓存自动刷新

---

## 6.11 管理员 API：查看规则变更历史

### 查看最近 50 条变更

```bash
curl http://10.146.15.188:8080/api/v1/rules/changelog \
  -H "X-API-Key: <admin_api_key>"
```

### 查看某条规则的变更历史

```bash
curl 'http://10.146.15.188:8080/api/v1/rules/changelog?rule_id=ipv4&limit=20' \
  -H "X-API-Key: <admin_api_key>"
```

---

## 7. 存储与更新机制说明

当前规则系统采用：

- SQLite 持久化存储
- 内存缓存加速读取

### 规则存储位置

服务器默认数据库文件：

```text
/opt/data-masking/backend/rules.db
```

### 存储内容

数据库中主要有三张表：

- `rules`
- `rule_suggestions`
- `rule_changelog`

### 更新机制

管理操作执行后会：

1. 写入 SQLite
2. 写入变更日志
3. 自动刷新服务内存缓存

因此，**不需要重启服务即可让新规则生效**。

---

## 8. 常见操作建议

## 8.1 普通用户推荐流程

1. 打开 Web 页面
2. 点击右上角 `Key`，保存自己的 API Key
3. 上传文件
4. 查看结果
5. 下载脱敏文件和报告
6. 如发现规则问题，提交建议

## 8.2 管理员推荐流程

1. 创建或确认管理员 key
2. 在 `/docs` 中测试管理接口
3. 先导出规则备份
4. 再创建 / 修改 / toggle 规则
5. 用实际样例文件回归测试
6. 查看 changelog 确认记录完整

---

## 9. 常见问题

## 9.1 上传时报 401

原因：

- 当前接口需要 API Key
- 浏览器中未保存 key
- key 已失效 / 被禁用

处理：

- 点右上角 `Key`
- 重新粘贴有效 key
- 点击 `Save`

## 9.2 上传时报 413

原因：

- 文件超过 500 MB

处理：

- 压缩文件
- 分拆文件后再上传

## 9.3 看不到自己的历史任务

原因：

- 当前浏览器保存的 `X-Session-ID` 与当时上传时不同

处理：

- 尽量在同一浏览器会话中操作
- API 调用时固定使用同一个 `X-Session-ID`

## 9.4 规则改了但没有生效

正常情况下不会发生，因为规则更新后会自动刷新缓存。

可检查：

- 是否更新的是正确的规则 `id`
- 是否被 `toggle` 为禁用
- 正则是否写错
- 上传样例是否确实命中该规则

## 9.5 管理员无法修改规则

检查：

- 是否使用了 admin key
- 请求头里是否带了 `X-API-Key`
- key 是否已过期或被禁用

---

## 10. 最小可用命令清单

## 普通用户

```bash
# 查看状态
curl http://10.146.15.188:8080/api/v1/status

# 创建 session
curl -X POST http://10.146.15.188:8080/api/v1/session

# 上传文件
curl -X POST http://10.146.15.188:8080/api/v1/mask \
  -H "X-Session-ID: <session_id>" \
  -F "file=@./sample.log"
```

## 管理员

```bash
# 查看规则
curl http://10.146.15.188:8080/api/v1/rules

# 创建规则
curl -X POST http://10.146.15.188:8080/api/v1/rules \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <admin_api_key>" \
  -d '{
    "id": "demo_rule",
    "name": "Demo Rule",
    "category": "custom",
    "pattern": "DEMO_[A-Za-z0-9]+",
    "strategy": "placeholder",
    "placeholder": "[DEMO]",
    "weight": 5,
    "enabled": true
  }'

# 导出规则
curl http://10.146.15.188:8080/api/v1/rules-export \
  -H "X-API-Key: <admin_api_key>" \
  -o rules-export.json
```

---

## 11. 文档结论

当前系统适合两类使用方式：

- 普通用户：以 Web 上传和结果下载为主
- 管理员：以 API / Swagger 做配置与治理为主

推荐实践：

- 普通用户使用 Web
- 管理员使用 `/docs` 或 `curl`
- 规则调整前先导出备份
- 规则调整后用真实样例回归验证
