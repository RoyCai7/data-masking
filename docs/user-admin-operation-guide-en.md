# SUSE Data Masking Service User Guide

> This is the only recommended document for testers and end users. If any other notes or materials conflict with this document, follow this one.

## 1. Purpose

This document describes how to use the currently deployed SUSE Data Masking Service for two roles:

- Regular users
- Administrators

It covers:

- Web UI operations
- API usage
- API Key usage
- Rule viewing and management
- Common issues and troubleshooting

---

## 2. Access URLs

### 2.1 Web Entry

Production Web URL:

- `http://10.146.15.188:8080`

### 2.2 API Base URL

API Base URL:

- `http://10.146.15.188:8080/api/v1`

### 2.3 Swagger Docs

Interactive API docs:

- `http://10.146.15.188:8080/docs`

---

## 2.4 Important Notes

Before using the system, please note:

- This system assists with masking, but **does not guarantee 100% removal of all sensitive information**
- Before sharing, uploading, or publishing masked output, you **must manually review the result**
- Web task history depends on the browser-stored `X-Session-ID`
- Sessions expire after **2 hours** by default; tasks and temporary files may be cleaned up automatically afterwards

---

## 3. Roles

## 3.1 Regular User

A regular user can:

- Upload files for masking
- View their own task list
- Download masked files
- Download JSON reports
- View their own API key information
- Rotate their own API key
- Submit rule suggestions
- View their own submitted suggestions

A regular user **cannot**:

- Create rules
- Modify rules
- Delete rules
- Enable/disable rules
- Import/export rules
- Approve rule suggestions
- Manage other users' API keys

## 3.2 Administrator

An administrator has all regular-user capabilities, and can also:

- Create API keys
- Disable API keys
- View all API keys
- Create rules
- Modify rules
- Delete custom rules
- Enable/disable rules
- Import/export rules
- View rule change history
- Approve or reject rule suggestions

---

## 4. Authentication and Isolation

The system uses two mechanisms:

### 4.1 Session Isolation

Session isolation ensures each user can only access their own tasks and files.

- The Web UI automatically generates and stores `X-Session-ID`
- For task-related API calls, `X-Session-ID` must be included

Example:

```http
X-Session-ID: 5f6fd5de-7d1f-4e6f-a9f5-8fa4a8bb4b2f
```

### 4.2 API Key Authentication

API key authentication is used for access control.

- Under the default deployment, **only a small set of public endpoints do not require an API key**
- Most business endpoints require `X-API-Key`
- Admin endpoints require both `X-API-Key` and an `admin` role

Use the table below as a quick reference:

| Endpoint Type | Needs `X-API-Key` | Typical Endpoints |
|------|------|------|
| Public endpoints | No | `/api/v1/status`, `/api/v1/rules`, `/api/v1/session` |
| Protected user endpoints | Yes | `/api/v1/mask`, `/api/v1/task/{task_id}`, `/api/v1/tasks`, `/api/v1/download/{task_id}`, `/api/v1/report/{task_id}`, `/api/v1/keys/me`, `/api/v1/keys/rotate` |
| Admin endpoints | Yes, and must be admin | `/api/v1/keys`, `/api/v1/keys/disable`, rule create/update/delete endpoints under `/api/v1/rules`, `/api/v1/rules-import`, `/api/v1/rules-export`, `/api/v1/rules/changelog` |

Example:

```http
X-API-Key: dms_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 5. Regular User Guide

## 5.1 Web: Upload and Mask a File

### Step 1: Open the system

Visit:

- `http://10.146.15.188:8080`

To upload files, query tasks, or download results, first save a valid API key from the `Key` button in the top-right corner.

### Step 2: Upload a file

In the upload area on the home page, you can:

- Drag and drop a file
- Click to select a file

Currently supported:

### Text files

- `.txt`
- `.log`
- `.csv`
- `.json`
- `.yaml`
- `.yml`
- `.ini`
- `.conf`
- `.cfg`

### Archives

- `.tar.gz`
- `.tgz`
- `.tar.bz2`
- `.tbz2`
- `.tar.xz`
- `.txz`
- `.tar`
- `.zip`

Limit:

- Maximum file size: 500 MB

### Step 3: Set a whitelist (optional)

Whitelist values will be excluded from masking, for example:

```text
localhost,127.0.0.1,my-test-domain
```

### Step 4: Start processing

