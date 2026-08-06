import { getToken } from './auth-storage';

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

export type AuthUser = {
  id: number;
  email: string;
  name: string;
  role: 'admin' | 'member';
};

export type GroupSummary = {
  id: number;
  name: string;
};

export type MeResponse = {
  user: AuthUser;
  groups: GroupSummary[];
};

type Envelope<T> = { success: boolean; data: T; error: { code: string; message: string } | null };

export type ActionItem = {
  content: string;
  /** YYYY-MM-DD. 마감일이 없으면 빈 문자열. */
  due_date: string;
  priority: 'high' | 'normal';
};

export type StructuredSummary = {
  headline: string;
  key_points: string[];
  requests: string[];
  action_items: ActionItem[];
  notes: string;
};

export type SummaryResponse = {
  id: number;
  filename: string;
  summary: string;
  category: string;
  /** 모델이 스키마를 못 지킨 경우 null — 이때는 summary 평문으로 폴백한다. */
  structured: StructuredSummary | null;
  created_todos: Todo[];
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
  structured: StructuredSummary | null;
  created_at: string;
};

export type ChatMessageRecord = {
  id: number;
  room_id: number;
  sender: string;
  content: string;
  is_bot: boolean;
  created_at: string;
};

export type ChatRoomRecord = {
  id: number;
  group_id: number;
  name: string;
  /** /help로 AI를 부른 상태. 방 전체에 공유된다. */
  ai_mode: boolean;
  member_count: number;
  created_at: string;
  /** 목록의 미리보기용. 아직 대화가 없으면 null. */
  last_message: ChatMessageRecord | null;
};

export type ChatRoomMember = {
  id: number;
  name: string;
  email: string;
  /** 방을 만든 사람. 다른 사람을 내보낼 수 있다. */
  is_owner: boolean;
};

export type GroupInvitation = {
  id: number;
  group_id: number;
  email: string;
  invited_by: number;
  created_at: string;
  /** 합류하면 시각이 찍힌다. 대기 목록에는 null인 것만 나온다. */
  accepted_at: string | null;
};

/** 이미 가입한 사람은 바로 합류하고, 아니면 대기 초대로 남는다. */
export type InviteResult =
  | { status: 'joined'; email: string; user: { id: number; email: string; name: string } }
  | { status: 'pending'; email: string; invitation: GroupInvitation };

export type CommitmentRecord = {
  id: number;
  content: string;
  client_id: number | null;
  client_name: string | null;
  due_date: string | null;
  status: 'proposed' | 'confirmed' | 'fulfilled' | 'dismissed';
  source_type: 'call' | 'document' | 'chat';
  source_id: number | null;
  evidence: string;
  is_overdue: boolean;
  is_due_soon: boolean;
  created_at: string;
};

export type AnnouncementRecord = {
  id: number;
  title: string;
  content: string;
  author_id: number;
  created_at: string;
};

export type ChatSendResult = {
  message: ChatMessageRecord;
  bot_message: ChatMessageRecord | null;
  ai_mode: boolean;
  todos: Todo[];
  schedules: ScheduleItem[];
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (options?.body) headers['Content-Type'] = 'application/json';
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const message = body?.error?.message || body?.detail || '요청이 실패했습니다.';
    throw new Error(message);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

async function requestEnveloped<T>(path: string, options?: RequestInit): Promise<T> {
  const envelope = await request<Envelope<T>>(path, options);
  return envelope.data;
}

async function postFile(path: string, file: File): Promise<SummaryResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    body: formData,
    headers,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const message = body?.error?.message || body?.detail || '요약 요청이 실패했습니다.';
    throw new Error(message);
  }

  return res.json();
}

export function summarizeCall(
  groupId: number,
  file: File,
  autoTodo: boolean,
): Promise<SummaryResponse> {
  return postFile(`/summarize-call?group_id=${groupId}&auto_todo=${autoTodo}`, file);
}

export function summarizeDocument(
  groupId: number,
  file: File,
  autoTodo: boolean,
): Promise<SummaryResponse> {
  return postFile(`/summarize-document?group_id=${groupId}&auto_todo=${autoTodo}`, file);
}

export function getTodos(groupId: number): Promise<Todo[]> {
  return request(`/todos?group_id=${groupId}`);
}

export function createTodo(
  groupId: number,
  content: string,
  dueDate?: string,
): Promise<Todo> {
  return request('/todos', {
    method: 'POST',
    body: JSON.stringify({ group_id: groupId, content, due_date: dueDate || null }),
  });
}

