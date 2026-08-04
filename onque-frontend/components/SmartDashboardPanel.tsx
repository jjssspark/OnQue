'use client';

import { useWorkspace } from '@/components/WorkspaceContext';

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' });
}

export function SmartDashboardPanel() {
  const { todos, schedules, loading, toggleTodo, removeTodo, removeSchedule } = useWorkspace();
  const openTodos = todos.filter((t) => !t.is_done);
  const doneTodos = todos.filter((t) => t.is_done);

  return (
    <aside className="hidden w-[320px] shrink-0 flex-col overflow-y-auto border-l border-border bg-surface lg:flex xl:w-[360px]">
      <div className="border-b border-border px-5 py-5">
        <p className="font-mono text-xs uppercase tracking-widest text-brand">Smart Dashboard</p>
        <h2 className="mt-1 text-sm font-bold text-foreground">실시간 업무 현황</h2>
      </div>

      <section className="border-b border-border px-5 py-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-xs font-bold text-foreground/70">✅ 할 일 {openTodos.length}</h3>
        </div>
        {loading && <p className="text-xs text-foreground/40">불러오는 중...</p>}
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
                className="shrink-0 text-[10px] text-foreground/30 opacity-0 hover:text-red-500 group-hover:opacity-100"
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
        <h3 className="mb-3 text-xs font-bold text-foreground/70">📅 일정 {schedules.length}</h3>
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
                className="shrink-0 text-[10px] text-foreground/30 opacity-0 hover:text-red-500 group-hover:opacity-100"
              >
                삭제
              </button>
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}