Click `Start Masking`.

The system will:

1. Create a task
2. Process the file in the background
3. Show task status in the task list

### Step 5: View results

After processing completes, you can view:

- Risk score
- Number of matched rules
- Match count by rule
- Example replacements
- Total lines / processed files
- Processing time

### Step 6: Download results

From the result view, you can download:

- Masked file
- JSON report

---

## 5.2 Web: Save Your API Key

Click in the top-right corner:

- `Key`

In the dialog:

1. Paste your API key
2. Click `Save`
3. The key is stored in browser local storage automatically

Notes:

- The input is shown in plain text by default for easier verification
- You can click the eye icon to show/hide the key

---

## 5.3 Web: View Your Key Info

After saving an API key, the dialog shows:

- Owner
- Role
- Created
- Expires
- Partial key preview

If the API key is invalid, expired, or disabled, the UI will show an error.

---

## 5.4 Web: Rotate Your API Key

If you want to replace your current key:

1. Open the `Key` settings dialog
2. Click `Rotate`
3. Confirm the action
4. The system generates a new key and disables the old one automatically

Notes:

- The full new key is shown only once
- You must copy and save it in time
- The browser updates to the new key automatically

---

## 5.5 API: Upload a File and View Results

### 5.5.1 Create a session (optional)

```bash
curl -X POST http://10.146.15.188:8080/api/v1/session
```

Response:

```json
{
  "session_id": "...",
  "message": "Session created successfully"
}
```

### 5.5.2 Upload a file

```bash
curl -X POST http://10.146.15.188:8080/api/v1/mask \
  -H "X-API-Key: <your_api_key>" \
  -H "X-Session-ID: <session_id>" \
  -F "file=@./sample.log" \
  -F "whitelist=localhost,127.0.0.1"
```

Response:

```json
{
  "task_id": "...",
  "session_id": "...",
  "status": "pending",
  "filename": "sample.log",
  "message": "File uploaded successfully. Processing started."
}
```

### 5.5.3 Query task status

```bash
curl http://10.146.15.188:8080/api/v1/task/<task_id> \
  -H "X-API-Key: <your_api_key>" \
  -H "X-Session-ID: <session_id>"
```

### 5.5.4 List all tasks in the current session

```bash
curl http://10.146.15.188:8080/api/v1/tasks \
  -H "X-API-Key: <your_api_key>" \
  -H "X-Session-ID: <session_id>"
```

### 5.5.5 Download masked file

```bash
curl http://10.146.15.188:8080/api/v1/download/<task_id> \
  -H "X-API-Key: <your_api_key>" \
  -H "X-Session-ID: <session_id>" \
  -o masked_output.dat
```

### 5.5.6 Get JSON report

```bash
curl http://10.146.15.188:8080/api/v1/report/<task_id> \
  -H "X-API-Key: <your_api_key>" \
  -H "X-Session-ID: <session_id>"
```

Notes:

- `/api/v1/session` is public and does not require `X-API-Key`
- Upload, task query, task list, download, and report endpoints require `X-API-Key` under the default deployment
- Task-related endpoints must use the same stable `X-Session-ID`

---

## 5.6 Public Endpoints Available to Regular Users

### View system status

```bash
curl http://10.146.15.188:8080/api/v1/status
```

### View rule list

```bash
curl http://10.146.15.188:8080/api/v1/rules
```

Notes:

- `GET /api/v1/rules` is a public endpoint
- `GET /api/v1/rules/{rule_id}` should **not** be treated as public under the current default authentication setup
- If you need single-rule detail, use a valid `X-API-Key`

Example:

```bash
curl http://10.146.15.188:8080/api/v1/rules/ipv4 \
  -H "X-API-Key: <your_api_key>"
```

---

## 5.7 Regular User: Submit Rule Suggestions

If you find missed masking or over-masking, you can submit a suggestion.

### Submit a new rule suggestion

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

### Submit a modification suggestion

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

### View your submitted suggestions

```bash
curl http://10.146.15.188:8080/api/v1/rules/suggestions \
  -H "X-API-Key: <your_api_key>"
```

Notes:

- Regular users can only see their own suggestions
- Administrators can see all suggestions

---

## 6. Administrator Guide

## 6.1 Get an Admin API Key

An admin key can be created from the server-side CLI.

Run on the server:

