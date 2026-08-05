'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/components/AuthContext';
import { AuthLayout } from '@/components/AuthLayout';
import { useSlowRequestHint } from '@/hooks/useSlowRequestHint';

export default function SignupPage() {
  const { signup } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const showSlowHint = useSlowRequestHint(submitting);

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
    <AuthLayout
      title="회원가입"
      subtitle="새 계정을 만들고 워크스페이스를 시작하세요."
      footer={
        <p className="text-xs text-sidebar-foreground/60">
          이미 계정이 있으신가요?{' '}
          <Link href="/login" className="font-semibold text-brand">
            로그인
          </Link>
        </p>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <input
          type="text"
          required
          placeholder="이름"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white placeholder:text-sidebar-foreground/40 focus:border-brand focus:outline-none"
        />
        <input
          type="email"
          required
          placeholder="이메일"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white placeholder:text-sidebar-foreground/40 focus:border-brand focus:outline-none"
        />
        <input
          type="password"
          required
          minLength={8}
          placeholder="비밀번호 (8자 이상)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white placeholder:text-sidebar-foreground/40 focus:border-brand focus:outline-none"
        />
        {error && <p className="text-xs text-red-400">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-brand py-2.5 text-sm font-semibold text-brand-foreground transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? '가입 중...' : '가입하기'}
        </button>
        {showSlowHint && (
          <p className="text-center text-xs leading-relaxed text-sidebar-foreground/50">
            서버를 깨우는 중입니다. 처음 접속은 1분까지 걸릴 수 있습니다.
          </p>
        )}
      </form>
    </AuthLayout>
  );
}
