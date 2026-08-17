import { describe, expect, it } from 'vitest';
import {
  budgetExhaustedText,
  isBudgetExhausted,
  isBudgetExhaustedError,
  isChatSendBlocked,
} from './ai-budget';
import { ApiError, type AiBudget } from './api';

function budget(overrides: Partial<AiBudget> = {}): AiBudget {
  return { used: 3, total: 20, resets_at: '2026-08-18T00:00:00Z', ...overrides };
}

describe('isBudgetExhausted', () => {
  it('예산을 아직 모르면 소진이 아니다 — 모를 때 막으면 서버는 멀쩡한데 화면만 잠긴다', () => {
    expect(isBudgetExhausted(null)).toBe(false);
  });

  it('남아 있으면 소진이 아니다', () => {
    expect(isBudgetExhausted(budget({ used: 19, total: 20 }))).toBe(false);
  });

  it('정확히 다 쓰면 소진이다', () => {
    expect(isBudgetExhausted(budget({ used: 20, total: 20 }))).toBe(true);
  });

  it('한도를 넘겨 쓴 기록도 소진이다', () => {
    expect(isBudgetExhausted(budget({ used: 21, total: 20 }))).toBe(true);
  });

  it('한도가 0이면 한 건도 쓰기 전부터 소진이다', () => {
    expect(isBudgetExhausted(budget({ used: 0, total: 0 }))).toBe(true);
  });
});

describe('budgetExhaustedText', () => {
  it('초기화 시각을 아는 경우 언제 풀리는지 말한다', () => {
    const text = budgetExhaustedText(budget({ used: 20, total: 20 }));
    expect(text.startsWith('오늘 AI 한도를 다 썼습니다.')).toBe(true);
    expect(text.endsWith('에 초기화됩니다.')).toBe(true);
  });

  it('예산을 모르는 채 서버가 거절한 경우 시각을 지어내지 않는다', () => {
    expect(budgetExhaustedText(null)).toBe('오늘 AI 한도를 다 썼습니다. 내일 다시 이용해주세요.');
  });

  it('초기화 시각을 파싱할 수 없으면 시각 없이 안내한다', () => {
    expect(budgetExhaustedText(budget({ resets_at: '언젠가' }))).toBe(
      '오늘 AI 한도를 다 썼습니다. 내일 다시 이용해주세요.',
    );
  });
});

describe('isChatSendBlocked', () => {
  const spent = budget({ used: 20, total: 20 });

  it('AI가 방에 없으면 소진이어도 막지 않는다 — Gemini를 부르지 않는 경로다', () => {
    expect(isChatSendBlocked('오늘 회의 몇 시죠', false, spent)).toBe(false);
  });

  it('잔량이 남아 있으면 막지 않는다', () => {
    expect(isChatSendBlocked('오늘 회의 몇 시죠', true, budget({ used: 3, total: 20 }))).toBe(false);
  });

  it('예산을 아직 모르면 막지 않는다', () => {
    expect(isChatSendBlocked('오늘 회의 몇 시죠', true, null)).toBe(false);
  });

  it('AI가 있는 방에서 소진되면 일반 메시지를 막는다', () => {
    expect(isChatSendBlocked('오늘 회의 몇 시죠', true, spent)).toBe(true);
  });

  it('/exit 는 소진돼도 보낼 수 있다 — 비서를 내보내는 길까지 막으면 방이 잠긴다', () => {
    expect(isChatSendBlocked('/exit', true, spent)).toBe(false);
  });

  it('앞뒤 공백이 있어도 명령으로 본다', () => {
    expect(isChatSendBlocked('  /exit  ', true, spent)).toBe(false);
  });

  it('모델을 부르는 명령도 보내게 둔다 — 가르는 건 서버 예산 문이고 429는 화면이 받는다', () => {
    expect(isChatSendBlocked('/요약', true, spent)).toBe(false);
  });

  it('문장 중간의 슬래시는 명령이 아니다', () => {
    expect(isChatSendBlocked('a/b 안건 정리해줘', true, spent)).toBe(true);
  });
});

describe('isBudgetExhaustedError', () => {
  it('서버가 한도 소진 코드로 거절하면 참이다', () => {
    const err = new ApiError('오늘 호출을 다 썼습니다', 'AI_DAILY_BUDGET_EXHAUSTED', 429);
    expect(isBudgetExhaustedError(err)).toBe(true);
  });

  it('같은 429라도 다른 코드면 거짓이다', () => {
    const err = new ApiError('요청이 너무 많습니다', 'RATE_LIMIT_EXCEEDED', 429);
    expect(isBudgetExhaustedError(err)).toBe(false);
  });

  it('문구가 같아도 code가 없으면 거짓이다 — message가 아니라 code로만 분기한다', () => {
    expect(isBudgetExhaustedError(new Error('오늘 AI 한도를 다 썼습니다.'))).toBe(false);
  });

  it('에러가 아닌 값에도 터지지 않는다', () => {
    expect(isBudgetExhaustedError(null)).toBe(false);
    expect(isBudgetExhaustedError(undefined)).toBe(false);
  });
});