```bash
cd /opt/data-masking
python3.11 generate_key.py create --name "Admin User" --role admin
```

Or with a virtual environment:

```bash
cd /opt/data-masking
source backend/venv/bin/activate
python generate_key.py create --name "Admin User" --role admin
```

Save the full key from the command output.

---

## 6.2 Administrator Web Usage

Administrators mainly use the Web UI to:

- Save their own API key
- Open `Admin Console`
- Manage keys, rules, suggestion approvals, and change history from the Web UI
- Validate rule behavior using normal file upload flow
- Access Swagger docs for API testing

The current frontend provides `Admin Console` with these typical operations:

- `Keys`: create keys, view keys, disable keys
- `Rules`: create rules, update rules, enable/disable rules, delete custom rules, import/export rules
- `Rule Approvals`: approve or reject user-submitted rule suggestions
- `History`: view rule change history

For bulk operations, request-body debugging, or advanced troubleshooting, Swagger or `curl` is still recommended.

---

## 6.3 Admin API: Manage API Keys

### Create a new user key

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

### Create a new admin key

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

### View all keys

```bash
curl http://10.146.15.188:8080/api/v1/keys \
  -H "X-API-Key: <admin_api_key>"
```

### Disable a key

```bash
curl -X POST http://10.146.15.188:8080/api/v1/keys/disable \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <admin_api_key>" \
  -d '{
    "key": "dms_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  }'
```

---

## 6.4 Admin API: View Rules

### View all rules

```bash
curl http://10.146.15.188:8080/api/v1/rules
```

### View enabled rules only

```bash
curl 'http://10.146.15.188:8080/api/v1/rules?enabled_only=true'
```

### Filter by category

```bash
curl 'http://10.146.15.188:8080/api/v1/rules?category=network'
```

### View single rule detail

```bash
curl http://10.146.15.188:8080/api/v1/rules/aws_access_key \
  -H "X-API-Key: <admin_api_key>"
```

Notes:

- Under the current default authentication setup, `GET /api/v1/rules/{rule_id}` should not be treated as public
- Administrators should always include a valid `X-API-Key` when requesting single-rule detail

---

## 6.5 Admin API: Create a Rule

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

Field descriptions:

- `id`: unique rule identifier
- `name`: display name
- `category`: rule category
- `pattern`: regex pattern
- `flags`: for example `IGNORECASE`
- `strategy`: `asterisk | placeholder | partial | hash`
- `placeholder`: replacement text
- `weight`: risk weight
- `enabled`: whether the rule is enabled

---

## 6.6 Admin API: Update a Rule

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

Notes:

- Only include the fields you want to update
- In-memory cache is refreshed automatically after updates

---

## 6.7 Admin API: Enable / Disable a Rule

```bash
curl -X PATCH http://10.146.15.188:8080/api/v1/rules/k8s_secret_token/toggle \
  -H "X-API-Key: <admin_api_key>"
```

Notes:

- This endpoint toggles the rule between enabled and disabled
- It is suitable when you want to temporarily disable a rule instead of deleting it

---

## 6.8 Admin API: Delete a Rule

```bash
curl -X DELETE http://10.146.15.188:8080/api/v1/rules/k8s_secret_token \
  -H "X-API-Key: <admin_api_key>"
```

Notes:

- Only custom rules can be deleted
- Built-in rules cannot be deleted; use `toggle` instead

---

## 6.9 Admin API: Export and Import Rules

### Export all rules

```bash
curl http://10.146.15.188:8080/api/v1/rules-export \
  -H "X-API-Key: <admin_api_key>" \
  -o rules-export.json
```

### Import rules

```bash
curl -X POST http://10.146.15.188:8080/api/v1/rules-import \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <admin_api_key>" \
  --data @rules-export.json
```

During import:

- Existing `id` values are updated
- New `id` values are created
- Cache is refreshed automatically afterwards

---

## 6.10 Admin API: Review Suggestions

### View all suggestions

```bash
curl http://10.146.15.188:8080/api/v1/rules/suggestions \
  -H "X-API-Key: <admin_api_key>"
```

### View pending suggestions only

```bash
curl 'http://10.146.15.188:8080/api/v1/rules/suggestions?status=pending' \
  -H "X-API-Key: <admin_api_key>"
```

### Approve a suggestion

```bash
curl -X PATCH http://10.146.15.188:8080/api/v1/rules/suggestions/1 \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <admin_api_key>" \
  -d '{"action": "approve"}'
```

