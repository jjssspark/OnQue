'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useWorkspace } from '@/components/WorkspaceContext';
import { useAuth } from '@/components/AuthContext';
import { NavLinkHint } from '@/components/NavLinkHint';
import { NAV_ITEMS, isNavItemActive } from '@/lib/navigation';

export function Sidebar() {
  const pathname = usePathname();
  const { todos } = useWorkspace();
  const { currentGroupId, setCurrentGroupId } = useWorkspace();
  const { groups, user, logout } = useAuth();
  const openTodoCount = todos.filter((t) => !t.is_done).length;

  return (
    <aside className="hidden md:flex w-64 shrink-0 flex-col bg-navy text-paper">
      <div className="px-6 py-7 border-b border-paper/10">
        <p className="text-xs font-mono tracking-widest text-paper/60 uppercase">
          Workspace
        </p>
        <h1 className="mt-1 text-xl font-bold text-card-2">
          On<span className="text-blue-wash">Que</span>
        </h1>
      </div>

      <div className="px-4 py-3 border-b border-paper/10">
        {groups.length > 0 ? (
          <select
            value={currentGroupId ?? ''}
            onChange={(e) => setCurrentGroupId(Number(e.target.value))}
            className="w-full rounded-md bg-paper/10 px-2 py-1.5 text-sm text-card-2"
          >
            {groups.map((g) => (
              <option key={g.id} value={g.id} className="bg-card text-ink">
                {g.name}
              </option>
            ))}
          </select>
        ) : (
          <p className="text-xs text-paper/60">받은 초대를 확인해 보세요.</p>
        )}
      </div>

      <nav className="flex-1 px-3 py-5 space-y-1">
        {NAV_ITEMS.map((item) => {
          const isActive = isNavItemActive(item.href, pathname);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`group flex items-start gap-3 rounded-lg px-3 py-2.5 transition-colors ${
                isActive
                  ? 'bg-paper/40 text-card-2'
                  : 'text-paper hover:bg-paper/5 hover:text-card-2'
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
                  isActive ? 'text-blue-wash' : 'text-paper/70 group-hover:text-card-2'
                }`}
              >
                {item.icon}
              </svg>
              <span className="flex flex-1 flex-col">
                <span className="text-sm font-semibold">{item.label}</span>
                <span className="text-[11px] text-paper/60">
                  {item.description}
                </span>
              </span>
              <NavLinkHint />
              {item.href === '/dashboard' && openTodoCount > 0 && (
                <span className="mt-0.5 shrink-0 rounded-full bg-blue px-1.5 py-0.5 text-[10px] font-bold text-card-2">
                  {openTodoCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="px-6 py-5 border-t border-paper/10">
        <p className="text-[11px] font-mono text-paper/60">{user?.name}</p>
        <div className="mt-2 flex gap-3">
          <Link
            href="/profile"
            className="text-[11px] font-mono text-paper/60 hover:text-card-2"
          >
            내 프로필
          </Link>
          <button
            type="button"
            onClick={logout}
            className="text-[11px] font-mono text-paper/60 hover:text-card-2"
          >
            로그아웃
          </button>
        </div>
      </div>
    </aside>
  );
}
