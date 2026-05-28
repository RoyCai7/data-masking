# CLAUDE.md — Data Masking Service

This file describes the project structure, development workflow, and CI/CD pipeline design for AI coding assistants.

---

## Project Overview

A data masking service with:
- **Backend**: FastAPI + SQLite, systemd on `root@10.146.15.188`, uvicorn at `127.0.0.1:8000`
- **Frontend**: React + Vite + Tailwind, nginx at `:8080`, serving compiled `dist/`
- **LLM**: ollama (`qwen2.5-coder:7b`) via SSH reverse tunnel from Mac → server `127.0.0.1:11434`
- **No Docker** on server

---

## Directory Structure

```
backend/
  app/
    api/          # FastAPI routers: keys, llm, mask, orgs, rules, status
    core/         # auth, executor, key_service, permissions, session
    engine/       # db, masker, repo_*, rule_service, rules, archive
    main.py       # app lifespan, router registration
  tests/          # pytest, 219 tests
  requirements.txt
frontend/
  src/
    components/   # AdminConsole, AiRegexPanel, FileUpload, Header, Modal,
                  # MyOrg, ResultView, RuleList, Settings, SuggestRule, TaskList
    hooks/        # useAiRegex, useModalA11y
    services/     # api.ts
  e2e/            # Playwright smoke tests (39 tests)
```

---

## Local Development

### Backend
```bash
cd backend
source venv/bin/activate          # or: python -m venv venv && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev                        # Vite dev server, proxies /api → localhost:8000
```

### LLM (ollama tunnel to Mac)
```bash
# On Mac — keep running while developing
ollama serve                       # must be running on 127.0.0.1:11434
ssh -R 11434:127.0.0.1:11434 root@10.146.15.188 -N
```

---

## Testing

### Unit + Integration (pytest)
```bash
cd backend
python -m pytest tests/ -q        # 219 tests, all should pass
```

### E2E (Playwright)
```bash
cd frontend
npx playwright test e2e/smoke.spec.ts --reporter=line
# Target: http://10.146.15.188:8080  (set in playwright.config.ts)
# 39 tests
```

---

## Deploy to Server (10.146.15.188)

### Full deploy
```bash
# 1. Push to GitHub
git add -A && git commit -m "..." && git push

# 2. Server: sync code
ssh root@10.146.15.188 "cd /opt/data-masking && git fetch origin && git reset --hard origin/main"

# 3. Server: rebuild frontend
ssh root@10.146.15.188 "cd /opt/data-masking/frontend && npm install --silent && npm run build"

# 4. Server: restart backend
ssh root@10.146.15.188 "systemctl restart data-masking"
```

### Backend-only deploy (no frontend change)
```bash
git push
ssh root@10.146.15.188 "cd /opt/data-masking && git reset --hard origin/main && systemctl restart data-masking"
```

### Verify
```bash
ssh root@10.146.15.188 "systemctl is-active data-masking nginx"
curl -s http://10.146.15.188:8080/api/status | python3 -m json.tool
```

---

## CI/CD Pipeline Design

### Proposed GitHub Actions pipeline (`.github/workflows/ci.yml`)

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   lint      │────▶│  unit test  │────▶│  build       │────▶│   deploy    │
│  (ruff/tsc) │     │  (pytest)   │     │  (vite build)│     │  (ssh)      │
└─────────────┘     └─────────────┘     └──────────────┘     └─────────────┘
                                                                     │
                                                              only on push to main
```

#### Stage 1 — Lint
- `ruff check backend/` (Python)
- `tsc --noEmit` (TypeScript)

#### Stage 2 — Unit & Integration Tests
- `pytest tests/ -q`
- SQLite in-memory (fixtures in `conftest.py`)
- No external dependencies (LLM tests mocked)

#### Stage 3 — Frontend Build
- `npm ci && npm run build`
- Confirms no TypeScript/build errors

#### Stage 4 — Deploy (main branch only)
```bash
ssh root@10.146.15.188 << 'EOF'
  set -e
  cd /opt/data-masking
  git fetch origin && git reset --hard origin/main
  cd frontend && npm ci --silent && npm run build
  systemctl restart data-masking
  sleep 3 && systemctl is-active data-masking
EOF
```

#### Stage 5 — Smoke Test (post-deploy)
```bash
curl -sf http://10.146.15.188:8080/api/status
```

---

## Server Configuration

### systemd service: `/etc/systemd/system/data-masking.service`
```ini
[Service]
WorkingDirectory=/opt/data-masking/backend
ExecStart=/opt/data-masking/backend/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Environment=OLLAMA_BASE_URL=http://127.0.0.1:11434
Environment=OLLAMA_DEFAULT_MODEL=qwen2.5-coder:7b
Restart=always
```

### nginx: serves `frontend/dist/` at `:8080`, proxies `/api/` → `127.0.0.1:8000`

### LLM tunnel (manual, not persisted across reboots)
```bash
ssh -R 11434:127.0.0.1:11434 root@10.146.15.188 -N -f
```
> ⚠️ If Mac disconnects, LLM features return 503. Core masking/rules/keys are unaffected.

---

## Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama endpoint (tunneled from Mac) |
| `OLLAMA_DEFAULT_MODEL` | `qwen2.5-coder:7b` | LLM model for regex suggestions |
| `OPENCODE_BASE_URL` | `http://10.146.15.188:3000/v1` | OpenAI-compat endpoint (unused) |

---

## Admin

- Default admin key: in `backend/keys.json` (not committed)
- Generate new key: `python generate_key.py`
- DB path: `backend/rules.db` (gitignored)
