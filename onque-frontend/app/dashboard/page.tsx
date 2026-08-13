'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/components/AuthContext';
import { useWorkspace } from '@/components/WorkspaceContext';
import { type Metric } from '@/components/MetricStrip';
import CommitmentPanel from '@/components/CommitmentPanel';
import ClientPanel from '@/components/ClientPanel';
import { ReceivedInvitations } from '@/components/ReceivedInvitations';
import { PriorityStream } from '@/components/dashboard/PriorityStream';
import { SummaryColumn } from '@/components/dashboard/SummaryColumn';
import { buildPriorityStream } from '@/lib/priority';
import {
  getCommitments,
  getDocuments,
  type CommitmentRecord,
  type DocumentRecord,
} from '@/lib/api';

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

export default function DashboardPage() {
  const { user, groups, refreshMe } = useAuth();
  const { todos, schedules, currentGroupId, toggleTodo, error: workspaceError } = useWorkspace();
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [commitments, setCommitments] = useState<CommitmentRecord[]>([]);
  const [commitmentsError, setCommitmentsError] = useState<string | null>(null);

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

  useEffect(() => {
    if (currentGroupId === null) {
      setCommitments([]);
      setCommitmentsError(null);
      return;
    }
    Promise.all([
      getCommitments(currentGroupId, 'proposed', 100),
      getCommitments(currentGroupId, 'confirmed', 100),
    ])
      .then(([proposed, confirmed]) => {
        setCommitments([...proposed, ...confirmed]);
        setCommitmentsError(null);
      })
      .catch((err: unknown) => {
        setCommitments([]);
        setCommitmentsError(err instanceof Error ? err.message : '약속을 불러오지 못했습니다.');
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

  const priorityStream = useMemo(() => {
    if (!todayKey) return [];
    return buildPriorityStream(commitments, todos, todayKey).slice(0, 8);
  }, [commitments, todos, todayKey]);

  const metrics: Metric[] = [
    { label: 'Open', value: openTodos.length, hint: '진행 중인 할 일' },
    { label: 'Today', value: dueTodayCount, hint: '오늘 마감', alert: true },
    { label: 'Overdue', value: overdueCount, hint: '기한 지남', alert: true },
    { label: 'Upcoming', value: upcomingSchedules.length, hint: '7일 내 일정' },
  ];

  if (currentGroupId === null) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-10">
        <ReceivedInvitations onChanged={refreshMe} />
        <p className="text-sm text-foreground/60">
          아직 소속된 팀이 없습니다. 받은 초대를 수락하거나 팀 관리에서 팀을 만들어 보세요.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-brand">Dashboard</p>
          <h1 className="mt-1 text-2xl font-bold text-foreground">업무 현황</h1>
        </div>
        <p className="text-xs text-fg-dim">
          {user?.name}
          {groupName && ` · ${groupName}`}
          {todayKey && ` · ${todayKey}`}
        </p>
      </div>

      {(workspaceError || documentsError || commitmentsError) && (
        <div
          role="alert"
          className="mt-5 rounded-xl border border-red-500/30 bg-red-500/[0.08] px-4 py-3 text-sm text-red-300"
        >
          <p className="font-semibold">일부 데이터를 불러오지 못했습니다.</p>
          <p className="mt-1 text-xs leading-relaxed opacity-80">
            아래 수치와 목록이 비어 보이는 것은 실제로 항목이 없어서가 아니라 조회에 실패했기
            때문일 수 있습니다.
          </p>
          <ul className="mt-2 space-y-0.5 font-mono text-[11px] opacity-70">
            {workspaceError && <li>할 일·일정: {workspaceError}</li>}
            {commitmentsError && <li>약속: {commitmentsError}</li>}
            {documentsError && <li>요약 이력: {documentsError}</li>}
          </ul>
        </div>
      )}

      <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_260px] xl:grid-cols-[1fr_280px]">
        {/* 좁은 화면에서는 요약이 본류 위로 올라간다. */}
        <div className="order-2 lg:order-1">
          <PriorityStream items={priorityStream} onCompleteTodo={(id) => toggleTodo(id, true)} />
        </div>
        <div className="order-1 lg:order-2">
          <SummaryColumn metrics={metrics} schedules={upcomingSchedules} documents={documents} />
        </div>
      </div>

      <div id="commitments" className="mt-8 scroll-mt-6">
        <CommitmentPanel groupId={currentGroupId} />
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_280px]">
        <div className="grid gap-3 sm:grid-cols-2">
          {MODULES.map((mod) => (
            <Link
              key={mod.href}
              href={mod.href}
              className="group rounded-xl bg-surface px-4 py-3.5 transition-[transform,background-color] duration-300 ease-[cubic-bezier(.16,1,.3,1)] hover:-translate-y-[3px] hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              <p className="text-xs font-bold text-foreground group-hover:text-brand">{mod.title}</p>
              <p className="mt-0.5 text-[11px] text-fg-dim">{mod.description}</p>
            </Link>
          ))}
        </div>
        <ClientPanel groupId={currentGroupId} />
      </div>
    </div>
  );
}
