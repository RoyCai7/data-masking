/**
 * E2E tests — targeting http://10.146.15.188:8080
 *
 * Group A: Infrastructure  (health, status, session)
 * Group B: Auth guards     (no key, invalid key, role check)
 * Group C: Masking pipeline (upload -> poll -> report -> download)
 * Group D: Rules CRUD + lifecycle
 * Group E: API key management
 * Group F: Organization management
 * Group G: Frontend UI interactions
 */

import { test, expect, Page } from '@playwright/test';

const ADMIN_KEY = 'dms_3be8006031f045d3aafdc6c78282f2e4';
const BASE_URL  = 'http://10.146.15.188:8080';
const API       = `${BASE_URL}/api/v1`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function loginWithKey(page: Page, key: string = ADMIN_KEY) {
  await page.goto(BASE_URL);
  await page.evaluate((k) => localStorage.setItem('dms-api-key', k), key);
  await page.reload();
  await page.waitForLoadState('networkidle');
}

async function uploadText(
  request: any,
  text: string,
  filename = 'test.txt',
  whitelist = '',
  attempt = 0,
) {
  const res = await request.post(`${API}/mask`, {
    headers: { 'X-API-Key': ADMIN_KEY },
    multipart: {
      file: { name: filename, mimeType: 'text/plain', buffer: Buffer.from(text) },
      whitelist,
    },
  });
  if (res.status() === 503 && attempt < 12) {
    await new Promise((r) => setTimeout(r, 2500));
    return uploadText(request, text, filename, whitelist, attempt + 1);
  }
  if (!res.ok()) {
    const body = await res.text();
    throw new Error(`uploadText failed: HTTP ${res.status()} — ${body.slice(0, 200)}`);
  }
  return (await res.json()) as { task_id: string; session_id: string };
}

async function waitForTask(
  request: any,
  task_id: string,
  session_id: string,
  maxWait = 15000,
) {
  const deadline = Date.now() + maxWait;
  while (Date.now() < deadline) {
    const poll = await request.get(`${API}/task/${task_id}`, {
      headers: { 'X-API-Key': ADMIN_KEY, 'X-Session-ID': session_id },
    });
    const body = await poll.json();
    if (body.status === 'completed' || body.status === 'failed') return body;
    await new Promise((r) => setTimeout(r, 400));
  }
  throw new Error('Task timed out');
}

// ===========================================================================
// GROUP A: Infrastructure
// ===========================================================================

