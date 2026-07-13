import axios from 'axios';

const API_BASE = '/api/v1';

// Generate UUID (compatible with non-HTTPS environments)
const generateUUID = (): string => {
  // Use crypto.randomUUID if available (HTTPS only)
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  // Fallback using crypto.getRandomValues (works on HTTP)
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
};

// Get or create session ID
const getSessionId = (): string => {
  let sessionId = localStorage.getItem('masking-session-id');
  if (!sessionId) {
    sessionId = generateUUID();
    localStorage.setItem('masking-session-id', sessionId);
  }
  return sessionId;
};

export const getSessionToken = (): string => {
  return localStorage.getItem('dms-session-token') || '';
};

export const setSessionToken = (token: string): void => {
  localStorage.setItem('dms-session-token', token);
  api.defaults.headers.common['X-Session-Token'] = token;
  window.dispatchEvent(new CustomEvent('auth-state-changed'));
};

export const clearSessionToken = (): void => {
  localStorage.removeItem('dms-session-token');
  delete api.defaults.headers.common['X-Session-Token'];
  window.dispatchEvent(new CustomEvent('auth-state-changed'));
};

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'X-Session-ID': getSessionId()
  }
});

// Update headers on each request
api.interceptors.request.use((config) => {
  config.headers['X-Session-ID'] = getSessionId();
  const sessionToken = getSessionToken();
  if (sessionToken) {
    config.headers['X-Session-Token'] = sessionToken;
  }
  return config;
});

export interface TaskInfo {
  task_id: string;
  filename: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  created_at: number;
  completed_at: number | null;
  total_matches?: number;
  risk_level?: string;
  error?: string;
}

export interface ReportBreakdown {
  rule_id: string;
  rule_name: string;
  matches: number;
  examples: Array<{
    line: number;
    original: string;
    masked: string;
    file?: string;
  }>;
}

export interface MaskingReport {
  report_id: string;
  generated_at: string;
  file_info: {
    name: string;
    size_bytes?: number;
    is_archive?: boolean;
    archive_type?: string;
    files_processed?: number;
    lines_total: number;
  };
  summary: {
    total_matches: number;
    risk_score: number;
    risk_level: string;
    processing_time_ms: number;
    whitelist_skipped: number;
  };
  breakdown: ReportBreakdown[];
}

export interface MaskingRule {
  id: string;
  name: string;
  enabled: boolean;
  weight: number;
}

export interface RuleDetail extends MaskingRule {
  category: string;
  pattern: string;
  flags: string;
  strategy: 'asterisk' | 'placeholder' | 'partial' | 'hash';
  placeholder: string;
  scope: 'system' | 'org' | 'private';
  org_id?: string | null;
  use_count?: number;
  is_builtin?: boolean;
  description?: string | null;
  example?: string | null;
  version?: number;
  created_at?: string;
  updated_at?: string;
  created_by?: string;
}

export interface Organization {
  id: string;
  name: string;
  owner?: string;
  owner_key_prefix?: string;
  invite_code?: string;
  invite_code_expires_at?: string;
  custom_rule_set?: boolean;
  created_at?: string;
}

export interface RuleSuggestion {
  id: number;
  rule_id?: string | null;
  action: 'create' | 'modify' | 'disable';
  name?: string | null;
  category?: string | null;
  pattern?: string | null;
  flags?: string | null;
  strategy?: string | null;
  placeholder?: string | null;
  weight?: number | null;
  reason?: string | null;
  status: 'pending' | 'approved' | 'rejected';
  submitted_by?: string | null;
  submitted_at?: string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
}

export interface RuleChangelogEntry {
  id: number;
  rule_id: string;
  action: string;
  old_value?: string | null;
  new_value?: string | null;
  changed_by: string;
  changed_at: string;
}

export interface ManagedKeyInfo {
  id?: number;
  name: string;
  role: string;
  org_id?: string;
  enabled: boolean;
  created_at: string;
  expires_at: string;
  key_preview: string;
  key?: string;
}

