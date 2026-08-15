# 프론트엔드 셸 개편 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 내비게이션·페이지 컨테이너·로딩 표현을 공통 구조로 통합해, 여러 화면이 같은 반응형·접근성 결함을 반복하지 않게 한다.

**Architecture:** 지금 결함의 원인은 화면이 아니라 셸이다. 같은 것을 두 군데 적어서 생긴 문제(모바일 프로필 부재, 메뉴 이름 불일치)와 8군데 복붙에서 온 문제(고정 여백)를 단일 출처(`lib/navigation.tsx`, `components/PageShell.tsx`)로 없앤다. 로딩 표현은 맨 글자에서 스켈레톤으로 바꿔 데이터 도착 시 레이아웃이 튀지 않게 한다.

**Tech Stack:** Next.js 16.3 (App Router), React 19, Tailwind CSS 4, TypeScript 5, vitest 3.2

**설계 문서:** `docs/superpowers/specs/2026-08-15-frontend-shell-design.md`

## Global Constraints

- 작업 디렉터리는 `onque-frontend/`다. **이 폴더는 저장소 루트(`/Users/tina/Project/OnQue`)와 별개의 git 저장소다.** 커밋은 `onque-frontend/` 안에서 한다.
- `onque-frontend/AGENTS.md`가 "이 Next.js는 기존 지식과 다르니 `node_modules/next/dist/docs/`를 먼저 읽으라"고 명시한다. Next API를 새로 쓰는 Task 8에서 반드시 지킨다.
- `app/globals.css`의 디자인 토큰(`--background`, `--brand`, `--fg-muted` 등)을 **변경하지 않는다.** 새 색을 만들지 않고 기존 토큰만 쓴다.
- 애니메이션은 `opacity`와 `transform`만 쓴다. `width`/`height`/`top`/`left`/`margin`/`padding`/`font-size`는 애니메이트하지 않는다.
- `components/AuthGuard.tsx:62-78`의 셸 높이 구조(`lg:h-screen`)를 **건드리지 않는다.** 그 주석이 TS-029 근거와 `lg` 미만으로 내리면 안 되는 이유를 기록하고 있다.
- 백엔드(`main.py`, `routers/`, `models.py`, `gemini_service.py`)를 수정하지 않는다.
- `/login`, `/signup`, `/`(랜딩)은 `AuthLayout`을 쓰는 별개 셸이다. **이 계획의 범위 밖이다.**
- 각 태스크 끝에서 `npx vitest run`이 통과해야 한다. 기준선은 **10 tests passed** (`lib/priority.test.ts`)이며, 이 10개는 어떤 태스크에서도 깨지면 안 된다.
- 로딩 상태를 스켈레톤으로 바꿀 때 **스크린리더 알림을 잃지 않는다.** 현재 `불러오는 중...`은 글자라서 읽히지만 순수 시각 스켈레톤은 읽히지 않는다. 반드시 `role="status"`와 `aria-label`을 준다.
- 화면별 잔여 반응형(설계 문서 5단계)과 `SummaryColumn.tsx:18`의 뒤집힌 그리드는 **이 계획의 범위 밖이다.** 1~4단계를 끝내고 브라우저로 확인한 뒤 별도 계획으로 다룬다.

---

## 파일 구조

**신규**

| 파일 | 책임 |
|---|---|
| `lib/navigation.tsx` | 내용 메뉴 7개의 단일 출처. href·label·shortLabel·description·icon |
| `lib/navigation.test.ts` | href가 실제 라우트를 가리키는지, 중복·빈 값이 없는지 검증 |
| `components/PageShell.tsx` | 페이지 컨테이너 + 헤더(eyebrow/title/description/actions) |
| `components/ui/Skeleton.tsx` | `Skeleton`(단일 블록), `SkeletonList`(행 반복) |
| `components/NavLinkHint.tsx` | 링크 전환 pending 점 (Task 8) |

**수정**

| 파일 | 무엇을 |
|---|---|
| `components/Sidebar.tsx` | 자체 `NAV_ITEMS` 삭제 → `lib/navigation` import, 프로필 링크 추가 |
| `components/MobileNav.tsx` | 동일 + 계정 버튼(프로필·로그아웃) 추가 |
| `app/globals.css` | `.hover-reveal`, `page-in` 키프레임, `.link-hint` |
| `app/calls/page.tsx` 외 7개 | `PageShell`로 교체 |
| `components/SmartDashboardPanel.tsx` | `.hover-reveal` 2곳, 스켈레톤 |
| `app/chat/page.tsx` | `.hover-reveal` 1곳, 스켈레톤 |
| `components/{ClientPanel,CommitmentPanel,ChatWindow,RoomMembers}.tsx` | 스켈레톤 |
| `components/dashboard/PriorityStream.tsx` | 스켈레톤 |
| `app/{announcements,history}/page.tsx` | 스켈레톤 |

---

## Task 1: 내비게이션 단일 출처

지금 `Sidebar.tsx`와 `MobileNav.tsx`가 각자 `NAV_ITEMS`를 선언한다. 그래서 같은 메뉴 이름이 어긋나 있다(`/announcements`가 "팀 공지" vs "전사 공지").

**Files:**
- Create: `lib/navigation.tsx`
- Create: `lib/navigation.test.ts`
- Modify: `components/Sidebar.tsx:16-96` (NAV_ITEMS 삭제), `:135-137`, `:178-187`
- Modify: `components/MobileNav.tsx:6-14` (NAV_ITEMS 삭제), `:27-43`

**Interfaces:**
- Produces: `NAV_ITEMS: NavItem[]`, `type NavItem = { href: string; label: string; shortLabel: string; description: string; icon: ReactNode }`, `isNavItemActive(href: string, pathname: string): boolean` — Task 2가 `MobileNav`를 더 고칠 때, Task 8이 링크에 pending 힌트를 붙일 때 쓴다.

**주의:** `lib/navigation.tsx`는 JSX(아이콘 `<path>`)를 담는다. `tsconfig.json`의 `"jsx": "react-jsx"` 설정 덕에 vitest가 별도 설정 없이 변환한다 — 이미 확인했다. Step 2에서 테스트가 "NAV_ITEMS를 찾을 수 없다"가 아니라 JSX 변환 오류로 실패하면 이 가정이 틀린 것이니, 그때 `vitest.config.ts`에 이미 설치된 `@vitejs/plugin-react`를 붙인다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`lib/navigation.test.ts`:

