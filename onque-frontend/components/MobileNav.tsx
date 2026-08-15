'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { NAV_ITEMS, isNavItemActive } from '@/lib/navigation';

export function MobileNav() {
  const pathname = usePathname();

  return (
    <div className="md:hidden sticky top-0 z-10 bg-sidebar text-sidebar-foreground">
      <div className="px-4 py-3 border-b border-white/10">
        <h1 className="text-lg font-bold text-white">
          On<span className="text-brand">Que</span>
        </h1>
      </div>
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
