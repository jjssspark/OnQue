'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/components/AuthContext';
import { useWorkspace } from '@/components/WorkspaceContext';
import { MetricStrip, type Metric } from '@/components/MetricStrip';
import { getDocuments, type DocumentRecord } from '@/lib/api';

const MODULES = [
  { href: '/calls', title: '통화 요약', description: '녹음 파일을 콜 리포트로' },
  { href: '/documents', title: '문서·회의록 요약', description: 'PDF·텍스트에서 핵심만' },
  { href: '/chat', title: '팀 채팅', description: '@비서가 할 일을 정리' },
  { href: '/history', title: '이력 조회', description: '지난 요약 검색' },
];

const UPCOMING_WINDOW_DAYS = 7;

function toDateKey(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

function shiftDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function dueLabel(dueDate: string, todayKey: string): { text: string; alert: boolean } {
  if (dueDate < todayKey) return { text: '지연', alert: true };
  if (dueDate === todayKey) return { text: '오늘 마감', alert: true };
  return { text: `마감 ${dueDate}`, alert: false };
}

export default function DashboardPage() {
  const { user, groups } = useAuth();
  const { todos, schedules, currentGroupId, toggleTodo, error: workspaceError } = useWorkspace();
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [documentsError, setDocumentsError] = useState<string | null>(null);

  // 날짜 계산을 마운트 이후로 미룬다 — 서버와 클라이언트의 시각이 달라 생기는
  // 하이드레이션 불일치를 피하기 위해서다.
  const [today, setToday] = useState<Date | null>(null);
  useEffect(() => setToday(new Date()), []);

  useEffect(() => {
    if (currentGroupId === null) {
      setDocuments([]);
      setDocumentsError(null);
      return;
    }
    getDocuments(currentGroupId)
      .then((docs) => {
        setDocuments(docs);
        setDocumentsError(null);
      })
      .catch((err: unknown) => {
        setDocuments([]);
        setDocumentsError(
          err instanceof Error ? err.message : '요약 이력을 불러오지 못했습니다.',
        );
      });
  }, [currentGroupId]);

  const todayKey = today ? toDateKey(today) : null;
  const groupName = groups.find((g) => g.id === currentGroupId)?.name;

  const openTodos = useMemo(() => todos.filter((t) => !t.is_done), [todos]);

  const { dueTodayCount, overdueCount } = useMemo(() => {
    if (!todayKey) return { dueTodayCount: 0, overdueCount: 0 };
    let dueToday = 0;
    let overdue = 0;
    for (const todo of openTodos) {
      if (!todo.due_date) continue;
      if (todo.due_date === todayKey) dueToday += 1;
      else if (todo.due_date < todayKey) overdue += 1;
    }
    return { dueTodayCount: dueToday, overdueCount: overdue };
  }, [openTodos, todayKey]);

  const upcomingSchedules = useMemo(() => {
    if (!today || !todayKey) return [];
    const limitKey = toDateKey(shiftDays(today, UPCOMING_WINDOW_DAYS));
    return schedules
      .filter((s) => s.scheduled_date >= todayKey && s.scheduled_date <= limitKey)
      .slice(0, 5);
  }, [schedules, today, todayKey]);

  // 마감 임박한 것부터 보여준다. 마감일 없는 항목은 뒤로 민다.
  const priorityTodos = useMemo(() => {
    return [...openTodos]
      .sort((a, b) => {
        if (a.due_date && b.due_date) return a.due_date.localeCompare(b.due_date);
        if (a.due_date) return -1;
        if (b.due_date) return 1;
        return 0;
      })
      .slice(0, 6);
  }, [openTodos]);

  const metrics: Metric[] = [
    { label: 'Open', value: openTodos.length, hint: '진행 중인 할 일' },
    { label: 'Today', value: dueTodayCount, hint: '오늘 마감', alert: true },
    { label: 'Overdue', value: overdueCount, hint: '기한 지남', alert: true },
    { label: 'Upcoming', value: upcomingSchedules.length, hint: '7일 내 일정' },
  ];

  if (currentGroupId === null) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-10 text-sm text-foreground/60">
        아직 소속된 그룹이 없습니다. 관리자가 그룹에 초대하면 이용할 수 있습니다.
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-brand">Dashboard</p>
          <h1 className="mt-1 text-2xl font-bold text-foreground">업무 현황</h1>
        </div>
        <p className="text-xs text-foreground/40">
          {user?.name}
          {groupName && ` · ${groupName}`}
          {todayKey && ` · ${todayKey}`}
        </p>
      </div>

      {(workspaceError || documentsError) && (
        <div
          role="alert"
          className="mt-5 rounded-xl border border-red-500/25 bg-red-500/[0.06] px-4 py-3 text-sm text-red-600 dark:text-red-400"
        >
          <p className="font-semibold">일부 데이터를 불러오지 못했습니다.</p>
          <p className="mt-1 text-xs leading-relaxed opacity-80">
            아래 수치와 목록이 비어 보이는 것은 실제로 항목이 없어서가 아니라 조회에 실패했기
            때문일 수 있습니다.
          </p>
          <ul className="mt-2 space-y-0.5 font-mono text-[11px] opacity-70">
            {workspaceError && <li>할 일·일정: {workspaceError}</li>}
            {documentsError && <li>요약 이력: {documentsError}</li>}
          </ul>
        </div>
      )}

      <div className="mt-6">
        <MetricStrip metrics={metrics} />
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <section className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="text-sm font-bold text-foreground">우선 처리할 일</h2>
            <Link href="/chat" className="text-[11px] text-foreground/40 hover:text-brand">
              채팅에서 추가
            </Link>
          </div>

          {priorityTodos.length === 0 ? (
            <p className="mt-6 rounded-xl border border-dashed border-border p-8 text-center text-sm text-foreground/40">
              처리할 할 일이 없습니다.
            </p>
          ) : (
            <ul className="mt-3 divide-y divide-border">
              {priorityTodos.map((todo) => {
                const due = todo.due_date && todayKey ? dueLabel(todo.due_date, todayKey) : null;
                return (
                  <li key={todo.id} className="flex items-start gap-3 py-3">
                    <input
                      type="checkbox"
                      checked={todo.is_done}
                      onChange={(e) => toggleTodo(todo.id, e.target.checked)}
                      className="mt-0.5 h-4 w-4 shrink-0"
                      aria-label={`${todo.content} 완료 처리`}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-foreground/90">{todo.content}</p>
                      {due && (
                        <p
                          className={`mt-0.5 font-mono text-[11px] ${
                            due.alert ? 'text-red-500' : 'text-foreground/40'
                          }`}
                        >
                          {due.text}
                        </p>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <div className="space-y-5">
          <section className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
            <h2 className="text-sm font-bold text-foreground">다가오는 일정</h2>
            {upcomingSchedules.length === 0 ? (
              <p className="mt-4 text-xs text-foreground/40">7일 안에 예정된 일정이 없습니다.</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {upcomingSchedules.map((schedule) => (
                  <li
                    key={schedule.id}
                    className="flex items-center gap-3 rounded-lg border border-border bg-background px-3 py-2"
                  >
                    <span className="shrink-0 font-mono text-[11px] text-brand">
                      {schedule.scheduled_date.slice(5)}
                    </span>
                    <span className="truncate text-xs text-foreground/80">{schedule.title}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="text-sm font-bold text-foreground">최근 요약</h2>
              <Link href="/history" className="text-[11px] text-foreground/40 hover:text-brand">
                전체 보기
              </Link>
            </div>
            {documents.length === 0 ? (
              <p className="mt-4 text-xs text-foreground/40">
                아직 요약한 통화·문서가 없습니다.
              </p>
            ) : (
              <ul className="mt-3 space-y-2">
                {documents.slice(0, 4).map((doc) => (
                  <li key={doc.id}>
                    <Link
                      href="/history"
                      className="block rounded-lg border border-border bg-background px-3 py-2.5 transition-colors hover:border-brand/40"
                    >
                      <div className="flex items-center gap-2">
                        <span className="shrink-0 rounded-full bg-brand/10 px-1.5 py-0.5 text-[10px] font-semibold text-brand">
                          {doc.category}
                        </span>
                        <span className="truncate text-xs font-semibold text-foreground">
                          {doc.filename}
                        </span>
                      </div>
                      <p className="mt-1 truncate text-[11px] text-foreground/45">
                        {doc.structured?.headline || doc.summary.replace(/\n/g, ' ')}
                      </p>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>

      <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {MODULES.map((mod) => (
          <Link
            key={mod.href}
            href={mod.href}
            className="group rounded-xl border border-border bg-surface px-4 py-3.5 transition-all hover:-translate-y-0.5 hover:border-brand/40 hover:shadow-md"
          >
            <p className="text-xs font-bold text-foreground group-hover:text-brand">{mod.title}</p>
            <p className="mt-0.5 text-[11px] text-foreground/45">{mod.description}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
