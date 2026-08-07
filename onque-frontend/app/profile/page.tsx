'use client';

import { useState } from 'react';
import { useAuth } from '@/components/AuthContext';
import { ReceivedInvitations } from '@/components/ReceivedInvitations';
import { changeMyPassword, updateMyName } from '@/lib/api';

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ko-KR');
}

export default function ProfilePage() {
  const { user, groups, refreshMe } = useAuth();

  const [name, setName] = useState(user?.name ?? '');
  const [nameBusy, setNameBusy] = useState(false);
  const [nameNotice, setNameNotice] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordNotice, setPasswordNotice] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  async function handleSaveName(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || nameBusy) return;

    setNameBusy(true);
    setNameError(null);
    setNameNotice(null);
    try {
      await updateMyName(trimmed);
      await refreshMe();
      setNameNotice('이름을 저장했습니다.');
    } catch (err) {
      setNameError(err instanceof Error ? err.message : '이름 저장에 실패했습니다.');
    } finally {
      setNameBusy(false);
    }
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    if (!currentPassword || !newPassword || passwordBusy) return;

    setPasswordBusy(true);
    setPasswordError(null);
    setPasswordNotice(null);
    try {
      await changeMyPassword(currentPassword, newPassword);
      setCurrentPassword('');
      setNewPassword('');
      setPasswordNotice('비밀번호를 변경했습니다.');
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : '비밀번호 변경에 실패했습니다.');
    } finally {
      setPasswordBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-brand">Profile</p>
      <h1 className="mt-1 text-2xl font-bold text-foreground">내 프로필</h1>
      <p className="mt-2 text-sm text-foreground/60">계정 정보와 비밀번호를 관리합니다.</p>

      <div className="mt-8 space-y-6">
        <section className="rounded-xl border border-border bg-surface p-5 shadow-sm">
          <h2 className="text-sm font-bold text-foreground">내 정보</h2>

          <form onSubmit={handleSaveName} className="mt-4 space-y-3">
            <div>
              <label htmlFor="profile-name" className="mb-1 block text-xs font-semibold text-foreground/50">
                이름
              </label>
              <input
                id="profile-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full max-w-xs rounded-lg border border-border bg-background px-3 py-2 text-sm"
              />
            </div>

            <div>
              <span className="mb-1 block text-xs font-semibold text-foreground/50">이메일</span>
              <p className="text-sm text-foreground/70">{user?.email}</p>
            </div>

            <div>
              <span className="mb-1 block text-xs font-semibold text-foreground/50">가입일</span>
              <p className="text-sm text-foreground/70">{user ? formatDate(user.created_at) : '-'}</p>
            </div>

            {nameError && <p className="text-sm text-red-500">{nameError}</p>}
            {nameNotice && (
              <p className="rounded-lg border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
                {nameNotice}
              </p>
            )}

            <button
              type="submit"
              disabled={nameBusy || !name.trim()}
              className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-brand-foreground transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {nameBusy ? '저장 중...' : '이름 저장'}
            </button>
          </form>
        </section>

        <section className="rounded-xl border border-border bg-surface p-5 shadow-sm">
          <h2 className="text-sm font-bold text-foreground">비밀번호 변경</h2>

          <form onSubmit={handleChangePassword} className="mt-4 space-y-3">
            <div>
              <label htmlFor="profile-current-password" className="mb-1 block text-xs font-semibold text-foreground/50">
                현재 비밀번호
              </label>
              <input
                id="profile-current-password"
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="w-full max-w-xs rounded-lg border border-border bg-background px-3 py-2 text-sm"
              />
            </div>

            <div>
              <label htmlFor="profile-new-password" className="mb-1 block text-xs font-semibold text-foreground/50">
                새 비밀번호
              </label>
              <input
                id="profile-new-password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full max-w-xs rounded-lg border border-border bg-background px-3 py-2 text-sm"
              />
            </div>

            {passwordError && <p className="text-sm text-red-500">{passwordError}</p>}
            {passwordNotice && (
              <p className="rounded-lg border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
                {passwordNotice}
              </p>
            )}

            <button
              type="submit"
              disabled={passwordBusy || !currentPassword || !newPassword}
              className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-brand-foreground transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {passwordBusy ? '변경 중...' : '비밀번호 변경'}
            </button>
          </form>
        </section>

        <ReceivedInvitations onChanged={refreshMe} />

        <section className="rounded-xl border border-border bg-surface p-5 shadow-sm">
          <h2 className="text-sm font-bold text-foreground">소속 팀</h2>

          {groups.length === 0 ? (
            <p className="mt-3 text-sm text-foreground/40">아직 소속된 팀이 없습니다.</p>
          ) : (
            <ul className="mt-3 divide-y divide-border">
              {groups.map((g) => (
                <li key={g.id} className="flex items-center justify-between gap-3 py-2.5">
                  <p className="text-sm text-foreground">{g.name}</p>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                      g.role === 'admin'
                        ? 'bg-brand/10 text-brand'
                        : 'bg-foreground/5 text-foreground/50'
                    }`}
                  >
                    {g.role === 'admin' ? '관리자' : '멤버'}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
