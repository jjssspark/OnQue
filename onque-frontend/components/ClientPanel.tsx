'use client';

import { useCallback, useEffect, useState } from 'react';

import { SkeletonList } from '@/components/ui/Skeleton';
import { createClient, getClients, type Client } from '@/lib/api';

export default function ClientPanel({ groupId }: { groupId: number }) {
  const [clients, setClients] = useState<Client[]>([]);
  const [name, setName] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    try {
      setClients(await getClients(groupId));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : '클라이언트를 불러오지 못했습니다.');
    } finally {
      setIsLoading(false);
    }
  }, [groupId]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || isSubmitting) return;

    setIsSubmitting(true);
    setError(null);
    try {
      const created = await createClient(groupId, trimmed);
      setClients((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
      setName('');
    } catch (e) {
      // 중복 이름(409 CLIENT_NAME_DUPLICATE)도 request()가 서버 메시지를
      // 그대로 던져주므로 여기서 별도 분기 없이 그대로 보여주면 된다.
      setError(e instanceof Error ? e.message : '등록에 실패했습니다.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-bold text-foreground">클라이언트</h2>
        <span className="rounded-full px-2 py-0.5 font-mono text-[11px] font-semibold text-foreground/30">
          {clients.length}곳
        </span>
      </div>
      <p className="mt-1 text-[11px] leading-relaxed text-foreground/45">
        등록된 클라이언트만 약속에 연결됩니다. 없으면 모든 약속이 클라이언트 미지정으로 남습니다.
      </p>

      <form onSubmit={handleSubmit} className="mt-3 flex gap-2">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="클라이언트 이름"
          className="min-w-0 flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-foreground/25 focus:border-brand focus:outline-none"
        />
        <button
          type="submit"
          disabled={isSubmitting || !name.trim()}
          className="shrink-0 rounded-lg bg-brand px-3 py-2 text-xs font-semibold text-brand-foreground transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-30"
        >
          등록
        </button>
      </form>

      {error && (
        <p role="alert" className="mt-2 text-xs leading-relaxed text-red-500">
          {error}
        </p>
      )}

      {isLoading ? (
        <SkeletonList rows={3} rowClassName="h-8" className="mt-3" label="클라이언트 불러오는 중" />
      ) : clients.length === 0 ? (
        <p className="mt-4 rounded-xl border border-dashed border-border p-4 text-center text-xs text-foreground/40">
          등록된 클라이언트가 없습니다.
        </p>
      ) : (
        <ul className="mt-3 space-y-1.5">
          {clients.map((c) => (
            <li
              key={c.id}
              className="truncate rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground/80"
            >
              {c.name}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
