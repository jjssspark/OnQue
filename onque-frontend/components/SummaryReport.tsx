'use client';

import { useState } from 'react';
import { useWorkspace } from '@/components/WorkspaceContext';
import { createTodo, type StructuredSummary } from '@/lib/api';

type SummaryReportProps = {
  structured: StructuredSummary | null;
  plainText: string;
  /** 자동 등록된 액션 아이템. 중복 등록을 막고 '등록됨'으로 표시한다. */
  registeredContents?: string[];
};

function Section({
  title,
  index,
  children,
}: {
  title: string;
  index: number;
  children: React.ReactNode;
}) {
  return (
    <section
      className="[animation:summary-in_0.45s_ease-out_backwards]"
      style={{ animationDelay: `${index * 70}ms` }}
    >
      <h3 className="font-mono text-[11px] uppercase tracking-widest text-foreground/35">
        {title}
      </h3>
      <div className="mt-2.5">{children}</div>
    </section>
  );
}

/**
 * 요약 리포트 렌더러.
 *
 * 부모는 요약이 바뀔 때 `key`를 함께 바꿔야 한다 — 등록 상태를 내부에 들고 있어서
 * 다시 마운트되지 않으면 이전 요약의 '등록됨' 표시가 남는다.
 */
export function SummaryReport({
  structured,
  plainText,
  registeredContents = [],
}: SummaryReportProps) {
  const { currentGroupId, refresh } = useWorkspace();
  const [registered, setRegistered] = useState<string[]>(registeredContents);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState('');

  if (!structured) {
    return (
      <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-foreground/90">
        {plainText}
      </pre>
    );
  }

  const handleRegister = async (content: string, dueDate: string) => {
    if (currentGroupId === null || pending) return;
    setPending(content);
    setError('');
    try {
      await createTodo(currentGroupId, content, dueDate || undefined);
      setRegistered((prev) => [...prev, content]);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : '할 일 등록에 실패했습니다.');
    } finally {
      setPending(null);
    }
  };

  const sections: React.ReactNode[] = [];
  let index = 0;

  if (structured.key_points.length > 0) {
    sections.push(
      <Section key="key_points" title="주요 내용" index={index++}>
        <ul className="space-y-1.5">
          {structured.key_points.map((point, i) => (
            <li
              key={i}
              className="group flex gap-3 rounded-lg px-3 py-2 transition-colors hover:bg-foreground/[0.03]"
            >
              <span className="mt-0.5 font-mono text-[11px] text-foreground/25 transition-colors group-hover:text-brand">
                {String(i + 1).padStart(2, '0')}
              </span>
              <span className="text-sm leading-relaxed text-foreground/85">{point}</span>
            </li>
          ))}
        </ul>
      </Section>,
    );
  }

  if (structured.requests.length > 0) {
    sections.push(
      <Section key="requests" title="상대방 요구사항" index={index++}>
        <ul className="space-y-1.5">
          {structured.requests.map((req, i) => (
            <li
              key={i}
              className="rounded-lg border-l-2 border-brand/40 bg-brand/[0.04] px-3 py-2 text-sm leading-relaxed text-foreground/85"
            >
              {req}
            </li>
          ))}
        </ul>
      </Section>,
    );
  }

  if (structured.action_items.length > 0) {
    sections.push(
      <Section key="action_items" title="액션 아이템" index={index++}>
        <ul className="space-y-2">
          {structured.action_items.map((item, i) => {
            const isRegistered = registered.includes(item.content);
            const isPending = pending === item.content;
            return (
              <li
                key={i}
                className="flex flex-col gap-2 rounded-xl border border-border bg-background/60 px-4 py-3 transition-colors hover:border-brand/40 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    {item.priority === 'high' && (
                      <span className="rounded-full bg-brand/[0.12] px-2 py-0.5 text-[10px] font-bold text-brand">
                        우선
                      </span>
                    )}
                    <span className="text-sm font-medium text-foreground">{item.content}</span>
                  </div>
                  {item.due_date && (
                    <p className="mt-1 font-mono text-[11px] text-foreground/40">
                      마감 {item.due_date}
                    </p>
                  )}
                </div>

                {isRegistered ? (
                  <span className="shrink-0 self-start rounded-lg bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-600 sm:self-auto dark:text-emerald-400">
                    할 일 등록됨
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => handleRegister(item.content, item.due_date)}
                    disabled={isPending}
                    className="shrink-0 self-start rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-foreground/70 transition-all hover:-translate-y-px hover:border-brand hover:text-brand disabled:opacity-50 sm:self-auto"
                  >
                    {isPending ? '등록 중...' : '할 일로 추가'}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      </Section>,
    );
  }

  if (structured.notes) {
    sections.push(
      <Section key="notes" title="메모" index={index++}>
        <p className="border-l-2 border-border pl-3 text-sm leading-relaxed text-foreground/60">
          {structured.notes}
        </p>
      </Section>,
    );
  }

  return (
    <div className="space-y-7">
      {structured.headline && (
        <p className="text-lg font-semibold leading-relaxed text-foreground [animation:summary-in_0.45s_ease-out_backwards] sm:text-xl">
          {structured.headline}
        </p>
      )}

      {error && <p className="text-sm text-red-500">{error}</p>}

      {sections}
    </div>
  );
}
