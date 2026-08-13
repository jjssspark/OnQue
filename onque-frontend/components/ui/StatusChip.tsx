import type { ReactNode } from 'react';

type Props = {
  tone: 'late' | 'soon' | 'neutral';
  children: ReactNode;
};

const TONE = {
  late: 'bg-late-bg text-late-fg',
  soon: 'bg-soon-bg text-soon-fg',
  neutral: 'bg-white/[0.07] text-fg-dim',
} as const;

/**
 * 상태 배지. children에 항상 글자를 넣는다 — 색만으로 구분하면
 * 색각 이상 사용자와 흑백 출력에서 정보가 사라진다.
 */
export function StatusChip({ tone, children }: Props) {
  return (
    <span
      className={`inline-block shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-extrabold tracking-tight ${TONE[tone]}`}
    >
      {children}
    </span>
  );
}
