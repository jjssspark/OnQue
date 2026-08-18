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
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-navy px-6 py-12">
      <div
        className="pointer-events-none absolute left-1/2 top-0 h-[480px] w-[480px] -translate-x-1/2 -translate-y-1/3 rounded-full bg-blue/20 blur-[120px]"
        aria-hidden
      />

      <div className="relative w-full max-w-sm">
        <Link href="/" className="text-3xl font-bold text-card-2">
          On<span className="text-blue">Que</span>
        </Link>
        <p className="mt-2 font-mono text-xs uppercase tracking-widest text-paper/60">
          AI Agent Workspace
        </p>

        <div className="mt-10 rounded-md border border-paper/10 bg-paper/[0.04] p-7 shadow-xl backdrop-blur-sm">
          <h1 className="text-lg font-bold text-card-2">{title}</h1>
          <p className="mt-1 text-sm text-paper/60">{subtitle}</p>
          <div className="mt-6">{children}</div>
        </div>

        <div className="mt-5 text-center">{footer}</div>
      </div>
    </div>
  );
}
