# Data Masking CLI 使用指南

通过 HTTP API 对文本文件进行脱敏处理，无需打开浏览器。

---

## 环境信息

| 项目 | 值 |
|---|---|
| 服务地址 | `http://10.146.15.188:8080` |
| API Base | `/api/v1` |
| API Key | `dms_3be8006031f045d3aafdc6c78282f2e4` |

设置环境变量方便复用：

```bash
export API_BASE="http://10.146.15.188:8080/api/v1"
export API_KEY="dms_3be8006031f045d3aafdc6c78282f2e4"
```

---

## 快速脱敏（一条命令）

上传文件并自动等待完成、打印脱敏结果：

```bash
python3 - <<'EOF'
import sys, json, time, urllib.request

API_BASE = "http://10.146.15.188:8080/api/v1"
API_KEY  = "dms_3be8006031f045d3aafdc6c78282f2e4"
FILE     = "test_data.txt"

headers = {"X-API-Key": API_KEY}

# 1. 上传文件
import urllib.parse, mimetypes
boundary = "----FormBoundary7MA4YWxkTrZu0gW"
with open(FILE, "rb") as f:
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{FILE}\"\r\n"
        f"Content-Type: text/plain\r\n\r\n"
    ).encode() + f.read() + f"\r\n--{boundary}--\r\n".encode()

req = urllib.request.Request(
    f"{API_BASE}/mask",
    data=body,
    headers={**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"}
)
task_id = json.loads(urllib.request.urlopen(req).read())["task_id"]
print(f"[*] Task ID: {task_id}", file=sys.stderr)

# 2. 轮询状态
for _ in range(30):
    req = urllib.request.Request(f"{API_BASE}/task/{task_id}", headers=headers)
    status = json.loads(urllib.request.urlopen(req).read())["status"]
    if status in ("completed", "failed"):
        print(f"[*] Status: {status}", file=sys.stderr)
        break
    time.sleep(0.5)

# 3. 下载结果
req = urllib.request.Request(f"{API_BASE}/download/{task_id}", headers=headers)
print(urllib.request.urlopen(req).read().decode())
EOF
```

---

## 分步操作（推荐用于调试）

### Step 1 — 上传文件

```bash
RESPONSE=$(curl -s -X POST "$API_BASE/mask" \
  -H "X-API-Key: $API_KEY" \
  -F "file=@test_data.txt")

TASK_ID=$(echo $RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
SESSION_ID=$(echo $RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")

echo "Task ID:    $TASK_ID"
echo "Session ID: $SESSION_ID"
```

---

### Step 2 — 查询任务状态

```bash
TASK_ID="abc123"
SESSION_ID="sess456"

curl -s "$API_BASE/task/$TASK_ID" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Session-ID: $SESSION_ID" \
  | python3 -m json.tool
```

`status` 字段说明：

| 值 | 含义 |
|---|---|
| `pending` | 等待处理 |
| `processing` | 处理中 |
| `completed` | 完成 |
| `failed` | 失败 |

---

### Step 3 — 下载脱敏结果

```bash
# 打印到终端
curl -s "$API_BASE/download/$TASK_ID" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Session-ID: $SESSION_ID"

# 保存到文件
curl -s "$API_BASE/download/$TASK_ID" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Session-ID: $SESSION_ID" \
  -o test_data.masked.txt
```

---

## 带白名单（跳过指定内容）

用逗号分隔多个白名单词，包含这些词的匹配项将被跳过：

```bash
curl -s -X POST "$API_BASE/mask" \
  -H "X-API-Key: $API_KEY" \
  -F "file=@test_data.txt" \
  -F "whitelist=INTERNAL-USE-ONLY-0a00-3e4a,43678356f84d44ed"
```

---

## 查看当前规则列表

```bash
curl -s "$API_BASE/rules" \
  -H "X-API-Key: $API_KEY" \
  | python3 -m json.tool
```

只看规则名称和 ID：

```bash
curl -s "$API_BASE/rules" \
  -H "X-API-Key: $API_KEY" \
  | python3 -c "
import sys, json
for r in json.load(sys.stdin):
    status = '✓' if r.get('enabled') else '✗'
    print(f\"{status} [{r['id']}] {r['name']}\")
"
```

---

## test_data.txt 脱敏预期结果

| 原始内容 | 脱敏后 | 规则 |
|---|---|---|
| `REGCODE=43678356f84d44ed` | `[SCC_REGCODE]` | SCC Registration Code |
| `REGCODE=INTERNAL-USE-ONLY-0a00-3e4a` | `[SCC_REGCODE]` | SCC Registration Code |
| `INTERNAL-USE-ONLY-abcd-1234` | `[MASKED]` | (内置规则) |
| `43678356f84d44ed`（独立 hex） | `[MASKED_HEX]` | 16-Char Hex Token |
| `-----BEGIN RSA PRIVATE KEY-----` … 整块 | `[REDACTED_FULL_PRIVATE_KEY]` | Full SSH Private Key |
| `-----BEGIN OPENSSH PRIVATE KEY-----` … 整块 | `[REDACTED_FULL_PRIVATE_KEY]` | Full SSH Private Key |
| `ssh-rsa AAAA...` | `[SSH_KEY]` | SSH Public Key |
| `ssh-ed25519 AAAA...` | `[SSH_KEY]` | SSH Public Key |

---

## 服务状态检查

```bash
# 检查服务是否在线
curl -s "$API_BASE/status"

# 查看 API 文档（浏览器打开）
open http://10.146.15.188:8080/docs
```
