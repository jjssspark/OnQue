'use client';

import Link from 'next/link';
import { Surface } from '@/components/ui/Surface';
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
      </div>
    </Surface>
  );
}
