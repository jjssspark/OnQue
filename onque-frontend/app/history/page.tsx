'use client';

import { useEffect, useMemo, useState } from 'react';
import { useWorkspace } from '@/components/WorkspaceContext';
import { SummaryReport } from '@/components/SummaryReport';
import { PageShell } from '@/components/PageShell';
import { SkeletonList } from '@/components/ui/Skeleton';
import { deleteDocument, getDocuments, type DocumentRecord } from '@/lib/api';

const CATEGORY_BADGE_CLASS: Record<string, string> = {
  기획: 'bg-blue-500/15 text-blue-300 ring-1 ring-blue-400/20',
  디자인: 'bg-pink-500/15 text-pink-300 ring-1 ring-pink-400/20',
  개발: 'bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-400/20',
  마케팅: 'bg-purple-500/15 text-purple-300 ring-1 ring-purple-400/20',
  기타: 'bg-slate-500/15 text-slate-300 ring-1 ring-slate-400/20',
  통화: 'bg-orange-500/15 text-orange-300 ring-1 ring-orange-400/20',
};

const CATEGORIES = ['전체', '통화', '기획', '디자인', '개발', '마케팅', '기타'] as const;

export default function HistoryPage() {
  const { currentGroupId } = useWorkspace();
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<(typeof CATEGORIES)[number]>('전체');
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (currentGroupId === null) return;
    getDocuments(currentGroupId)
      .then(setDocuments)
      .catch(() => setErrorMsg('이력을 불러오지 못했습니다.'))
      .finally(() => setLoading(false));
  }, [currentGroupId]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return documents.filter((doc) => {
      if (category !== '전체' && doc.category !== category) return false;
      if (!normalized) return true;
      return (
        doc.filename.toLowerCase().includes(normalized) ||
        doc.summary.toLowerCase().includes(normalized)
      );
    });
  }, [documents, query, category]);

  const handleDelete = async (id: number) => {
    try {
      await deleteDocument(id);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
    } catch {
      setErrorMsg('삭제에 실패했습니다.');
    }
  };

  if (currentGroupId === null) {
    return (
      <PageShell
        eyebrow="History"
        title="이력 조회"
        description="지금까지 요약한 통화·문서 결과를 검색하고 다시 확인할 수 있습니다."
      >
        <p className="text-sm text-foreground/60">
          아직 소속된 그룹이 없습니다. 관리자가 그룹에 초대하면 이용할 수 있습니다.
        </p>
      </PageShell>
    );
  }

  return (
    <PageShell
      eyebrow="History"
      title="이력 조회"
      description="지금까지 요약한 통화·문서 결과를 검색하고 다시 확인할 수 있습니다."
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="파일명 또는 요약 내용 검색"
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm sm:max-w-xs"
        />

        <div className="flex flex-wrap gap-1">
          {CATEGORIES.map((c) => (
            <button
              key={c}
              onClick={() => setCategory(c)}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                category === c
                  ? 'bg-brand text-brand-foreground'
                  : 'border border-border bg-surface text-foreground/60 hover:bg-foreground/5'
              }`}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      {errorMsg && <p className="mt-3 text-sm text-red-500">{errorMsg}</p>}

      <div className="mt-6 space-y-3">
        {loading && <SkeletonList rows={4} rowClassName="h-16" label="이력 불러오는 중" />}

        {!loading && filtered.length === 0 && (
          <div className="rounded-xl border border-dashed border-border p-10 text-center text-sm text-foreground/40">
            아직 저장된 요약 이력이 없습니다.
          </div>
        )}

        {filtered.map((doc) => {
          const isExpanded = expandedId === doc.id;
          return (
            <div key={doc.id} className="rounded-xl border border-border bg-surface shadow-sm">
              <div className="flex w-full items-center justify-between gap-3 px-5 py-4">
                <button
                  onClick={() => setExpandedId(isExpanded ? null : doc.id)}
                  className="min-w-0 flex-1 text-left"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                        CATEGORY_BADGE_CLASS[doc.category] ?? CATEGORY_BADGE_CLASS['기타']
                      }`}
                    >
                      {doc.category}
                    </span>
                    <span className="truncate text-sm font-semibold text-foreground">
                      {doc.filename}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-xs text-foreground/50">
                    {doc.structured?.headline || doc.summary.replace(/\n/g, ' ')}
                  </p>
                </button>
                <div className="flex shrink-0 items-center gap-3">
                  <span className="font-mono text-[11px] text-foreground/40">
                    {new Date(doc.created_at).toLocaleString('ko-KR')}
                  </span>
                  <button
                    onClick={() => handleDelete(doc.id)}
                    className="text-[11px] text-foreground/30 hover:text-red-500"
                  >
                    삭제
                  </button>
                </div>
              </div>

              {isExpanded && (
                <div className="border-t border-border px-5 py-5">
                  <SummaryReport
                    key={doc.id}
                    structured={doc.structured}
                    plainText={doc.summary}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </PageShell>
  );
}
