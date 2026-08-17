'use client';

import Link from 'next/link';
import { Surface } from '@/components/ui/Surface';
import { useWorkspace } from '@/components/WorkspaceContext';
import { buildSweepStatus } from '@/lib/sweep-status';
import { isBudgetExhausted } from '@/lib/ai-budget';
import type { Metric } from '@/lib/metrics';
import type { DocumentRecord, ScheduleItem } from '@/lib/api';

type Props = {
  metrics: Metric[];
  schedules: ScheduleItem[];
  documents: DocumentRecord[];
};

export function SummaryColumn({ metrics, schedules, documents }: Props) {
  return (
    <Surface level="sunken" className="p-4">
      {/* 1024px 미만에서는 본류 위로 올라가 가로로 눕는다. */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-1 lg:gap-0">
        {metrics.map((metric, index) => (
          <div
            key={metric.label}
            className={index > 0 ? 'lg:mt-3 lg:border-t lg:border-hairline lg:pt-3' : ''}
          >
            <p
              className={`text-2xl font-bold leading-none tracking-tight tabular-nums ${
                metric.alert && metric.value > 0 ? 'text-late' : 'text-foreground'
              }`}
            >
              {metric.value}
            </p>
            <p className="mt-1 text-[10px] font-semibold text-fg-dim">{metric.hint}</p>
          </div>
        ))}
      </div>

      {/* 768px 미만에서는 숫자만 남기고 접는다. */}
      <div className="hidden md:block">
        <div className="mt-4 border-t border-hairline pt-4">
          <p className="text-[10px] font-semibold text-fg-dim">다가오는 일정</p>
          {schedules.length === 0 ? (
            <p className="mt-2 text-[11px] text-fg-dim">7일 안에 예정된 일정이 없습니다.</p>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {schedules.map((schedule) => (
                <li key={schedule.id} className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-[11px] text-fg-muted">{schedule.title}</span>
                  <span className="shrink-0 text-[10px] tabular-nums text-fg-dim">
                    {schedule.scheduled_date.slice(5)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="mt-4 border-t border-hairline pt-4">
          <div className="flex items-baseline justify-between gap-2">
            <p className="text-[10px] font-semibold text-fg-dim">최근 요약</p>
            <Link
              href="/history"
              className="rounded text-[10px] text-fg-dim transition-colors hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              전체 보기
            </Link>
          </div>
          {documents.length === 0 ? (
            <p className="mt-2 text-[11px] text-fg-dim">아직 요약한 통화·문서가 없습니다.</p>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {documents.slice(0, 3).map((doc) => (
                <li key={doc.id} className="truncate text-[11px] text-fg-muted">
                  {doc.filename}
                </li>
              ))}
            </ul>
          )}
        </div>

        <SweepStatusLine />
      </div>
    </Surface>
  );
}

/** "12분 전 · 대화 34개에서 2건 찾음" + "오늘 3/8".
 *
 * 스윕은 아무 표시 없이 돌아서, 사용자 입장에서는 약속이 어느 날 그냥 생겨
 * 있다. 목록을 믿으려면 언제 무엇을 보고 만든 건지 보여야 한다.
 *
 * 아직 한 번도 안 훑었으면 아무것도 그리지 않는다. "0건 찾음"을 띄우면
 * 일하고 있는데 성과가 없는 것처럼 읽힌다. */
function SweepStatusLine() {
  const { sweep, aiBudget, lastSyncedAt } = useWorkspace();
  // 기준 시각으로 Date.now()가 아니라 마지막 동기화 시각을 쓴다. 렌더 중
  // Date.now()를 부르면 같은 상태에서 매번 다른 화면이 나와 순수성이 깨지고,
  // 의미상으로도 이게 맞다 — "이 데이터가 도착한 시점 기준 경과"다.
  // 조회가 30초마다 돌아 값이 따라 갱신되고, 스윕 간격은 10분이라 티가 없다.
  if (sweep === null || lastSyncedAt === null) return null;

  const status = buildSweepStatus(sweep, lastSyncedAt);
  if (status.line === null && aiBudget === null) return null;

  const exhausted = isBudgetExhausted(aiBudget);

  return (
    <div className="mt-4 border-t border-hairline pt-4">
      <p className="text-[10px] font-semibold text-fg-dim">자동 확인</p>
      {status.line && (
        <p className="mt-2 text-[11px] leading-relaxed text-fg-muted">{status.line}</p>
      )}
      {aiBudget && (
        <p className="mt-1 text-[10px] tabular-nums text-fg-dim">
          오늘 {aiBudget.used}/{aiBudget.total}
          {exhausted && ' · 한도를 다 써 내일 이어서 확인합니다'}
        </p>
      )}
    </div>
  );
}
