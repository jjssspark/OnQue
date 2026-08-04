'use client';

import { useEffect, useState } from 'react';
import { searchHistory, type HistoryEntry, type HistoryEntryType } from '@/lib/history';

const TYPE_LABEL: Record<HistoryEntryType, string> = {
  call: '통화 요약',
  document: '문서·회의록',
};

const TYPE_BADGE_CLASS: Record<HistoryEntryType, string> = {
  call: 'bg-brand/10 text-brand',
  document: 'bg-accent/10 text-accent',
};

export default function HistoryPage() {
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<HistoryEntryType | 'all'>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [entries, setEntries] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    setEntries(searchHistory(query, typeFilter === 'all' ? undefined : typeFilter));
  }, [query, typeFilter]);

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-brand">History</p>
      <h1 className="mt-1 text-2xl font-bold text-foreground">🔍 이력 조회</h1>
      <p className="mt-2 text-sm text-foreground/60">
        지금까지 요약한 통화·문서 결과를 검색하고 다시 확인할 수 있습니다. (이 브라우저에만 저장됩니다)
      </p>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="파일명 또는 요약 내용 검색"
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm sm:max-w-xs"
        />

        <div className="flex gap-1">
          {(['all', 'call', 'document'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTypeFilter(t)}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                typeFilter === t
                  ? 'bg-brand text-brand-foreground'
                  : 'bg-surface text-foreground/60 hover:bg-foreground/5 border border-border'
              }`}
            >
              {t === 'all' ? '전체' : TYPE_LABEL[t]}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-6 space-y-3">
        {entries.length === 0 && (
          <div className="rounded-xl border border-dashed border-border p-10 text-center text-sm text-foreground/40">
            아직 저장된 요약 이력이 없습니다.
          </div>
        )}

        {entries.map((entry) => {
          const isExpanded = expandedId === entry.id;
          return (
            <div
              key={entry.id}
              className="rounded-xl border border-border bg-surface shadow-sm"
            >
              <button
                onClick={() => setExpandedId(isExpanded ? null : entry.id)}
                className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${TYPE_BADGE_CLASS[entry.type]}`}
                    >
                      {TYPE_LABEL[entry.type]}
                    </span>
                    <span className="truncate text-sm font-semibold text-foreground">
                      {entry.filename}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-xs text-foreground/50">
                    {entry.summary.replace(/\n/g, ' ')}
                  </p>
                </div>
                <span className="shrink-0 font-mono text-[11px] text-foreground/40">
                  {new Date(entry.createdAt).toLocaleString('ko-KR')}
                </span>
              </button>

              {isExpanded && (
                <div className="border-t border-border px-5 py-4">
                  <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-foreground/90">
                    {entry.summary}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
