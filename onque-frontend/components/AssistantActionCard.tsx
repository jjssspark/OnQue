'use client';

import { useState } from 'react';
import {
  bulkUpdateCommitments,
  createSchedule,
  createTodo,
  deleteSchedule,
  deleteTodo,
  updateTodo,
  type AssistantAction,
} from '@/lib/api';

type State = 'idle' | 'running' | 'applied' | 'declined' | 'failed';

/** 서버가 kind를 정해서 내려보내고, 프론트는 여기서 고정 분기한다.
 * 응답에 URL을 담지 않는 이유다 — 모델 출력이 요청 경로에 닿지 않게 한다.
 * 생성 계열은 만들어진 id를 돌려준다(취소할 때 필요하다). */
export async function applySafeAction(
  action: AssistantAction,
  groupId: number,
): Promise<number | null> {
  const p = action.payload;
  switch (action.kind) {
    case 'todo_add': {
      const todo = await createTodo(
        groupId,
        p.content as string,
        (p.due_date as string | null) ?? undefined,
      );
      return todo.id;
    }
    case 'todo_done':
      await updateTodo(p.todo_id as number, { is_done: true });
      return null;
    case 'todo_delete':
      await deleteTodo(p.todo_id as number);
      return null;
    case 'schedule_add': {
      const schedule = await createSchedule(
        groupId,
        p.title as string,
        p.scheduled_date as string,
      );
      return schedule.id;
    }
    case 'schedule_delete':
      await deleteSchedule(p.schedule_id as number);
      return null;
    case 'commitment_status':
      await bulkUpdateCommitments(
        [p.commitment_id as number],
        p.to_status as 'confirmed' | 'fulfilled' | 'dismissed',
      );
      return null;
  }
}

/** 방금 한 일을 되돌린다. safe 액션에만 붙는다 — confirm 액션은 애초에
 * 되돌릴 수 없어서 승인을 받는 것이다. */
async function undo(action: AssistantAction, createdId: number | null): Promise<void> {
  switch (action.kind) {
    case 'todo_add':
      if (createdId !== null) await deleteTodo(createdId);
      return;
    case 'todo_done':
      await updateTodo(action.payload.todo_id as number, { is_done: false });
      return;
    case 'schedule_add':
      if (createdId !== null) await deleteSchedule(createdId);
      return;
    default:
      return;
  }
}

export function AssistantActionCard({
  action,
  groupId,
  createdId = null,
  failed = false,
  onChanged,
}: {
  action: AssistantAction;
  groupId: number;
  /** safe 액션은 AssistantPanel이 응답 직후 이미 실행했다. 그때 만들어진 id. */
  createdId?: number | null;
  /** safe 액션이 AssistantPanel의 즉시 실행 루프에서 실패했으면 true.
   * 실행 안 된 걸 '적용됨'으로 보여주지 않기 위한 초기 상태 판정. */
  failed?: boolean;
  onChanged: () => void;
}) {
  const [state, setState] = useState<State>(
    action.risk === 'safe' ? (failed ? 'failed' : 'applied') : 'idle',
  );
  const [madeId, setMadeId] = useState<number | null>(createdId);
  const [failure, setFailure] = useState<string | null>(null);

  const run = async () => {
    setState('running');
    setFailure(null);
    try {
      setMadeId(await applySafeAction(action, groupId));
      setState('applied');
      onChanged();
    } catch (err) {
      setState('failed');
      setFailure(err instanceof Error ? err.message : '실행하지 못했습니다.');
    }
  };

  const rollback = async () => {
    setState('running');
    setFailure(null);
    try {
      await undo(action, madeId);
      setState('declined');
      onChanged();
    } catch (err) {
      setState('failed');
      setFailure(err instanceof Error ? err.message : '되돌리지 못했습니다.');
    }
  };

  return (
    <div className="rounded-lg border border-rule-strong bg-card-2 px-3 py-2">
      <p className="text-xs font-bold leading-relaxed text-ink">{action.label}</p>

      {action.kind === 'commitment_status' && (
        <p className="mt-1 border-l-2 border-rule pl-2 text-xs italic leading-relaxed text-ink-2">
          {String(action.payload.content ?? '')}
          {action.payload.client_name ? ` — ${String(action.payload.client_name)}` : ''}
        </p>
      )}

      {action.warning && state !== 'declined' && (
        <p className="mt-1 font-mono text-[10px] text-soon">{action.warning}</p>
      )}

      {failure && (
        <p role="alert" className="mt-1 text-[10px] leading-relaxed text-late">
          {failure}
        </p>
      )}

      <div className="mt-2 flex gap-2">
        {state === 'idle' && (
          <>
            <button
              type="button"
              onClick={run}
              className="rounded border border-soon/40 px-2 py-1 text-[10px] font-bold text-soon transition hover:bg-soon-wash"
            >
              그렇게 해
            </button>
            <button
              type="button"
              onClick={() => setState('declined')}
              className="rounded border border-rule px-2 py-1 text-[10px] text-ink-2 transition hover:bg-card"
            >
              아니
            </button>
          </>
        )}

        {state === 'running' && <span className="text-[10px] text-ink-3">처리 중…</span>}

        {state === 'applied' && (
          <>
            <span className="text-[10px] text-ink-3">적용됨</span>
            {action.risk === 'safe' && (
              <button
                type="button"
                onClick={rollback}
                className="rounded border border-rule px-2 py-1 text-[10px] text-ink-2 transition hover:bg-card"
              >
                취소
              </button>
            )}
          </>
        )}

        {state === 'declined' && <span className="text-[10px] text-ink-3">하지 않음</span>}

        {state === 'failed' && (
          <button
            type="button"
            onClick={run}
            className="rounded border border-rule px-2 py-1 text-[10px] text-ink-2 transition hover:bg-card"
          >
            다시 시도
          </button>
        )}
      </div>
    </div>
  );
}