export function updateTodo(id: number, body: { is_done?: boolean }): Promise<Todo> {
  return request(`/todos/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
}

export function deleteTodo(id: number): Promise<void> {
  return request(`/todos/${id}`, { method: 'DELETE' });
}

export function getSchedules(groupId: number): Promise<ScheduleItem[]> {
  return request(`/schedules?group_id=${groupId}`);
}

export function deleteSchedule(id: number): Promise<void> {
  return request(`/schedules/${id}`, { method: 'DELETE' });
}

export function getDocuments(groupId: number): Promise<DocumentRecord[]> {
  return request(`/documents?group_id=${groupId}`);
}

export function deleteDocument(id: number): Promise<void> {
  return request(`/documents/${id}`, { method: 'DELETE' });
}

export function listChatRooms(groupId: number): Promise<ChatRoomRecord[]> {
  return request(`/chat/rooms?group_id=${groupId}`);
}

export function createChatRoom(groupId: number, name: string): Promise<ChatRoomRecord> {
  return request('/chat/rooms', {
    method: 'POST',
    body: JSON.stringify({ group_id: groupId, name }),
  });
}

export function deleteChatRoom(roomId: number): Promise<void> {
  return request(`/chat/rooms/${roomId}`, { method: 'DELETE' });
}

export function listRoomMembers(roomId: number): Promise<ChatRoomMember[]> {
  return request(`/chat/rooms/${roomId}/members`);
}

export function inviteRoomMember(roomId: number, userId: number): Promise<ChatRoomMember> {
  return request(`/chat/rooms/${roomId}/members`, {
    method: 'POST',
    body: JSON.stringify({ user_id: userId }),
  });
}

export function removeRoomMember(
  roomId: number,
  userId: number,
): Promise<{ removed: boolean; room_deleted: boolean }> {
  return request(`/chat/rooms/${roomId}/members/${userId}`, { method: 'DELETE' });
}

export function getChatMessages(roomId: number): Promise<ChatMessageRecord[]> {
  return request(`/chat/messages?room_id=${roomId}`);
}

export function sendChatMessage(
  roomId: number,
  sender: string,
  content: string,
): Promise<ChatSendResult> {
  return request(`/chat/messages?room_id=${roomId}`, {
    method: 'POST',
    body: JSON.stringify({ sender, content }),
  });
}

export function signup(email: string, password: string, name: string): Promise<{ user: AuthUser; token: string }> {
  return requestEnveloped('/api/v1/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ email, password, name }),
  });
}

export function login(email: string, password: string): Promise<{ user: AuthUser; token: string }> {
  return requestEnveloped('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export function getMe(): Promise<MeResponse> {
  return requestEnveloped('/api/v1/me');
}

export function listUsers(): Promise<AuthUser[]> {
  return requestEnveloped('/api/v1/users');
}

export function createGroup(name: string): Promise<GroupSummary> {
  return requestEnveloped('/api/v1/groups', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export function listGroupMembers(groupId: number): Promise<AuthUser[]> {
  return requestEnveloped(`/api/v1/groups/${groupId}/members`);
}

export function addGroupMember(groupId: number, userId: number): Promise<unknown> {
  return requestEnveloped(`/api/v1/groups/${groupId}/members`, {
    method: 'POST',
    body: JSON.stringify({ user_id: userId }),
  });
}

export function removeGroupMember(groupId: number, userId: number): Promise<unknown> {
  return requestEnveloped(`/api/v1/groups/${groupId}/members/${userId}`, {
    method: 'DELETE',
  });
}

export function inviteToGroupByEmail(groupId: number, email: string): Promise<InviteResult> {
  return requestEnveloped(`/api/v1/groups/${groupId}/invitations`, {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

export function listGroupInvitations(groupId: number): Promise<GroupInvitation[]> {
  return requestEnveloped(`/api/v1/groups/${groupId}/invitations`);
}

export function cancelGroupInvitation(groupId: number, invitationId: number): Promise<unknown> {
  return requestEnveloped(`/api/v1/groups/${groupId}/invitations/${invitationId}`, {
    method: 'DELETE',
  });
}

export function listAnnouncements(): Promise<AnnouncementRecord[]> {
  return requestEnveloped('/api/v1/announcements');
}

export function createAnnouncement(title: string, content: string): Promise<AnnouncementRecord> {
  return requestEnveloped('/api/v1/announcements', {
    method: 'POST',
    body: JSON.stringify({ title, content }),
  });
}

export function getCommitments(
  groupId: number,
  status?: CommitmentRecord['status'],
  limit?: number,
): Promise<CommitmentRecord[]> {
  const params = new URLSearchParams({ group_id: String(groupId) });
  if (status) params.set('status', status);
  if (limit) params.set('limit', String(limit));
  return requestEnveloped<CommitmentRecord[]>(`/api/v1/commitments?${params}`);
}

export function bulkUpdateCommitments(
  ids: number[],
  status: CommitmentRecord['status'],
): Promise<{ updated: number }> {
  return requestEnveloped<{ updated: number }>('/api/v1/commitments/bulk-status', {
    method: 'POST',
    body: JSON.stringify({ ids, status }),
  });
}
