'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { useAuth } from '@/components/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileNav } from '@/components/MobileNav';
import { SmartDashboardPanel } from '@/components/SmartDashboardPanel';

const PUBLIC_PATHS = ['/', '/login', '/signup'];

function SplashScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-sidebar">
      <div className="flex flex-col items-center gap-4">
        <p className="text-2xl font-bold text-white">
          On<span className="text-brand">Que</span>
        </p>
        <div className="flex gap-1.5">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand [animation-delay:-0.3s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand [animation-delay:-0.15s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand" />
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

  useEffect(() => {
    if (loading) return;
    if (!user && !isPublicPath) router.push('/login');
    if (user && isPublicPath) router.push('/dashboard');
  }, [loading, user, isPublicPath, router]);

  if (loading) return <SplashScreen />;
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
