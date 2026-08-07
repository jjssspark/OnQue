'use client';

import { useCallback, useEffect, useState } from 'react';

import {
  acceptInvitation,
  declineInvitation,
  listMyInvitations,
  type ReceivedInvitation,
} from '@/lib/api';

type Props = {
  onChanged: () => void | Promise<void>;
};

export function ReceivedInvitations({ onChanged }: Props) {
  const [invitations, setInvitations] = useState<ReceivedInvitation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setInvitations(await listMyInvitations());
    } catch (err) {
      setError(err instanceof Error ? err.message : '초대를 불러오지 못했습니다.');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function respond(id: number, accept: boolean) {
    setBusyId(id);
    setError(null);
    try {
      if (accept) {
        await acceptInvitation(id);
      } else {
        await declineInvitation(id);
      }
      setInvitations((prev) => prev.filter((i) => i.id !== id));
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : '처리하지 못했습니다.');
      await load();
    } finally {
      setBusyId(null);
    }
  }

  if (invitations.length === 0 && !error) return null;

  return (
    <section className="mb-6 rounded-xl border border-border bg-surface p-5 shadow-sm">
      <h2 className="text-sm font-bold text-foreground">받은 초대</h2>
      {error && (
        <p role="alert" className="mt-3 text-sm text-red-500">
          {error}
        </p>
      )}
      <ul className="mt-3 divide-y divide-border">
        {invitations.map((inv) => (
          <li key={inv.id} className="flex items-center justify-between gap-3 py-2.5">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-foreground">{inv.group_name}</p>
              <p className="truncate text-xs text-foreground/50">
                {inv.invited_by_name}님이 초대했습니다.
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <button
                type="button"
                disabled={busyId === inv.id}
                onClick={() => respond(inv.id, true)}
                className="shrink-0 rounded-lg bg-brand px-3 py-1.5 text-xs font-semibold text-brand-foreground transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
              >
                수락
              </button>
              <button
                type="button"
                disabled={busyId === inv.id}
                onClick={() => respond(inv.id, false)}
                className="shrink-0 text-[11px] text-foreground/30 transition-colors hover:text-red-400 disabled:opacity-50"
              >
                거절
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
