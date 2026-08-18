import type { ButtonHTMLAttributes } from 'react';

type Props = {
  variant?: 'primary' | 'ghost' | 'danger';
  size?: 'sm' | 'md';
} & ButtonHTMLAttributes<HTMLButtonElement>;

const VARIANT = {
  primary: 'bg-blue text-card-2 hover:bg-blue-deep active:bg-blue-deep',
  ghost: 'bg-transparent text-ink-2 hover:bg-blue-wash hover:text-blue-deep',
  danger: 'bg-late-wash text-late hover:bg-late hover:text-card-2',
} as const;

const SIZE = {
  sm: 'px-3 py-1.5 text-[11px]',
  md: 'px-4 py-2 text-xs',
} as const;

type ButtonClassesOptions = {
  variant?: 'primary' | 'ghost' | 'danger';
  size?: 'sm' | 'md';
  className?: string;
  /** 버튼이 놓이는 면. 링 오프셋 색을 그 면에 맞춘다. 기본값은 기존 동작과 같은 'paper'. */
  onSurface?: 'paper' | 'card' | 'card-2' | 'navy';
};

// className으로 ring-offset을 덮어쓰는 방식은 같은 Tailwind 특이도라 생성된
// CSS 순서에 따라 승패가 갈려 못 믿는다. 그래서 오프셋 색을 옵션으로 받는다.
const RING_OFFSET = {
  paper: 'focus-visible:ring-offset-paper',
  card: 'focus-visible:ring-offset-card',
  'card-2': 'focus-visible:ring-offset-card-2',
  navy: 'focus-visible:ring-offset-navy',
} as const;

// ring-blue는 남색 위에서 1.88:1로 보이지 않는다. 남색 면에서만 링 색도
// blue-wash로 같이 바꾼다 (남색 위 11.51:1) — 나머지 세 면은 그대로 blue.
const RING_COLOR = {
  paper: 'focus-visible:ring-blue',
  card: 'focus-visible:ring-blue',
  'card-2': 'focus-visible:ring-blue',
  navy: 'focus-visible:ring-blue-wash',
} as const;

// 다음 태스크의 약속 카드는 <a> 안에 <button>을 넣지 않고 <Link>에 이
// 클래스를 직접 입힌다. 그래서 클래스 문자열을 함수로 빼 export 한다.
//
// transition 목록의 filter는 허용 목록(transform/opacity/background-color)
// 밖이지만 의도적으로 남긴다. filter는 GPU 합성이라 리플로우가 없다 —
// 제약이 막으려는 해악(레이아웃 스래싱)이 애초에 발생하지 않는다.
export function buttonClasses({
  variant = 'primary',
  size = 'md',
  className = '',
  onSurface = 'paper',
}: ButtonClassesOptions = {}): string {
  // focus-visible 링은 필수다. 기존 코드에는 포커스 표시가 아예 없어
  // 키보드 사용자가 지금 어디에 있는지 알 수 없었다.
  // 링 색과 오프셋 색 둘 다 버튼이 놓인 면(onSurface)에 맞춘다.
  return `inline-flex items-center rounded-md font-bold transition-[transform,filter,background-color] duration-150 active:scale-[.96] focus-visible:outline-none focus-visible:ring-2 ${RING_COLOR[onSurface]} focus-visible:ring-offset-2 ${RING_OFFSET[onSurface]} disabled:pointer-events-none disabled:opacity-50 ${VARIANT[variant]} ${SIZE[size]} ${className}`;
}

export function Button({
  variant = 'primary',
  size = 'md',
  className = '',
  type = 'button',
  ...rest
}: Props) {
  return (
    <button type={type} className={buttonClasses({ variant, size, className })} {...rest} />
  );
}