export interface SystemStatus {
  service: string;
  version: string;
  status: string;
  auth_enabled: boolean;
  executor: {
    max_workers: number;
    active_tasks: number;
    available_slots: number;
  };
}

// Handle 401 auth errors globally
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Dispatch custom event so the Settings component can open the API key dialog
      window.dispatchEvent(new CustomEvent('api-key-required'));
    }
    return Promise.reject(error);
  }
);

// API functions
export const uploadFile = async (file: File, whitelist: string[] = []): Promise<{ task_id: string; session_id: string }> => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('whitelist', whitelist.join(','));
  
  const response = await api.post('/mask', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  });
  
  // Store session ID from response
  if (response.data.session_id) {
    localStorage.setItem('masking-session-id', response.data.session_id);
  }
  
  return response.data;
};

export const getTaskStatus = async (taskId: string): Promise<TaskInfo & { report?: MaskingReport }> => {
  const response = await api.get(`/task/${taskId}`);
  return response.data;
};

export const getTaskList = async (): Promise<{ tasks: TaskInfo[] }> => {
  const response = await api.get('/tasks');
  return response.data;
};

export const getReport = async (taskId: string): Promise<MaskingReport> => {
  const response = await api.get(`/report/${taskId}`);
  return response.data;
};

export const downloadMaskedFile = async (taskId: string): Promise<Blob> => {
  const response = await api.get(`/download/${taskId}`, {
    responseType: 'blob'
  });
  return response.data;
};

export const getRules = async (): Promise<{ rules: MaskingRule[] }> => {
  const response = await api.get('/rules');
  return response.data;
};

export const getRulesDetailed = async (params?: { category?: string; enabled_only?: boolean }): Promise<{ total: number; rules: RuleDetail[] }> => {
  const response = await api.get('/rules', { params });
  return response.data;
};

export const createRule = async (payload: Omit<RuleDetail, 'is_builtin' | 'version' | 'created_at' | 'updated_at' | 'created_by'>): Promise<{ message: string; rule: RuleDetail }> => {
  const response = await api.post('/rules', payload);
  return response.data;
};

export const updateRule = async (ruleId: string, payload: Partial<RuleDetail>): Promise<{ message: string; rule: RuleDetail }> => {
  const response = await api.put(`/rules/${ruleId}`, payload);
  return response.data;
};

export const toggleRule = async (ruleId: string): Promise<{ message: string; rule: RuleDetail }> => {
  const response = await api.patch(`/rules/${ruleId}/toggle`);
  return response.data;
};

export const promoteRule = async (
  ruleId: string,
  scope: 'org' | 'system' | 'private',
  orgId?: string
): Promise<{ message: string; rule: RuleDetail }> => {
  const response = await api.patch(`/rules/${ruleId}/promote`, { scope, org_id: orgId });
  return response.data;
};

// ─── Organization APIs ────────────────────────────────────────────────────────

export const listOrgs = async (): Promise<{ total: number; orgs: Organization[] }> => {
  const response = await api.get('/orgs');
  return response.data;
};

export const createOrg = async (payload: { id: string; name: string }): Promise<{ message: string; org: Organization }> => {
  const response = await api.post('/orgs', payload);
  return response.data;
};

export const deleteOrg = async (orgId: string): Promise<{ message: string }> => {
  const response = await api.delete(`/orgs/${orgId}`);
  return response.data;
};

export const getMyOrg = async (): Promise<Organization> => {
  const response = await api.get('/orgs/mine');
  return response.data;
};

export const refreshInviteCode = async (orgId: string): Promise<{ message: string; invite_code: string; org: Organization }> => {
  const response = await api.post(`/orgs/${orgId}/invite`);
  return response.data;
};

export const joinOrg = async (invite_code: string): Promise<{ message: string; org_id: string; org_name: string }> => {
  const response = await api.post('/orgs/join', { invite_code });
  return response.data;
};

