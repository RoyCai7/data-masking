#!/usr/bin/env python3
"""
Comprehensive API Test — SUSE Data Masking Service
Verified response shapes:
  /status          → {service,version,status,auth_enabled,executor}
  /keys/me         → {name,role,org_id,created_at,expires_at,key_preview}
  /keys GET        → {total,keys:[{name,role,enabled,key,...}]}
  /keys POST       → {message,key,name,role,created_at,expires_at}
  /orgs            → {total,orgs:[{id,name,created_at}]}
  /rules           → {total,rules:[{id,name,pattern,scope,use_count,...}]}
  /rules/{id} GET  → {id,name,category,pattern,...,scope,use_count}
  /rules PUT       → updated rule object
  /rules/promote   → PATCH, updated rule object
  /mask POST       → {task_id,session_id,status,filename,message}
  /task/{id}       → {task_id,filename,status,report:{report_id,summary,breakdown}}
"""

import os, requests, sys, time, io

BASE = os.getenv("DMS_SERVER", "http://localhost:8080") + "/api/v1"
WEB  = os.getenv("DMS_SERVER", "http://localhost:8080")
ADMIN_KEY = os.getenv("DMS_ADMIN_KEY", "")
AH = {"X-API-Key": ADMIN_KEY}
AJ = {**AH, "Content-Type": "application/json"}

passed = failed = _sp = _sf = 0

def section(t):
    global _sp, _sf
    if _sp+_sf: print(f"   → {_sp} pass / {_sf} fail")
    _sp = _sf = 0
    print(f"\n{'='*58}\n  {t}\n{'='*58}")

def check(name, ok, detail=""):
    global passed, failed, _sp, _sf
    if ok:
        print(f"  ✓  {name}"); passed += 1; _sp += 1
    else:
        print(f"  ✗  {name}")
        if detail: print(f"       {str(detail)[:220]}")
        failed += 1; _sf += 1

def G(p, **kw):  return requests.get(f"{BASE}{p}", headers=AH, timeout=15, **kw)
def P(p, **kw):  return requests.post(f"{BASE}{p}", headers=AJ, timeout=15, **kw)
def PU(p, **kw): return requests.put(f"{BASE}{p}", headers=AJ, timeout=15, **kw)
def PA(p, **kw): return requests.patch(f"{BASE}{p}", headers=AJ, timeout=15, **kw)
def D(p, **kw):  return requests.delete(f"{BASE}{p}", headers=AH, timeout=15, **kw)

def unwrap(d, *keys):
    """Unwrap {message, <key>: {...}} envelope; tries keys in order, falls back to d"""
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
    return d

