'use client';

import Link from 'next/link';
import { Surface } from '@/components/ui/Surface';
import { Button, buttonClasses } from '@/components/ui/Button';
import { StatusChip } from '@/components/ui/StatusChip';
import { SkeletonList } from '@/components/ui/Skeleton';
import type { PriorityItem } from '@/lib/priority';

type Props = {
  items: PriorityItem[];
  /** 아직 조회 중이면 빈 목록이 "처리할 것 없음"으로 오해되지 않도록 구분한다. */
  isLoading?: boolean;
  onCompleteTodo: (id: number) => void;
};

function dueText(item: PriorityItem): string {
  if (item.daysPastDue !== null) return `기한 ${item.dueDate}`;
  if (item.dueDate) return `${item.dueDate}까지`;
  return '기한 없음';
}

export function PriorityStream({ items, isLoading = false, onCompleteTodo }: Props) {
  // 로딩과 "할 일 없음"은 다른 상태다. 예전에는 같은 카드 안에서 문구만
  // 바꿔, 데이터가 도착하면 카드가 통째로 목록으로 바뀌며 화면이 튀었다.
  if (isLoading && items.length === 0) {
    // h-[72px]는 브라우저에서 잰 카드 높이다. h-24(96px)는 24px씩 넘쳤다.
    //
    // 다만 이 값은 마우스 기준이다. globals.css의 .card-actions가 데스크톱에서는
    // max-height:0으로 접혀 있고 @media (pointer: coarse)에서는 펼쳐져 카드가
    // 130px 가까이 커진다. 한 값으로 두 쪽을 다 맞출 수 없어 더 흔한 쪽을 골랐다.
    return <SkeletonList rows={3} rowClassName="h-[72px]" label="우선순위 항목 불러오는 중" />;
  }

  if (items.length === 0) {
    return (
      <Surface level="sunken" className="p-10 text-center">
        <p className="text-sm text-fg-dim">지금 처리할 것이 없습니다.</p>
      </Surface>
    );
  }

  return (
    <ul className="space-y-2">
      {items.map((item) => (
        <li key={item.key}>
          <Surface
            interactive
            tone={item.daysPastDue !== null ? 'late' : 'default'}
            className="group p-4"
          >
            <div className="flex items-start gap-2.5">
              {item.daysPastDue !== null && (
                <span
                  aria-hidden
                  className="mt-1.5 h-[7px] w-[7px] shrink-0 rounded-full bg-late [animation:pulse-late_2.2s_ease-in-out_infinite]"
                />
              )}
              <p className="min-w-0 flex-1 text-sm font-semibold leading-snug text-foreground">
                {item.content}
              </p>
              {item.daysPastDue !== null && (
                <StatusChip tone="late">{item.daysPastDue}일 지남</StatusChip>
              )}
              {item.daysPastDue === null && item.isDueSoon && (
                <StatusChip tone="soon">마감 임박</StatusChip>
              )}
            </div>

            <p className="mt-1 text-[11px] text-fg-dim">
              {item.sourceLabel} · {dueText(item)}
              {item.isUnconfirmed && ' · 아직 확정 안 됨'}
            </p>

            <div className="card-actions">
              {item.kind === 'todo' ? (
                <Button size="sm" onClick={() => onCompleteTodo(item.id)}>
                  완료
                </Button>
              ) : (
                <Link href="/dashboard#commitments" className={buttonClasses({ size: 'sm' })}>
                  약속 확인하기
                </Link>
              )}
            </div>
          </Surface>
        </li>
      ))}
    </ul>
  );
}
