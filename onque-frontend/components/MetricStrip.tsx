'use client';

import { useEffect, useRef, useState } from 'react';

export type Metric = {
  label: string;
  value: number;
  hint: string;
  /** 주의가 필요한 수치(지연 등)를 경고색으로 표시한다. */
  alert?: boolean;
};

const DURATION_MS = 700;

function useCountUp(target: number): number {
  const [value, setValue] = useState(target);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / DURATION_MS);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.round(target * eased));
      if (progress < 1) frameRef.current = requestAnimationFrame(tick);
    };
    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    };
  }, [target]);

  return value;
}

function MetricCard({ metric, index }: { metric: Metric; index: number }) {
  const displayed = useCountUp(metric.value);

  return (
    <div
      className="group relative overflow-hidden rounded-xl border border-border bg-surface px-4 py-4 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md [animation:metric-in_0.5s_ease-out_backwards]"
      style={{ animationDelay: `${index * 80}ms` }}
    >
      <div
        className={`pointer-events-none absolute -right-6 -top-6 h-20 w-20 rounded-full blur-2xl transition-opacity duration-500 ${
          metric.alert ? 'bg-red-500/25' : 'bg-brand/20'
        } ${metric.value > 0 ? 'opacity-100' : 'opacity-0'}`}
        aria-hidden
      />
      <p className="font-mono text-[11px] uppercase tracking-widest text-foreground/35">
        {metric.label}
      </p>
      <p
        className={`mt-2 text-3xl font-bold tabular-nums ${
          metric.alert && metric.value > 0 ? 'text-red-500' : 'text-foreground'
        }`}
      >
        {displayed}
      </p>
      <p className="mt-1 text-[11px] text-foreground/40">{metric.hint}</p>
    </div>
  );
}

export function MetricStrip({ metrics }: { metrics: Metric[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {metrics.map((metric, i) => (
        <MetricCard key={metric.label} metric={metric} index={i} />
      ))}
    </div>
  );
}
