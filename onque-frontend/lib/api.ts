export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

export type SummaryResponse = {
  id: number;
  filename: string;
  summary: string;
  category: string;
};

export type Todo = {
  id: number;
  content: string;
  due_date: string | null;
  is_done: boolean;
  created_at: string;
};

export type ScheduleItem = {
  id: number;
  title: string;
  scheduled_date: string;
  created_at: string;
};

export type DocumentRecord = {
  id: number;
  source_type: 'call' | 'document';
  category: string;
  filename: string;
  summary: string;
  created_at: string;
};

export type ChatMessageRecord = {
  id: number;
  sender: string;
  content: string;
  is_bot: boolean;
  created_at: string;
};

export type ChatSendResult = {
  message: ChatMessageRecord;
  bot_message: ChatMessageRecord | null;
  todos: Todo[];
  schedules: ScheduleItem[];
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: options?.body ? { 'Content-Type': 'application/json' } : undefined,
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || '요청이 실패했습니다.');
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

async function postFile(path: string, file: File): Promise<SummaryResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || '요약 요청이 실패했습니다.');
  }

  return res.json();
}

export function summarizeCall(file: File): Promise<SummaryResponse> {
  return postFile('/summarize-call', file);
}

export function summarizeDocument(file: File): Promise<SummaryResponse> {
  return postFile('/summarize-document', file);
}

export function getTodos(): Promise<Todo[]> {
  return request('/todos');
}

export function updateTodo(id: number, body: { is_done?: boolean }): Promise<Todo> {
  return request(`/todos/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
}

export function deleteTodo(id: number): Promise<void> {
  return request(`/todos/${id}`, { method: 'DELETE' });
}

export function getSchedules(): Promise<ScheduleItem[]> {
  return request('/schedules');
}

export function deleteSchedule(id: number): Promise<void> {
  return request(`/schedules/${id}`, { method: 'DELETE' });
}

export function getDocuments(): Promise<DocumentRecord[]> {
  return request('/documents');
}

export function deleteDocument(id: number): Promise<void> {
  return request(`/documents/${id}`, { method: 'DELETE' });
}

export function getChatMessages(): Promise<ChatMessageRecord[]> {
  return request('/chat/messages');
}

export function sendChatMessage(sender: string, content: string): Promise<ChatSendResult> {
  return request('/chat/messages', {
    method: 'POST',
    body: JSON.stringify({ sender, content }),
  });
}
