import type { ReactNode } from 'react';

type Width = 'narrow' | 'default' | 'wide';

// 새로 정하는 값이 아니라 현재 화면들이 이미 쓰는 값에 이름을 붙인 것이다.
const WIDTH: Record<Width, string> = {
  narrow: 'max-w-3xl',
  default: 'max-w-4xl',
  wide: 'max-w-6xl',
};

type Props = {
  /** 제목 위 작은 영문 라벨. 예: "Call Summary" */
  eyebrow: string;
  title: string;
  /**
   * string이 아니라 ReactNode다. /chat의 설명문에 <span className="font-mono
   * text-brand">/help</span> 가 들어 있어 문자열로는 담기지 않는다.
   */
  description?: ReactNode;
  width?: Width;
  /** 헤더 우측 버튼. 좁은 폭에서는 제목 아래로 내려간다 */
  actions?: ReactNode;
  children: ReactNode;
};

export function PageShell({
  eyebrow,
  title,
  description,
  width = 'default',
  actions,
  children,
}: Props) {
  return (
    // 여백이 폭에 따라 줄어든다. 예전에는 모든 화면이 px-6 py-10 고정이라
    // 320px 기기에서 좌우 48px을 여백으로 썼다.
    <div
      className={`mx-auto ${WIDTH[width]} px-4 py-6 sm:px-6 sm:py-10 [animation:page-in_0.28s_ease-out]`}
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-xs uppercase tracking-widest text-brand">{eyebrow}</p>
          <h1 className="mt-1 text-2xl font-bold text-foreground">{title}</h1>
          {description && <p className="mt-2 text-sm text-foreground/60">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </div>

      <div className="mt-6">{children}</div>
    </div>
  );
}
