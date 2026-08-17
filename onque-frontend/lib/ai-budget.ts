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

/** 채팅방에만 덧붙이는 탈출구 안내.
 *
 * 예산은 AI 기능의 한도이지 채팅방의 한도가 아니다. 소진됐다는 사실만 알리고
 * 나갈 길을 안 알려주면 사용자는 방이 고장 난 줄 안다.
 * 요약·비서 화면에는 /exit 개념이 없어 이 문장을 공유하지 않는다. */
export const CHAT_BUDGET_ESCAPE_HINT =
  '/ 로 시작하는 명령은 보낼 수 있습니다. /exit 로 비서를 내보내면 대화를 이어갈 수 있습니다.';

/** 소진 상태에서 이 채팅 입력을 막아야 하는가.
 *
 * 명령은 막지 않는다. /exit·/help는 모델을 부르지 않아 통과해야 하고,
 * /요약·/문서는 서버 예산 문이 429로 가른다 — 어느 명령이 모델을 부르는지를
 * 프론트가 따로 외우면 서버가 바뀔 때 조용히 어긋난다. 가르는 일은 서버에 두고,
 * 여기서는 "명령이냐 아니냐"만 본다. */
export function isChatSendBlocked(
  input: string,
  aiMode: boolean,
  budget: AiBudget | null,
): boolean {
  // AI가 방에 없으면 Gemini를 부르지 않으므로 한도와 무관하다.
  if (!aiMode || !isBudgetExhausted(budget)) return false;
  return !input.trim().startsWith('/');
}

/** 서버가 한도 소진으로 거절했는가.
 *
 * 화면의 예산 값은 워크스페이스를 불러온 시점의 것이라 연달아 보내면 실제보다
 * 낙관적이다. 사전 차단은 헛수고를 줄이는 장치일 뿐 보장이 아니므로, 새어 나간
 * 요청은 여기서 받는다. */
export function isBudgetExhaustedError(err: unknown): boolean {
  return err instanceof ApiError && err.code === 'AI_DAILY_BUDGET_EXHAUSTED';
}

/** 채팅 전송이 실패한 뒤 화면을 어떻게 되돌릴 것인가.
 *
 * 서버는 사용자 메시지를 Gemini에 넘기기 전에 이미 확정한다. 그래서 한도 소진
 * 거절은 "안 보내졌다"가 아니라 "저장은 됐고 비서가 답을 못 했다"이다. 이때
 * 입력창으로 되돌리면 화면에서만 사라지고, 다시 보내면 서버에 그대로 중복된다.
 * 남은 실패(네트워크 등)는 정말 안 보내진 것이라 입력을 되돌리는 게 맞다. */
export type ChatSendRecovery = 'resync' | 'restore-input';

export function chatSendRecovery(err: unknown): ChatSendRecovery {
  return isBudgetExhaustedError(err) ? 'resync' : 'restore-input';
}
