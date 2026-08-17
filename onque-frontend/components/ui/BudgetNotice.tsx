'use client';

import { useWorkspace } from '@/components/WorkspaceContext';
import { budgetExhaustedText, isBudgetExhausted } from '@/lib/ai-budget';

type BudgetNoticeProps = {
  /** 막아둔 입력구의 aria-describedby가 가리킬 id. 왜 못 쓰는지가 보조기술에
   * 닿으려면 안내와 입력구가 연결돼 있어야 한다. 여러 화면이 동시에 떠 있어도
   * 겹치지 않도록 호출부의 useId를 받는다. */
  id?: string;
  /** 화면마다 다른 탈출구 안내. 입력이 조건부로 열려 있는 화면(채팅방)은
   * 무엇이 되고 무엇이 안 되는지를 여기 담아 describedby로 함께 전달한다. */
  hint?: string;
};

/** 오늘 AI 한도를 다 썼을 때 입력구 자리에 놓는 안내.
 *
 * 잔량이 있으면 아무것도 그리지 않아, 호출부는 조건 없이 놓기만 하면 된다.
 * 조건을 호출부마다 쓰면 세 곳 중 한 곳이 빠진다.
 *
 * 눌러보고 실패하게 두지 않는 이유: 하루 한도는 잠시 후에 안 풀린다.
 * "잠시 후 다시"를 믿고 재시도를 반복하면 앱이 고장난 것처럼 보인다. */
export function BudgetNotice({ id, hint }: BudgetNoticeProps) {
  const { aiBudget } = useWorkspace();
  if (!isBudgetExhausted(aiBudget)) return null;

  return (
    <div
      id={id}
      role="status"
      className="rounded-xl border border-hairline bg-surface-sunken px-4 py-3 text-xs leading-relaxed text-fg-muted"
    >
      <p>{budgetExhaustedText(aiBudget)}</p>
      {/* 줄을 나눠 "언제 풀리는지"와 "지금 뭘 할 수 있는지"가 각각 눈에 들어오게 한다. */}
      {hint && <p className="mt-1.5 text-foreground/70">{hint}</p>}
    </div>
  );
}
