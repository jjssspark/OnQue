import type { ButtonHTMLAttributes } from 'react';

type Props = {
  variant?: 'primary' | 'ghost';
  size?: 'sm' | 'md';
} & ButtonHTMLAttributes<HTMLButtonElement>;

const VARIANT = {
  primary: 'bg-brand text-brand-foreground hover:brightness-110',
  ghost: 'bg-white/10 text-fg-muted hover:bg-white/[0.16]',
} as const;

const SIZE = {
  sm: 'px-3 py-1.5 text-[11px]',
  md: 'px-4 py-2 text-xs',
} as const;

type ButtonClassesOptions = {
  variant?: 'primary' | 'ghost';
  size?: 'sm' | 'md';
  className?: string;
};

// 다음 태스크의 약속 카드는 <a> 안에 <button>을 넣지 않고 <Link>에 이
// 클래스를 직접 입힌다. 그래서 클래스 문자열을 함수로 빼 export 한다.
//
// transition 목록의 filter는 허용 목록(transform/opacity/background-color)
// 밖이지만 의도적으로 남긴다. filter는 GPU 합성이라 리플로우가 없다 —
// 제약이 막으려는 해악(레이아웃 스래싱)이 애초에 발생하지 않는다.
// hover:brightness-110의 부드러운 밝기 변화는 이것 없이는 즉시 튄다.
export function buttonClasses({
  variant = 'primary',
  size = 'md',
  className = '',
}: ButtonClassesOptions = {}): string {
  // focus-visible 링은 필수다. 기존 코드에는 포커스 표시가 아예 없어
  // 키보드 사용자가 지금 어디에 있는지 알 수 없었다.
  return `inline-flex items-center rounded-lg font-bold transition-[transform,filter,background-color] duration-150 active:scale-[.96] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 ${VARIANT[variant]} ${SIZE[size]} ${className}`;
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