def mask_wait(sid, tid, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        r = requests.get(f"{BASE}/task/{tid}",
                         headers={**AH,"X-Session-ID":sid}, timeout=10)
        if r.status_code != 200: return None
        d = r.json()
        if d.get("status") in ("completed","failed"): return d
        time.sleep(0.5)
    return None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 0. Web UI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("0. Web UI Reachability")
r = requests.get(WEB, timeout=10)
check("GET / → 200", r.status_code == 200, r.status_code)
check("Content-Type: text/html", "text/html" in r.headers.get("Content-Type",""), r.headers.get("Content-Type"))
check("HTML page served", "<!doctype" in r.text.lower() or '<div id="root"' in r.text, r.text[:80])
r = requests.get(f"{WEB}/index.html", timeout=10)
check("GET /index.html → 200", r.status_code == 200, r.status_code)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Service Status
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("1. Service Status")
r = G("/status")
check("GET /status → 200", r.status_code == 200, r.text[:100])
if r.ok:
    d = r.json()
    check("status = healthy", d.get("status") == "healthy", d)
    check("auth_enabled field present", "auth_enabled" in d, d)
    check("version field present", "version" in d, d)
    ex = d.get("executor", {})
    check("executor.max_workers > 0", ex.get("max_workers",0) > 0, ex)
    check("executor.active_tasks present", "active_tasks" in ex, ex)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Auth — key identity
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("2. Auth — Key Identity")
r = G("/keys/me")
check("GET /keys/me → 200", r.status_code == 200, r.text[:100])
if r.ok:
    d = r.json()
    check("name present",       "name"       in d, d)
    check("role = admin",       d.get("role") == "admin", d)
    check("org_id present",     "org_id"     in d, d)
    check("key_preview present","key_preview" in d, d)
    check("expires_at present", "expires_at"  in d, d)

r_bad = requests.get(f"{BASE}/keys/me", headers={"X-API-Key": "bad_key_xyz"}, timeout=10)
check("Bad key → 401/403", r_bad.status_code in (401,403), r_bad.status_code)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Key Management (admin)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("3. Key Management")
r = G("/keys")
check("GET /keys → 200", r.status_code == 200, r.text[:80])
temp_key = None
temp_key_id = None
if r.ok:
    d = r.json()
    check("response has 'total'", "total" in d, d)
    check("response has 'keys' list", isinstance(d.get("keys"), list), d)
    check("keys count > 0", d.get("total",0) > 0, d.get("total"))
    k0 = d["keys"][0] if d.get("keys") else {}
    for f in ("name","role","enabled","key_preview"):
        check(f"key has field: {f}", f in k0, k0)

# create temp key (cleanup first)
P("/keys/disable", json={"name":"smoke_temp_key"})
r = P("/keys", json={"name":"smoke_temp_key","role":"user","org_id":"default"})
check("POST /keys → 200/201", r.status_code in (200,201), r.text[:200])
if r.ok:
    d = r.json()
    check("POST /keys returns key string", bool(d.get("key")), d)
    check("POST /keys returns name", d.get("name") == "smoke_temp_key", d)
    temp_key = d.get("key")
    temp_key_id = d.get("id")

if temp_key:
    # user key can read rules
    r2 = requests.get(f"{BASE}/rules", headers={"X-API-Key":temp_key}, timeout=10)
    check("user key: GET /rules → 200", r2.status_code == 200, r2.text[:80])
    # user key cannot manage keys (admin-only)
    r3 = requests.get(f"{BASE}/keys", headers={"X-API-Key":temp_key}, timeout=10)
    check("user key: GET /keys → 401/403", r3.status_code in (401,403), r3.text[:80])
    # disable by key_id
    rd = P("/keys/disable", json={"key_id": temp_key_id}) if temp_key_id else P("/keys/disable", json={"key": temp_key})
    check("POST /keys/disable → 200", rd.status_code == 200, rd.text[:100])
    # disabled key rejected on auth-required endpoint
    r4 = requests.get(f"{BASE}/keys/me", headers={"X-API-Key":temp_key}, timeout=10)
    check("disabled key → 401/403", r4.status_code in (401,403), r4.status_code)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Organizations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("4. Organizations")
r = G("/orgs")
check("GET /orgs → 200", r.status_code == 200, r.text[:80])
if r.ok:
    d = r.json()
    check("response has 'total'", "total" in d, d)
    check("response has 'orgs' list", isinstance(d.get("orgs"), list), d)
    check("default org exists", any(o["id"]=="default" for o in d.get("orgs",[])), d)

TEST_ORG = "smoke_test_org_77"
D(f"/orgs/{TEST_ORG}")  # pre-clean
r = P("/orgs", json={"id":TEST_ORG,"name":"Smoke Org 77"})
check("POST /orgs → 200/201", r.status_code in (200,201), r.text[:200])
if r.ok:
    d = unwrap(r.json(), "org")
    check("created org has id", d.get("id") == TEST_ORG, r.json())

r2 = P("/orgs", json={"id":TEST_ORG,"name":"Dup"})
check("Duplicate org → 400/409/422", r2.status_code in (400,409,422), r2.text[:100])

r = G("/orgs")
if r.ok:
    check("new org in list", any(o["id"]==TEST_ORG for o in r.json().get("orgs",[])), "")

r = D("/orgs/default")
check("DELETE 'default' org → 400/403/422", r.status_code in (400,403,422), r.text[:100])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. Rules — List & Filter
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("5. Rules — List & Filter")
r = G("/rules")
check("GET /rules → 200", r.status_code == 200, r.text[:80])
if r.ok:
    d = r.json()
    check("has 'total'", "total" in d, d)
    check("has 'rules' list", isinstance(d.get("rules"), list), d)
    check("total > 0", d.get("total",0) > 0, d.get("total"))
    ru = d["rules"][0] if d.get("rules") else {}
    for f in ("id","name","pattern","scope","use_count","strategy","enabled"):
        check(f"rule field: {f}", f in ru, list(ru.keys()))

r = G("/rules?scope=system")
check("GET /rules?scope=system → 200", r.status_code == 200)
if r.ok:
    sys_r = r.json().get("rules",[])
    check("all system scope", all(x["scope"]=="system" for x in sys_r), [x["scope"] for x in sys_r[:3]])
    check("system rules >= 10", len(sys_r) >= 10, len(sys_r))

r = G("/rules?scope=private")
check("GET /rules?scope=private → 200", r.status_code == 200)
if r.ok:
    priv_r = r.json().get("rules",[])
    check("all private scope", all(x["scope"]=="private" for x in priv_r), [x["scope"] for x in priv_r[:3]])

# GET single rule
r = G("/rules/ipv4")
check("GET /rules/ipv4 → 200", r.status_code == 200, r.text[:100])
if r.ok:
    d = r.json()
    check("rule id = ipv4", d.get("id") == "ipv4", d.get("id"))
    check("scope field present", "scope" in d, d)
    check("use_count field present", "use_count" in d, d)

r = G("/rules/email")
check("GET /rules/email → 200", r.status_code == 200, r.text[:100])

r = G("/rules/nonexistent_rule_xyz")
check("GET nonexistent rule → 404", r.status_code == 404, r.text[:100])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. Rules — CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("6. Rules — CRUD")
RID = "smoke_crud_001"
D(f"/rules/{RID}")

r = P("/rules", json={
    "id": RID, "name": "Smoke CRUD Rule", "category": "PII",
    "pattern": r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    "strategy": "partial", "placeholder": "[EMAIL]", "weight": 50, "enabled": True
})
check("POST /rules → 200/201", r.status_code in (200,201), r.text[:300])
if r.ok:
    d = unwrap(r.json(), "rule")
    check("id matches", d.get("id") == RID, d.get("id"))
    check("scope = private (default)", d.get("scope") == "private", d.get("scope"))
    check("use_count = 0", d.get("use_count",0) == 0, d.get("use_count"))

r = G(f"/rules/{RID}")
check("GET /rules/{id} → 200", r.status_code == 200, r.text[:100])
if r.ok:
    check("retrieved id matches", r.json().get("id") == RID, r.json().get("id"))

# Update uses PUT
r = PU(f"/rules/{RID}", json={"name":"Smoke CRUD Rule (Updated)","weight":75})
check("PUT /rules/{id} → 200", r.status_code == 200, r.text[:200])
if r.ok:
    d = unwrap(r.json(), "rule")
    check("name updated", d.get("name") == "Smoke CRUD Rule (Updated)", d.get("name"))
    check("weight updated", d.get("weight") == 75, d.get("weight"))

# PATCH should 405
r = PA(f"/rules/{RID}", json={"weight":99})
check("PATCH /rules/{id} → 405 (not supported)", r.status_code == 405, r.status_code)

# delete nonexistent
r = D("/rules/nonexistent_xyz_123")
check("DELETE nonexistent rule → 404/400", r.status_code in (404,400), r.text[:100])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. Scope Promotion
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("7. Scope Promotion Workflow")
PRID = "smoke_promo_001"
D(f"/rules/{PRID}")
r = P("/rules", json={
    "id": PRID, "name": "Promo Rule", "category": "PII",
    "pattern": r"\d{3}-\d{2}-\d{4}", "strategy": "placeholder", "placeholder": "[SSN]"
})
check("Create private rule", r.status_code in (200,201), r.text[:100])

r = PA(f"/rules/{PRID}/promote", json={"scope":"org","org_id":"default"})
check("Promote private→org → 200", r.status_code == 200, r.text[:200])
if r.ok:
    d = unwrap(r.json(), "rule")
    check("scope = org", d.get("scope") == "org", d.get("scope"))
    check("org_id = default", d.get("org_id") == "default", d.get("org_id"))

r = PA(f"/rules/{PRID}/promote", json={"scope":"system"})
check("Promote org→system → 200", r.status_code == 200, r.text[:200])
if r.ok:
    d = unwrap(r.json(), "rule")
    check("scope = system", d.get("scope") == "system", d.get("scope"))
    check("org_id = None for system", d.get("org_id") is None, d.get("org_id"))

r = PA(f"/rules/{PRID}/promote", json={"scope":"org","org_id":"default"})
check("Demote system→org → 200", r.status_code == 200, r.text[:100])

r = PA(f"/rules/{PRID}/promote", json={"scope":"invalid_scope_xyz"})
check("Invalid scope → 400/422", r.status_code in (400,422), r.text[:100])

r = PA(f"/rules/{PRID}/promote", json={"scope":"org","org_id":"nonexistent_fake_org"})
check("Promote to nonexistent org → 400/404/422", r.status_code in (400,404,422), r.text[:100])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. org_id Validation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("8. org_id Validation")
BID = "smoke_badorg_001"
D(f"/rules/{BID}")
# When scope=org is sent with a fake org_id, the API uses the caller's org_id (default);
# the injected org_id overrides the provided one — test that behavior is correct
r = P("/rules", json={
    "id": BID, "name": "Bad Org Test", "category": "test",
    "pattern": r"\d+", "strategy": "placeholder",
    "scope": "org", "org_id": "totally_fake_org_abc123"
})
# API either rejects (400/422) or overrides with caller's org — both are acceptable
if r.status_code in (400, 422):
    check("org_id validation on create (rejected)", True)
elif r.ok:
    actual_org = unwrap(r.json(), "rule").get("org_id")
    check("org_id validation on create (overridden to caller org)",
          actual_org != "totally_fake_org_abc123", f"org_id was: {actual_org}")
    D(f"/rules/{BID}")
else:
    check("org_id validation on create", False, r.text[:200])

r = PU(f"/rules/{RID}", json={"org_id":"fake_org_9999"})
check("Update rule to fake org_id → 400/422", r.status_code in (400,422), r.text[:200])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9. Masking — Single File (async)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("9. Masking — Single File (async)")
content = b"Contact: user@example.com or admin@company.org. Server: 192.168.1.100"
r = requests.post(f"{BASE}/mask", headers=AH,
                  files={"file":("test.txt", io.BytesIO(content), "text/plain")}, timeout=15)
check("POST /mask → 200", r.status_code == 200, r.text[:200])
if r.ok:
    d = r.json()
    check("has task_id",   "task_id"   in d, d)
    check("has session_id","session_id" in d, d)
    check("status=pending", d.get("status") == "pending", d.get("status"))
    tr = mask_wait(d["session_id"], d["task_id"])
    check("task completes ≤30s", tr is not None, "timeout")
    if tr:
        check("status=completed", tr.get("status") == "completed", tr.get("status"))
        rpt = tr.get("report", {})
        check("report present", bool(rpt), tr.keys())
        sm = rpt.get("summary", {})
        check("summary.total_matches > 0", sm.get("total_matches",0) > 0, sm)
        bk = rpt.get("breakdown", [])
        check("breakdown list present", isinstance(bk, list), type(bk))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 10. Masking — use_count tracking
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("10. Masking — use_count Tracking")
r_b = G("/rules/ipv4")
uc_before = r_b.json().get("use_count", 0) if r_b.ok else 0

r = requests.post(f"{BASE}/mask", headers=AH,
                  files={"file":("ips.txt", io.BytesIO(b"10.0.0.1 and 172.16.5.5"), "text/plain")}, timeout=15)
if r.ok:
    d = r.json()
    tr = mask_wait(d["session_id"], d["task_id"])
    if tr and tr.get("status") == "completed":
        r_a = G("/rules/ipv4")
        uc_after = r_a.json().get("use_count", 0) if r_a.ok else 0
        check("ipv4 use_count incremented", uc_after > uc_before, f"before={uc_before} after={uc_after}")
    else:
        check("ipv4 use_count incremented", False, f"task status: {tr}")
else:
    check("ipv4 use_count incremented", False, r.text)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 11. Masking — Edge Cases
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("11. Masking — Edge Cases")
# unsupported type
r = requests.post(f"{BASE}/mask", headers=AH,
                  files={"file":("bad.exe", io.BytesIO(b"MZ\x90"), "application/octet-stream")}, timeout=10)
check("Unsupported file type → 400", r.status_code == 400, r.text[:100])

# empty file (should not 500)
r = requests.post(f"{BASE}/mask", headers=AH,
                  files={"file":("empty.txt", io.BytesIO(b""), "text/plain")}, timeout=15)
check("Empty file → not 500", r.status_code != 500, r.status_code)
if r.ok and r.json().get("task_id"):
    d = r.json()
    tr = mask_wait(d["session_id"], d["task_id"])
    check("Empty file task resolves (not crash)", tr is not None and tr.get("status") in ("completed","failed"), tr)

# no auth (some deployments allow anonymous, others return 401/403/503)
r = requests.post(f"{BASE}/mask",
                  files={"file":("t.txt", io.BytesIO(b"hello"), "text/plain")}, timeout=10)
check("Mask no auth → not 500", r.status_code != 500, r.status_code)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 12. Task Polling
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("12. Task Polling")
r = requests.get(f"{BASE}/task/00000000-0000-0000-0000-000000000000",
                 headers={**AH,"X-Session-ID":"00000000-0000-0000-0000-000000000000"}, timeout=10)
check("Unknown task → 404", r.status_code == 404, r.text[:100])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 13. LLM Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("13. LLM Endpoints")
r = G("/llm/providers")
check("GET /llm/providers → 200", r.status_code == 200, r.text[:100])
if r.ok:
    raw = r.json()
    # supports both plain list and {total, providers:[...]} envelope
    prov = raw.get("providers", raw) if isinstance(raw, dict) else raw
    check("providers not empty", len(prov) > 0, raw)
    check("ollama present", any(
        (p.get("id") if isinstance(p,dict) else p) == "ollama" for p in prov), prov)

r = G("/llm/models")
check("GET /llm/models → 200", r.status_code == 200, r.text[:100])
if r.ok:
    models = r.json()
    check("models list not empty", len(models) > 0, models)

t0 = time.time()
r = P("/llm/generate-regex", json={
    "description": "match IPv4 like 192.168.1.1",
    "provider": "ollama", "model": "gemma3:1b"
})
elapsed = time.time() - t0
check(f"POST /llm/generate-regex → 200 ({elapsed:.1f}s)", r.status_code == 200, r.text[:200])
if r.ok:
    d = r.json()
    check("has pattern",            bool(d.get("pattern")),            d)
    check("has suggested_name",     "suggested_name"     in d,         d)
    check("has suggested_category", "suggested_category" in d,         d)
    check("has explanation",         "explanation"        in d,         d)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 14. Rule Suggestions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("14. Rule Suggestions")
r = P("/rules/suggestions", json={
    "action":"create","name":"Smoke Test Suggest","category":"PII",
    "pattern":r"[A-Z]{2}\d{6}","strategy":"placeholder","reason":"auto test"
})
check("POST /rules/suggestions → 200/201", r.status_code in (200,201), r.text[:200])

r = G("/rules/suggestions")
check("GET /rules/suggestions → 200", r.status_code == 200, r.text[:100])
if r.ok:
    body = r.json()
    sugs = body.get("suggestions", body) if isinstance(body,dict) else body
    check("suggestions is list", isinstance(sugs,list), type(sugs))
    check("at least 1 suggestion", len(sugs) >= 1, len(sugs))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 15. Org Lifecycle (self-service)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("15. Org Lifecycle — Invite / Join / Leave")

# create a fresh user key to act as org owner
USER_KEY_NAME = "smoke_org_owner_key"
P("/keys/disable", json={"name": USER_KEY_NAME})
r = P("/keys", json={"name": USER_KEY_NAME, "role": "user", "org_id": "default"})
check("Create owner user key", r.status_code in (200, 201), r.text[:200])
owner_key = r.json().get("key") if r.ok else None

owner_org_id = None
if owner_key:
    UH = {"X-API-Key": owner_key}
    UJ = {**UH, "Content-Type": "application/json"}

    # owner creates an org (auto-slug, no id needed from client)
    r = requests.post(f"{BASE}/orgs", headers=UJ,
                      json={"id": "smoke-lifecycle-00", "name": "Lifecycle Test Org"},
                      timeout=10)
    check("Owner: POST /orgs → 200/201", r.status_code in (200, 201), r.text[:200])
    if r.ok:
        owner_org_id = unwrap(r.json(), "org").get("id") or "smoke-lifecycle-00"
        check("Org has invite code", bool(unwrap(r.json(), "org").get("invite_code")), r.json())
        invite = unwrap(r.json(), "org").get("invite_code")

        # GET /orgs/mine as owner
        r2 = requests.get(f"{BASE}/orgs/mine", headers=UH, timeout=10)
        check("Owner: GET /orgs/mine → 200", r2.status_code == 200, r2.text[:100])
        if r2.ok:
            mine = r2.json()
            check("mine.id matches", mine.get("id") == owner_org_id, mine.get("id"))

        # Create second user key that will join/leave
        JOINER_NAME = "smoke_org_joiner_key"
        P("/keys/disable", json={"name": JOINER_NAME})
        r3 = P("/keys", json={"name": JOINER_NAME, "role": "user", "org_id": "default"})
        check("Create joiner key", r3.status_code in (200, 201), r3.text[:100])
        joiner_key = r3.json().get("key") if r3.ok else None

        if joiner_key and invite:
            JH = {"X-API-Key": joiner_key}
            JJ = {**JH, "Content-Type": "application/json"}

            # Join via invite code
            r4 = requests.post(f"{BASE}/orgs/join", headers=JJ,
                               json={"invite_code": invite}, timeout=10)
            check("Joiner: POST /orgs/join → 200", r4.status_code == 200, r4.text[:200])
            if r4.ok:
                check("Joiner now in org", r4.json().get("org_id") == owner_org_id,
                      r4.json().get("org_id"))

            # Bad invite code
            r5 = requests.post(f"{BASE}/orgs/join", headers=JJ,
                               json={"invite_code": "BADCODE"}, timeout=10)
            check("Bad invite code → 400/404", r5.status_code in (400, 404), r5.text[:100])

            # Joiner leaves
            r6 = requests.post(f"{BASE}/orgs/leave", headers=JJ, timeout=10)
            check("Joiner: POST /orgs/leave → 200", r6.status_code == 200, r6.text[:100])

            # Owner cannot leave own org
            r7 = requests.post(f"{BASE}/orgs/leave", headers=UJ, timeout=10)
            check("Owner: POST /orgs/leave → 400/403", r7.status_code in (400, 403), r7.text[:100])

            # Rotate invite code
            r8 = requests.post(f"{BASE}/orgs/{owner_org_id}/invite", headers=UJ, timeout=10)
            check("Owner: POST /orgs/{id}/invite (rotate) → 200", r8.status_code == 200, r8.text[:100])
            if r8.ok:
                new_code = r8.json().get("invite_code")
                check("New invite code differs from old", new_code != invite, new_code)

            # non-owner cannot rotate invite
            r9 = requests.post(f"{BASE}/orgs/{owner_org_id}/invite", headers=JJ, timeout=10)
            check("Non-owner: rotate invite → 403", r9.status_code == 403, r9.text[:100])

            # Cleanup joiner key
            requests.post(f"{BASE}/keys/disable", headers=AJ, json={"key": joiner_key}, timeout=10)

    # Cleanup owner key
    if owner_key:
        requests.post(f"{BASE}/keys/disable", headers=AJ, json={"key": owner_key}, timeout=10)
else:
    check("Org lifecycle skipped — couldn't create owner key", False)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 16. Cleanup
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("16. Cleanup")
for rid in (RID, PRID, BID):
    r = D(f"/rules/{rid}")
    check(f"DELETE {rid} → 200/204/400/404", r.status_code in (200,204,400,404), r.text[:80])

r = D(f"/orgs/{TEST_ORG}")
check(f"DELETE org {TEST_ORG} → 200/204", r.status_code in (200,204), r.text[:80])

if owner_org_id:
    r = D(f"/orgs/{owner_org_id}")
    check(f"DELETE lifecycle org → 200/204", r.status_code in (200,204), r.text[:80])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Final
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section("DONE")
total = passed + failed
print(f"\n{'='*58}")
print(f"  TOTAL : {total} checks")
print(f"  PASS  : {passed}  ({passed*100//total if total else 0}%)")
print(f"  FAIL  : {failed}")
print(f"{'='*58}")
sys.exit(0 if failed == 0 else 1)