```ts
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { NAV_ITEMS } from './navigation';

// vitest는 프로젝트 루트(onque-frontend/)를 cwd로 실행한다.
const APP_DIR = join(process.cwd(), 'app');

describe('NAV_ITEMS', () => {
  it('모든 href가 실제 라우트를 가리킨다', () => {
    for (const item of NAV_ITEMS) {
      const segment = item.href.replace(/^\//, '');
      expect(
        existsSync(join(APP_DIR, segment, 'page.tsx')),
        `${item.href} 에 해당하는 app/${segment}/page.tsx 가 없다`,
      ).toBe(true);
    }
  });

  it('href가 중복되지 않는다', () => {
    const hrefs = NAV_ITEMS.map((i) => i.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it('label·shortLabel·description이 모두 비어 있지 않다', () => {
    for (const item of NAV_ITEMS) {
      expect(item.label.length, `${item.href} label`).toBeGreaterThan(0);
      expect(item.shortLabel.length, `${item.href} shortLabel`).toBeGreaterThan(0);
      expect(item.description.length, `${item.href} description`).toBeGreaterThan(0);
    }
  });

  it('내용 메뉴만 담는다 — 계정 동작(/profile)은 여기 없다', () => {
    expect(NAV_ITEMS.map((i) => i.href)).not.toContain('/profile');
  });
});
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `cd onque-frontend && npx vitest run lib/navigation.test.ts`
Expected: FAIL — `Failed to load ./navigation` 또는 `Cannot find module`

- [ ] **Step 3: `lib/navigation.tsx`를 만든다**

`label`·`description`·`icon`은 현재 `components/Sidebar.tsx:16-96`의 값을 그대로 옮긴다(사이드바 쪽이 정본). `shortLabel`은 신규이며 `/documents` 하나만 축약하고 나머지는 `label`과 같다.

`MobileNav`의 현재 "전사 공지"는 버린다 — 공지는 그룹 단위다(`routers/announcements.py:40,44`가 `Announcement.group_id`로 필터하고 `require_group_member`로 접근을 막는다). "팀 공지"가 맞는 이름이다.

```tsx
import type { ReactNode } from 'react';

export type NavItem = {
  href: string;
  /** 사이드바에 쓰는 정식 이름 */
  label: string;
  /** 모바일 칩에 쓰는 짧은 이름. CSS로 줄이지 않고 여기 명시한다 */
  shortLabel: string;
  /** 사이드바 2행 설명 */
  description: string;
  /** <svg viewBox="0 0 24 24"> 안에 들어갈 내용 */
  icon: ReactNode;
};

/**
 * 내용 메뉴의 단일 출처. Sidebar와 MobileNav가 이 배열만 읽는다.
 *
 * /profile은 여기 없다 — 프로필과 로그아웃은 내용 메뉴가 아니라 계정 동작이고,
 * 두 셸에서 각각 별도 자리를 갖는다. 예전에는 두 컴포넌트가 배열을 각자
 * 선언해서 모바일에만 /profile이 빠졌고, 같은 메뉴 이름도 어긋나 있었다.
 */
export const NAV_ITEMS: NavItem[] = [
  {
    href: '/dashboard',
    label: '대시보드',
    shortLabel: '대시보드',
    description: '업무 현황 한눈에',
    icon: <path d="M3 11.5 12 4l9 7.5M5 10v9a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1v-9" />,
  },
  {
    href: '/calls',
    label: '통화 요약',
    shortLabel: '통화 요약',
    description: '녹음 파일 → 콜 리포트',
    icon: (
      <path d="M4 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L14 13l5 2v4a2 2 0 0 1-2 2C9.2 21 3 14.8 3 7a2 2 0 0 1 1-1Z" />
    ),
  },
  {
    href: '/documents',
    label: '문서·회의록 요약',
    shortLabel: '문서·회의록',
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
    shortLabel: '팀 채팅',
    description: '팀 대화와 AI 명령',
    icon: <path d="M4 5h16v11H8l-4 4V5Z" />,
  },
  {
    href: '/history',
    label: '이력 조회',
    shortLabel: '이력 조회',
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
    shortLabel: '팀 공지',
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
    shortLabel: '그룹 관리',
    description: '부서·팀과 멤버',
    icon: (
      <>
        <circle cx="9" cy="8" r="3" />
        <path d="M3 20a6 6 0 0 1 12 0M16.5 5.5a3 3 0 0 1 0 5.8M18 20a5.5 5.5 0 0 0-3-4.9" />
      </>
    ),
  },
];

