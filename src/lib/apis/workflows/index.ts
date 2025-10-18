import { WEBUI_API_BASE_URL } from '$lib/constants';

const BASE = `${WEBUI_API_BASE_URL}/workflows`; // typically '/api/v1/workflows'

type Json = Record<string, any>;

export type Workflow = {
  id: string;
  user_id: string;
  name: string;
  description?: string;
  workflow_type: 'langflow' | 'n8n' | 'langchain' | 'custom';
  config: Json;
  is_active: boolean;
  created_at: string | number;
  updated_at: string | number;
};

export type WorkflowCredential = {
  id: string;
  user_id: string;
  service_name: string;
  endpoint_url?: string | null;
  additional_config?: Json | null;
  created_at: string | number;
  updated_at: string | number;
};

export type WorkflowExecution = {
  id: string;
  workflow_id: string;
  user_id: string;
  chat_id?: string | null;
  message_id?: string | null;
  input_data?: Json | null;
  output_data?: Json | null;
  status: 'pending' | 'running' | 'completed' | 'failed';
  error_message?: string | null;
  started_at: string | number;
  completed_at?: string | number | null;
};

// --- helpers ---
async function handle(res: Response) {
  if (!res.ok) {
    let detail = 'Request failed';
    try {
      const j = await res.json();
      detail = j?.detail || detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return res.json();
}

function jfetch(url: string, init: RequestInit = {}) {
  return fetch(url, {
    credentials: 'include', // session cookie-based auth
    headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
    ...init
  });
}

// =======================
// Workflows (CRUD)
// =======================

export const createNewWorkflow = async (_token: string, workflow: Partial<Workflow>) => {
  const res = await jfetch(`${BASE}/`, {
    method: 'POST',
    body: JSON.stringify(workflow)
  });
  return handle(res) as Promise<Workflow>;
};

export const getWorkflows = async (_token: string = '') => {
  const res = await jfetch(`${BASE}/`, { method: 'GET' });
  return handle(res) as Promise<Workflow[]>;
};

// alias for list view
export const getWorkflowList = async (_token: string = '') => {
  const res = await jfetch(`${BASE}/`, { method: 'GET' });
  return handle(res) as Promise<Workflow[]>;
};

// there is no export endpoint yet; return current list
export const exportWorkflows = async (_token: string = '') => {
  const res = await jfetch(`${BASE}/`, { method: 'GET' });
  return handle(res) as Promise<Workflow[]>;
};

export const getWorkflowById = async (_token: string, id: string) => {
  const res = await jfetch(`${BASE}/${id}`, { method: 'GET' });
  return handle(res) as Promise<Workflow>;
};

export const updateWorkflowById = async (_token: string, id: string, workflow: Partial<Workflow>) => {
  const res = await jfetch(`${BASE}/${id}`, {
    method: 'PUT',
    body: JSON.stringify(workflow)
  });
  return handle(res) as Promise<Workflow>;
};

export const deleteWorkflowById = async (_token: string, id: string) => {
  const res = await jfetch(`${BASE}/${id}`, { method: 'DELETE' });
  return handle(res) as Promise<{ status: boolean; message: string }>;
};

// =======================
// Credentials
// =======================

export const listCredentials = async () => {
  const res = await jfetch(`${BASE}/credentials/list`, { method: 'GET' });
  return handle(res) as Promise<WorkflowCredential[]>;
};

export const createCredential = async (payload: {
  service_name: string; // 'langflow' | 'n8n' | 'langchain' | 'custom'
  api_key: string;
  endpoint_url?: string;
  additional_config?: Json;
}) => {
  const res = await jfetch(`${BASE}/credentials`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
  return handle(res) as Promise<WorkflowCredential>;
};

export const deleteCredential = async (credentialId: string) => {
  const res = await jfetch(`${BASE}/credentials/${credentialId}`, { method: 'DELETE' });
  return handle(res) as Promise<{ status: boolean; message: string }>;
};

// =======================
// Executions
// =======================

export const executeWorkflow = async (workflowId: string, input_data: Json = {}, chat_id?: string, message_id?: string) => {
  const body: any = { input_data };
  if (chat_id) body.chat_id = chat_id;
  if (message_id) body.message_id = message_id;

  const res = await jfetch(`${BASE}/${workflowId}/execute`, {
    method: 'POST',
    body: JSON.stringify(body)
  });
  return handle(res) as Promise<WorkflowExecution>; // status=pending initially
};

export const getExecutions = async (limit = 50) => {
  const url = new URL(`${BASE}/executions/list`, window.location.origin);
  url.searchParams.set('limit', String(limit));
  const res = await jfetch(url.toString(), { method: 'GET' });
  return handle(res) as Promise<WorkflowExecution[]>;
};

export const getExecutionById = async (executionId: string) => {
  const res = await jfetch(`${BASE}/executions/${executionId}`, { method: 'GET' });
  return handle(res) as Promise<WorkflowExecution>;
};

export const getExecutionStatus = async (executionId: string) => {
  const res = await jfetch(`${BASE}/executions/${executionId}/status`, { method: 'GET' });
  return handle(res) as Promise<{
    id: string;
    status: WorkflowExecution['status'];
    started_at: string | number;
    completed_at?: string | number | null;
    error_message?: string | null;
  }>;
};
