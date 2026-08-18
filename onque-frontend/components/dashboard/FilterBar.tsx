'use client';

import { FILTERS, type FilterKey } from '@/lib/dashboard-filter';

type Props = {
  counts: Record<FilterKey, number>;
  value: FilterKey;
  onChange: (key: FilterKey) => void;
};

/**
 * 지표 카드를 대신하는 필터 줄.
 *
 * 카드 네 장으로 숫자를 보여주고 목록을 따로 두면, 숫자를 보고 나서 그 숫자에
 * 해당하는 것을 목록에서 다시 찾아야 한다. 세는 일과 좁히는 일을 한 자리에
 * 합치면 그 왕복이 없어진다.
 *
 * role="tablist"를 쓰지 않은 이유: 탭은 패널을 갈아끼우지만 여기는 같은 목록을
 * 좁힐 뿐이다. 대신 aria-pressed로 눌린 상태를 알린다.
 */
export function FilterBar({ counts, value, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="목록 좁히기">
      {FILTERS.map(({ key, label }) => {
        const active = key === value;
        return (
          <button
            key={key}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(key)}
            className={`flex items-baseline gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue focus-visible:ring-offset-2 focus-visible:ring-offset-paper ${
              active
                ? 'border-blue bg-blue text-card-2'
                : 'border-rule bg-card text-ink-2 hover:border-rule-strong hover:text-ink'
            }`}
          >
            <span>{label}</span>
            {/* 숫자는 mono. 버튼 폭이 숫자 자릿수에 따라 덜 흔들린다 */}
            <span
              className={`font-mono text-[11px] tabular-nums ${
                active ? 'text-blue-wash' : 'text-ink-3'
              }`}
            >
              {counts[key]}
            </span>
          </button>
        );
      })}
    </div>
  );
}