test.describe('A. Infrastructure', () => {
  test('A1. /health returns 200', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/health`);
    expect(res.ok()).toBeTruthy();
  });

  test('A2. /api/v1/status returns healthy', async ({ request }) => {
    const res = await request.get(`${API}/status`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.status).toBe('healthy');
    expect(body).toHaveProperty('executor');
    expect(body.executor).toHaveProperty('max_workers');
  });

  test('A3. POST /api/v1/session creates session id', async ({ request }) => {
    const res = await request.post(`${API}/session`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty('session_id');
    expect((body.session_id as string).length).toBeGreaterThan(8);
  });

  test('A4. Frontend page loads', async ({ page }) => {
    await page.goto(BASE_URL);
    await expect(page).toHaveTitle(/Data Masking|SUSE/i);
    await expect(page.getByText('Upload File')).toBeVisible();
  });
});

// ===========================================================================
// GROUP B: Auth guards
// ===========================================================================

test.describe('B. Auth guards', () => {
  test('B1. GET /api/v1/rules is public (no key needed)', async ({ request }) => {
    const res = await request.get(`${API}/rules`);
    expect(res.status()).toBe(200);
  });

  test('B2. POST /api/v1/mask without key -> 401', async ({ request }) => {
    const res = await request.post(`${API}/mask`, {
      multipart: {
        file: { name: 'f.txt', mimeType: 'text/plain', buffer: Buffer.from('hi') },
        whitelist: '',
      },
    });
    expect(res.status()).toBe(401);
  });

  test('B3. GET /api/v1/keys with invalid key -> 401 or 403', async ({ request }) => {
    const res = await request.get(`${API}/keys`, {
      headers: { 'X-API-Key': 'dms_invalid000000000000000000000000' },
    });
    expect([401, 403]).toContain(res.status());
  });

  test('B4. GET /api/v1/keys/me returns admin role', async ({ request }) => {
    const res = await request.get(`${API}/keys/me`, {
      headers: { 'X-API-Key': ADMIN_KEY },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.role).toBe('admin');
  });
});

// ===========================================================================
// GROUP C: Masking pipeline
// ===========================================================================

test.describe('C. Masking pipeline', () => {
  test('C1. Upload returns task_id and session_id', async ({ request }) => {
    const body = await uploadText(request, 'hello user@test.com');
    expect(body).toHaveProperty('task_id');
    expect(body).toHaveProperty('session_id');
  });

  test('C2. Task completes with status=completed', async ({ request }) => {
    const { task_id, session_id } = await uploadText(
      request,
      'Contact admin@secret.org and 10.0.0.1',
    );
    const task = await waitForTask(request, task_id, session_id);
    expect(task.status).toBe('completed');
  });

  test('C3. Completed task has report with total_matches', async ({ request }) => {
    const { task_id, session_id } = await uploadText(
      request,
      'email: foo@bar.baz\nip: 192.168.0.1',
    );
    const task = await waitForTask(request, task_id, session_id);
    expect(task.status).toBe('completed');
    expect(task.report).toBeTruthy();
    expect(task.report.summary.total_matches).toBeGreaterThan(0);
  });

  test('C4. GET /report/{id} returns structured report', async ({ request }) => {
    const { task_id, session_id } = await uploadText(
      request,
      'tok: ghp_abc123\nip: 172.16.0.1',
    );
    await waitForTask(request, task_id, session_id);
    const res = await request.get(`${API}/report/${task_id}`, {
      headers: { 'X-API-Key': ADMIN_KEY, 'X-Session-ID': session_id },
    });
    expect(res.ok()).toBeTruthy();
    const report = await res.json();
    expect(report).toHaveProperty('summary');
    expect(report).toHaveProperty('breakdown');
    expect(report.summary).toHaveProperty('risk_level');
  });

  test('C5. GET /download/{id} returns masked file', async ({ request }) => {
    const { task_id, session_id } = await uploadText(request, 'user: admin@corp.com\n');
    await waitForTask(request, task_id, session_id);
    const res = await request.get(`${API}/download/${task_id}`, {
      headers: { 'X-API-Key': ADMIN_KEY, 'X-Session-ID': session_id },
    });
    expect(res.ok()).toBeTruthy();
    const text = await res.text();
    expect(text.length).toBeGreaterThan(0);
    expect(text).not.toContain('admin@corp.com');
  });

  test('C6. GET /tasks lists session tasks', async ({ request }) => {
    const { session_id } = await uploadText(request, 'test@example.com');
    const res = await request.get(`${API}/tasks`, {
      headers: { 'X-API-Key': ADMIN_KEY, 'X-Session-ID': session_id },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty('tasks');
    expect(Array.isArray(body.tasks)).toBeTruthy();
  });

  test('C7. Whitelist: whitelisted IP preserved, other IP masked', async ({
    request,
  }) => {
    const { task_id, session_id } = await uploadText(
      request,
      'ip: 10.0.0.1\nother: 192.168.1.1\n',
      't.txt',
      '10.0.0.1',
    );
    await waitForTask(request, task_id, session_id);
    const dl = await request.get(`${API}/download/${task_id}`, {
      headers: { 'X-API-Key': ADMIN_KEY, 'X-Session-ID': session_id },
    });
    const text = await dl.text();
    expect(text).toContain('10.0.0.1');
    expect(text).not.toContain('192.168.1.1');
  });
});

// ===========================================================================
// GROUP D: Rules
// ===========================================================================

test.describe('D. Rules', () => {
  let createdRuleId = '';

  test('D1. GET /rules returns list', async ({ request }) => {
    const res = await request.get(`${API}/rules`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(Array.isArray(body.rules)).toBeTruthy();
    expect(body.rules.length).toBeGreaterThan(0);
  });

  test('D2. POST /rules creates custom rule', async ({ request }) => {
    const ruleId = `e2e-rule-${Date.now()}`;
    const res = await request.post(`${API}/rules`, {
      headers: { 'X-API-Key': ADMIN_KEY, 'Content-Type': 'application/json' },
      data: {
        id: ruleId,
        name: 'E2E Test Rule',
        category: 'custom',
        pattern: 'E2E_SECRET_\\d+',
        strategy: 'asterisk',
        placeholder: '[REDACTED]',
        scope: 'system',
        enabled: true,
        weight: 50,
      },
    });
    expect(res.status()).toBe(201);
    createdRuleId = (await res.json()).rule.id;
    expect(createdRuleId).toBeTruthy();
  });

  test('D3. PATCH /rules/{id}/toggle disables rule', async ({ request }) => {
    if (!createdRuleId) test.skip();
    const res = await request.patch(`${API}/rules/${createdRuleId}/toggle`, {
      headers: { 'X-API-Key': ADMIN_KEY },
    });
    expect(res.ok()).toBeTruthy();
    expect((await res.json()).rule.enabled).toBeFalsy();
  });

  test('D4. PUT /rules/{id} updates rule name', async ({ request }) => {
    if (!createdRuleId) test.skip();
    const res = await request.put(`${API}/rules/${createdRuleId}`, {
      headers: { 'X-API-Key': ADMIN_KEY, 'Content-Type': 'application/json' },
      data: { name: 'E2E Updated Rule' },
    });
    expect(res.ok()).toBeTruthy();
    expect((await res.json()).rule.name).toBe('E2E Updated Rule');
  });

  test('D5. GET /rules-export returns all rules', async ({ request }) => {
    const res = await request.get(`${API}/rules-export`, {
      headers: { 'X-API-Key': ADMIN_KEY },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(Array.isArray(body.rules)).toBeTruthy();
    expect(body.total).toBeGreaterThan(0);
  });

  test('D6. DELETE /rules/{id} removes rule', async ({ request }) => {
    if (!createdRuleId) test.skip();
    const del = await request.delete(`${API}/rules/${createdRuleId}`, {
      headers: { 'X-API-Key': ADMIN_KEY },
    });
    expect([200, 204]).toContain(del.status());
    const check = await request.get(`${API}/rules/${createdRuleId}`, {
      headers: { 'X-API-Key': ADMIN_KEY },
    });
    expect(check.status()).toBe(404);
  });

  test('D7. GET /rules/changelog returns audit log', async ({ request }) => {
    const res = await request.get(`${API}/rules/changelog`, {
      headers: { 'X-API-Key': ADMIN_KEY },
    });
    expect(res.ok()).toBeTruthy();
    expect(await res.json()).toHaveProperty('changelog');
  });
});

// ===========================================================================
// GROUP E: API key management
// ===========================================================================

test.describe('E. Key management', () => {
  let newKeyId    = -1;
  let newKeyPlain = '';

  test('E1. GET /keys lists all keys (admin)', async ({ request }) => {
    const res = await request.get(`${API}/keys`, {
      headers: { 'X-API-Key': ADMIN_KEY },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.total).toBeGreaterThan(0);
    expect(Array.isArray(body.keys)).toBeTruthy();
  });

  test('E2. POST /keys creates new key', async ({ request }) => {
    const res = await request.post(`${API}/keys`, {
      headers: { 'X-API-Key': ADMIN_KEY, 'Content-Type': 'application/json' },
      data: { name: 'e2e-temp-key', role: 'user', expires_days: 1 },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.key).toMatch(/^dms_/);
    newKeyPlain = body.key;
    const list = await request.get(`${API}/keys`, { headers: { 'X-API-Key': ADMIN_KEY } });
    // pick the highest-id key with this name (latest created) to avoid stale entries
    const keysWithName = (await list.json()).keys.filter((k: any) => k.name === 'e2e-temp-key') as any[];
    keysWithName.sort((a: any, b: any) => b.id - a.id);
    const found = keysWithName[0];
    newKeyId = found?.id ?? -1;
  });

  test('E3. GET /keys/me with new key returns user info', async ({ request }) => {
    if (!newKeyPlain) test.skip();
    const res = await request.get(`${API}/keys/me`, {
      headers: { 'X-API-Key': newKeyPlain },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.name).toBe('e2e-temp-key');
    expect(body.role).toBe('user');
  });

  test('E4. GET /keys/{id}/reveal returns plaintext key', async ({ request }) => {
    if (newKeyId < 0) test.skip();
    const res = await request.get(`${API}/keys/${newKeyId}/reveal`, {
      headers: { 'X-API-Key': ADMIN_KEY },
    });
    expect(res.ok()).toBeTruthy();
    expect((await res.json()).key).toBe(newKeyPlain);
  });

  test('E5. POST /keys/disable -> disabled key fails auth', async ({ request }) => {
    if (newKeyId < 0) test.skip();
    const res = await request.post(`${API}/keys/disable`, {
      headers: { 'X-API-Key': ADMIN_KEY, 'Content-Type': 'application/json' },
      data: { key_id: newKeyId },
    });
    expect(res.ok()).toBeTruthy();
    const check = await request.get(`${API}/keys/me`, {
      headers: { 'X-API-Key': newKeyPlain },
    });
    expect([401, 403]).toContain(check.status());
  });

  test('E6. POST /keys/rotate issues a new key and invalidates the old one', async ({ request }) => {
    // Create a fresh key to rotate
    const createRes = await request.post(`${API}/keys`, {
      headers: { 'X-API-Key': ADMIN_KEY, 'Content-Type': 'application/json' },
      data: { name: 'e2e-rotate-key', role: 'user', expires_days: 1 },
    });
    const oldKey = (await createRes.json()).key;
    expect(oldKey).toMatch(/^dms_/);

    // Rotate it
    const rotateRes = await request.post(`${API}/keys/rotate`, {
      headers: { 'X-API-Key': oldKey },
    });
    expect(rotateRes.ok()).toBeTruthy();
    const body = await rotateRes.json();
    expect(body.new_key).toMatch(/^dms_/);
    expect(body.new_key).not.toBe(oldKey);

    // Old key should now be rejected
    const checkOld = await request.get(`${API}/keys/me`, {
      headers: { 'X-API-Key': oldKey },
    });
    expect([401, 403]).toContain(checkOld.status());

    // New key should be accepted
    const checkNew = await request.get(`${API}/keys/me`, {
      headers: { 'X-API-Key': body.new_key },
    });
    expect(checkNew.ok()).toBeTruthy();
  });
});

// ===========================================================================
// GROUP F: Organization management
// ===========================================================================

test.describe('F. Organizations', () => {
  const orgId       = `e2e-org-${Date.now()}`;
  let orgOwnerKey   = '';
  let orgOwnerKeyId = -1;
  let inviteCode    = '';

  test('F1. GET /orgs lists orgs (admin)', async ({ request }) => {
    const res = await request.get(`${API}/orgs`, {
      headers: { 'X-API-Key': ADMIN_KEY },
    });
    expect(res.ok()).toBeTruthy();
    expect(await res.json()).toHaveProperty('orgs');
  });

  test('F2. Create temp owner key', async ({ request }) => {
    const res = await request.post(`${API}/keys`, {
      headers: { 'X-API-Key': ADMIN_KEY, 'Content-Type': 'application/json' },
      data: { name: 'e2e-org-owner', role: 'user', expires_days: 1 },
    });
    orgOwnerKey = (await res.json()).key;
    const list    = await request.get(`${API}/keys`, { headers: { 'X-API-Key': ADMIN_KEY } });
    const ownerCandidates = (await list.json()).keys.filter((k: any) => k.name === 'e2e-org-owner') as any[];
    ownerCandidates.sort((a: any, b: any) => b.id - a.id);
    orgOwnerKeyId = ownerCandidates[0]?.id ?? -1;
    expect(orgOwnerKey).toMatch(/^dms_/);
  });

  test('F3. POST /orgs creates org', async ({ request }) => {
    if (!orgOwnerKey) test.skip();
    const res = await request.post(`${API}/orgs`, {
      headers: { 'X-API-Key': orgOwnerKey, 'Content-Type': 'application/json' },
      data: { id: orgId, name: 'E2E Test Org' },
    });
    expect(res.status()).toBe(201);
    const body  = await res.json();
    expect(body.org.id).toBe(orgId);
    inviteCode   = body.org.invite_code ?? '';
  });

  test('F4. GET /orgs/mine returns new org for owner', async ({ request }) => {
    if (!orgOwnerKey) test.skip();
    const res = await request.get(`${API}/orgs/mine`, {
      headers: { 'X-API-Key': orgOwnerKey },
    });
    expect(res.ok()).toBeTruthy();
    expect((await res.json()).id).toBe(orgId);
  });

  test('F5. POST /orgs/{id}/invite refreshes invite code', async ({ request }) => {
    if (!orgOwnerKey) test.skip();
    const res = await request.post(`${API}/orgs/${orgId}/invite`, {
      headers: { 'X-API-Key': orgOwnerKey },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    inviteCode  = body.invite_code ?? inviteCode;
    expect(inviteCode.length).toBeGreaterThan(3);
  });

  test('F6. POST /orgs/join using invite code', async ({ request }) => {
    if (!inviteCode) test.skip();
    const kRes     = await request.post(`${API}/keys`, {
      headers: { 'X-API-Key': ADMIN_KEY, 'Content-Type': 'application/json' },
      data: { name: 'e2e-joiner', role: 'user', expires_days: 1 },
    });
    const joinerKey = (await kRes.json()).key;
    const joinRes   = await request.post(`${API}/orgs/join`, {
      headers: { 'X-API-Key': joinerKey, 'Content-Type': 'application/json' },
      data: { invite_code: inviteCode },
    });
    expect(joinRes.ok()).toBeTruthy();
    expect((await joinRes.json()).org_id).toBe(orgId);
    // cleanup joiner key
    const list    = await request.get(`${API}/keys`, { headers: { 'X-API-Key': ADMIN_KEY } });
    const joinerId = (await list.json()).keys.find((k: any) => k.name === 'e2e-joiner')?.id;
    if (joinerId) {
      await request.post(`${API}/keys/disable`, {
        headers: { 'X-API-Key': ADMIN_KEY, 'Content-Type': 'application/json' },
        data: { key_id: joinerId },
      });
    }
  });

  test('F7. DELETE /orgs resets member keys to default (regression)', async ({ request }) => {
    if (orgOwnerKeyId < 0) test.skip();
    const del = await request.delete(`${API}/orgs/${orgId}`, {
      headers: { 'X-API-Key': ADMIN_KEY },
    });
    expect([200, 204]).toContain(del.status());
    // owner key org must be reset to 'default'
    const mine = await request.get(`${API}/orgs/mine`, {
      headers: { 'X-API-Key': orgOwnerKey },
    });
    expect(mine.status()).toBe(200);
    expect((await mine.json()).id).toBe('default');
    // cleanup owner key
    await request.post(`${API}/keys/disable`, {
      headers: { 'X-API-Key': ADMIN_KEY, 'Content-Type': 'application/json' },
      data: { key_id: orgOwnerKeyId },
    });
  });
});

// ===========================================================================
// GROUP G: Frontend UI interactions
// ===========================================================================

test.describe('G. Frontend UI', () => {
  test('G1. Settings: save API key persists in localStorage', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.click('button[title="API Key Settings"]');
    await expect(page.getByRole('dialog', { name: 'API Key Settings' })).toBeVisible();
    await page.locator('input[placeholder*="dms_"]').fill(ADMIN_KEY);
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByText('Roy Cai')).toBeVisible({ timeout: 8000 });
    await page.reload();
    await page.waitForLoadState('networkidle');
    const stored = await page.evaluate(() => localStorage.getItem('dms-api-key'));
    expect(stored).toBe(ADMIN_KEY);
  });

  test('G2. Admin Console opens and shows key list', async ({ page }) => {
    await loginWithKey(page);
    await expect(page.locator('button[title="Admin Console"]')).toBeVisible({ timeout: 8000 });
    await page.locator('button[title="Admin Console"]').click();
    await expect(page.getByText('Roy Cai').first()).toBeVisible({ timeout: 8000 });
  });

  test('G3. My Organization panel opens', async ({ page }) => {
    await loginWithKey(page);
    const orgBtn = page.locator('button[title="My Organization"]');
    await expect(orgBtn).toBeVisible({ timeout: 8000 });
    await orgBtn.click();
    await expect(page.getByText(/organization|org/i).first()).toBeVisible({ timeout: 8000 });
  });

  test('G4. api-key-required event opens Settings modal', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.evaluate(() =>
      window.dispatchEvent(new CustomEvent('api-key-required')),
    );
    await expect(
      page.getByRole('dialog', { name: 'API Key Settings' }),
    ).toBeVisible({ timeout: 5000 });
  });
});
