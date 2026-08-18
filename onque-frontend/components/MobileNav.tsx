'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import { useAuth } from '@/components/AuthContext';
import { NavLinkHint } from '@/components/NavLinkHint';
import { NAV_ITEMS, isNavItemActive } from '@/lib/navigation';

export function MobileNav() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  // 라우트가 바뀌면 패널이 닫혀야 한다. 안 닫으면 프로필로 이동한 뒤에도
  // 패널이 열린 채 남아 화면을 가린다.
  //
  // effect로 상태를 되돌리지 않고 파생값으로 만든다. "어느 화면에서 열었는가"를
  // 저장해 두면 라우트가 달라지는 순간 자동으로 닫힌 것이 된다 — 렌더를 한 번 더
  // 돌리지 않고, react-hooks/set-state-in-effect에도 걸리지 않는다.
  const [openedOn, setOpenedOn] = useState<string | null>(null);
  const accountOpen = openedOn === pathname;

  return (
    <div className="md:hidden sticky top-0 z-10 bg-navy text-paper">
      <div className="flex items-center justify-between gap-3 border-b border-paper/10 px-4 py-3">
        <h1 className="text-lg font-bold text-card-2">
          On<span className="text-blue-wash">Que</span>
        </h1>

        <button
          type="button"
          onClick={() => setOpenedOn(accountOpen ? null : pathname)}
          aria-expanded={accountOpen}
          aria-controls="mobile-account-menu"
          className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-semibold text-paper/80 transition-colors hover:bg-paper/10 hover:text-card-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue"
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

      {/* 껍데기는 항상 렌더한다. 닫혔을 때 통째로 없애면 위 버튼의 aria-controls가
          없는 id를 가리켜, 정작 "이 버튼이 뭘 여는가"를 알아야 할 닫힌 상태에서
          참조가 끊긴다. SmartDashboardPanel이 같은 이유로 같은 판단을 해뒀다.

          flex를 조건부로 거는 이유: display를 지정하는 클래스는 브라우저 기본
          스타일 [hidden]{display:none}을 이긴다. flex를 그냥 두면 hidden을
          붙여도 패널이 계속 보인다. */}
      <div
        id="mobile-account-menu"
        hidden={!accountOpen}
        className="gap-2 border-b border-paper/10 px-4 py-2.5 [&:not([hidden])]:flex [animation:fade-in_0.15s_ease-out]"
      >
        <Link
          href="/profile"
          className="rounded-md bg-paper/10 px-3 py-1.5 text-xs font-semibold text-card-2 transition-colors hover:bg-paper/20"
        >
          내 프로필
        </Link>
        <button
          type="button"
          onClick={logout}
          className="rounded-md px-3 py-1.5 text-xs font-semibold text-paper/70 transition-colors hover:bg-paper/5 hover:text-card-2"
        >
          로그아웃
        </button>
      </div>

      <nav className="flex gap-1 overflow-x-auto px-3 pb-2">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
              isNavItemActive(item.href, pathname)
                ? 'bg-paper/40 text-card-2'
                : 'text-paper/70 hover:bg-paper/5 hover:text-card-2'
            }`}
          >
            {item.shortLabel}
            <NavLinkHint />
          </Link>
        ))}
      </nav>
    </div>
  );
}
