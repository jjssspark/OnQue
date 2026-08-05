'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/components/AuthContext';

export default function SignupPage() {
  const { signup } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await signup(email, password, name);
    } catch (err) {
      setError(err instanceof Error ? err.message : '회원가입에 실패했습니다.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-6">
      <h1 className="text-xl font-bold text-foreground">
        On<span className="text-brand">Que</span> 회원가입
      </h1>
      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <input
          type="text"
          required
          placeholder="이름"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-lg border border-border px-3 py-2 text-sm"
        />
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
          minLength={8}
          placeholder="비밀번호 (8자 이상)"
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
          {submitting ? '가입 중...' : '가입하기'}
        </button>
      </form>
      <p className="mt-4 text-center text-xs text-foreground/60">
        이미 계정이 있으신가요? <Link href="/login" className="text-brand">로그인</Link>
      </p>
    </div>
  );
}
