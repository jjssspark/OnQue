'use client';

import { Surface } from '@/components/ui/Surface';
import { StatusChip } from '@/components/ui/StatusChip';
import { SkeletonList } from '@/components/ui/Skeleton';
import type { PriorityItem } from '@/lib/priority';

type Props = {
  items: PriorityItem[];
  /** 아직 조회 중이면 빈 목록이 "처리할 것 없음"으로 오해되지 않도록 구분한다. */
  isLoading?: boolean;
  /** 지금 고른 항목의 key. 아무것도 안 골랐으면 null */
  selectedKey: string | null;
  onSelect: (item: PriorityItem) => void;
};

function dueText(item: PriorityItem): string {
  if (item.daysPastDue !== null) return `기한 ${item.dueDate}`;
  if (item.dueDate) return `${item.dueDate}까지`;
  return '기한 없음';
}

export function PriorityStream({ items, isLoading = false, selectedKey, onSelect }: Props) {
  // 로딩과 "할 일 없음"은 다른 상태다. 예전에는 같은 카드 안에서 문구만
  // 바꿔, 데이터가 도착하면 카드가 통째로 목록으로 바뀌며 화면이 튀었다.
  if (isLoading && items.length === 0) {
    return <SkeletonList rows={3} rowClassName="h-[72px]" label="우선순위 항목 불러오는 중" />;
  }

  if (items.length === 0) {
    return (
      <Surface level="sunken" className="p-10 text-center">
        <p className="text-sm text-ink-3">지금 처리할 것이 없습니다.</p>
      </Surface>
    );
  }

  return (
    <ul className="divide-y divide-rule">
      {items.map((item) => {
        const isLate = item.daysPastDue !== null;
        const isSelected = item.key === selectedKey;

        // 선택(파랑)과 지남(빨강)은 둘 다 왼쪽 선을 쓴다 — 지금 보는 항목이
        // 뭔지가 지남 여부보다 급하므로 선택이 우선한다.
        //
        // hover는 배경색만 바꾸고 border-l-* 유틸은 절대 건드리지 않는다.
        // Surface의 interactive+tone 조합을 그대로 쓰면 hover가 테두리 전체
        // 색(border-rule-strong)을 덮어써 지남 표시(border-l-late)가
        // 사라진다 — 여기서는 그 조합을 쓰지 않고 배경/테두리를 행에서 직접
        // 관리해 hover가 border-l 색에 손대지 않게 한다.
        const borderClass = isSelected
          ? 'border-l-blue'
          : isLate
            ? 'border-l-late'
            : 'border-l-transparent';
        const bgClass = isSelected
          ? 'bg-blue-wash'
          : isLate
            ? 'bg-late-wash'
            : 'hover:bg-card-2';

        return (
          <li key={item.key}>
            <button
              type="button"
              onClick={() => onSelect(item)}
              aria-current={isSelected ? 'true' : undefined}
              className={`w-full border-l-2 px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue ${borderClass} ${bgClass}`}
            >
              <div className="flex items-start gap-2.5">
                {isLate && (
                  <span
                    aria-hidden
                    className="mt-1.5 h-[7px] w-[7px] shrink-0 rounded-full bg-late [animation:pulse-late_2.2s_ease-in-out_infinite]"
                  />
                )}
                <p className="min-w-0 flex-1 text-sm font-semibold leading-snug text-ink">
                  {item.content}
                </p>
                {isLate && <StatusChip tone="late">{item.daysPastDue}일 지남</StatusChip>}
                {!isLate && item.isDueSoon && <StatusChip tone="soon">마감 임박</StatusChip>}
              </div>

              <p className="mt-1 text-[11px] text-ink-3">
                {item.sourceLabel} · {dueText(item)}
                {item.isUnconfirmed && ' · 아직 확정 안 됨'}
              </p>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
