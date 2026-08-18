import type { PriorityItem } from './priority';

/** '이번 주'가 보는 날짜 폭. 오늘을 포함해 7일 뒤까지. */
const WEEK_WINDOW_DAYS = 7;

const MS_PER_DAY = 86_400_000;

export type FilterKey = 'all' | 'overdue' | 'today' | 'week' | 'unconfirmed';

/** 화면에 이 순서로 그린다. 급한 것부터 왼쪽. */
export const FILTERS: ReadonlyArray<{ key: FilterKey; label: string }> = [
  { key: 'all', label: '전체' },
  { key: 'overdue', label: '지남' },
  { key: 'today', label: '오늘' },
  { key: 'week', label: '이번 주' },
  { key: 'unconfirmed', label: '확인 필요' },
];

function shiftKey(dayKey: string, days: number): string {
  return new Date(Date.parse(`${dayKey}T00:00:00Z`) + days * MS_PER_DAY)
    .toISOString()
    .slice(0, 10);
}

/**
 * 항목이 이 필터에 걸리는가.
 *
 * '이번 주'가 지난 것을 빼는 이유는 '지남'과 겹치면 한 항목이 두 버튼에서
 * 세어지고, 사용자가 숫자를 더해 봤을 때 전체보다 커지기 때문이다.
 */
export function matchesFilter(item: PriorityItem, key: FilterKey, todayKey: string): boolean {
  switch (key) {
    case 'all':
      return true;
    case 'overdue':
      return item.daysPastDue !== null;
    case 'today':
      return item.dueDate === todayKey;
    case 'week':
      if (!item.dueDate) return false;
      return item.dueDate >= todayKey && item.dueDate <= shiftKey(todayKey, WEEK_WINDOW_DAYS);
    case 'unconfirmed':
      return item.isUnconfirmed;
  }
}

export function applyFilter(
  items: PriorityItem[],
  key: FilterKey,
  todayKey: string,
): PriorityItem[] {
  return items.filter((item) => matchesFilter(item, key, todayKey));
}

/** 버튼에 붙일 숫자. applyFilter와 같은 판정을 써야 화면이 어긋나지 않는다. */
export function countByFilter(
  items: PriorityItem[],
  todayKey: string,
): Record<FilterKey, number> {
  const counts = { all: 0, overdue: 0, today: 0, week: 0, unconfirmed: 0 };
  for (const item of items) {
    for (const { key } of FILTERS) {
      if (matchesFilter(item, key, todayKey)) counts[key] += 1;
    }
  }
  return counts;
}
