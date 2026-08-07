'use client';

import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/components/AuthContext';
import { ReceivedInvitations } from '@/components/ReceivedInvitations';
import {
  cancelGroupInvitation,
  createGroup,
  inviteToGroupByEmail,
  listGroupInvitations,
  listGroupMembers,
  removeGroupMember,
  type GroupInvitation,
  type GroupMember,
} from '@/lib/api';

export default function GroupsPage() {
  const { user, groups, refreshMe } = useAuth();

  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null);
  const isAdmin = groups.find((g) => g.id === selectedGroupId)?.role === 'admin';

  const [members, setMembers] = useState<GroupMember[]>([]);
  const [newGroupName, setNewGroupName] = useState('');
  const [invitations, setInvitations] = useState<GroupInvitation[]>([]);
  const [inviteEmail, setInviteEmail] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (selectedGroupId === null && groups.length > 0) {
      setSelectedGroupId(groups[0].id);
    }
  }, [groups, selectedGroupId]);

  const loadMembers = useCallback(async (groupId: number) => {
    try {
      const [nextMembers, nextInvitations] = await Promise.all([
        listGroupMembers(groupId),
        listGroupInvitations(groupId),
      ]);
      setMembers(nextMembers);
      setInvitations(nextInvitations);
    } catch (err) {
      setError(err instanceof Error ? err.message : '멤버를 불러오지 못했습니다.');
    }
  }, []);

  useEffect(() => {
    if (selectedGroupId !== null) loadMembers(selectedGroupId);
  }, [selectedGroupId, loadMembers]);

  async function handleCreateGroup(e: React.FormEvent) {
    e.preventDefault();
    const name = newGroupName.trim();
    if (!name || busy) return;

    setBusy(true);
    setError(null);
    try {
      const group = await createGroup(name);
      setNewGroupName('');
      await refreshMe();
      setSelectedGroupId(group.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '그룹 생성에 실패했습니다.');
    } finally {
      setBusy(false);
    }
  }

  async function handleInviteByEmail(e: React.FormEvent) {
    e.preventDefault();
    const email = inviteEmail.trim();
    if (!email || selectedGroupId === null || busy) return;

    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await inviteToGroupByEmail(selectedGroupId, email);
      setInviteEmail('');
      setNotice('초대했습니다. 상대가 수락하면 팀에 합류합니다.');
      await loadMembers(selectedGroupId);
    } catch (err) {
      setError(err instanceof Error ? err.message : '초대에 실패했습니다.');
    } finally {
      setBusy(false);
    }
  }

  async function handleCancelInvitation(invitationId: number) {
    if (selectedGroupId === null || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await cancelGroupInvitation(selectedGroupId, invitationId);
      await loadMembers(selectedGroupId);
    } catch (err) {
      setError(err instanceof Error ? err.message : '초대 취소에 실패했습니다.');
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveMember(userId: number) {
    if (selectedGroupId === null || busy) return;
    setBusy(true);
    setError(null);
    try {
      await removeGroupMember(selectedGroupId, userId);
      await loadMembers(selectedGroupId);
      // 자기 자신을 뺐다면 소속 그룹 목록이 바뀌므로 갱신한다.
      if (userId === user?.id) await refreshMe();
    } catch (err) {
      setError(err instanceof Error ? err.message : '멤버 제거에 실패했습니다.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <ReceivedInvitations onChanged={refreshMe} />
      <p className="font-mono text-xs uppercase tracking-widest text-brand">Groups</p>
      <h1 className="mt-1 text-2xl font-bold text-foreground">그룹 관리</h1>
      <p className="mt-2 text-sm text-foreground/60">
        부서·팀 단위로 그룹을 나누면 채팅·할 일·일정·문서가 그룹별로 분리됩니다.
      </p>

      {error && <p className="mt-4 text-sm text-red-500">{error}</p>}
      {notice && (
        <p className="mt-4 rounded-lg border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
          {notice}
        </p>
      )}

      {groups.length > 0 && (
        <form onSubmit={handleCreateGroup} className="mt-6 flex gap-2">
          <input
            type="text"
            value={newGroupName}
            onChange={(e) => setNewGroupName(e.target.value)}
            placeholder="새 그룹 이름"
            className="flex-1 rounded-lg border border-border bg-surface px-3 py-2 text-sm sm:max-w-xs"
          />
          <button
            type="submit"
            disabled={busy || !newGroupName.trim()}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-brand-foreground transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
          >
            그룹 만들기
          </button>
        </form>
      )}

      {groups.length === 0 ? (
        <div className="mt-8 rounded-xl border border-dashed border-border p-10 text-center">
          <h2 className="text-sm font-bold text-foreground">아직 속한 팀이 없습니다</h2>
          <p className="mt-2 text-sm text-foreground/60">
            팀을 만들면 동료를 이메일로 초대할 수 있습니다.
          </p>
          <form onSubmit={handleCreateGroup} className="mt-6 flex justify-center gap-2">
            <input
              type="text"
              value={newGroupName}
              onChange={(e) => setNewGroupName(e.target.value)}
              placeholder="팀 이름"
              className="w-full max-w-xs rounded-lg border border-border bg-surface px-3 py-2 text-sm"
            />
            <button
              type="submit"
              disabled={busy || !newGroupName.trim()}
              className="shrink-0 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-brand-foreground transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
            >
              팀 만들기
            </button>
          </form>
        </div>
      ) : (
        <div className="mt-8 grid gap-6 md:grid-cols-[200px_1fr]">
          <nav className="space-y-1">
            {groups.map((g) => (
              <button
                key={g.id}
                onClick={() => setSelectedGroupId(g.id)}
                className={`w-full rounded-lg px-3 py-2 text-left text-sm font-semibold transition-colors ${
                  selectedGroupId === g.id
                    ? 'bg-brand text-brand-foreground'
                    : 'border border-border bg-surface text-foreground/70 hover:bg-foreground/5'
                }`}
              >
                {g.name}
              </button>
            ))}
          </nav>

          <div className="space-y-6">
            <section className="rounded-xl border border-border bg-surface p-5 shadow-sm">
              <h2 className="text-sm font-bold text-foreground">멤버 {members.length}</h2>
              <ul className="mt-3 divide-y divide-border">
                {members.map((m) => (
                  <li key={m.id} className="flex items-center justify-between gap-3 py-2.5">
                    <div className="min-w-0">
                      <p className="truncate text-sm text-foreground">
                        {m.name}
                        {m.role === 'admin' && (
                          <span className="ml-2 rounded-full bg-brand/10 px-2 py-0.5 text-[10px] font-semibold text-brand">
                            관리자
                          </span>
                        )}
                      </p>
                      <p className="truncate font-mono text-[11px] text-foreground/40">{m.email}</p>
                    </div>
                    {isAdmin && (
                      <button
                        onClick={() => handleRemoveMember(m.id)}
                        disabled={busy}
                        className="shrink-0 text-[11px] text-foreground/30 hover:text-red-500 disabled:opacity-50"
                      >
                        제외
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </section>

            {isAdmin && (
              <section className="rounded-xl border border-border bg-surface p-5 shadow-sm">
                <h2 className="text-sm font-bold text-foreground">이메일로 초대</h2>
                <p className="mt-1 text-xs leading-relaxed text-foreground/45">
                  아직 가입 전이어도 초대해 둘 수 있습니다. 상대가 초대를 수락해야 이 그룹에
                  합류합니다.
                </p>
                <form onSubmit={handleInviteByEmail} className="mt-3 flex gap-2">
                  <input
                    type="email"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    placeholder="name@company.com"
                    className="min-w-0 flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-foreground/25 focus:border-brand focus:outline-none"
                  />
                  <button
                    type="submit"
                    disabled={busy || !inviteEmail.trim()}
                    className="shrink-0 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-brand-foreground transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    초대
                  </button>
                </form>

                {invitations.length > 0 && (
                  <>
                    <h3 className="mt-5 font-mono text-[10px] uppercase tracking-widest text-foreground/35">
                      가입 대기 {invitations.length}
                    </h3>
                    <ul className="mt-2 divide-y divide-border">
                      {invitations.map((inv) => (
                        <li
                          key={inv.id}
                          className="flex items-center justify-between gap-3 py-2.5"
                        >
                          <p className="min-w-0 truncate font-mono text-xs text-foreground/60">
                            {inv.email}
                          </p>
                          <button
                            onClick={() => handleCancelInvitation(inv.id)}
                            disabled={busy}
                            className="shrink-0 text-[11px] text-foreground/30 transition-colors hover:text-red-400 disabled:opacity-50"
                          >
                            취소
                          </button>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </section>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
