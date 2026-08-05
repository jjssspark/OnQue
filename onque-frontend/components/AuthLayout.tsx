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
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-sidebar px-6 py-12">
      <div
        className="pointer-events-none absolute left-1/2 top-0 h-[480px] w-[480px] -translate-x-1/2 -translate-y-1/3 rounded-full bg-brand/20 blur-[120px]"
        aria-hidden
      />

      <div className="relative w-full max-w-sm">
        <Link href="/" className="text-lg font-bold text-white">
          On<span className="text-brand">Que</span>
        </Link>
        <p className="mt-1 font-mono text-[11px] uppercase tracking-widest text-sidebar-foreground/40">
          AI Agent Workspace
        </p>

        <div className="mt-8 rounded-2xl border border-white/10 bg-white/[0.04] p-7 shadow-xl backdrop-blur-sm">
          <h1 className="text-lg font-bold text-white">{title}</h1>
          <p className="mt-1 text-sm text-sidebar-foreground/60">{subtitle}</p>
          <div className="mt-6">{children}</div>
        </div>

        <div className="mt-5 text-center">{footer}</div>
      </div>
    </div>
  );
}
