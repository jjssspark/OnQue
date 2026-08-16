'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useWorkspace } from '@/components/WorkspaceContext';
import { AssistantPanel } from '@/components/AssistantPanel';
import { SkeletonList } from '@/components/ui/Skeleton';

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' });
}

/** 마감까지 남은 날을 사람 말로. 서버 호출 없이 시간만으로 계산한다. */
function dueLabel(dueDate: string | null): string {
  if (!dueDate) return '기한 없음';
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(`${dueDate}T00:00:00`);
  const days = Math.round((due.getTime() - today.getTime()) / 86_400_000);
  if (days === 0) return '오늘 마감';
  if (days > 0) return `${days}일 남음`;
  return `${-days}일 지남`;
}

/** lastSyncedAt 이후 흐른 시간을 1초마다 다시 계산한다. API 호출은 없다. */
function useElapsedLabel(lastSyncedAt: number | null): string | null {
  const [, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  if (lastSyncedAt === null) return null;
  const secs = Math.floor((Date.now() - lastSyncedAt) / 1000);
  if (secs < 5) return '방금 갱신';
  if (secs < 60) return `${secs}초 전 갱신`;
  return `${Math.floor(secs / 60)}분 전 갱신`;
}

export function SmartDashboardPanel() {
  const { todos, schedules, loading, error, toggleTodo, removeTodo, removeSchedule,
          proposedCount, dueSoon, lastSyncedAt } = useWorkspace();
  const elapsed = useElapsedLabel(lastSyncedAt);
  const [expanded, setExpanded] = useState(false);
  const openTodos = todos.filter((t) => !t.is_done);
  const doneTodos = todos.filter((t) => t.is_done);

  return (
    <aside className="hidden w-[320px] shrink-0 flex-col overflow-hidden border-l border-border bg-surface lg:flex xl:w-[360px]">
      <div className="border-b border-border px-5 py-5">
        <p className="font-mono text-xs uppercase tracking-widest text-brand">Smart Dashboard</p>
        <h2 className="mt-1 text-sm font-bold text-foreground">실시간 업무 현황</h2>
        {elapsed && (
          <p className="mt-1 font-mono text-[10px] text-foreground/30">{elapsed}</p>
        )}
      </div>

      {error && (
        <p
          role="alert"
          className="border-b border-red-500/25 bg-red-500/[0.08] px-5 py-3 text-xs leading-relaxed text-red-300"
        >
          업무 데이터를 불러오지 못했습니다. 아래 목록은 비어 있는 것이 아니라 조회에 실패한
          상태입니다.
          <span className="mt-1 block font-mono text-[10px] opacity-70">{error}</span>
        </p>
      )}

      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-controls="smart-dashboard-lists"
        className="flex w-full items-center justify-between border-b border-border px-5 py-3 text-left transition hover:bg-foreground/[0.03]"
      >
        <span className="font-mono text-[10px] text-foreground/60">
          할 일 {openTodos.length} · 일정 {schedules.length}
          {(proposedCount > 0 || dueSoon.length > 0) &&
            ` · 확인 필요 ${proposedCount} · 기한 주의 ${dueSoon.length}`}
        </span>
        <span className="font-mono text-[10px] text-foreground/40">
          {expanded ? '접기' : '펼치기'}
        </span>
      </button>

      {/* 껍데기는 항상 렌더한다. 접었을 때 통째로 없애면 위 버튼의
          aria-controls가 없는 id를 가리켜, 정작 "이 버튼이 뭘 펼치는가"를
          알아야 할 접힌 상태에서 참조가 끊긴다. 안쪽 목록은 그대로 조건부라
          접혀 있는 동안 항목 200개를 만들지는 않는다. */}
      <div
        id="smart-dashboard-lists"
        hidden={!expanded}
        className="max-h-[45vh] shrink-0 overflow-y-auto"
      >
        {expanded && (
          <>
      {(proposedCount > 0 || dueSoon.length > 0) && (
        <section className="border-b border-border px-5 py-4">
          {proposedCount > 0 && (
            <Link
              href="/dashboard"
              className="mb-3 flex items-center justify-between rounded-lg border border-accent/30 bg-accent/[0.06] px-3 py-2 transition hover:bg-accent/[0.12]"
            >
              <span className="text-xs font-bold text-foreground">확인 필요</span>
              <span className="font-mono text-xs text-accent">{proposedCount}건</span>
            </Link>
          )}

          {dueSoon.length > 0 && (
            <Link
              href="/dashboard"
              aria-label={`기한 주의 약속 ${dueSoon.length}건 전체 보기`}
              className="block rounded-lg transition hover:bg-foreground/[0.04]"
            >
              <h3 className="mb-2 text-xs font-bold text-foreground/70">기한 주의 {dueSoon.length}</h3>
              <ul className="space-y-2">
                {dueSoon.slice(0, 5).map((c) => (
                  <li key={c.id} className="min-w-0">
                    <p className="truncate text-xs leading-relaxed text-foreground/90">{c.content}</p>
                    <p
                      className={`font-mono text-[10px] ${
                        c.is_overdue ? 'text-red-400' : 'text-accent'
                      }`}
                    >
                      {dueLabel(c.due_date)}
                    </p>
                  </li>
                ))}
              </ul>
            </Link>
          )}
        </section>
      )}

      <section className="border-b border-border px-5 py-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-xs font-bold text-foreground/70">할 일 {openTodos.length}</h3>
        </div>
        {/* h-9(36px)는 브라우저에서 실측한 값이다. 아래 <li>는 기한이 붙으면 35px,
            없으면 20px인데 할 일 대부분이 추출된 약속에서 와서 기한을 갖는다.
            3행이면 gap 포함 124px로 실측 120px에 거의 맞는다.
            계산으로 두 번 틀렸던 자리다 — 기한 없는 행만 보고 h-5로 낮췄더니 44px
            모자랐고, 그 전 h-10은 16px 넘쳤다. 결국 화면에서 재서 정했다. */}
        {loading && <SkeletonList rows={3} rowClassName="h-9" label="할 일 불러오는 중" />}
        {!loading && openTodos.length === 0 && (
          <p className="text-xs text-foreground/40">진행 중인 할 일이 없습니다.</p>
        )}
        <ul className="space-y-2">
          {openTodos.map((todo) => (
            <li key={todo.id} className="group flex items-start gap-2">
              <button
                onClick={() => toggleTodo(todo.id, true)}
                className="mt-0.5 h-4 w-4 shrink-0 rounded border border-border hover:border-brand"
                aria-label="완료 처리"
              />
              <div className="min-w-0 flex-1">
                <p className="text-xs leading-relaxed text-foreground/90">{todo.content}</p>
                {todo.due_date && (
                  <p className="text-[10px] text-foreground/40">~{formatDate(todo.due_date)}</p>
                )}
              </div>
              <button
                onClick={() => removeTodo(todo.id)}
                className="hover-reveal shrink-0 text-[10px] text-foreground/30 hover:text-red-500"
              >
                삭제
              </button>
            </li>
          ))}
        </ul>
        {doneTodos.length > 0 && (
          <p className="mt-3 text-[10px] text-foreground/30">완료 {doneTodos.length}건</p>
        )}
      </section>

      <section className="px-5 py-4">
        <h3 className="mb-3 text-xs font-bold text-foreground/70">일정 {schedules.length}</h3>
        {!loading && schedules.length === 0 && (
          <p className="text-xs text-foreground/40">등록된 일정이 없습니다.</p>
        )}
        <ul className="space-y-2">
          {schedules.map((schedule) => (
            <li key={schedule.id} className="group flex items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-xs text-foreground/90">{schedule.title}</p>
                <p className="text-[10px] font-mono text-foreground/40">
                  {formatDate(schedule.scheduled_date)}
                </p>
              </div>
              <button
                onClick={() => removeSchedule(schedule.id)}
                className="hover-reveal shrink-0 text-[10px] text-foreground/30 hover:text-red-500"
              >
                삭제
              </button>
            </li>
          ))}
        </ul>
      </section>
          </>
        )}
      </div>
      <AssistantPanel />
    </aside>
  );
}
