'use client';

import { useState, useSyncExternalStore } from 'react';

const SEEN_KEY = 'onque_chat_intro_seen';

/** 채팅방에 처음 들어온 사람에게 한 번만 보여주는 안내.
 *
 * 이 방의 대화는 백그라운드에서 훑여 약속으로 뽑힌다. 그걸 모르면 대시보드에
 * 처음 보는 항목이 생겼을 때 어디서 온 건지 알 수 없고, 반대로 여기 적은 말이
 * 어디로 가는지도 모른 채 쓰게 된다. 둘 다 한 번은 말해줘야 하는 것들이다.
 *
 * 방마다가 아니라 사람마다 한 번이다. 방을 옮길 때마다 같은 안내가 다시 뜨면
 * 읽히지 않고 닫는 버튼이 된다. */
export function ChatIntroNotice() {
  // 서버 렌더에는 localStorage가 없다. effect로 읽어 setState 하면 렌더가 한 번
  // 더 돌고 react-hooks/set-state-in-effect에도 걸리므로, 서버에 없는 값을
  // 읽는 정석인 useSyncExternalStore를 쓴다. 서버 스냅샷은 "이미 봤음"이라
  // 서버 HTML에는 안내가 없고, 하이드레이션 뒤 처음 온 사람에게만 나타난다.
  const seen = useSyncExternalStore(
    // 이 값은 아래 dismiss 말고는 바뀌지 않는다. 구독할 외부 이벤트가 없다.
    () => () => {},
    () => window.localStorage.getItem(SEEN_KEY) !== null,
    () => true,
  );
  // 위 스냅샷은 우리가 쓴 값을 다시 읽어오지 않으므로, 닫힘은 따로 기억한다.
  const [dismissed, setDismissed] = useState(false);

  const dismiss = () => {
    window.localStorage.setItem(SEEN_KEY, '1');
    setDismissed(true);
  };

  if (seen || dismissed) return null;

  return (
    <aside className="rounded-xl border border-brand/25 bg-brand/[0.06] px-4 py-3.5">
      <p className="text-xs font-semibold text-brand">이 방은 이렇게 동작합니다</p>
      <p className="mt-1.5 text-xs leading-relaxed text-foreground/60">
        여기 오간 대화는 주기적으로 자동 확인되어, 약속으로 보이는 말이 대시보드의
        &lsquo;확인 필요&rsquo;에 올라옵니다. 확정하기 전까지는 아무것도 일정이나 할 일이 되지
        않습니다. 요약이나 문서 작성이 필요하면{' '}
        <span className="font-mono text-brand">/help</span> 로 비서를 부르세요.
      </p>
      <button
        type="button"
        onClick={dismiss}
        className="mt-2.5 rounded text-[11px] font-semibold text-fg-dim transition-colors hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        알겠습니다
      </button>
    </aside>
  );
}
