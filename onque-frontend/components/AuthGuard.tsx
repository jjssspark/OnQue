'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { useAuth } from '@/components/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileNav } from '@/components/MobileNav';
import { SmartDashboardPanel } from '@/components/SmartDashboardPanel';

const PUBLIC_PATHS = ['/', '/login', '/signup'];
const MIN_SPLASH_MS = 700;

function SplashScreen() {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-sidebar">
      <div
        className="pointer-events-none absolute left-1/2 top-1/2 h-[420px] w-[420px] rounded-full bg-brand/25 blur-[120px] [animation:splash-glow_2.4s_ease-in-out_infinite]"
        aria-hidden
      />
      <div className="relative flex flex-col items-center gap-5 [animation:splash-in_0.5s_ease-out]">
        <p className="text-3xl font-bold text-white">
          On<span className="text-brand">Que</span>
        </p>
        <div className="flex gap-1.5">
          <span className="h-2 w-2 animate-bounce rounded-full bg-brand [animation-delay:-0.3s]" />
          <span className="h-2 w-2 animate-bounce rounded-full bg-brand [animation-delay:-0.15s]" />
          <span className="h-2 w-2 animate-bounce rounded-full bg-brand" />
        </div>
      </div>
    </div>
  );
}

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isPublicPath = PUBLIC_PATHS.includes(pathname);
  const [minTimeElapsed, setMinTimeElapsed] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setMinTimeElapsed(true), MIN_SPLASH_MS);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!user && !isPublicPath) router.push('/login');
    if (user && isPublicPath) router.push('/dashboard');
  }, [loading, user, isPublicPath, router]);

  if (loading || !minTimeElapsed) return <SplashScreen />;
  if (!user && !isPublicPath) return <SplashScreen />;
  if (user && isPublicPath) return <SplashScreen />;

  if (isPublicPath) return <>{children}</>;

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex min-h-screen min-w-0 flex-1 flex-col">
        <MobileNav />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
      <SmartDashboardPanel />
    </div>
  );
}
