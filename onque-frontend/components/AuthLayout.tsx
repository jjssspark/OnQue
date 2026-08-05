import Link from 'next/link';
import type { ReactNode } from 'react';

type AuthLayoutProps = {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
};

export function AuthLayout({ title, subtitle, children, footer }: AuthLayoutProps) {
  return (
    <div className="flex min-h-screen">
      <div className="hidden w-[380px] shrink-0 flex-col justify-between bg-sidebar px-10 py-12 text-sidebar-foreground lg:flex">
        <Link href="/" className="text-xl font-bold text-white">
          On<span className="text-brand">Que</span>
        </Link>
        <p className="text-sm leading-relaxed text-sidebar-foreground/70">
          통화 녹음, 회의록, 팀 채팅 속 할 일과 일정을
          <br />
          Gemini AI가 대신 정리하는 업무 워크스페이스입니다.
        </p>
        <p className="font-mono text-[11px] text-white/30">© 2026 OnQue</p>
      </div>

      <div className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <Link href="/" className="text-lg font-bold text-foreground lg:hidden">
            On<span className="text-brand">Que</span>
          </Link>
          <h1 className="mt-4 text-xl font-bold text-foreground lg:mt-0">{title}</h1>
          <p className="mt-1 text-sm text-foreground/60">{subtitle}</p>
          <div className="mt-6">{children}</div>
          <div className="mt-4">{footer}</div>
        </div>
      </div>
    </div>
  );
}