### Reject a suggestion

```bash
curl -X PATCH http://10.146.15.188:8080/api/v1/rules/suggestions/1 \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <admin_api_key>" \
  -d '{"action": "reject"}'
```

Notes:

- After `approve`, the suggestion is applied to the rule store automatically
- Cache is refreshed automatically after successful application

---

## 6.11 Admin API: View Rule Change History

### View the latest 50 changes

```bash
curl http://10.146.15.188:8080/api/v1/rules/changelog \
  -H "X-API-Key: <admin_api_key>"
```

### View change history for one rule

```bash
curl 'http://10.146.15.188:8080/api/v1/rules/changelog?rule_id=ipv4&limit=20' \
  -H "X-API-Key: <admin_api_key>"
```

---

## 7. Storage and Update Mechanism

The current rule system uses:

- SQLite for persistent storage
- In-memory cache for faster reads

### Rule database location

The rule database path is controlled by the `RULES_DB_PATH` environment variable.

If the variable is not set, the code default is:

```text
backend/rules.db
```

The current Docker Compose deployment uses:

```text
/app/data/rules.db
```

### Stored tables

The database mainly contains three tables:

- `rules`
- `rule_suggestions`
- `rule_changelog`

### Update mechanism

After an admin operation, the system will:

1. Write to SQLite
2. Write a change log
3. Refresh the in-memory cache automatically

Therefore, **new rules take effect without restarting the service**.

---

## 8. Recommended Workflows

## 8.1 Recommended flow for regular users

1. Open the Web page
2. Click `Key` in the top-right corner and save your API key
3. Upload a file
4. View the result
5. Manually review the masked output
6. Download the masked file and report
7. Submit a rule suggestion if you find a rule issue

## 8.2 Recommended flow for administrators

1. Create or confirm an admin key
2. Test management APIs in `/docs`
3. Export a backup of rules first
4. Then create / update / toggle rules
5. Run regression checks with real sample files
6. Review changelog entries for completeness

---

## 9. Frequently Asked Questions

## 9.1 I get 401 during upload

Reasons:

- The endpoint requires an API key
- No key is saved in the browser
- The key is expired or disabled

What to do:

- Click `Key` in the top-right corner
- Paste a valid key again
- Confirm you are calling a protected endpoint rather than a public one
- Click `Save`

## 9.2 I get 413 during upload

Reason:

- The file is larger than 500 MB

What to do:

- Compress the file
- Split the file and upload again

## 9.3 I cannot see my previous task history

Reasons:

- The current browser `X-Session-ID` is different from the one used during upload
- Sessions expire after 2 hours by default, and task data may already have been cleaned up

What to do:

- Use the same browser session whenever possible
- Use the same stable `X-Session-ID` for API calls
- Download important results in time instead of relying on temporary browser task history

## 9.4 I changed a rule but it does not take effect

Normally this should not happen, because cache refresh is automatic after updates.

Check:

- Whether you updated the correct rule `id`
- Whether the rule was toggled to disabled
- Whether the regex is incorrect
- Whether the sample input actually matches the rule

## 9.5 An admin cannot modify rules

Check:

- Whether you are using an admin key
- Whether the request includes `X-API-Key`
- Whether the key is expired or disabled

---

## 10. Minimum Useful Command Set

## Regular User

```bash
# View status
curl http://10.146.15.188:8080/api/v1/status

# Create session
curl -X POST http://10.146.15.188:8080/api/v1/session

# Upload file
curl -X POST http://10.146.15.188:8080/api/v1/mask \
  -H "X-API-Key: <your_api_key>" \
  -H "X-Session-ID: <session_id>" \
  -F "file=@./sample.log"
```

## Administrator

```bash
# View rules
curl http://10.146.15.188:8080/api/v1/rules

# Create rule
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

# Export rules
curl http://10.146.15.188:8080/api/v1/rules-export \
  -H "X-API-Key: <admin_api_key>" \
  -o rules-export.json
```

---

## 11. Conclusion

The current system is best used in two ways:

- Regular users: mainly through the Web UI for upload and result download
- Administrators: mainly through API / Swagger for configuration and governance

Recommended practice:

- Regular users should use the Web UI
- Administrators should use `/docs` or `curl`
- Export a backup before changing rules
- Run regression validation with real samples after rule changes
