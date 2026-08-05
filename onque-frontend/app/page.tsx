import Link from 'next/link';

const FEATURES = [
  {
    title: '통화 요약',
    description: '녹음 파일을 업로드하면 Gemini AI가 핵심 내용과 액션 아이템을 콜 리포트로 정리합니다.',
  },
  {
    title: '문서·회의록 요약',
    description: 'PDF, 텍스트 문서를 업로드하면 핵심만 추려 팀이 바로 확인할 수 있는 형태로 정리합니다.',
  },
  {
    title: '팀 채팅',
    description: '@비서에게 말을 걸면 대화 내용에서 할 일과 일정을 자동으로 추출해 등록합니다.',
  },
  {
    title: '그룹별 워크스페이스',
    description: '부서·팀 단위로 그룹을 나누고, 전사 공지와 문서 템플릿은 모든 그룹이 함께 씁니다.',
  },
];

export default function LandingPage() {
  return (
    <div className="relative min-h-screen overflow-hidden bg-sidebar text-sidebar-foreground">
      <div
        className="pointer-events-none absolute left-1/2 top-[-120px] h-[520px] w-[520px] -translate-x-1/2 rounded-full bg-brand/20 blur-[140px]"
        aria-hidden
      />

      <header className="relative flex items-center justify-between px-6 py-6 sm:px-10">
        <p className="text-lg font-bold text-white">
          On<span className="text-brand">Que</span>
        </p>
        <nav className="flex items-center gap-3">
          <Link href="/login" className="text-sm font-semibold text-sidebar-foreground/70 hover:text-white">
            로그인
          </Link>
          <Link
            href="/signup"
            className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-brand-foreground transition hover:brightness-110"
          >
            시작하기
          </Link>
        </nav>
      </header>

      <section className="relative px-6 pb-20 pt-16 sm:px-10 sm:pt-24">
        <div className="mx-auto max-w-3xl">
          <p className="font-mono text-xs uppercase tracking-widest text-brand">Workspace for agencies</p>
          <h1 className="mt-3 text-3xl font-bold leading-tight text-white sm:text-5xl">
            반복되는 업무 문서 정리,
            <br />
            팀 대신 AI가 처리합니다
          </h1>
          <p className="mt-5 max-w-xl text-sm leading-relaxed text-sidebar-foreground/70 sm:text-base">
            통화 녹음, 회의록, 팀 채팅 속 할 일과 일정을 Gemini AI가 자동으로 정리해주는
            회사 업무 워크스페이스입니다. 반복 업무가 많은 대행업체 팀을 위해 만들었습니다.
          </p>

          <div className="mt-6 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 font-mono text-xs text-sidebar-foreground/60">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" aria-hidden />
            Gemini AI 상시 대기 중
          </div>

          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href="/signup"
              className="rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-brand-foreground transition hover:brightness-110"
            >
              무료로 시작하기
            </Link>
            <Link
              href="/login"
              className="rounded-lg border border-white/15 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-white/5"
            >
              로그인
            </Link>
          </div>
        </div>
      </section>

      <section className="relative mx-auto max-w-4xl px-6 pb-24 sm:px-10">
        <p className="font-mono text-xs uppercase tracking-widest text-brand">Features</p>
        <h2 className="mt-2 text-xl font-bold text-white">네 가지 업무를 한 곳에서</h2>

        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          {FEATURES.map((f, i) => (
            <div key={f.title} className="rounded-xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-sm">
              <span className="font-mono text-xs text-sidebar-foreground/30">
                {String(i + 1).padStart(2, '0')}
              </span>
              <h3 className="mt-3 text-sm font-bold text-white">{f.title}</h3>
              <p className="mt-1.5 text-xs leading-relaxed text-sidebar-foreground/50">{f.description}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="relative border-t border-white/10 px-6 py-8 text-center sm:px-10">
        <p className="font-mono text-[11px] text-sidebar-foreground/30">© 2026 OnQue</p>
      </footer>
    </div>
  );
}
