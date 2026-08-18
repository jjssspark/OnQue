'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { useAuth } from '@/components/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileNav } from '@/components/MobileNav';
import { SmartDashboardPanel } from '@/components/SmartDashboardPanel';

const PUBLIC_PATHS = ['/', '/login', '/signup'];
// 스플래시 최소 노출 시간. 이 값이 곧 진입의 하한이다 — 인증이 즉시 끝나도
// (토큰이 없으면 네트워크 없이 판정된다) 이만큼은 무조건 기다린다.
// 2500ms는 로고를 보여주는 값으로 과해서, 인지는 되면서 깜빡임으로 보이지도
// 않는 800ms로 낮췄다.
const MIN_SPLASH_MS = 800;

function SplashScreen() {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-navy">
      <div
        className="pointer-events-none absolute left-1/2 top-1/2 h-[420px] w-[420px] rounded-full bg-blue/25 blur-[120px] [animation:splash-glow_2.4s_ease-in-out_infinite]"
        aria-hidden
      />
      <div className="relative flex flex-col items-center gap-5 [animation:splash-in_0.5s_ease-out]">
        <p className="text-3xl font-bold text-card-2">
          On<span className="text-blue">Que</span>
        </p>
        <div className="flex gap-1.5">
          <span className="h-2 w-2 animate-bounce rounded-full bg-blue [animation-delay:-0.3s]" />
          <span className="h-2 w-2 animate-bounce rounded-full bg-blue [animation-delay:-0.15s]" />
          <span className="h-2 w-2 animate-bounce rounded-full bg-blue" />
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
  const [minTimeElapsed, setMinTimeElapsed] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setMinTimeElapsed(true), MIN_SPLASH_MS);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!user && !isPublicPath) router.push('/login');
    if (user && isPublicPath) router.push('/dashboard');
  }, [loading, user, isPublicPath, router]);

  if (loading || !minTimeElapsed) return <SplashScreen />;
  if (!user && !isPublicPath) return <SplashScreen />;
  if (user && isPublicPath) return <SplashScreen />;

  if (isPublicPath) return <>{children}</>;

  // min-h-screen은 하한선이지 확정 높이가 아니다. 본문이 길면 이 컬럼이 그만큼
  // 자라고, 형제인 우측 패널도 같이 늘어나 비서 입력창이 뷰포트 밖으로 나간다
  // (TS-029). lg에서만 h-screen을 덧대 셸을 뷰포트 높이에 못박는다.
  //
  // lg 미만으로 내리지 않는 이유: 우측 패널이 lg:flex라 그 아래에서는 밀려날
  // 입력창이 애초에 없고, h-screen을 걸면 페이지 스크롤이 main 내부 스크롤로
  // 바뀐다. 모바일 브라우저의 100vh는 주소창을 포함해 실제 보이는 높이보다
  // 크므로, 페이지가 안 스크롤되면 바닥이 주소창에 가린 채 남는다.
  return (
    <div className="flex min-h-screen lg:h-screen">
      <Sidebar />
      <div className="flex min-h-screen min-w-0 flex-1 flex-col lg:h-screen">
        <MobileNav />
        {/* lg 이상에서 셸이 확정 높이를 갖는 순간 문서가 아니라 이 요소가
            스크롤 컨테이너가 된다. tabindex가 없으면 아무 데도 포커스하지 않은
            채 Space·PageDown을 눌러도 스크롤되지 않는다 — 키보드만 쓰는
            사용자가 본문을 못 읽는다(WCAG 2.1.1). */}
        <main tabIndex={0} className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
      <SmartDashboardPanel />
    </div>
  );
}
