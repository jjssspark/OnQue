import { describe, expect, it } from 'vitest';
import { applyFilter, countByFilter, matchesFilter } from './dashboard-filter';
import type { PriorityItem } from './priority';

const TODAY = '2026-08-18';

function makeItem(over: Partial<PriorityItem>): PriorityItem {
  return {
    key: 'todo-1',
    kind: 'todo',
    id: 1,
    content: '무엇',
    dueDate: null,
    daysPastDue: null,
    isDueSoon: false,
    sourceLabel: '할 일',
    createdAt: '2026-08-18T00:00:00Z',
    isUnconfirmed: false,
    evidence: null,
    clientName: null,
    sourceType: null,
    ...over,
  };
}

describe('matchesFilter', () => {
  it('전체는 무엇이든 통과시킨다', () => {
    expect(matchesFilter(makeItem({}), 'all', TODAY)).toBe(true);
  });

  it('지남은 기한이 오늘보다 앞선 것만 고른다', () => {
    expect(matchesFilter(makeItem({ dueDate: '2026-08-17', daysPastDue: 1 }), 'overdue', TODAY)).toBe(true);
    expect(matchesFilter(makeItem({ dueDate: TODAY }), 'overdue', TODAY)).toBe(false);
    expect(matchesFilter(makeItem({ dueDate: null }), 'overdue', TODAY)).toBe(false);
  });

  it('지남은 daysPastDue만 보고 dueDate로 다시 계산하지 않는다', () => {
    // 지났는지는 buildPriorityStream 한 곳에서만 결정한다. dueDate와
    // daysPastDue가 일부러 어긋나는 이 행은 실무에서 나올 리 없는 값이
    // 아니라, matchesFilter가 그 결정을 믿지 않고 dueDate에서 다시
    // 계산하기 시작하면 바로 드러나는 경우를 잡아내기 위한 것이다.
    expect(
      matchesFilter(makeItem({ dueDate: '2026-08-17', daysPastDue: null }), 'overdue', TODAY),
    ).toBe(false);
    expect(matchesFilter(makeItem({ dueDate: null, daysPastDue: 3 }), 'overdue', TODAY)).toBe(true);
  });

  it('오늘은 기한이 오늘인 것만 고른다', () => {
    expect(matchesFilter(makeItem({ dueDate: TODAY }), 'today', TODAY)).toBe(true);
    expect(matchesFilter(makeItem({ dueDate: '2026-08-19' }), 'today', TODAY)).toBe(false);
  });

  it('이번 주는 오늘부터 7일 안을 고르고 지난 것은 빼놓는다', () => {
    expect(matchesFilter(makeItem({ dueDate: TODAY }), 'week', TODAY)).toBe(true);
    expect(matchesFilter(makeItem({ dueDate: '2026-08-25' }), 'week', TODAY)).toBe(true);
    expect(matchesFilter(makeItem({ dueDate: '2026-08-26' }), 'week', TODAY)).toBe(false);
    // 지난 것은 '지남'이 맡는다. 여기 또 들어가면 한 항목이 두 번 세어진다.
    expect(matchesFilter(makeItem({ dueDate: '2026-08-17', daysPastDue: 1 }), 'week', TODAY)).toBe(false);
  });

  it('확인 필요는 아직 확정 안 된 약속만 고른다', () => {
    expect(matchesFilter(makeItem({ isUnconfirmed: true }), 'unconfirmed', TODAY)).toBe(true);
    expect(matchesFilter(makeItem({ isUnconfirmed: false }), 'unconfirmed', TODAY)).toBe(false);
  });
});

describe('countByFilter', () => {
  it('버튼에 붙일 숫자를 필터마다 센다', () => {
    const items = [
      makeItem({ key: 'a', dueDate: '2026-08-17', daysPastDue: 1 }),
      makeItem({ key: 'b', dueDate: TODAY }),
      makeItem({ key: 'c', dueDate: '2026-08-20', isUnconfirmed: true }),
      makeItem({ key: 'd', dueDate: null }),
    ];

    expect(countByFilter(items, TODAY)).toEqual({
      all: 4,
      overdue: 1,
      today: 1,
      week: 2,
      unconfirmed: 1,
    });
  });
});

describe('applyFilter', () => {
  it('센 숫자와 좁힌 결과의 개수가 같다', () => {
    const items = [
      makeItem({ key: 'a', dueDate: '2026-08-17', daysPastDue: 1 }),
      makeItem({ key: 'b', dueDate: TODAY }),
      makeItem({ key: 'c', dueDate: null }),
    ];
    const counts = countByFilter(items, TODAY);

    // 숫자와 목록이 다른 로직으로 만들어지면 언젠가 어긋난다.
    // 같은 판정을 쓰는지 여기서 못 박는다.
    for (const key of ['all', 'overdue', 'today', 'week', 'unconfirmed'] as const) {
      expect(applyFilter(items, key, TODAY)).toHaveLength(counts[key]);
    }
  });

  it('좁혀도 원래 순서를 흐트러뜨리지 않는다', () => {
    const items = [makeItem({ key: 'a' }), makeItem({ key: 'b' }), makeItem({ key: 'c' })];
    expect(applyFilter(items, 'all', TODAY).map((i) => i.key)).toEqual(['a', 'b', 'c']);
  });
});
