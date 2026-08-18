'use client';

import { StatusChip } from '@/components/ui/StatusChip';
import { buttonClasses } from '@/components/ui/Button';
import { TodayOverview } from '@/components/dashboard/TodayOverview';
import type { DocumentRecord, ScheduleItem } from '@/lib/api';
import type { PriorityItem } from '@/lib/priority';

const SOURCE_TEXT: Record<NonNullable<PriorityItem['sourceType']>, string> = {
  call: '통화 기록에서 뽑음',
  document: '문서에서 뽑음',
  chat: '채팅에서 뽑음',
};

type Props = {
  item: PriorityItem | null;
  schedules: ScheduleItem[];
  documents: DocumentRecord[];
  onCompleteTodo: (id: number) => void;
};

/**
 * 오른쪽 상세 패널. item이 없으면 오늘 개요로 대체한다.
 *
 * 근거(evidence)는 약속만 가진다. 할 일은 evidence가 항상 null이고, 이는
 * "이 종류에는 근거라는 개념이 없다"는 뜻이라 빈 인용 상자를 그리지 않고
 * 출처 기록이 없다는 사실을 문장으로 밝힌다. 조용히 섹션을 생략하면
 * "이번엔 어쩌다 못 남았다"처럼 읽혀 다르게 처리했다.
 */
export function DetailPanel({ item, schedules, documents, onCompleteTodo }: Props) {
  if (!item) return <TodayOverview schedules={schedules} documents={documents} />;

  return (
    <div className="p-5">
      <div className="flex flex-wrap items-center gap-1.5">
        <StatusChip tone="neutral">{item.sourceLabel}</StatusChip>
        {item.daysPastDue !== null && (
          <StatusChip tone="late">{item.daysPastDue}일 지남</StatusChip>
        )}
        {item.daysPastDue === null && item.isDueSoon && <StatusChip tone="soon">임박</StatusChip>}
        {item.isUnconfirmed && <StatusChip tone="unconfirmed">확인 필요</StatusChip>}
      </div>

      <h2 className="mt-3 text-lg font-semibold leading-snug text-ink">{item.content}</h2>

      <dl className="mt-4 space-y-2 border-t border-rule pt-4 text-xs">
        <div className="flex gap-3">
          <dt className="w-16 shrink-0 text-ink-3">기한</dt>
          <dd className="font-mono tabular-nums text-ink-2">{item.dueDate ?? '없음'}</dd>
        </div>
        {item.clientName && (
          <div className="flex gap-3">
            <dt className="w-16 shrink-0 text-ink-3">고객</dt>
            <dd className="text-ink-2">{item.clientName}</dd>
          </div>
        )}
        <div className="flex gap-3">
          <dt className="w-16 shrink-0 text-ink-3">등록</dt>
          <dd className="font-mono tabular-nums text-ink-2">{item.createdAt.slice(0, 10)}</dd>
        </div>
      </dl>

      {item.evidence !== null ? (
        <div className="mt-5 border-t border-rule pt-4">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">
            {item.sourceType ? SOURCE_TEXT[item.sourceType] : '근거'}
          </p>
          <blockquote className="mt-2 border-l-2 border-blue bg-blue-wash px-3 py-2.5 text-xs leading-relaxed text-ink">
            {item.evidence || '근거 문장이 비어 있습니다.'}
          </blockquote>
        </div>
      ) : (
        <p className="mt-5 border-t border-rule pt-4 text-[11px] leading-relaxed text-ink-3">
          이 할 일은 어느 대화에서 나왔는지 기록이 남아 있지 않습니다.
        </p>
      )}

      {item.kind === 'todo' && (
        <button
          type="button"
          onClick={() => onCompleteTodo(item.id)}
          className={`mt-5 ${buttonClasses({ variant: 'primary', size: 'sm' })}`}
        >
          완료로 표시
        </button>
      )}
    </div>
  );
}
