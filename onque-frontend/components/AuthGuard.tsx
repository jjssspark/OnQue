'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { useAuth } from '@/components/AuthContext';

const PUBLIC_PATHS = ['/login', '/signup'];

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isPublicPath = PUBLIC_PATHS.includes(pathname);

  useEffect(() => {
    if (loading) return;
    if (!user && !isPublicPath) router.push('/login');
    if (user && isPublicPath) router.push('/');
  }, [loading, user, isPublicPath, router]);

  if (loading) return null;
  if (!user && !isPublicPath) return null;
  if (user && isPublicPath) return null;

  return <>{children}</>;
}
