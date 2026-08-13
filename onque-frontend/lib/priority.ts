import type { CommitmentRecord, Todo } from './api';

/** 기한이 이 일수 안으로 남았으면 임박으로 본다. 백엔드 DUE_SOON_DAYS와 같은 값. */
const DUE_SOON_DAYS = 2;

const MS_PER_DAY = 86_400_000;

const SOURCE_LABEL: Record<CommitmentRecord['source_type'], string> = {
  call: '통화',
  document: '문서',
  chat: '채팅',
};

/** 아직 처리 중인 약속만 스트림에 올린다. */
const OPEN_STATUSES: ReadonlySet<CommitmentRecord['status']> = new Set(['proposed', 'confirmed']);

export type PriorityItem = {
  /** React key. 종류가 다른 두 목록을 섞으므로 id만으로는 충돌한다. */
  key: string;
  kind: 'commitment' | 'todo';
  id: number;
  content: string;
  dueDate: string | null;
  /** 기한이 지났으면 지난 일수, 아니면 null */
  daysPastDue: number | null;
  isDueSoon: boolean;
  /** '약속 · 통화' 또는 '할 일' */
  sourceLabel: string;
  /** 정렬 최후 기준. ISO 8601 문자열 */
  createdAt: string;
  /** 약속만 가진다. 화면에 "아직 확정 안 됨"을 표시할지 판단한다. */
  isUnconfirmed: boolean;
};

function dayDiff(fromKey: string, toKey: string): number {
  return Math.round(
    (Date.parse(`${toKey}T00:00:00Z`) - Date.parse(`${fromKey}T00:00:00Z`)) / MS_PER_DAY,
  );
}

/**
 * 기한이 며칠 지났는지. 안 지났거나 기한이 없으면 null.
 *
 * 오늘이 기한인 것은 "지난" 것으로 세지 않는다 — 아직 하루가 남아 있다.
 */
export function daysPastDue(dueDate: string | null, todayKey: string): number | null {
  if (!dueDate || dueDate >= todayKey) return null;
  return dayDiff(dueDate, todayKey);
}

function isDueSoon(dueDate: string | null, todayKey: string): boolean {
  if (!dueDate || dueDate < todayKey) return false;
  return dayDiff(todayKey, dueDate) <= DUE_SOON_DAYS;
}

/** 급한 정도의 등급. 낮을수록 위. */
function rank(item: PriorityItem): number {
  if (item.daysPastDue !== null) return 0;
  if (item.isDueSoon) return 1;
  if (item.dueDate) return 2;
  return 3;
}

function compare(a: PriorityItem, b: PriorityItem): number {
  const rankDiff = rank(a) - rank(b);
  if (rankDiff !== 0) return rankDiff;

  // 많이 지난 것이 위
  if (a.daysPastDue !== null && b.daysPastDue !== null) return b.daysPastDue - a.daysPastDue;
  // 기한이 가까운 것이 위
  if (a.dueDate && b.dueDate) return a.dueDate.localeCompare(b.dueDate);
  // 기한이 없으면 최근 등록이 위
  return b.createdAt.localeCompare(a.createdAt);
}

/**
 * 약속과 할 일을 종류가 아니라 급한 순으로 하나의 목록에 섞는다.
 *
 * 종류별로 카드를 나누면 "지금 뭐가 급한가"를 알려고 여러 카드를 훑어야 한다.
 * 대신 각 항목에 출처를 글자로 붙여 섞여도 무엇인지 알 수 있게 한다.
 */
export function buildPriorityStream(
  commitments: CommitmentRecord[],
  todos: Todo[],
  todayKey: string,
): PriorityItem[] {
  const items: PriorityItem[] = [];

  for (const c of commitments) {
    if (!OPEN_STATUSES.has(c.status)) continue;
    items.push({
      key: `commitment-${c.id}`,
      kind: 'commitment',
      id: c.id,
      content: c.content,
      dueDate: c.due_date,
      daysPastDue: daysPastDue(c.due_date, todayKey),
      isDueSoon: isDueSoon(c.due_date, todayKey),
      sourceLabel: `약속 · ${SOURCE_LABEL[c.source_type]}`,
      createdAt: c.created_at,
      isUnconfirmed: c.status === 'proposed',
    });
  }

  for (const t of todos) {
    if (t.is_done) continue;
    items.push({
      key: `todo-${t.id}`,
      kind: 'todo',
      id: t.id,
      content: t.content,
      dueDate: t.due_date,
      daysPastDue: daysPastDue(t.due_date, todayKey),
      isDueSoon: isDueSoon(t.due_date, todayKey),
      sourceLabel: '할 일',
      createdAt: t.created_at,
      isUnconfirmed: false,
    });
  }

  return items.sort(compare);
}
