'use client';

import Link from 'next/link';
import { BudgetGauge } from '@/components/dashboard/BudgetGauge';
import type { DocumentRecord, ScheduleItem } from '@/lib/api';

type Props = {
  schedules: ScheduleItem[];
  documents: DocumentRecord[];
};

/** DocumentRecord에는 title이 없다. history 페이지와 같은 방식으로
 *  headline이 있으면 그걸, 없으면 summary 평문을 쓴다. 둘 다 비어 있으면
 *  링크에 읽을 글자가 하나도 없는 빈 줄이 되므로 filename까지 내려간다. */
function documentLabel(doc: DocumentRecord): string {
  return doc.structured?.headline || doc.summary.replace(/\n/g, ' ') || doc.filename;
}

/**
 * 아무것도 안 골랐을 때의 오른쪽.
 *
 * 빈 패널로 두지 않는 이유는 화면 절반이 노는 것이기 때문이고, 별도 탭으로
 * 빼지 않는 이유는 하루에 한 번 볼까 말까 한 자리가 되기 때문이다.
 */
export function TodayOverview({ schedules, documents }: Props) {
  return (
    <div className="space-y-6 p-5">
      <div>
        <h2 className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">
          다가오는 일정
        </h2>
        {schedules.length === 0 ? (
          <p className="mt-2 text-xs text-ink-3">7일 안에 예정된 일정이 없습니다.</p>
        ) : (
          <ul className="mt-2 space-y-1.5">
            {schedules.map((schedule) => (
              <li key={schedule.id} className="flex items-baseline justify-between gap-3">
                <span className="truncate text-xs text-ink-2">{schedule.title}</span>
                <span className="shrink-0 font-mono text-[11px] tabular-nums text-ink-3">
                  {schedule.scheduled_date.slice(5)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-rule pt-5">
        <h2 className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">최근 요약</h2>
        {documents.length === 0 ? (
          <p className="mt-2 text-xs text-ink-3">아직 만든 요약이 없습니다.</p>
        ) : (
          <ul className="mt-2 space-y-1.5">
            {documents.slice(0, 5).map((doc) => (
              <li key={doc.id}>
                <Link
                  href="/history"
                  className="block truncate text-xs text-ink-2 hover:text-blue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue focus-visible:ring-offset-2 focus-visible:ring-offset-card-2"
                >
                  {documentLabel(doc)}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-rule pt-5">
        <BudgetGauge />
      </div>
    </div>
  );
}
