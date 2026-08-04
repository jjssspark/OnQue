'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { getDocuments, type DocumentRecord } from '@/lib/api';

export function RecentActivity() {
  const [entries, setEntries] = useState<DocumentRecord[] | null>(null);

  useEffect(() => {
    getDocuments()
      .then((docs) => setEntries(docs.slice(0, 5)))
      .catch(() => setEntries([]));
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
            <p className="text-xs text-foreground/40">{entry.category}</p>
          </div>
          <span className="shrink-0 font-mono text-[11px] text-foreground/40">
            {new Date(entry.created_at).toLocaleDateString('ko-KR')}
          </span>
        </Link>
      ))}
    </div>
  );
}
