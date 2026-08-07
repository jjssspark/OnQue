'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { useWorkspace } from '@/components/WorkspaceContext';
import { useAuth } from '@/components/AuthContext';

type NavItem = {
  href: string;
  label: string;
  description: string;
  icon: ReactNode;
};

const NAV_ITEMS: NavItem[] = [
  {
    href: '/dashboard',
    label: '대시보드',
    description: '업무 현황 한눈에',
    icon: (
      <path d="M3 11.5 12 4l9 7.5M5 10v9a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1v-9" />
    ),
  },
  {
    href: '/calls',
    label: '통화 요약',
    description: '녹음 파일 → 콜 리포트',
    icon: (
      <path d="M4 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L14 13l5 2v4a2 2 0 0 1-2 2C9.2 21 3 14.8 3 7a2 2 0 0 1 1-1Z" />
    ),
  },
  {
    href: '/documents',
    label: '문서·회의록 요약',
    description: 'PDF/텍스트 → 핵심 정리',
    icon: (
      <>
        <path d="M7 3h7l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
        <path d="M14 3v5h5M9 13h6M9 17h6M9 9h2" />
      </>
    ),
  },
  {
    href: '/chat',
    label: '팀 채팅',
    description: '팀 대화와 AI 명령',
    icon: (
      <path d="M4 5h16v11H8l-4 4V5Z" />
    ),
  },
  {
    href: '/history',
    label: '이력 조회',
    description: '지난 요약 검색',
    icon: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.2-3.2M11 8v3l2 2" />
      </>
    ),
  },
  {
    href: '/announcements',
    label: '팀 공지',
    description: '우리 팀 공지사항',
    icon: (
      <>
        <path d="M4 9v6h4l6 4V5L8 9H4Z" />
        <path d="M18 8.5a5 5 0 0 1 0 7" />
      </>
    ),
  },
  {
    href: '/groups',
    label: '그룹 관리',
    description: '부서·팀과 멤버',
    icon: (
      <>
        <circle cx="9" cy="8" r="3" />
        <path d="M3 20a6 6 0 0 1 12 0M16.5 5.5a3 3 0 0 1 0 5.8M18 20a5.5 5.5 0 0 0-3-4.9" />
      </>
    ),
  },
  {
    href: '/profile',
    label: '내 프로필',
    description: '이름·비밀번호 관리',
    icon: (
      <>
        <circle cx="12" cy="8" r="4" />
        <path d="M4 20a8 8 0 0 1 16 0" />
      </>
    ),
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const { todos } = useWorkspace();
  const { currentGroupId, setCurrentGroupId } = useWorkspace();
  const { groups, user, logout } = useAuth();
  const openTodoCount = todos.filter((t) => !t.is_done).length;

  return (
    <aside className="hidden md:flex w-64 shrink-0 flex-col bg-sidebar text-sidebar-foreground">
      <div className="px-6 py-7 border-b border-white/10">
        <p className="text-xs font-mono tracking-widest text-white/40 uppercase">
          Workspace
        </p>
        <h1 className="mt-1 text-xl font-bold text-white">
          On<span className="text-brand">Que</span>
        </h1>
      </div>

      <div className="px-4 py-3 border-b border-white/10">
        {groups.length > 0 ? (
          <select
            value={currentGroupId ?? ''}
            onChange={(e) => setCurrentGroupId(Number(e.target.value))}
            className="w-full rounded-md bg-white/10 px-2 py-1.5 text-sm text-white"
          >
            {groups.map((g) => (
              <option key={g.id} value={g.id} className="bg-surface text-foreground">
                {g.name}
              </option>
            ))}
          </select>
        ) : (
          <p className="text-xs text-white/50">아직 소속된 그룹이 없습니다. 관리자의 초대를 기다려주세요.</p>
        )}
      </div>

      <nav className="flex-1 px-3 py-5 space-y-1">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === '/dashboard' ? pathname === '/dashboard' : pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`group flex items-start gap-3 rounded-lg px-3 py-2.5 transition-colors ${
                isActive
                  ? 'bg-white/10 text-white'
                  : 'text-sidebar-foreground hover:bg-white/5 hover:text-white'
              }`}
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={1.8}
                strokeLinecap="round"
                strokeLinejoin="round"
                className={`mt-0.5 h-5 w-5 shrink-0 ${
                  isActive ? 'text-brand' : 'text-sidebar-foreground/70 group-hover:text-white'
                }`}
              >
                {item.icon}
              </svg>
              <span className="flex flex-1 flex-col">
                <span className="text-sm font-semibold">{item.label}</span>
                <span className="text-[11px] text-sidebar-foreground/50">
                  {item.description}
                </span>
              </span>
              {item.href === '/dashboard' && openTodoCount > 0 && (
                <span className="mt-0.5 shrink-0 rounded-full bg-brand px-1.5 py-0.5 text-[10px] font-bold text-brand-foreground">
                  {openTodoCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="px-6 py-5 border-t border-white/10">
        <p className="text-[11px] font-mono text-sidebar-foreground/40">{user?.name}</p>
        <button
          type="button"
          onClick={logout}
          className="mt-2 text-[11px] font-mono text-sidebar-foreground/60 hover:text-white"
        >
          로그아웃
        </button>
      </div>
    </aside>
  );
}
