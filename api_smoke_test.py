import os
import requests
import json
import sys
import time

BASE = os.getenv("DMS_SERVER", "http://127.0.0.1:8000") + "/api/v1"
ADMIN_KEY = os.getenv("DMS_ADMIN_KEY", "")
HEADERS = {"X-API-Key": ADMIN_KEY, "Content-Type": "application/json"}

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  [PASS] {name}")
        passed += 1
    else:
        print(f"  [FAIL] {name} -- {detail}")
        failed += 1

# ── 1. LLM Providers ─────────────────────────────────────────────────────────
print("=== 1. LLM Providers ===")
r = requests.get(f"{BASE}/llm/providers", headers=HEADERS, timeout=10)
check("GET /llm/providers 200", r.status_code == 200, r.text[:200])
if r.status_code == 200:
    providers = r.json()
    check("providers list not empty", len(providers) > 0, str(providers))

# ── 2. LLM Models ────────────────────────────────────────────────────────────
print("=== 2. LLM Models ===")
r = requests.get(f"{BASE}/llm/models", headers=HEADERS, timeout=10)
check("GET /llm/models 200", r.status_code == 200, r.text[:200])
if r.status_code == 200:
    models = r.json()
    check("models list not empty", len(models) > 0, str(models))

# ── 3. Generate Regex via Ollama ──────────────────────────────────────────────
print("=== 3. Generate Regex via Ollama (gemma3:1b) ===")
t0 = time.time()
payload = {"description": "match email addresses", "provider": "ollama", "model": "gemma3:1b"}
r = requests.post(f"{BASE}/llm/generate-regex", headers=HEADERS, json=payload, timeout=120)
elapsed = time.time() - t0
check(f"POST /llm/generate-regex 200 ({elapsed:.1f}s)", r.status_code == 200, r.text[:300])
if r.status_code == 200:
    data = r.json()
    check("response has pattern field", "pattern" in data, str(data))
    check("pattern not empty", bool(data.get("pattern", "")), str(data))

# ── 4. Suggest Rule ───────────────────────────────────────────────────────────
print("=== 4. Suggest Rule ===")
suggestion = {
    "action": "create",
    "name": "Smoke Test Email Rule",
    "category": "PII",
    "pattern": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "strategy": "partial",
    "reason": "Smoke test suggestion"
}
r = requests.post(f"{BASE}/rules/suggestions", headers=HEADERS, json=suggestion, timeout=10)
check("POST /rules/suggestions 200/201", r.status_code in (200, 201), r.text[:200])

# ── 5. List Suggestions ───────────────────────────────────────────────────────
print("=== 5. List Suggestions ===")
r = requests.get(f"{BASE}/rules/suggestions", headers=HEADERS, timeout=10)
check("GET /rules/suggestions 200", r.status_code == 200, r.text[:200])
if r.status_code == 200:
    body = r.json()
    suggestions = body.get("suggestions", body) if isinstance(body, dict) else body
    check("suggestion list is list", isinstance(suggestions, list), str(type(suggestions)))

# ── 6. Create Rule ────────────────────────────────────────────────────────────
print("=== 6. Create Rule ===")
rule = {
    "id": "smoke_test_rule_001",
    "name": "Smoke Test Rule",
    "category": "PII",
    "pattern": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "strategy": "partial",
    "placeholder": "***",
    "weight": 50,
    "enabled": True
}
r = requests.post(f"{BASE}/rules", headers=HEADERS, json=rule, timeout=10)
check("POST /rules 200/201", r.status_code in (200, 201), r.text[:200])

# ── 7. Delete Rule ────────────────────────────────────────────────────────────
print("=== 7. Delete Rule ===")
r = requests.delete(f"{BASE}/rules/smoke_test_rule_001", headers=HEADERS, timeout=10)
check("DELETE /rules/smoke_test_rule_001 200/204", r.status_code in (200, 204), r.text[:200])

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n=== RESULT: {passed} passed, {failed} failed ===")
sys.exit(0 if failed == 0 else 1)