export const leaveOrg = async (): Promise<{ message: string }> => {
  const response = await api.post('/orgs/leave');
  return response.data;
};

export const deleteRule = async (ruleId: string): Promise<{ message: string }> => {
  const response = await api.delete(`/rules/${ruleId}`);
  return response.data;
};

export const exportRules = async (): Promise<{ total: number; rules: RuleDetail[] }> => {
  const response = await api.get('/rules-export');
  return response.data;
};

export const importRules = async (rules: RuleDetail[]): Promise<{ message: string; created: number; updated: number; errors: Array<{ id?: string; error: string }> }> => {
  const response = await api.post('/rules-import', { rules });
  return response.data;
};

export const listRuleSuggestions = async (status?: string): Promise<{ total: number; suggestions: RuleSuggestion[] }> => {
  const response = await api.get('/rules/suggestions', { params: status ? { status } : undefined });
  return response.data;
};

export const reviewRuleSuggestion = async (suggestionId: number, action: 'approve' | 'reject'): Promise<{ message: string; suggestion: RuleSuggestion }> => {
  const response = await api.patch(`/rules/suggestions/${suggestionId}`, { action });
  return response.data;
};

export const listRuleChangelog = async (params?: { rule_id?: string; limit?: number }): Promise<{ total: number; changelog: RuleChangelogEntry[] }> => {
  const response = await api.get('/rules/changelog', { params });
  return response.data;
};

export const getSystemStatus = async (): Promise<SystemStatus> => {
  const response = await api.get('/status');
  return response.data;
};

// --- API Key self-service ---

export interface KeyInfo {
  name: string;
  email?: string;
  role: string;
  org_id: string;
  is_org_owner: boolean;
  created_at: string;
  expires_at: string;
  key_preview: string;
}

export interface AuthUser {
  id?: number;
  user_id?: number;
  email: string;
  name: string;
  role: string;
  org_id: string;
  enabled?: boolean;
  created_at?: string;
}

export interface AuthResponse {
  token: string;
  expires_at: string;
  user: AuthUser;
}

export interface RegisterResponse {
  message: string;
  email: string;
  email_sent: boolean;
  delivery_detail: string;
  user: AuthUser;
}

export interface ForgotPasswordResponse {
  message: string;
  email: string;
  email_sent: boolean;
  delivery_detail: string;
}

export interface AccountTokenInfo {
  id: number;
  name: string;
  role: string;
  org_id: string;
  enabled: boolean;
  created_at: string;
  expires_at: string;
  key_preview: string;
}

export interface CreateAccountTokenResponse {
  message: string;
  id: number;
  key: string;
  name: string;
  role: string;
  org_id: string;
  created_at: string;
  expires_at: string;
}

export const getMyKeyInfo = async (): Promise<KeyInfo> => {
  const response = await api.get('/keys/me');
  return response.data;
};

export const registerAccount = async (payload: { email: string; password: string; name?: string }): Promise<RegisterResponse> => {
  const response = await api.post('/auth/register', payload);
  return response.data;
};

export const loginAccount = async (payload: { email: string; password: string }): Promise<AuthResponse> => {
  const response = await api.post('/auth/login', payload);
  if (response.data.token) {
    setSessionToken(response.data.token);
  }
  return response.data;
};

export const verifyEmail = async (token: string): Promise<AuthResponse> => {
  const response = await api.post('/auth/verify-email', { token });
  if (response.data.token) {
    setSessionToken(response.data.token);
  }
  return response.data;
};

export const logoutAccount = async (): Promise<void> => {
  try {
    await api.post('/auth/logout');
  } finally {
    clearSessionToken();
  }
};

export const forgotPassword = async (email: string): Promise<ForgotPasswordResponse> => {
  const response = await api.post('/auth/forgot-password', { email });
  return response.data;
};

export const resetPassword = async (token: string, newPassword: string): Promise<{ message: string }> => {
  const response = await api.post('/auth/reset-password', { token, new_password: newPassword });
  return response.data;
};

