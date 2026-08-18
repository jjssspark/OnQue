'use client';

import { useWorkspace } from '@/components/WorkspaceContext';
import { formatResetTime } from '@/lib/sweep-status';

/**
 * 오늘 쓴 AI 호출을 칸으로 그린다.
 *
 * "3/20" 숫자만 보여주면 얼마나 남았는지가 머리로 계산해야 알 수 있다.
 * 칸으로 그리면 남은 양이 눈에 바로 들어온다. 하루 20건이라 칸이 스무 개를
 * 넘지 않아 이 방식이 성립한다.
 *
 * 스윕(자동 정리) 몫과 사용자 호출 몫을 구분해 칠하지 않는다 — AiBudget에는
 * used/total/resets_at만 있고 몫을 나눌 필드가 없다. 없는 값을 지어 그리지 않는다.
 */
export function BudgetGauge() {
  const { aiBudget } = useWorkspace();

  // null은 "아직 모른다"이지 "0을 썼다"가 아니다. 0칸을 그리면 잔량이 가득한
  // 것처럼 보여 실제와 어긋난다.
  if (!aiBudget) return null;

  const { used, total, resets_at } = aiBudget;
  const resetsAt = formatResetTime(resets_at);
  // 음수 total에서의 RangeError와 used > total일 때 칸이 넘치는 것을 막는다.
  const safeTotal = Math.max(total, 0);
  const safeUsed = Math.min(Math.max(used, 0), safeTotal);

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">AI 사용량</p>
        <p className="font-mono text-[11px] tabular-nums text-ink-2">
          {used} / {total}
        </p>
      </div>

      <div
        className="mt-2 flex gap-[3px]"
        role="img"
        aria-label={`오늘 AI 호출 ${total}건 중 ${used}건 사용`}
      >
        {Array.from({ length: safeTotal }, (_, i) => (
          <span
            key={i}
            className={`h-4 flex-1 rounded-[2px] ${i < safeUsed ? 'bg-blue' : 'bg-rule'}`}
          />
        ))}
      </div>

      {resetsAt && <p className="mt-1.5 text-[10px] text-ink-3">{resetsAt}에 초기화</p>}
    </div>
  );
}
