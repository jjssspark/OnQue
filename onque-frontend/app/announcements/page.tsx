'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/components/AuthContext';
import { createAnnouncement, listAnnouncements, type AnnouncementRecord } from '@/lib/api';

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('ko-KR');
}

export default function AnnouncementsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [items, setItems] = useState<AnnouncementRecord[]>([]);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listAnnouncements()
      .then(setItems)
      .catch(() => setError('공지를 불러오지 못했습니다.'))
      .finally(() => setLoading(false));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !content.trim() || busy) return;

    setBusy(true);
    setError(null);
    try {
      const created = await createAnnouncement(title.trim(), content.trim());
      setItems((prev) => [created, ...prev]);
      setTitle('');
      setContent('');
    } catch (err) {
      setError(err instanceof Error ? err.message : '공지 등록에 실패했습니다.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-brand">Announcements</p>
      <h1 className="mt-1 text-2xl font-bold text-foreground">전사 공지사항</h1>
      <p className="mt-2 text-sm text-foreground/60">
        그룹과 관계없이 회사 전체가 함께 보는 공지입니다. 등록은 관리자만 할 수 있습니다.
      </p>

      {error && <p className="mt-4 text-sm text-red-500">{error}</p>}

      {isAdmin && (
        <form
          onSubmit={handleSubmit}
          className="mt-6 space-y-3 rounded-xl border border-border bg-surface p-5 shadow-sm"
        >
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="공지 제목"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
          />
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="공지 내용"
            rows={4}
            className="w-full resize-y rounded-lg border border-border bg-background px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={busy || !title.trim() || !content.trim()}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-brand-foreground transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? '등록 중...' : '공지 등록'}
          </button>
        </form>
      )}

      <div className="mt-8 space-y-3">
        {loading && <p className="text-sm text-foreground/40">불러오는 중...</p>}

        {!loading && items.length === 0 && (
          <div className="rounded-xl border border-dashed border-border p-10 text-center text-sm text-foreground/40">
            아직 등록된 공지가 없습니다.
          </div>
        )}

        {items.map((item) => (
          <article key={item.id} className="rounded-xl border border-border bg-surface p-5 shadow-sm">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="text-sm font-bold text-foreground">{item.title}</h2>
              <span className="shrink-0 font-mono text-[11px] text-foreground/40">
                {formatDateTime(item.created_at)}
              </span>
            </div>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-foreground/80">
              {item.content}
            </p>
          </article>
        ))}
      </div>
    </div>
  );
}