export const listAccountTokens = async (): Promise<{ total: number; tokens: AccountTokenInfo[] }> => {
  const response = await api.get('/account/tokens');
  return response.data;
};

export const createAccountToken = async (payload: { name: string; expires_days: number }): Promise<CreateAccountTokenResponse> => {
  const response = await api.post('/account/tokens', payload);
  return response.data;
};

export const disableAccountToken = async (tokenId: number): Promise<{ message: string }> => {
  const response = await api.post(`/account/tokens/${tokenId}/disable`);
  return response.data;
};

export const listApiKeys = async (): Promise<{ total: number; keys: ManagedKeyInfo[] }> => {
  const response = await api.get('/keys');
  return response.data;
};

export const createApiKey = async (payload: { name: string; role: 'admin' | 'user'; expires_days: number; org_id?: string }): Promise<{ message: string; key: string; name: string; role: string; created_at: string; expires_at: string }> => {
  const response = await api.post('/keys', payload);
  return response.data;
};

export const disableApiKey = async (key_id: number): Promise<{ message: string }> => {
  const response = await api.post('/keys/disable', { key_id });
  return response.data;
};

export const updateApiKey = async (payload: { key_id: number; org_id?: string; role?: string }): Promise<{ message: string; name: string; org_id: string; role: string }> => {
  const response = await api.put('/keys/update', payload);
  return response.data;
};

export const revealApiKey = async (key_id: number): Promise<{ key: string }> => {
  const response = await api.get(`/keys/${key_id}/reveal`);
  return response.data;
};

export const submitRuleSuggestion = async (payload: {
  rule_id?: string | null;
  action: 'create' | 'modify' | 'disable';
  name?: string | null;
  category?: string | null;
  pattern?: string | null;
  flags?: string | null;
  strategy?: string | null;
  placeholder?: string | null;
  weight?: number | null;
  reason: string;
}): Promise<{ message: string; suggestion: RuleSuggestion }> => {
  const response = await api.post('/rules/suggestions', payload);
  return response.data;
};

export { getSessionId };

// ─── LLM / Regex Generation ───────────────────────────────────────────────────

export interface OllamaModel {
  name: string;
  size: number;
  modified_at: string;
  details: Record<string, unknown>;
}

export interface LlmModelsResponse {
  ollama_url: string;
  total: number;
  models: OllamaModel[];
}

export interface GenerateRegexRequest {
  description: string;
  model: string;
  context?: string;
  provider?: 'ollama' | 'opencode';
}

export interface GenerateRegexResponse {
  pattern: string;
  flags: string;
  description?: string | null;
  placeholder: string;
  weight: number;
  examples?: { match: string[]; no_match: string[] } | null;
  model: string;
  provider: string;
  suggested_name?: string | null;
  suggested_category?: string | null;
  raw_response: string;
  structured: boolean;
}

export interface LlmProvider {
  id: string;
  name: string;
  note: string;
  kind: 'ollama' | 'openai_compat';
  base_url: string;
  default_model: string;
  supports_model_list: boolean;
}

export interface LlmProvidersResponse {
  total: number;
  providers: LlmProvider[];
}

export const listLlmModels = async (): Promise<LlmModelsResponse> => {
  const response = await api.get('/llm/models');
  return response.data;
};

export const listLlmProviders = async (): Promise<LlmProvidersResponse> => {
  const response = await api.get('/llm/providers');
  return response.data;
};

export const generateRegex = async (
  payload: GenerateRegexRequest,
  options?: { signal?: AbortSignal },
): Promise<GenerateRegexResponse> => {
  const response = await api.post('/llm/generate-regex', payload, { signal: options?.signal });
  return response.data;
};

export const forkSystemRules = async (): Promise<{ message: string; copied: number; org_id: string }> => {
  const response = await api.post('/rules/fork-system');
  return response.data;
};
