'use client';

import { useLinkStatus } from 'next/link';

/**
 * 링크 전환이 진행 중임을 알리는 점.
 *
 * 반드시 <Link>의 자식으로 둔다 — useLinkStatus는 부모 Link의 상태를 읽는다.
 *
 * 이 앱에서 효과는 작다. 화면들이 클라이언트 컴포넌트라 라우트 전환이 이미
 * 즉시고, 해당 라우트의 JS 청크가 아직 없는 첫 클릭에서만 pending이 보인다.
 * .link-hint의 100ms 지연이 그 외 경우를 전부 걸러낸다.
 */
export function NavLinkHint() {
  const { pending } = useLinkStatus();
  return (
    <span
      aria-hidden
      className={`link-hint ml-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-brand ${
        pending ? 'is-pending' : ''
      }`}
    />
  );
}
