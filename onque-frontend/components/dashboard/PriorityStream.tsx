'use client';

import Link from 'next/link';
import { Surface } from '@/components/ui/Surface';
import { Button, buttonClasses } from '@/components/ui/Button';
import { StatusChip } from '@/components/ui/StatusChip';
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
  if (items.length === 0) {
    return (
      <Surface level="sunken" className="p-10 text-center">
        <p className="text-sm text-fg-dim">
          {isLoading ? '불러오는 중...' : '지금 처리할 것이 없습니다.'}
        </p>
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