/** /dashboard만 정확히 일치로 판정한다. 나머지는 하위 경로도 활성으로 본다. */
export function isNavItemActive(href: string, pathname: string): boolean {
  return href === '/dashboard' ? pathname === '/dashboard' : pathname.startsWith(href);
}
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `cd onque-frontend && npx vitest run lib/navigation.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 5: `Sidebar.tsx`가 새 출처를 쓰게 바꾼다**

`components/Sidebar.tsx`에서 `NavItem` 타입 정의와 `NAV_ITEMS` 배열(16~96행)을 통째로 지우고 import를 바꾼다:

```tsx
import { NAV_ITEMS, isNavItemActive } from '@/lib/navigation';
```

`import type { ReactNode } from 'react';`는 더 이상 쓰이지 않으니 지운다.

136~137행의 활성 판정을 공용 함수로 교체한다:

```tsx
        {NAV_ITEMS.map((item) => {
          const isActive = isNavItemActive(item.href, pathname);
```

나머지(아이콘 `<svg>`, 배지, 클래스)는 **그대로 둔다.** `/profile`이 메뉴 배열에서 빠지므로 계정 영역(178~187행)에 프로필 링크를 추가한다:

```tsx
      <div className="px-6 py-5 border-t border-white/10">
        <p className="text-[11px] font-mono text-sidebar-foreground/40">{user?.name}</p>
        <div className="mt-2 flex gap-3">
          <Link
            href="/profile"
            className="text-[11px] font-mono text-sidebar-foreground/60 hover:text-white"
          >
            내 프로필
          </Link>
          <button
            type="button"
            onClick={logout}
            className="text-[11px] font-mono text-sidebar-foreground/60 hover:text-white"
          >
            로그아웃
          </button>
        </div>
      </div>
```

- [ ] **Step 6: `MobileNav.tsx`가 새 출처를 쓰게 바꾼다**

`NAV_ITEMS` 배열(6~14행)을 지우고 import한다. 칩에는 `shortLabel`을 쓴다.

```tsx
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
```

- [ ] **Step 7: 전체 테스트와 타입을 확인한다**

Run: `cd onque-frontend && npx vitest run && npx tsc --noEmit`
Expected: 14 tests passed (기존 10 + 신규 4), 타입 오류 없음

- [ ] **Step 8: 커밋**

```bash
cd onque-frontend
git add lib/navigation.tsx lib/navigation.test.ts components/Sidebar.tsx components/MobileNav.tsx
git commit -m "refactor: 내비게이션 항목을 lib/navigation 단일 출처로

Sidebar와 MobileNav가 각자 NAV_ITEMS를 선언해 같은 메뉴 이름이 어긋나 있었다
(/announcements가 팀 공지 vs 전사 공지). 공지는 그룹 단위이므로 팀 공지가 맞다."
```

---

## Task 2: 모바일에서 프로필·로그아웃 도달

**지금 768px 미만에서는 프로필 화면에도, 로그아웃에도 갈 방법이 아예 없다.** 사이드바는 `md:flex`라 숨겨져 있고 모바일 헤더에는 계정 관련 버튼이 없다.

**Files:**
- Modify: `components/MobileNav.tsx` (Task 1 완료 후 상태)

**Interfaces:**
- Consumes: `NAV_ITEMS`, `isNavItemActive` (Task 1)
- Consumes: `useAuth()` → `{ user, logout }` — `components/AuthContext.tsx`가 제공한다. `Sidebar.tsx:102`가 같은 방식으로 쓴다.

- [ ] **Step 1: 계정 버튼과 패널을 추가한다**

`components/MobileNav.tsx` 전체를 아래로 바꾼다.

```tsx
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
```

`fade-in` 키프레임은 `app/globals.css:85-92`에 이미 있다. 새로 만들지 않는다.

- [ ] **Step 2: 타입과 테스트를 확인한다**

Run: `cd onque-frontend && npx tsc --noEmit && npx vitest run`
Expected: 타입 오류 없음, 14 tests passed

- [ ] **Step 3: 브라우저에서 확인한다**

`npm run dev` 후 375px 폭에서:
1. 헤더 우측에 사용자 이름이 붙은 계정 버튼이 보인다
2. 누르면 "내 프로필"과 "로그아웃"이 나타난다
3. "내 프로필"을 누르면 `/profile`로 이동하고 **패널이 닫혀 있다**
4. 로그아웃이 동작한다

- [ ] **Step 4: 커밋**

```bash
cd onque-frontend
git add components/MobileNav.tsx
git commit -m "fix: 모바일에서 프로필·로그아웃에 갈 수 없던 것

768px 미만에서는 사이드바가 숨겨지는데 모바일 헤더에 계정 동작이 없어
프로필 화면과 로그아웃에 도달할 방법이 아예 없었다."
```

---

## Task 3: `PageShell` 생성 및 서버 컴포넌트 2개 적용

7개 인증 화면이 `mx-auto max-w-* px-6 py-10`을 각자 복사해 갖고 있다. `px-6 py-10`이 모든 폭에서 고정이라 320px 화면에서 좌우 여백만 48px을 쓴다.

**Files:**
- Create: `components/PageShell.tsx`
- Modify: `app/calls/page.tsx` (전체 25행)
- Modify: `app/documents/page.tsx`

**Interfaces:**
- Produces: `PageShell` 컴포넌트. props는 `{ eyebrow: string; title: string; description?: ReactNode; width?: 'narrow' | 'default' | 'wide'; actions?: ReactNode; children: ReactNode }`. Task 4가 나머지 6개 화면에 쓴다. Task 8이 이 파일에 진입 애니메이션 클래스를 추가한다.
- **`description`은 `string`이 아니라 `ReactNode`다.** `/chat`의 설명문이 `<span className="font-mono text-brand">/help</span>`를 품고 있어 문자열 타입으로는 Task 4에서 막힌다.

- [ ] **Step 1: `components/PageShell.tsx`를 만든다**

```tsx
import type { ReactNode } from 'react';

type Width = 'narrow' | 'default' | 'wide';

// 새로 정하는 값이 아니라 현재 화면들이 이미 쓰는 값에 이름을 붙인 것이다.
const WIDTH: Record<Width, string> = {
  narrow: 'max-w-3xl',
  default: 'max-w-4xl',
  wide: 'max-w-6xl',
};

type Props = {
  /** 제목 위 작은 영문 라벨. 예: "Call Summary" */
  eyebrow: string;
  title: string;
  /**
   * string이 아니라 ReactNode다. /chat의 설명문에 <span className="font-mono
   * text-brand">/help</span> 가 들어 있어 문자열로는 담기지 않는다.
   */
  description?: ReactNode;
  width?: Width;
  /** 헤더 우측 버튼. 좁은 폭에서는 제목 아래로 내려간다 */
  actions?: ReactNode;
  children: ReactNode;
};

export function PageShell({
  eyebrow,
  title,
  description,
  width = 'default',
  actions,
  children,
}: Props) {
  return (
    // 여백이 폭에 따라 줄어든다. 예전에는 모든 화면이 px-6 py-10 고정이라
    // 320px 기기에서 좌우 48px을 여백으로 썼다.
    <div className={`mx-auto ${WIDTH[width]} px-4 py-6 sm:px-6 sm:py-10`}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-xs uppercase tracking-widest text-brand">{eyebrow}</p>
          <h1 className="mt-1 text-2xl font-bold text-foreground">{title}</h1>
          {description && <p className="mt-2 text-sm text-foreground/60">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </div>

      <div className="mt-6">{children}</div>
    </div>
  );
}
```

- [ ] **Step 2: `app/calls/page.tsx`를 교체한다**

`children` 컨테이너가 이미 `mt-6`을 주므로, 페이지가 갖고 있던 `<div className="mt-6">` 래퍼는 지운다. 안 지우면 간격이 두 배가 된다.

```tsx
import { PageShell } from '@/components/PageShell';
import { UploadPanel } from '@/components/UploadPanel';

export default function CallsPage() {
  return (
    <PageShell
      eyebrow="Call Summary"
      title="통화 요약"
      description="통화 녹음 파일을 업로드하면 Gemini AI가 핵심 내용을 자동으로 정리해드립니다."
      width="narrow"
    >
      <UploadPanel
        accept=".mp3,.m4a,.wav"
        acceptHint="지원 형식: mp3, m4a, wav"
        historyType="call"
        submitLabel="요약 시작하기"
        loadingLabel="AI 분석 중입니다..."
        loadingHint="통화 길이에 따라 약 10~30초 정도 소요됩니다."
        emptySelectionMessage="통화 녹음 파일을 먼저 선택해주세요."
      />
    </PageShell>
  );
}
```

- [ ] **Step 3: `app/documents/page.tsx`를 교체한다**

```tsx
import { PageShell } from '@/components/PageShell';
import { UploadPanel } from '@/components/UploadPanel';

export default function DocumentsPage() {
  return (
    <PageShell
      eyebrow="Document Summary"
      title="문서·회의록 요약"
      description="회의록, 보고서 등 텍스트 문서를 업로드하면 Gemini AI가 핵심만 정리해드립니다."
      width="narrow"
    >
      <UploadPanel
        accept=".pdf,.txt,.md"
        acceptHint="지원 형식: pdf, txt, md"
        historyType="document"
        submitLabel="요약 시작하기"
        loadingLabel="AI 분석 중입니다..."
        loadingHint="문서 분량에 따라 약 10~30초 정도 소요됩니다."
        emptySelectionMessage="문서 파일을 먼저 선택해주세요."
      />
    </PageShell>
  );
}
```

- [ ] **Step 4: 타입·테스트·빌드를 확인한다**

Run: `cd onque-frontend && npx tsc --noEmit && npx vitest run && npm run build`
Expected: 타입 오류 없음, 14 tests passed, 빌드 성공

- [ ] **Step 5: 브라우저에서 확인한다**

`/calls`와 `/documents`를 320px과 1440px에서 연다.
1. 제목·설명·업로드 패널이 예전과 같은 순서로 보인다
2. 320px에서 가로 스크롤이 없다
3. 320px의 좌우 여백이 1440px보다 좁다

- [ ] **Step 6: 커밋**

```bash
cd onque-frontend
git add components/PageShell.tsx app/calls/page.tsx app/documents/page.tsx
git commit -m "feat: PageShell 도입, 업로드 화면 2개 적용

여백이 모든 폭에서 px-6 py-10 고정이라 320px에서 좌우 48px을 여백에 썼다.
컨테이너를 한 곳으로 모아 반응형 여백을 한 번에 정의한다."
```

---

## Task 4: 나머지 6개 화면에 `PageShell` 적용

**Files:**
- Modify: `app/dashboard/page.tsx:194`, `:204-212`
- Modify: `app/history/page.tsx:59`, `:66-71`
- Modify: `app/announcements/page.tsx:57`, `:64-70`
- Modify: `app/chat/page.tsx:109`, `:116-126`
- Modify: `app/groups/page.tsx:125-131`
- Modify: `app/profile/page.tsx:65-69`

**Interfaces:**
- Consumes: `PageShell` (Task 3)

**폭 배정** — 현재 값을 그대로 옮긴다. 새로 정하지 않는다.

| 화면 | width | 현재 값 |
|---|---|---|
| `/chat`, `/announcements` | `narrow` | `max-w-3xl` |
| `/history`, `/groups`, `/profile` | `default` | `max-w-4xl` |
| `/dashboard` | `wide` | `max-w-6xl` |

**빈 상태 분기도 대상이다.** `/dashboard:194`, `/announcements:57`, `/chat:109`, `/history:59`는 "소속 그룹 없음"일 때 `mx-auto max-w-2xl px-6 py-10`로 맨 문장만 보여준다. 이 분기도 `PageShell`로 감싼다 — 그래야 (a) 320px 여백 문제가 이 상태에서도 풀리고, (b) 처음 가입한 사용자가 자기가 어느 화면에 있는지 알 수 있다. 지금은 제목조차 안 나온다.

- [ ] **Step 1: `app/history/page.tsx`를 교체한다**

두 분기 모두 감싼다. 본문 첫 자식의 `mt-6`을 지운다(`PageShell`이 이미 준다). 두 번째 `mt-6`은 남긴다.

```tsx
  if (currentGroupId === null) {
    return (
      <PageShell
        eyebrow="History"
        title="이력 조회"
        description="지금까지 요약한 통화·문서 결과를 검색하고 다시 확인할 수 있습니다."
      >
        <p className="text-sm text-foreground/60">
          아직 소속된 그룹이 없습니다. 관리자가 그룹에 초대하면 이용할 수 있습니다.
        </p>
      </PageShell>
    );
  }

  return (
    <PageShell
      eyebrow="History"
      title="이력 조회"
      description="지금까지 요약한 통화·문서 결과를 검색하고 다시 확인할 수 있습니다."
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        {/* 검색 input과 카테고리 버튼: 현재 73~97행 내용을 그대로. 바깥 div의 mt-6만 제거 */}
      </div>

      {errorMsg && <p className="mt-3 text-sm text-red-500">{errorMsg}</p>}

      <div className="mt-6 space-y-3">
        {/* 현재 101행 이하 그대로 */}
      </div>
    </PageShell>
  );
```

`import { PageShell } from '@/components/PageShell';`를 추가한다.

- [ ] **Step 2: 나머지 5개 화면을 교체한다**

**`eyebrow`/`title`/`description`은 아래 값을 쓴다. 새로 짓지 않는다.** 현재 각 파일에 있는 값을 그대로 옮긴 것이다.

| 화면 | eyebrow | title | description |
|---|---|---|---|
| `/dashboard` | `Dashboard` | `업무 현황` | **없음** (설명문이 원래 없다) |
| `/announcements` | `Announcements` | `팀 공지사항` | `지금 선택된 그룹의 팀원이 함께 보는 공지입니다. 등록은 관리자만 할 수 있습니다.` |
| `/chat` | `Team Chat` | `팀 채팅` | **JSX다.** 현재 `app/chat/page.tsx`의 `<p className="mt-2 text-sm leading-relaxed text-foreground/55">` 안 내용을 통째로 `description={<>...</>}`로 옮긴다. `<span className="font-mono text-brand">/help</span>`와 `{' '}`가 들어 있어 문자열로 못 만든다 |
| `/groups` | `Groups` | `그룹 관리` | `부서·팀 단위로 그룹을 나누면 채팅·할 일·일정·문서가 그룹별로 분리됩니다.` |
| `/profile` | `Profile` | `내 프로필` | `계정 정보와 비밀번호를 관리합니다.` |

`/dashboard`는 설명문 대신 헤더 우측에 사용자·그룹 이름이 있다. 이것을 `actions`로 옮긴다:

```tsx
      actions={
        <p className="text-xs text-fg-dim">
          {user?.name}
          {groupName && ` · ${groupName}`}
        </p>
      }
```

그리고 이 요소를 감싸던 `<div className="flex flex-wrap items-end justify-between gap-3">`(205행)를 지운다 — `PageShell` 헤더가 같은 배치를 제공한다.

`/profile`의 본문 첫 자식은 `mt-6`이 아니라 `mt-8`이다(69행). 이것도 지운다 — `PageShell`이 `mt-6`을 준다.

각 파일마다 동일하게:
1. `import { PageShell } from '@/components/PageShell';` 추가
2. 바깥 `<div className="mx-auto max-w-* px-6 py-10">`를 `<PageShell>`로 교체 (폭은 위 배정표대로)
3. `eyebrow`/`title`/`description`은 **위 문구표의 값**을 쓴다
4. 본문에 남은 헤더 3줄(`<p className="font-mono ...">`, `<h1>`, 설명 `<p>`)을 지운다 — `PageShell`이 렌더한다
5. 본문 첫 자식의 상단 여백 클래스(`mt-6`, `/profile`은 `mt-8`) 제거
6. 빈 상태 분기(`/dashboard:194`, `/announcements:57`, `/chat:109`)도 같은 `eyebrow`/`title`로 감싼다

`/groups`와 `/profile`은 빈 상태 분기가 없다(`/groups:161`의 "아직 속한 팀이 없습니다"는 본문 안 카드라 그대로 둔다).

- [ ] **Step 3: 타입·테스트·빌드를 확인한다**

Run: `cd onque-frontend && npx tsc --noEmit && npx vitest run && npm run build`
Expected: 타입 오류 없음, 14 tests passed, 빌드 성공

- [ ] **Step 4: 브라우저에서 8개 화면을 모두 확인한다**

320 / 768 / 1024 / 1440px에서 `/dashboard`, `/calls`, `/documents`, `/chat`, `/history`, `/announcements`, `/groups`, `/profile`을 연다.

1. **가로 스크롤이 없다** (모든 폭, 모든 화면)
2. 제목·설명이 예전과 같은 문구다
3. 제목과 본문 사이 간격이 두 배가 되지 않았다
4. `/dashboard`의 헤더 우측 요소가 제자리에 있고, 320px에서는 제목 아래로 내려간다

- [ ] **Step 5: 커밋**

```bash
cd onque-frontend
git add app/dashboard/page.tsx app/history/page.tsx app/announcements/page.tsx \
        app/chat/page.tsx app/groups/page.tsx app/profile/page.tsx
git commit -m "refactor: 나머지 6개 화면을 PageShell로

빈 상태 분기도 함께 감쌌다. 처음 가입해 소속 그룹이 없는 사용자에게
제목조차 없이 문장 하나만 보이던 상태였다."
```

---

## Task 5: hover에서만 보이던 컨트롤 노출

삭제 버튼 3개가 `opacity-0 group-hover:opacity-100`이다. **터치 기기에서는 hover가 없어 영영 안 보이고**, 그중 둘은 키보드 포커스로도 안 나타난다.

`app/globals.css:157-192`의 `.card-actions`가 이 문제를 이미 세 갈래(`:focus-within`, `pointer: coarse`, `prefers-reduced-motion`)로 풀어놨다. 같은 해법을 재사용한다. **새 규칙을 발명하지 않는다.**

**Files:**
- Modify: `app/globals.css` (`.card-actions` 블록 뒤, 192행 부근)
- Modify: `app/chat/page.tsx:228`
- Modify: `components/SmartDashboardPanel.tsx:159`, `:187`

- [ ] **Step 1: `.hover-reveal`을 `app/globals.css`에 추가한다**

`.card-actions` 관련 블록(157~192행) **바로 뒤**에 넣는다.

```css
/* .card-actions와 같은 문제를 opacity만으로 푸는 판. 카드 액션은 max-height로
   자리까지 접지만, 이쪽(목록 행의 삭제 버튼)은 자리를 이미 차지하고 있어
   보이기만 토글하면 된다.

   세 갈래를 모두 처리해야 한다. hover만 쓰면 터치와 키보드에서 아예 못 쓴다 —
   실제로 이 규칙을 만들기 전까지 우측 패널의 삭제 버튼 두 개가 그랬다. */
.hover-reveal {
  opacity: 0;
  transition: opacity 0.2s;
}

.group:hover .hover-reveal,
.group:focus-within .hover-reveal {
  opacity: 1;
}

/* 터치 기기에는 hover가 없다. 항상 보여 둔다. */
@media (pointer: coarse) {
  .hover-reveal {
    opacity: 1;
  }
}

/* 이 파일 위쪽 전역 규칙이 모션 최소화 시 transition을 0.01ms로 죽인다.
   전환에만 맡기면 깜빡이며 나타나거나 안 나타난다. 처음부터 보여 둔다. */
@media (prefers-reduced-motion: reduce) {
  .hover-reveal {
    opacity: 1;
  }
}
```

- [ ] **Step 2: `components/SmartDashboardPanel.tsx`의 삭제 버튼 2개를 바꾼다**

159행 (할 일 삭제):

```tsx
              <button
                onClick={() => removeTodo(todo.id)}
                className="hover-reveal shrink-0 text-[10px] text-foreground/30 hover:text-red-500"
              >
                삭제
              </button>
```

187행 (일정 삭제):

```tsx
              <button
                onClick={() => removeSchedule(schedule.id)}
                className="hover-reveal shrink-0 text-[10px] text-foreground/30 hover:text-red-500"
              >
                삭제
              </button>
```

두 곳 모두 `opacity-0`과 `group-hover:opacity-100`을 지우고 `hover-reveal`을 넣는다. 부모 `<li>`에 `group` 클래스가 이미 있다(145행, 178행) — 확인만 하고 건드리지 않는다.

- [ ] **Step 3: `app/chat/page.tsx:228`을 바꾼다**

이쪽은 `focus-visible:opacity-100`이 있어 키보드는 이미 되지만 터치가 안 된다. `hover-reveal`로 통일한다.

```tsx
                className="hover-reveal mr-3 shrink-0 rounded-lg px-2 py-1 text-[11px] text-foreground/25 transition-all hover:bg-red-500/10 hover:text-red-300"
```

`opacity-0`, `focus-visible:opacity-100`, `group-hover:opacity-100`을 지운다. 부모에 `group`이 있는지 확인한다.

- [ ] **Step 4: 브라우저에서 세 갈래를 모두 확인한다**

1. **키보드**: Tab만 눌러 세 버튼에 도달한다. 포커스가 들어가면 버튼이 보인다
2. **터치**: DevTools에서 기기 에뮬레이션(터치)을 켜고 새로고침한다. 세 버튼이 **처음부터** 보인다
3. **모션 최소화**: DevTools Rendering → `prefers-reduced-motion: reduce`. 세 버튼이 처음부터 보인다
4. **마우스**: 항목에 마우스를 올리면 부드럽게 나타난다 (평소엔 안 보인다)

- [ ] **Step 5: 테스트와 빌드를 확인한다**

Run: `cd onque-frontend && npx vitest run && npm run build`
Expected: 14 tests passed, 빌드 성공

- [ ] **Step 6: 커밋**

```bash
cd onque-frontend
git add app/globals.css app/chat/page.tsx components/SmartDashboardPanel.tsx
git commit -m "fix: 터치·키보드에서 도달 불가였던 삭제 버튼 3개

opacity-0 group-hover:opacity-100은 hover가 없는 기기에서 영영 안 보인다.
.card-actions가 이미 푼 방식(focus-within + pointer:coarse + reduced-motion)을
.hover-reveal로 뽑아 재사용한다."
```

---

## Task 6: `Skeleton` 생성 및 우측 패널·대시보드 적용

`불러오는 중...`이라는 맨 글자가 9곳에 흩어져 있다. 최종 레이아웃과 모양이 달라 데이터가 도착하는 순간 화면이 튄다. 백엔드가 Render 무료 티어라 콜드 스타트가 실측 32~54초여서, 사용자는 이 상태를 오래 본다.

**스켈레톤의 목적은 "기다리는 중"을 알리는 게 아니라 도착할 내용의 자리를 미리 잡는 것이다.** 따라서 각 사용처의 스켈레톤은 그 자리 실제 콘텐츠와 비슷한 높이·개수여야 한다.

**Files:**
- Create: `components/ui/Skeleton.tsx`
- Modify: `components/SmartDashboardPanel.tsx:139`
- Modify: `components/dashboard/PriorityStream.tsx:22-31`

**Interfaces:**
- Produces: `Skeleton({ className }: { className?: string })` — 단일 블록. `SkeletonList({ rows, rowClassName, className, label }: { rows?: number; rowClassName?: string; className?: string; label?: string })` — 행 반복. Task 7이 나머지 7곳에 쓴다.

- [ ] **Step 1: `components/ui/Skeleton.tsx`를 만든다**

```tsx
type SkeletonProps = {
  className?: string;
};

/**
 * 로딩 중 자리를 잡아두는 회색 블록. 크기는 호출부가 className으로 준다.
 *
 * animate-pulse는 opacity만 건드려 컴포지터에서 처리된다. 모션 최소화에서는
 * globals.css의 전역 규칙(117~125행)이 애니메이션을 멈춘다 — 여기서 따로
 * 처리하지 않는다.
 */
export function Skeleton({ className = '' }: SkeletonProps) {
  return <div aria-hidden className={`animate-pulse rounded bg-foreground/[0.07] ${className}`} />;
}

type SkeletonListProps = {
  rows?: number;
  /** 행 하나의 높이. 그 자리에 올 실제 콘텐츠와 비슷하게 준다 */
  rowClassName?: string;
  className?: string;
  /** 스크린리더가 읽을 문구 */
  label?: string;
};

/**
 * 목록 자리를 잡는 스켈레톤.
 *
 * role="status"와 aria-label이 반드시 필요하다. 이전의 "불러오는 중..."은
 * 글자라서 스크린리더가 읽었는데, 순수 시각 블록으로 바꾸면 그 알림이
 * 사라진다. 눈으로 보는 사람만 상태를 알게 되는 건 후퇴다.
 */
export function SkeletonList({
  rows = 3,
  rowClassName = 'h-14',
  className = '',
  label = '불러오는 중',
}: SkeletonListProps) {
  return (
    <div role="status" aria-label={label} className={`space-y-2 ${className}`}>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={`w-full ${rowClassName}`} />
      ))}
    </div>
  );
}
```

- [ ] **Step 2: `components/SmartDashboardPanel.tsx`의 할 일 로딩을 바꾼다**

139행. 이 자리의 실제 콘텐츠는 체크박스 + 2줄 텍스트인 작은 행이므로 `h-10`, 3행으로 잡는다.

```tsx
        {loading && <SkeletonList rows={3} rowClassName="h-10" label="할 일 불러오는 중" />}
```

`import { SkeletonList } from '@/components/ui/Skeleton';`를 추가한다.

- [ ] **Step 3: `components/dashboard/PriorityStream.tsx`의 로딩 분기를 바꾼다**

현재 22~31행은 `items.length === 0`일 때 로딩과 빈 상태를 **한 덩어리로** 처리하며 문구만 바꾼다. 로딩을 앞으로 분리한다.

```tsx
export function PriorityStream({ items, isLoading = false, onCompleteTodo }: Props) {
  // 로딩과 "할 일 없음"은 다른 상태다. 예전에는 같은 카드 안에서 문구만
  // 바꿔, 데이터가 도착하면 카드가 통째로 목록으로 바뀌며 화면이 튀었다.
  if (isLoading && items.length === 0) {
    return <SkeletonList rows={3} rowClassName="h-24" label="우선순위 항목 불러오는 중" />;
  }

  if (items.length === 0) {
    return (
      <Surface level="sunken" className="p-10 text-center">
        <p className="text-sm text-fg-dim">지금 처리할 것이 없습니다.</p>
      </Surface>
    );
  }
```

`import { SkeletonList } from '@/components/ui/Skeleton';`를 추가한다. `h-24`는 우선순위 카드가 제목 + 메타 + 액션을 담아 그만큼 높기 때문이다.

- [ ] **Step 4: 타입·테스트·빌드를 확인한다**

Run: `cd onque-frontend && npx tsc --noEmit && npx vitest run && npm run build`
Expected: 타입 오류 없음, 14 tests passed, 빌드 성공

- [ ] **Step 5: 백엔드를 끈 상태로 확인한다**

백엔드를 정지하거나 DevTools Network에서 3G 스로틀을 켠 뒤 `/dashboard`에 진입한다.

1. 우선순위 영역과 우측 패널 할 일 영역에 회색 블록이 뜬다
2. 데이터가 도착할 때 **블록이 있던 자리에 콘텐츠가 들어온다** — 화면이 위아래로 튀지 않는다
3. 스크린리더(macOS VoiceOver: Cmd+F5)가 "할 일 불러오는 중"을 읽는다

- [ ] **Step 6: 커밋**

```bash
cd onque-frontend
git add components/ui/Skeleton.tsx components/SmartDashboardPanel.tsx components/dashboard/PriorityStream.tsx
git commit -m "feat: 로딩 표시를 스켈레톤으로 — 우측 패널·우선순위

맨 글자 '불러오는 중...'은 최종 레이아웃과 모양이 달라 데이터 도착 시
화면이 튀었다. 백엔드 콜드 스타트가 32~54초라 이 상태를 오래 본다.
role=status로 스크린리더 알림은 유지한다."
```

---

## Task 7: 나머지 7곳에 스켈레톤 적용

**Files:**
- Modify: `app/announcements/page.tsx:103`
- Modify: `app/chat/page.tsx:160`
- Modify: `app/history/page.tsx:102`
- Modify: `components/ChatWindow.tsx:208`
- Modify: `components/ClientPanel.tsx:86`
- Modify: `components/CommitmentPanel.tsx:143`
- Modify: `components/RoomMembers.tsx:90-92`

**Interfaces:**
- Consumes: `SkeletonList` (Task 6)

각 자리의 실제 콘텐츠 높이에 맞춰 `rowClassName`을 정한다. **모든 자리에 같은 값을 쓰지 않는다** — 그러면 자리를 잡아준다는 목적이 무너진다.

| 위치 | 현재 코드 | 바꿀 코드 | 근거 |
|---|---|---|---|
| `announcements:103` | `{loading && <p className="text-sm text-foreground/40">불러오는 중...</p>}` | `{loading && <SkeletonList rows={3} rowClassName="h-24" label="공지 불러오는 중" />}` | 공지 카드가 제목+본문+작성자 |
| `chat/page:160` | 같은 형태 | `{loading && <SkeletonList rows={3} rowClassName="h-16" label="채팅방 불러오는 중" />}` | 방 목록 행이 이름+최근 메시지 |
| `history:102` | 같은 형태 | `{loading && <SkeletonList rows={4} rowClassName="h-16" label="이력 불러오는 중" />}` | 이력 카드가 접힌 상태에서 한 줄 헤더 |
| `ChatWindow:208` | 같은 형태 | `{loading && <SkeletonList rows={4} rowClassName="h-12" label="메시지 불러오는 중" />}` | 말풍선 한 줄 |
| `ClientPanel:86` | `<p className="mt-4 text-xs text-foreground/40">불러오는 중...</p>` | `<SkeletonList rows={3} rowClassName="h-8" className="mt-3" label="클라이언트 불러오는 중" />` | 클라이언트 행이 이름 한 줄 |
| `CommitmentPanel:143` | `<p className="mt-4 text-xs text-foreground/40">불러오는 중...</p>` | `<SkeletonList rows={2} rowClassName="h-20" className="mt-4" label="확인할 약속 불러오는 중" />` | 약속 카드가 내용+마감+버튼 |
| `RoomMembers:90-92` | `if (loading) { return <p className="px-5 py-4 text-xs text-foreground/40">멤버를 불러오는 중...</p>; }` | 아래 코드 | 멤버 행이 이름+역할 |

`components/RoomMembers.tsx`:

```tsx
  if (loading) {
    return (
      <div className="border-b border-border bg-background/60 px-5 py-4">
        <SkeletonList rows={3} rowClassName="h-8" label="멤버 불러오는 중" />
      </div>
    );
  }
```

바깥 `div`의 배경·테두리는 로딩이 끝난 뒤 렌더되는 컨테이너(94행)와 맞춘 것이다. 없으면 멤버 목록이 뜨는 순간 배경이 생기며 튄다.

- [ ] **Step 1: 7개 파일을 위 표대로 바꾼다**

각 파일에 `import { SkeletonList } from '@/components/ui/Skeleton';`를 추가한다. `CommitmentPanel:143`은 삼항 연산자의 첫 가지이므로 JSX 구조를 유지한 채 내용만 바꾼다 — `isLoading ? (...) : proposed.length === 0 ? (...) : (...)` 형태를 깨지 않는다.

- [ ] **Step 2: `불러오는 중` 맨 글자가 남았는지 확인한다**

Run: `cd onque-frontend && grep -rn '불러오는 중\.\.\.' app components`
Expected: 결과 없음 (`UploadPanel`의 `loadingLabel`은 "AI 분석 중입니다..."라 여기 걸리지 않는다)

- [ ] **Step 3: 타입·테스트·빌드를 확인한다**

Run: `cd onque-frontend && npx tsc --noEmit && npx vitest run && npm run build`
Expected: 타입 오류 없음, 14 tests passed, 빌드 성공

- [ ] **Step 4: 백엔드를 끈 상태로 7곳을 모두 확인한다**

`/announcements`, `/chat`(방 목록과 방 내부, 멤버 패널), `/history`, `/dashboard`(클라이언트·약속 패널)에 진입한다.

1. 각 자리에 회색 블록이 뜬다
2. 데이터 도착 시 화면이 위아래로 튀지 않는다
3. 블록 높이가 실제 콘텐츠와 크게 다르지 않다 (반 이상 차이 나면 값을 조정한다)

- [ ] **Step 5: 커밋**

```bash
cd onque-frontend
git add app/announcements/page.tsx app/chat/page.tsx app/history/page.tsx \
        components/ChatWindow.tsx components/ClientPanel.tsx \
        components/CommitmentPanel.tsx components/RoomMembers.tsx
git commit -m "feat: 남은 7곳의 로딩 표시를 스켈레톤으로

자리마다 실제 콘텐츠 높이에 맞춘 rowClassName을 준다. 전부 같은 값을 쓰면
자리를 미리 잡는다는 목적이 무너진다."
```

---

## Task 8: 페이지 진입 모션과 링크 pending 힌트

라우트 전환 자체는 이미 즉시다 — 화면들이 클라이언트 컴포넌트라 서버를 기다리지 않는다. 그래서 오히려 화면이 바뀐 것을 인지하기 어렵다.

`useLinkStatus`는 **효과가 작다.** 전환이 즉시라 해당 라우트의 JS 청크가 아직 안 받아진 첫 클릭에서만 pending이 관측된다. 비용이 거의 없어 넣는 것이지 주된 개선이 아니다.

**Files:**
- Modify: `app/globals.css` (파일 끝에 `page-in` 키프레임, `.link-hint`)
- Modify: `components/PageShell.tsx`
- Create: `components/NavLinkHint.tsx`
- Modify: `components/Sidebar.tsx`, `components/MobileNav.tsx`

**Interfaces:**
- Consumes: `PageShell` (Task 3), `NAV_ITEMS` (Task 1)
- Produces: `NavLinkHint` — `<Link>`의 **자식**으로만 쓸 수 있다. `useLinkStatus`는 부모 `<Link>`의 상태를 읽으므로 밖에서 쓰면 동작하지 않는다.

- [ ] **Step 1: Next 문서를 읽는다**

`AGENTS.md`가 요구하는 절차다. 이 태스크는 Next 고유 API를 새로 쓴다.

Read: `onque-frontend/node_modules/next/dist/docs/01-app/01-getting-started/04-linking-and-navigating.md` 229~266행 (Slow networks 절)

확인할 것: `useLinkStatus`가 `next/link`에서 오는지, `{ pending }`을 주는지, 반드시 `<Link>` 자식에서 호출해야 하는지. 문서와 아래 코드가 다르면 **문서를 따른다.**

- [ ] **Step 2: `app/globals.css`에 키프레임과 힌트 스타일을 추가한다**

파일 끝에 넣는다.

```css
/* 페이지 진입. 라우트 전환이 즉시라 오히려 바뀐 것을 인지하기 어렵다.
   summary-in과 같은 성격(opacity + translateY)으로 맞춘다. */
@keyframes page-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

/* 링크 pending 힌트. 100ms 지연 후에야 나타나므로 빠른 전환에서는 보이지
   않는다 — 깜빡임이 전환보다 더 거슬리는 것을 막는다. */
.link-hint {
  opacity: 0;
}

.link-hint.is-pending {
  animation: fade-in 0.2s ease-out 0.1s forwards;
}
```

`fade-in`은 85~92행에 이미 있다. 새로 만들지 않는다.

- [ ] **Step 3: `PageShell`에 진입 모션을 붙인다**

`components/PageShell.tsx`의 바깥 `div` className에 애니메이션을 더한다.

```tsx
    <div
      className={`mx-auto ${WIDTH[width]} px-4 py-6 sm:px-6 sm:py-10 [animation:page-in_0.28s_ease-out]`}
    >
```

- [ ] **Step 4: `components/NavLinkHint.tsx`를 만든다**

```tsx
'use client';

import { useLinkStatus } from 'next/link';

/**
 * 링크 전환이 진행 중임을 알리는 점.
 *
 * 반드시 <Link>의 자식으로 둔다 — useLinkStatus는 부모 Link의 상태를 읽는다.
 *
 * 이 앱에서 효과는 작다. 화면들이 클라이언트 컴포넌트라 라우트 전환이 이미
 * 즉시고, 해당 라우트의 JS 청크가 아직 없는 첫 클릭에서만 pending이 보인다.
 * .link-hint의 100ms 지연이 그 외 경우를 전부 걸러낸다.
 */
export function NavLinkHint() {
  const { pending } = useLinkStatus();
  return (
    <span
      aria-hidden
      className={`link-hint ml-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-brand ${
        pending ? 'is-pending' : ''
      }`}
    />
  );
}
```

- [ ] **Step 5: 두 내비게이션에 힌트를 붙인다**

`components/Sidebar.tsx`의 `<Link>` 안, 라벨 `<span>` 다음에 넣는다:

```tsx
              <span className="flex flex-1 flex-col">
                <span className="text-sm font-semibold">{item.label}</span>
                <span className="text-[11px] text-sidebar-foreground/50">{item.description}</span>
              </span>
              <NavLinkHint />
```

`components/MobileNav.tsx`의 칩 `<Link>` 안, `{item.shortLabel}` 다음에 넣는다:

```tsx
            {item.shortLabel}
            <NavLinkHint />
```

두 파일에 `import { NavLinkHint } from '@/components/NavLinkHint';`를 추가한다.

- [ ] **Step 6: 타입·테스트·빌드를 확인한다**

Run: `cd onque-frontend && npx tsc --noEmit && npx vitest run && npm run build`
Expected: 타입 오류 없음, 14 tests passed, 빌드 성공

`useLinkStatus`가 `next/link`에 없다는 타입 오류가 나면 Step 1의 문서를 다시 보고 정확한 import 경로를 쓴다.

- [ ] **Step 7: 브라우저에서 확인한다**

1. 메뉴를 눌러 화면을 옮기면 본문이 살짝 아래에서 올라오며 나타난다
2. **빠른 전환에서는 pending 점이 보이지 않는다** (100ms 지연이 동작한다)
3. DevTools에서 Slow 3G로 스로틀하고 아직 방문하지 않은 메뉴를 처음 누르면 점이 잠깐 보인다
4. DevTools Rendering → `prefers-reduced-motion: reduce`에서 진입 모션과 점 애니메이션이 멈춘다

- [ ] **Step 8: 커밋**

```bash
cd onque-frontend
git add app/globals.css components/PageShell.tsx components/NavLinkHint.tsx \
        components/Sidebar.tsx components/MobileNav.tsx
git commit -m "feat: 페이지 진입 모션과 링크 pending 힌트

전환이 이미 즉시라 오히려 바뀐 것을 인지하기 어려웠다. useLinkStatus는
효과가 작다 — 청크가 없는 첫 클릭에서만 보이고, 100ms 지연으로 그 외에는
나타나지 않는다."
```

---

## 완료 기준

8개 태스크가 모두 끝난 뒤, 설계 문서의 육안 검증 6개를 순서대로 확인한다.

1. 375px 폭에서 계정 버튼을 눌러 `/profile`로 이동하고, 로그아웃이 동작한다
2. 320 / 768 / 1024 / 1440px에서 8개 인증 화면 모두 가로 스크롤이 없다
3. 백엔드를 정지한 상태로 각 화면에 진입하면, 스켈레톤이 실제 콘텐츠와 같은 자리·비슷한 높이로 뜬다 (데이터 도착 시 화면이 튀지 않는다)
4. 키보드 Tab만으로 숨은 삭제 버튼 3개에 모두 도달할 수 있다
5. 터치 에뮬레이션(`pointer: coarse`)에서 같은 3개가 처음부터 보인다
6. 사이드바와 모바일 내비의 메뉴 이름이 같다 (`/documents`만 `shortLabel`로 축약)

이 중 하나라도 실패하면 해당 태스크로 돌아간다.

**후속 (이 계획 범위 밖):** 위 검증 2번에서 발견된 화면별 문제와 `components/dashboard/SummaryColumn.tsx:18`의 뒤집힌 그리드(`grid-cols-2 lg:grid-cols-1`)는 별도 계획으로 다룬다. 지금 목록을 만들면 `PageShell` 적용 후 달라질 내용이라 절반이 틀린 목록이 된다.
