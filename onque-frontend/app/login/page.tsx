'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/components/AuthContext';

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : '로그인에 실패했습니다.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-6">
      <h1 className="text-xl font-bold text-foreground">
        On<span className="text-brand">Que</span> 로그인
      </h1>
      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <input
          type="email"
          required
          placeholder="이메일"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-lg border border-border px-3 py-2 text-sm"
        />
        <input
          type="password"
          required
          placeholder="비밀번호"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-lg border border-border px-3 py-2 text-sm"
        />
        {error && <p className="text-xs text-red-500">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-brand py-2 text-sm font-semibold text-brand-foreground disabled:opacity-50"
        >
          {submitting ? '로그인 중...' : '로그인'}
        </button>
      </form>
      <p className="mt-4 text-center text-xs text-foreground/60">
        계정이 없으신가요? <Link href="/signup" className="text-brand">회원가입</Link>
      </p>
    </div>
  );
}
