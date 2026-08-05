'use client';

import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/components/AuthContext';
import {
  addGroupMember,
  createGroup,
  listGroupMembers,
  listUsers,
  removeGroupMember,
  type AuthUser,
} from '@/lib/api';

export default function GroupsPage() {
  const { user, groups, refreshMe } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null);
  const [members, setMembers] = useState<AuthUser[]>([]);
  const [allUsers, setAllUsers] = useState<AuthUser[]>([]);
  const [newGroupName, setNewGroupName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (selectedGroupId === null && groups.length > 0) {
      setSelectedGroupId(groups[0].id);
    }
  }, [groups, selectedGroupId]);

  const loadMembers = useCallback(async (groupId: number) => {
    try {
      setMembers(await listGroupMembers(groupId));
    } catch (err) {
      setError(err instanceof Error ? err.message : '멤버를 불러오지 못했습니다.');
    }
  }, []);

  useEffect(() => {
    if (selectedGroupId !== null) loadMembers(selectedGroupId);
  }, [selectedGroupId, loadMembers]);

  useEffect(() => {
    if (!isAdmin) return;
    listUsers()
      .then(setAllUsers)
      .catch(() => setAllUsers([]));
  }, [isAdmin]);

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

  async function handleAddMember(userId: number) {
    if (selectedGroupId === null || busy) return;
    setBusy(true);
    setError(null);
    try {
      await addGroupMember(selectedGroupId, userId);
      await loadMembers(selectedGroupId);
    } catch (err) {
      setError(err instanceof Error ? err.message : '멤버 추가에 실패했습니다.');
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

  const memberIds = new Set(members.map((m) => m.id));
  const candidates = allUsers.filter((u) => !memberIds.has(u.id));

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-brand">Groups</p>
      <h1 className="mt-1 text-2xl font-bold text-foreground">그룹 관리</h1>
      <p className="mt-2 text-sm text-foreground/60">
        부서·팀 단위로 그룹을 나누면 채팅·할 일·일정·문서가 그룹별로 분리됩니다.
      </p>

      {error && <p className="mt-4 text-sm text-red-500">{error}</p>}

      {isAdmin && (
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
        <p className="mt-8 rounded-xl border border-dashed border-border p-10 text-center text-sm text-foreground/40">
          아직 소속된 그룹이 없습니다. 관리자가 그룹에 초대하면 표시됩니다.
        </p>
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
                <h2 className="text-sm font-bold text-foreground">초대할 수 있는 사람</h2>
                {candidates.length === 0 ? (
                  <p className="mt-3 text-xs text-foreground/40">
                    초대할 수 있는 사용자가 없습니다. 먼저 회원가입이 필요합니다.
                  </p>
                ) : (
                  <ul className="mt-3 divide-y divide-border">
                    {candidates.map((u) => (
                      <li key={u.id} className="flex items-center justify-between gap-3 py-2.5">
                        <div className="min-w-0">
                          <p className="truncate text-sm text-foreground">{u.name}</p>
                          <p className="truncate font-mono text-[11px] text-foreground/40">
                            {u.email}
                          </p>
                        </div>
                        <button
                          onClick={() => handleAddMember(u.id)}
                          disabled={busy}
                          className="shrink-0 rounded-md border border-border px-2.5 py-1 text-[11px] font-semibold text-foreground/70 transition-colors hover:bg-foreground/5 disabled:opacity-50"
                        >
                          초대
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
