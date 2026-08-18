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

export function Surface({
  level = 'card',
  interactive = false,
  tone = 'default',
  className = '',
  children,
}: Props) {
  const motion = interactive
    ? 'transition-[transform,background-color] duration-300 ease-[cubic-bezier(.16,1,.3,1)] hover:-translate-y-[3px] hover:bg-card-2 focus-within:-translate-y-[3px] focus-within:bg-card-2'
    : '';

  return (
    <div className={`rounded-md ${LEVEL[level]} ${TONE[tone]} ${motion} ${className}`}>
      {children}
    </div>
  );
}
