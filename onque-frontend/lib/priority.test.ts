import { describe, expect, it } from 'vitest';
import { buildPriorityStream, daysPastDue } from './priority';
import type { CommitmentRecord, Todo } from './api';

const TODAY = '2026-08-11';

function commitment(over: Partial<CommitmentRecord> & { id: number }): CommitmentRecord {
  return {
    content: '약속',
    client_id: null,
    client_name: null,
    due_date: null,
    status: 'proposed',
    source_type: 'call',
    source_id: null,
    room_id: null,
    evidence: '근거',
    is_overdue: false,
    is_due_soon: false,
    created_at: '2026-08-01T00:00:00Z',
    ...over,
  };
}

function todo(over: Partial<Todo> & { id: number }): Todo {
  return {
    content: '할 일',
    due_date: null,
    is_done: false,
    created_at: '2026-08-01T00:00:00Z',
    ...over,
  };
}

describe('daysPastDue', () => {
  it('기한이 지났으면 지난 일수를 센다', () => {
    expect(daysPastDue('2026-08-10', TODAY)).toBe(1);
    expect(daysPastDue('2026-08-04', TODAY)).toBe(7);
  });

  it('오늘이 기한이면 아직 안 지난 것이다', () => {
    expect(daysPastDue(TODAY, TODAY)).toBeNull();
  });

  it('기한이 남았거나 없으면 null이다', () => {
    expect(daysPastDue('2026-08-14', TODAY)).toBeNull();
    expect(daysPastDue(null, TODAY)).toBeNull();
  });
});

describe('buildPriorityStream', () => {
  it('기한 지난 것을 맨 앞에, 많이 지난 순으로 놓는다', () => {
    const stream = buildPriorityStream(
      [commitment({ id: 1, due_date: '2026-08-10' })],
      [todo({ id: 2, due_date: '2026-08-04' })],
      TODAY,
    );
    expect(stream.map((i) => i.key)).toEqual(['todo-2', 'commitment-1']);
    expect(stream[0].daysPastDue).toBe(7);
  });

  it('지난 것 다음에 임박한 것, 그다음 기한 있는 것을 기한 순으로 놓는다', () => {
    const stream = buildPriorityStream(
      [
        commitment({ id: 1, due_date: '2026-08-25' }),
        commitment({ id: 2, due_date: '2026-08-12' }),
      ],
      [todo({ id: 3, due_date: '2026-08-09' })],
      TODAY,
    );
    expect(stream.map((i) => i.key)).toEqual(['todo-3', 'commitment-2', 'commitment-1']);
    expect(stream[1].isDueSoon).toBe(true);
    expect(stream[2].isDueSoon).toBe(false);
  });

  it('기한 없는 것은 맨 뒤에, 최근 등록 순으로 놓는다', () => {
    const stream = buildPriorityStream(
      [],
      [
        todo({ id: 1, created_at: '2026-08-02T00:00:00Z' }),
        todo({ id: 2, created_at: '2026-08-09T00:00:00Z' }),
      ],
      TODAY,
    );
    expect(stream.map((i) => i.key)).toEqual(['todo-2', 'todo-1']);
  });

  it('완료한 할 일과 종료된 약속은 넣지 않는다', () => {
    const stream = buildPriorityStream(
      [
        commitment({ id: 1, status: 'fulfilled' }),
        commitment({ id: 2, status: 'dismissed' }),
        commitment({ id: 3, status: 'confirmed' }),
      ],
      [todo({ id: 4, is_done: true })],
      TODAY,
    );
    expect(stream.map((i) => i.key)).toEqual(['commitment-3']);
  });

  it('출처를 글자로 붙여 섞여도 무엇인지 알 수 있게 한다', () => {
    const stream = buildPriorityStream(
      [commitment({ id: 1, source_type: 'document' })],
      [todo({ id: 2 })],
      TODAY,
    );
    const byKey = Object.fromEntries(stream.map((i) => [i.key, i.sourceLabel]));
    expect(byKey['commitment-1']).toBe('약속 · 문서');
    expect(byKey['todo-2']).toBe('할 일');
  });

  it('확정 안 된 약속만 isUnconfirmed로 표시한다', () => {
    const stream = buildPriorityStream(
      [
        commitment({ id: 1, status: 'proposed' }),
        commitment({ id: 2, status: 'confirmed' }),
      ],
      [todo({ id: 3 })],
      TODAY,
    );
    const byKey = Object.fromEntries(stream.map((i) => [i.key, i.isUnconfirmed]));
    expect(byKey['commitment-1']).toBe(true);
    expect(byKey['commitment-2']).toBe(false);
    expect(byKey['todo-3']).toBe(false);
  });

  it('빈 입력에 빈 배열을 돌려준다', () => {
    expect(buildPriorityStream([], [], TODAY)).toEqual([]);
  });
});

describe('상세 패널용 필드', () => {
  it('약속은 근거 원문과 고객, 출처를 함께 싣는다', () => {
    const c = commitment({
      id: 1,
      content: '견적서 보내기',
      evidence: '내일까지 견적서 보내드릴게요',
      client_name: '한빛상사',
      source_type: 'chat',
    });

    const [item] = buildPriorityStream([c], [], TODAY);

    expect(item.evidence).toBe('내일까지 견적서 보내드릴게요');
    expect(item.clientName).toBe('한빛상사');
    expect(item.sourceType).toBe('chat');
  });

  it('할 일은 근거가 없다는 것을 null로 밝힌다', () => {
    const t = todo({ id: 1, content: '자료 정리' });

    const [item] = buildPriorityStream([], [t], TODAY);

    // 빈 문자열이 아니라 null이어야 한다. ''는 "근거가 비어 있다"로 읽히고
    // null은 "근거라는 것이 애초에 없다"로 읽힌다. 상세 패널이 이 둘을
    // 다르게 그려야 한다.
    expect(item.evidence).toBeNull();
    expect(item.clientName).toBeNull();
    expect(item.sourceType).toBeNull();
  });
});
