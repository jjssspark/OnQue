import { getToken } from './auth-storage';

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

export type AuthUser = {
  id: number;
  email: string;
  name: string;
  created_at: string;
};

export type GroupSummary = {
  id: number;
  name: string;
  role: 'admin' | 'member';
};

/** 그룹 멤버 목록의 각 행. role은 그 그룹에서의 역할(전역 role 아님). */
export type GroupMember = {
  id: number;
  name: string;
  email: string;
  role: 'admin' | 'member';
};

export type MeResponse = {
  user: AuthUser;
  groups: GroupSummary[];
};

export type ListMeta = { total: number; limit: number; hasNext: boolean };

export type ErrorDetail = { field: string | null; code: string };

type Envelope<T, M extends ListMeta = ListMeta> = {
  success: boolean;
  data: T;
  error: { code: string; message: string; details?: ErrorDetail[] } | null;
  meta?: M;
};

/** 봉투의 error.code를 살려서 던진다.
 *
 * 지금까지 request()가 message만 뽑아 `new Error(message)`로 던져 code를
 * 버렸다. 그래서 프론트는 서버 문구를 문자열 비교할 수밖에 없었는데,
 * api-contract.md는 message가 아니라 **code로 분기하라**고 못박는다 —
 * 문구는 언제든 바뀌고 그때마다 분기가 조용히 깨지기 때문이다.
 *
 * Error를 상속하므로 기존 `err instanceof Error ? err.message : ...`
 * 호출부는 하나도 고치지 않아도 그대로 동작한다. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  /** 검증 실패(VALIDATION_FAILED)일 때 어느 필드가 왜 틀렸는지. */
  readonly details: ErrorDetail[] | null;

  constructor(
    message: string,
    code: string,
    status: number,
    details: ErrorDetail[] | null = null,
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

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

/** 가입 여부와 무관하게 항상 이 형태로 응답한다 — 응답 차이로 가입 여부를 열거하지 못하게 하기 위함. */
export type InviteResult = { status: 'invited'; email: string };

/** 로그인한 사용자가 받은, 아직 응답하지 않은 그룹 초대. */
export type ReceivedInvitation = {
  id: number;
  group_id: number;
  group_name: string;
  invited_by_name: string;
  created_at: string;
};

export type Client = {
  id: number;
  name: string;
  created_at: string;
};

export type CommitmentRecord = {
  id: number;
  content: string;
  client_id: number | null;
  client_name: string | null;
  due_date: string | null;
  status: 'proposed' | 'confirmed' | 'fulfilled' | 'dismissed';
  source_type: 'call' | 'document' | 'chat';
  source_id: number | null;
  /** 채팅에서 뽑힌 약속의 출처 방. 다른 출처면 null. */
  room_id: number | null;
  evidence: string;
  is_overdue: boolean;
  is_due_soon: boolean;
  created_at: string;
};

/** 백그라운드 스윕이 직전에 무엇을 했는지.
 *
 * 아직 한 번도 대화를 훑지 않았으면 세 값이 모두 null이다. 0이 아닌 이유는
 * "훑었는데 못 찾음"과 "아직 훑은 적 없음"이 다른 상태이기 때문이다. */
export type SweepMeta = {
  last_at: string | null;
  scanned: number | null;
  found: number | null;
};

/** 오늘 AI 호출을 얼마나 썼는지.
 *
 * 스윕 메타와 분리돼 있다 — 이 예산은 스윕만의 것이 아니라 요약·비서·채팅이
 * 함께 쓴다. 남은 게 없으면 화면이 입력을 미리 막는 데 쓴다. */
export type AiBudget = {
  used: number;
  total: number;
  resets_at: string;
};

export type CommitmentListMeta = ListMeta & { sweep: SweepMeta; ai_budget: AiBudget };

export type AssistantActionKind =
  | 'todo_add'
  | 'todo_done'
  | 'todo_delete'
  | 'schedule_add'
  | 'schedule_delete'
  | 'commitment_status';

/** 서버가 검증을 마친 제안. payload는 kind마다 모양이 달라 실행 시점에 좁힌다. */
export type AssistantAction = {
  id: string;
  risk: 'safe' | 'confirm';
  kind: AssistantActionKind;
  label: string;
  warning: string | null;
  payload: Record<string, unknown>;
};

export type AssistantTurn = { role: 'user' | 'assistant'; content: string };

export type AssistantReply = { reply: string; actions: AssistantAction[] };

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
    // 봉투 밖 응답(리버스 프록시 오류 페이지 등)은 code가 없다. 그때만
    // UNKNOWN으로 떨어지고, 우리 API는 이제 항상 code를 채워 보낸다.
    throw new ApiError(
      message,
      body?.error?.code ?? 'UNKNOWN',
      res.status,
      body?.error?.details ?? null,
    );
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

async function requestEnveloped<T>(path: string, options?: RequestInit): Promise<T> {
  const envelope = await request<Envelope<T>>(path, options);
  return envelope.data;
}

/** requestEnveloped와 같은 언랩이지만 목록 조회의 meta(전체 개수 등)도 함께 돌려준다.
 * 화면에 온 개수와 서버가 가진 전체 개수가 다를 수 있는 목록(예: 약속 확인 필요 큐)에서
 * 조용한 잘림을 막으려면 meta가 필요하다. */
async function requestEnvelopedWithMeta<T, M extends ListMeta = ListMeta>(
  path: string,
  options?: RequestInit,
): Promise<{ data: T; meta: M | null }> {
  const envelope = await request<Envelope<T, M>>(path, options);
  return { data: envelope.data, meta: envelope.meta ?? null };
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
    throw new ApiError(
      message,
      body?.error?.code ?? 'UNKNOWN',
      res.status,
      body?.error?.details ?? null,
    );
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

export function createSchedule(
  groupId: number,
  title: string,
  scheduledDate: string,
): Promise<ScheduleItem> {
  return request('/schedules', {
    method: 'POST',
    body: JSON.stringify({ group_id: groupId, title, scheduled_date: scheduledDate }),
  });
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

export function createGroup(name: string): Promise<{ id: number; name: string }> {
  return requestEnveloped('/api/v1/groups', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export function updateMyName(name: string) {
  return requestEnveloped('/api/v1/me', {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  });
}

export function changeMyPassword(currentPassword: string, newPassword: string) {
  return requestEnveloped('/api/v1/me/password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

export function listGroupMembers(groupId: number): Promise<GroupMember[]> {
  return requestEnveloped(`/api/v1/groups/${groupId}/members`);
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

export function listMyInvitations(): Promise<ReceivedInvitation[]> {
  return requestEnveloped('/api/v1/me/invitations');
}

export function acceptInvitation(invitationId: number): Promise<{ group_id: number }> {
  return requestEnveloped(`/api/v1/me/invitations/${invitationId}/accept`, {
    method: 'POST',
  });
}

export function declineInvitation(invitationId: number): Promise<{ declined: boolean }> {
  return requestEnveloped(`/api/v1/me/invitations/${invitationId}`, {
    method: 'DELETE',
  });
}

export function listAnnouncements(
  groupId: number,
  limit?: number,
): Promise<{ data: AnnouncementRecord[]; meta: ListMeta | null }> {
  const params = new URLSearchParams({ group_id: String(groupId) });
  if (limit) params.set('limit', String(limit));
  return requestEnvelopedWithMeta<AnnouncementRecord[]>(`/api/v1/announcements?${params}`);
}

export function createAnnouncement(
  groupId: number,
  title: string,
  content: string,
): Promise<AnnouncementRecord> {
  return requestEnveloped('/api/v1/announcements', {
    method: 'POST',
    body: JSON.stringify({ group_id: groupId, title, content }),
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

/** getCommitments와 같은 조회지만 meta(전체 개수)도 함께 필요할 때 쓴다. */
export function getCommitmentsPage(
  groupId: number,
  status?: CommitmentRecord['status'],
  limit?: number,
): Promise<{ data: CommitmentRecord[]; meta: CommitmentListMeta | null }> {
  const params = new URLSearchParams({ group_id: String(groupId) });
  if (status) params.set('status', status);
  if (limit) params.set('limit', String(limit));
  return requestEnvelopedWithMeta<CommitmentRecord[], CommitmentListMeta>(
    `/api/v1/commitments?${params}`,
  );
}

export function getClients(groupId: number): Promise<Client[]> {
  return requestEnveloped<Client[]>(`/api/v1/clients?group_id=${groupId}&limit=100`);
}

export function createClient(groupId: number, name: string): Promise<Client> {
  return requestEnveloped<Client>('/api/v1/clients', {
    method: 'POST',
    body: JSON.stringify({ group_id: groupId, name }),
  });
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

export function sendAssistantMessage(
  groupId: number,
  message: string,
  history: AssistantTurn[],
): Promise<AssistantReply> {
  return requestEnveloped<AssistantReply>('/api/v1/assistant/messages', {
    method: 'POST',
    body: JSON.stringify({ group_id: groupId, message, history }),
  });
}
