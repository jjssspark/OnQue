'use client';

import { useEffect, useState } from 'react';

// 백엔드가 무료 티어라 유휴 상태에서 깨어나는 데 1분 가까이 걸린다.
// 그동안 사용자가 멈춘 것으로 오해하지 않도록 안내를 띄우기 위한 훅.
const DEFAULT_DELAY_MS = 3000;

export function useSlowRequestHint(active: boolean, delayMs = DEFAULT_DELAY_MS): boolean {
  const [isSlow, setIsSlow] = useState(false);

  useEffect(() => {
    if (!active) {
      setIsSlow(false);
      return;
    }
    const timer = setTimeout(() => setIsSlow(true), delayMs);
    return () => clearTimeout(timer);
  }, [active, delayMs]);

  return isSlow;
}
