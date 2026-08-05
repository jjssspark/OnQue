'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { useAuth } from '@/components/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileNav } from '@/components/MobileNav';
import { SmartDashboardPanel } from '@/components/SmartDashboardPanel';

const PUBLIC_PATHS = ['/', '/login', '/signup'];

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

  if (loading) return null;
  if (!user && !isPublicPath) return null;
  if (user && isPublicPath) return null;

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
