import type { SweepMeta } from '@/lib/api';

/** 스윕 상태 한 줄을 만든다. 렌더링과 분리해 둔 이유는 경계값이 많아서다 —
 * 안 돌았을 때, 못 찾았을 때, 예산이 떨어졌을 때가 화면에서 각각 달라야 한다. */
export type SweepStatus = {
  /** 예: "12분 전 · 대화 34개에서 2건 찾음". 보여줄 게 없으면 null. */
  line: string | null;
  /** 오늘 예산을 다 썼는지. 다 썼으면 "왜 안 도는지"를 덧붙여야 한다. */
  exhausted: boolean;
};

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** "방금 / 12분 전 / 3시간 전 / 2일 전".
 *
 * 초 단위까지 내려가지 않는 이유: 스윕은 10분에 한 번이 상한이라 "8초 전"이
 * 나올 일이 없고, 나온다면 시계가 어긋난 것이다. */
export function formatElapsed(fromIso: string, now: number): string | null {
  const then = Date.parse(fromIso);
  if (Number.isNaN(then)) return null;

  const diff = now - then;
  // 서버 시계가 앞서 있으면 음수가 된다. "-3분 전"을 보여주느니 방금으로 뭉갠다.
  if (diff < MINUTE) return '방금';
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}분 전`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}시간 전`;
  return `${Math.floor(diff / DAY)}일 전`;
}

export function buildSweepStatus(sweep: SweepMeta | null, now: number): SweepStatus {
  const exhausted = sweep !== null && sweep.budget_used >= sweep.budget_total;
  if (sweep === null || sweep.last_at === null) {
    return { line: null, exhausted };
  }

  const elapsed = formatElapsed(sweep.last_at, now);
  if (elapsed === null) return { line: null, exhausted };

  // scanned/found는 last_at과 같은 순간에 기록되므로 함께 있거나 함께 없다.
  // 그래도 한쪽만 있는 응답을 만나면 시각만 보여준다 — 개수를 지어내지 않는다.
  if (sweep.scanned === null || sweep.found === null) {
    return { line: `${elapsed} 확인함`, exhausted };
  }

  const result =
    sweep.found > 0
      ? `대화 ${sweep.scanned}개에서 ${sweep.found}건 찾음`
      : `대화 ${sweep.scanned}개 확인, 새 약속 없음`;
  return { line: `${elapsed} · ${result}`, exhausted };
}
