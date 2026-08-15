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
