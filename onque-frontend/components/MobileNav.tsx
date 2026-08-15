'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { useAuth } from '@/components/AuthContext';
import { NAV_ITEMS, isNavItemActive } from '@/lib/navigation';

export function MobileNav() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [accountOpen, setAccountOpen] = useState(false);

  // 라우트가 바뀌면 패널을 닫는다. 안 닫으면 프로필로 이동한 뒤에도
  // 패널이 열린 채 남아 화면을 가린다.
  useEffect(() => {
    setAccountOpen(false);
  }, [pathname]);

  return (
    <div className="md:hidden sticky top-0 z-10 bg-sidebar text-sidebar-foreground">
      <div className="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
        <h1 className="text-lg font-bold text-white">
          On<span className="text-brand">Que</span>
        </h1>

        <button
          type="button"
          onClick={() => setAccountOpen((v) => !v)}
          aria-expanded={accountOpen}
          aria-controls="mobile-account-menu"
          className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-semibold text-sidebar-foreground/80 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.8}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-4 w-4"
            aria-hidden
          >
            <circle cx="12" cy="8" r="4" />
            <path d="M4 20a8 8 0 0 1 16 0" />
          </svg>
          <span className="max-w-[7rem] truncate">{user?.name ?? '계정'}</span>
        </button>
      </div>

      {accountOpen && (
        <div
          id="mobile-account-menu"
          className="flex gap-2 border-b border-white/10 px-4 py-2.5 [animation:fade-in_0.15s_ease-out]"
        >
          <Link
            href="/profile"
            className="rounded-md bg-white/10 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-white/20"
          >
            내 프로필
          </Link>
          <button
            type="button"
            onClick={logout}
            className="rounded-md px-3 py-1.5 text-xs font-semibold text-sidebar-foreground/70 transition-colors hover:bg-white/5 hover:text-white"
          >
            로그아웃
          </button>
        </div>
      )}

      <nav className="flex gap-1 overflow-x-auto px-3 pb-2">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
              isNavItemActive(item.href, pathname)
                ? 'bg-white/10 text-white'
                : 'text-sidebar-foreground/70 hover:bg-white/5 hover:text-white'
            }`}
          >
            {item.shortLabel}
          </Link>
        ))}
      </nav>
    </div>
  );
}
