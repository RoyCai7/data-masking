import axios from 'axios';

const API_BASE = '/api/v1';

// Generate UUID (compatible with non-HTTPS environments)
const generateUUID = (): string => {
  // Use crypto.randomUUID if available (HTTPS only)
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  // Fallback for HTTP environments
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
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

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'X-Session-ID': getSessionId()
  }
});

// Update session header on each request
api.interceptors.request.use((config) => {
  config.headers['X-Session-ID'] = getSessionId();
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
    size_bytes: number;
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
  executor: {
    max_workers: number;
    active_tasks: number;
    available_slots: number;
  };
}

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

export { getSessionId };
