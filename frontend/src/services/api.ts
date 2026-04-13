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

// Get or set API Key
export const getApiKey = (): string => {
  return localStorage.getItem('dms-api-key') || '';
};

export const setApiKey = (key: string): void => {
  localStorage.setItem('dms-api-key', key);
  // Update default header immediately
  api.defaults.headers.common['X-API-Key'] = key;
};

export const clearApiKey = (): void => {
  localStorage.removeItem('dms-api-key');
  delete api.defaults.headers.common['X-API-Key'];
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
  const apiKey = getApiKey();
  if (apiKey) {
    config.headers['X-API-Key'] = apiKey;
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

export const getSystemStatus = async (): Promise<SystemStatus> => {
  const response = await api.get('/status');
  return response.data;
};

// --- API Key self-service ---

export interface KeyInfo {
  name: string;
  role: string;
  created_at: string;
  expires_at: string;
  key_preview: string;
}

export interface RotateKeyResponse {
  message: string;
  new_key: string;
  name: string;
  role: string;
  created_at: string;
  expires_at: string;
  warning: string;
}

export const getMyKeyInfo = async (): Promise<KeyInfo> => {
  const response = await api.get('/keys/me');
  return response.data;
};

export const rotateMyKey = async (): Promise<RotateKeyResponse> => {
  const response = await api.post('/keys/rotate');
  // Auto-update stored key
  if (response.data.new_key) {
    setApiKey(response.data.new_key);
  }
  return response.data;
};

export { getSessionId };
