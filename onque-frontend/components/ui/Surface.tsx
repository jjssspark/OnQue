import type { ReactNode } from 'react';

type Props = {
  /** card는 목록이 놓이는 기본 면, sunken은 뒤로 물러난 면, raised는 본문 대비가
   * 가장 센 읽는 면. 밝기로 층위를 만든다. */
  level?: 'card' | 'sunken' | 'raised';
  /** hover·focus에서 떠오르게 한다. 클릭 가능한 카드에만 준다. */
  interactive?: boolean;
  /** 기한 지난 항목은 왼쪽 굵은 선과 배경으로 알린다. */
  tone?: 'default' | 'late';
  className?: string;
  children: ReactNode;
};

const LEVEL: Record<NonNullable<Props['level']>, string> = {
  card: 'bg-card border border-rule',
  sunken: 'bg-paper border border-rule',
  raised: 'bg-card-2 border border-rule-strong',
};

// 기한 지난 것은 색만이 아니라 왼쪽 굵은 선으로도 알린다.
// 색각 이상에서도 구분되게 하려면 색 하나로는 부족하다.
const TONE: Record<NonNullable<Props['tone']>, string> = {
  default: '',
  late: 'border-l-2 border-l-late bg-late-wash',
};

// interactive hover는 level별로 다르다. card/raised는 이미 밝기 램프
// 위쪽이라 배경을 더 밝힐 여지가 없다 — sunken만 배경을 밝히고,
// card는 테두리를, raised는 그림자를 hover 신호로 쓴다.
const HOVER: Record<NonNullable<Props['level']>, string> = {
  card: 'hover:border-rule-strong focus-within:border-rule-strong',
  sunken: 'hover:bg-card-2 focus-within:bg-card-2',
  raised: 'hover:shadow-md hover:shadow-navy/20 focus-within:shadow-md focus-within:shadow-navy/20',
};

export function Surface({
  level = 'card',
  interactive = false,
  tone = 'default',
  className = '',
  children,
}: Props) {
  const motion = interactive
    ? `transition-[transform,background-color,border-color,box-shadow] duration-300 ease-[cubic-bezier(.16,1,.3,1)] hover:-translate-y-[3px] focus-within:-translate-y-[3px] ${HOVER[level]}`
    : '';

  return (
    <div className={`rounded-md ${LEVEL[level]} ${TONE[tone]} ${motion} ${className}`}>
      {children}
    </div>
  );
}
