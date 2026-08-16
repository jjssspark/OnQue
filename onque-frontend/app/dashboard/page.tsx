'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/components/AuthContext';
import { useWorkspace } from '@/components/WorkspaceContext';
import { type Metric } from '@/lib/metrics';
import CommitmentPanel from '@/components/CommitmentPanel';
import ClientPanel from '@/components/ClientPanel';
import { ReceivedInvitations } from '@/components/ReceivedInvitations';
import { PriorityStream } from '@/components/dashboard/PriorityStream';
import { SummaryColumn } from '@/components/dashboard/SummaryColumn';
import { PageShell } from '@/components/PageShell';
import { buildPriorityStream } from '@/lib/priority';
import {
  getCommitmentsPage,
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

// CommitmentPanel.tsx의 MAX_LIMIT과 같은 이유. 서버 기본 limit(20)에 걸리면
// 스트림이 실제보다 적어 보이는데, 아무 표시도 없이 그렇게 된다.
const COMMITMENTS_MAX_LIMIT = 100;

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
  const {
    todos,
    schedules,
    currentGroupId,
    toggleTodo,
    error: workspaceError,
    loading: workspaceLoading,
  } = useWorkspace();
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [commitments, setCommitments] = useState<CommitmentRecord[]>([]);
  const [commitmentsError, setCommitmentsError] = useState<string | null>(null);
  const [commitmentsLoading, setCommitmentsLoading] = useState(true);
  // 열린 약속이 COMMITMENTS_MAX_LIMIT을 넘겨 서버가 잘랐는지. 잘렸으면 가장
  // 오래된 것부터 빠지므로 스트림이 "지금 제일 급한 것"인 척하면 안 된다.
  const [commitmentsTruncated, setCommitmentsTruncated] = useState(false);

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

  // proposed·confirmed를 함께 조회해 하나로 합친다. meta.hasNext가 있으면
  // 서버가 잘랐다는 뜻이라 그 사실도 같이 돌려준다.
  const fetchCommitments = useCallback(async (groupId: number) => {
    const [proposed, confirmed] = await Promise.all([
      getCommitmentsPage(groupId, 'proposed', COMMITMENTS_MAX_LIMIT),
      getCommitmentsPage(groupId, 'confirmed', COMMITMENTS_MAX_LIMIT),
    ]);
    return {
      items: [...proposed.data, ...confirmed.data],
      truncated: Boolean(proposed.meta?.hasNext || confirmed.meta?.hasNext),
    };
  }, []);

  // CommitmentPanel에서 확정·무시가 끝난 뒤 호출된다. 패널은 자기 목록만
  // 다시 불러오므로, 스트림(본류)이 따라오려면 여기서도 다시 조회해야 한다.
  const refreshCommitments = useCallback(() => {
    if (currentGroupId === null) return;
    fetchCommitments(currentGroupId)
      .then(({ items, truncated }) => {
        setCommitments(items);
        setCommitmentsTruncated(truncated);
        setCommitmentsError(null);
      })
      .catch((err: unknown) => {
        setCommitments([]);
        setCommitmentsError(err instanceof Error ? err.message : '약속을 불러오지 못했습니다.');
      });
  }, [currentGroupId, fetchCommitments]);

  useEffect(() => {
    if (currentGroupId === null) {
      setCommitments([]);
      setCommitmentsError(null);
      setCommitmentsTruncated(false);
      setCommitmentsLoading(false);
      return;
    }
    // 그룹을 빠르게 전환하면 이전 그룹의 응답이 늦게 도착해 새 상태를 덮을 수
    // 있다. 언마운트·재실행 시 ignore를 세워 뒤늦은 응답을 버린다.
    let ignore = false;
    setCommitmentsLoading(true);
    fetchCommitments(currentGroupId)
      .then(({ items, truncated }) => {
        if (ignore) return;
        setCommitments(items);
        setCommitmentsTruncated(truncated);
        setCommitmentsError(null);
      })
      .catch((err: unknown) => {
        if (ignore) return;
        setCommitments([]);
        setCommitmentsError(err instanceof Error ? err.message : '약속을 불러오지 못했습니다.');
      })
      .finally(() => {
        if (ignore) return;
        setCommitmentsLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [currentGroupId, fetchCommitments]);

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

  // todayKey가 아직 없거나 할 일·약속 조회가 안 끝났으면 빈 배열이 "처리할
  // 것 없음"이 아니라 "아직 모른다"는 뜻이다. PriorityStream이 둘을 구분하게 한다.
  const isPriorityStreamLoading = !todayKey || workspaceLoading || commitmentsLoading;

  const metrics: Metric[] = [
    { label: 'Open', value: openTodos.length, hint: '진행 중인 할 일' },
    { label: 'Today', value: dueTodayCount, hint: '오늘 마감', alert: true },
    { label: 'Overdue', value: overdueCount, hint: '기한 지남', alert: true },
    { label: 'Upcoming', value: upcomingSchedules.length, hint: '7일 내 일정' },
  ];

  if (currentGroupId === null) {
    return (
      <PageShell eyebrow="Dashboard" title="업무 현황" width="wide">
        <ReceivedInvitations onChanged={refreshMe} />
        <p className="text-sm text-foreground/60">
          아직 소속된 팀이 없습니다. 받은 초대를 수락하거나 팀 관리에서 팀을 만들어 보세요.
        </p>
      </PageShell>
    );
  }

  return (
    <PageShell
      eyebrow="Dashboard"
      title="업무 현황"
      width="wide"
      actions={
        <p className="text-xs text-fg-dim">
          {user?.name}
          {groupName && ` · ${groupName}`}
          {todayKey && ` · ${todayKey}`}
        </p>
      }
    >
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
          <PriorityStream
            items={priorityStream}
            isLoading={isPriorityStreamLoading}
            onCompleteTodo={(id) => toggleTodo(id, true)}
          />
          {commitmentsTruncated && (
            <p className="mt-2 text-[11px] leading-relaxed text-foreground/40">
              오래된 약속 일부가 이 목록에 없습니다. 확인 필요에서 전체를 볼 수 있습니다.
            </p>
          )}
        </div>
        <div className="order-1 lg:order-2">
          <SummaryColumn metrics={metrics} schedules={upcomingSchedules} documents={documents} />
        </div>
      </div>

      <div id="commitments" className="mt-8 scroll-mt-6">
        <CommitmentPanel groupId={currentGroupId} onChanged={refreshCommitments} />
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_260px] xl:grid-cols-[1fr_280px]">
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
    </PageShell>
  );
}
