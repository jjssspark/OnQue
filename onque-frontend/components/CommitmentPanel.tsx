'use client';

import { useCallback, useEffect, useState } from 'react';

import {
  bulkUpdateCommitments,
  getCommitments,
  type CommitmentRecord,
} from '@/lib/api';

const SOURCE_LABEL: Record<CommitmentRecord['source_type'], string> = {
  call: '통화',
  document: '문서',
  chat: '채팅',
};

export default function CommitmentPanel({ groupId }: { groupId: number }) {
  const [proposed, setProposed] = useState<CommitmentRecord[]>([]);
  const [tracked, setTracked] = useState<CommitmentRecord[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [isApplying, setIsApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      // 조회가 스윕을 겸한다. proposed를 먼저 불러야 갓 추출된 항목이 반영된다.
      const fresh = await getCommitments(groupId, 'proposed');
      const confirmed = await getCommitments(groupId, 'confirmed');
      setProposed(fresh);
      setTracked(confirmed.filter((c) => c.is_overdue || c.is_due_soon));
      setSelected(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : '약속을 불러오지 못했습니다.');
    } finally {
      setIsLoading(false);
    }
  }, [groupId]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const allSelected = proposed.length > 0 && selected.size === proposed.length;

  const toggleAll = () => {
    setSelected(allSelected ? new Set() : new Set(proposed.map((c) => c.id)));
  };

  const apply = async (status: 'confirmed' | 'dismissed') => {
    if (selected.size === 0 || isApplying) return;
    setIsApplying(true);
    setError(null);
    try {
      await bulkUpdateCommitments([...selected], status);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : '처리에 실패했습니다.');
    } finally {
      setIsApplying(false);
    }
  };

  return (
    <section className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-bold text-foreground">확인 필요</h2>
        <span
          className={`rounded-full px-2 py-0.5 font-mono text-[11px] font-semibold ${
            proposed.length > 0 ? 'bg-brand/10 text-brand' : 'text-foreground/30'
          }`}
        >
          {proposed.length}건
        </span>
      </div>

      {error && (
        <p role="alert" className="mt-3 text-xs leading-relaxed text-red-500">
          {error}
        </p>
      )}

      {tracked.length > 0 && (
        <div className="mt-4 rounded-xl border border-accent/30 bg-accent/[0.08] px-3 py-3">
          <p className="font-mono text-[10px] uppercase tracking-widest text-accent">기한 주의</p>
          <ul className="mt-2 space-y-1.5">
            {tracked.map((c) => (
              <li key={c.id} className="flex items-start justify-between gap-3 text-xs">
                <span className="min-w-0 truncate text-foreground/75">
                  {c.client_name ?? '클라이언트 미지정'} · {c.content}
                </span>
                <span className="shrink-0 font-mono text-[11px] font-semibold text-accent">
                  {c.is_overdue ? '기한 초과' : `${c.due_date}까지`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {isLoading ? (
        <p className="mt-4 text-xs text-foreground/40">불러오는 중...</p>
      ) : proposed.length === 0 ? (
        <p className="mt-6 rounded-xl border border-dashed border-border p-6 text-center text-xs text-foreground/40">
          확인할 약속이 없습니다.
        </p>
      ) : (
        <>
          <label className="mt-4 flex w-fit cursor-pointer items-center gap-2 text-[11px] text-foreground/40 hover:text-foreground/70">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={toggleAll}
              className="h-3.5 w-3.5"
            />
            전체 선택
          </label>

          <ul className="mt-2 space-y-2">
            {proposed.map((c) => (
              <li
                key={c.id}
                className={`rounded-xl border p-3.5 transition-colors ${
                  selected.has(c.id)
                    ? 'border-brand/50 bg-brand/[0.06]'
                    : 'border-border bg-background hover:border-brand/30'
                }`}
              >
                <label className="flex cursor-pointer items-start gap-3">
                  <input
                    type="checkbox"
                    checked={selected.has(c.id)}
                    onChange={() => toggle(c.id)}
                    className="mt-1 h-4 w-4 shrink-0"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold leading-snug text-foreground">
                      {c.content}
                    </span>
                    <span className="mt-1 flex flex-wrap items-center gap-x-1.5 font-mono text-[11px] text-foreground/40">
                      <span>{c.client_name ?? '클라이언트 미지정'}</span>
                      <span>·</span>
                      <span>{c.due_date ? `${c.due_date}까지` : '기한 없음'}</span>
                      <span>·</span>
                      <span>{SOURCE_LABEL[c.source_type]}</span>
                    </span>
                    <span className="mt-2 block border-l-2 border-border pl-2.5 text-xs italic leading-relaxed text-foreground/55">
                      &ldquo;{c.evidence}&rdquo;
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>

          <div className="mt-4 flex gap-2">
            <button
              type="button"
              onClick={() => apply('confirmed')}
              disabled={selected.size === 0 || isApplying}
              className="rounded-lg bg-brand px-4 py-2 text-xs font-semibold text-brand-foreground transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-30"
            >
              확정{selected.size > 0 && ` (${selected.size})`}
            </button>
            <button
              type="button"
              onClick={() => apply('dismissed')}
              disabled={selected.size === 0 || isApplying}
              className="rounded-lg border border-border px-4 py-2 text-xs font-semibold text-foreground/70 transition hover:border-red-500/40 hover:text-red-400 disabled:cursor-not-allowed disabled:opacity-30"
            >
              무시
            </button>
          </div>
        </>
      )}
    </section>
  );
}
