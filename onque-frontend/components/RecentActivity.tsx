'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { getHistory, type HistoryEntry } from '@/lib/history';

const TYPE_LABEL: Record<HistoryEntry['type'], string> = {
  call: '통화 요약',
  document: '문서·회의록',
};

export function RecentActivity() {
  const [entries, setEntries] = useState<HistoryEntry[] | null>(null);

  useEffect(() => {
    setEntries(getHistory().slice(0, 5));
  }, []);

  if (entries === null) return null;

  if (entries.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-foreground/40">
        아직 처리한 업무가 없습니다. 통화 요약이나 문서 요약을 먼저 실행해보세요.
      </div>
    );
  }

  return (
    <div className="divide-y divide-border rounded-xl border border-border bg-surface shadow-sm">
      {entries.map((entry) => (
        <Link
          key={entry.id}
          href="/history"
          className="flex items-center justify-between gap-3 px-5 py-3.5 transition-colors hover:bg-foreground/5"
        >
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-foreground">
              {entry.filename}
            </p>
            <p className="text-xs text-foreground/40">{TYPE_LABEL[entry.type]}</p>
          </div>
          <span className="shrink-0 font-mono text-[11px] text-foreground/40">
            {new Date(entry.createdAt).toLocaleDateString('ko-KR')}
          </span>
        </Link>
      ))}
    </div>
  );
}
