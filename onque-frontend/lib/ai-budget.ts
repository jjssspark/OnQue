import { ApiError, type AiBudget } from '@/lib/api';
import { formatResetTime } from '@/lib/sweep-status';

/** 오늘 몫을 다 썼는가.
 *
 * null은 "아직 모른다"이지 "소진됐다"가 아니다. 모를 때 막으면 서버는 멀쩡한데
 * 화면만 잠긴다 — 워크스페이스 첫 조회 전이 항상 그 상태다. */
export function isBudgetExhausted(budget: AiBudget | null): boolean {
  return budget !== null && budget.used >= budget.total;
}

/** 소진을 알리는 문장.
 *
 * 사전 차단 안내와 429를 받았을 때의 안내가 같은 문장을 쓰도록 한곳에서 만든다.
 * 서버가 준 문구를 그대로 쓰지 않는 이유는 api-contract 규약이다 — 문구는
 * 언제든 바뀌고, 프론트는 code로 분기하고 표시는 스스로 책임진다. */
export function budgetExhaustedText(budget: AiBudget | null): string {
  const resetsAt = budget === null ? null : formatResetTime(budget.resets_at);
  return resetsAt
    ? `오늘 AI 한도를 다 썼습니다. ${resetsAt}에 초기화됩니다.`
    : '오늘 AI 한도를 다 썼습니다. 내일 다시 이용해주세요.';
}

/** 서버가 한도 소진으로 거절했는가.
 *
 * 화면의 예산 값은 워크스페이스를 불러온 시점의 것이라 연달아 보내면 실제보다
 * 낙관적이다. 사전 차단은 헛수고를 줄이는 장치일 뿐 보장이 아니므로, 새어 나간
 * 요청은 여기서 받는다. */
export function isBudgetExhaustedError(err: unknown): boolean {
  return err instanceof ApiError && err.code === 'AI_DAILY_BUDGET_EXHAUSTED';
}
