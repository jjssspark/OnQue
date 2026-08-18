'use client';

import { useEffect, useState } from 'react';

type AnalyzingOverlayProps = {
  filename: string;
  /** 0=업로드, 1=분석, 2=정리. 경과 시간으로 부모가 넘긴다. */
  stage: number;
  stages: readonly string[];
  hint: string;
};

/**
 * 요약은 수십 초가 걸린다. 서버가 진행률을 주지 않으므로 단계는 추정값이지만,
 * 경과 시간은 실제값이라 "멈춘 건 아닌가" 하는 의심을 없애준다.
 */
export function AnalyzingOverlay({ filename, stage, stages, hint }: AnalyzingOverlayProps) {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div
      className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-5 rounded-md bg-card-2/85 px-6 py-8 backdrop-blur-md [animation:fade-in_0.2s_ease-out]"
      role="status"
      aria-live="polite"
    >
      <div className="relative h-16 w-16" aria-hidden>
        <span className="absolute inset-0 rounded-full border-2 border-blue/15" />
        <span className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-t-blue border-r-blue/40" />
        <span className="absolute inset-3 animate-pulse rounded-full bg-blue/20" />
      </div>

      <div className="text-center">
        <p className="text-sm font-semibold text-ink">{stages[stage]}</p>
        <p className="mt-1 max-w-[22rem] truncate font-mono text-[11px] text-ink-3">
          {filename}
        </p>
      </div>

      <ol className="flex w-full max-w-xs items-center gap-2">
        {stages.map((label, i) => (
          <li key={label} className="flex flex-1 flex-col gap-1.5">
            <span
              className={`h-1 rounded-full transition-colors duration-500 ${
                i < stage ? 'bg-blue' : i === stage ? 'animate-pulse bg-blue' : 'bg-ink-3'
              }`}
            />
            <span
              className={`text-[10px] transition-colors ${
                i === stage ? 'font-semibold text-blue' : 'text-ink-3'
              }`}
            >
              {label}
            </span>
          </li>
        ))}
      </ol>

      <div className="text-center">
        <p className="font-mono text-xs tabular-nums text-ink-3">{seconds}초 경과</p>
        <p className="mt-1.5 max-w-xs text-[11px] leading-relaxed text-ink-3">{hint}</p>
      </div>
    </div>
  );
}
