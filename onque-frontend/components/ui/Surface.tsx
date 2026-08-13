import type { ReactNode } from 'react';

type Props = {
  /** card는 떠 있는 면, sunken은 뒤로 물러난 면. 밝기로 층위를 만든다. */
  level?: 'card' | 'sunken';
  /** hover·focus에서 떠오르게 한다. 클릭 가능한 카드에만 준다. */
  interactive?: boolean;
  /** 기한 지난 항목은 배경에 코랄 기미를 준다. */
  tone?: 'default' | 'late';
  className?: string;
  children: ReactNode;
};

const LEVEL: Record<NonNullable<Props['level']>, string> = {
  card: 'bg-surface',
  sunken: 'bg-surface-sunken',
};

export function Surface({
  level = 'card',
  interactive = false,
  tone = 'default',
  className = '',
  children,
}: Props) {
  const toneClass =
    tone === 'late' ? 'bg-[linear-gradient(101deg,#241318_0%,#12151f_58%)]' : LEVEL[level];
  const motion = interactive
    ? 'transition-[transform,background-color] duration-300 ease-[cubic-bezier(.16,1,.3,1)] hover:-translate-y-[3px] hover:bg-surface-hover focus-within:-translate-y-[3px] focus-within:bg-surface-hover'
    : '';

  return <div className={`rounded-2xl ${toneClass} ${motion} ${className}`}>{children}</div>;
}
