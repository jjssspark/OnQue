import Link from 'next/link';
import { RecentActivity } from '@/components/RecentActivity';

const MODULES = [
  {
    href: '/calls',
    emoji: '📞',
    title: '통화 요약',
    description: '녹음 파일(mp3, m4a, wav)을 업로드하면 콜 리포트를 자동으로 생성합니다.',
  },
  {
    href: '/documents',
    emoji: '📄',
    title: '문서·회의록 요약',
    description: 'PDF, 텍스트 문서를 업로드하면 핵심 내용과 액션 아이템을 정리합니다.',
  },
  {
    href: '/history',
    emoji: '🔍',
    title: '이력 조회',
    description: '지금까지 처리한 요약 결과를 검색하고 다시 확인합니다.',
  },
];

export default function DashboardPage() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-brand">Dashboard</p>
      <h1 className="mt-1 text-2xl font-bold text-foreground">
        오늘도 수고 많으셨습니다 👋
      </h1>
      <p className="mt-2 text-sm text-foreground/60">
        OnQue는 Gemini AI로 반복적인 업무 문서를 대신 정리해주는 워크스페이스입니다.
        아래에서 필요한 업무를 바로 시작하세요.
      </p>

      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {MODULES.map((mod) => (
          <Link
            key={mod.href}
            href={mod.href}
            className="group rounded-xl border border-border bg-surface p-5 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
          >
            <span className="text-2xl">{mod.emoji}</span>
            <h2 className="mt-3 text-sm font-bold text-foreground group-hover:text-brand">
              {mod.title}
            </h2>
            <p className="mt-1.5 text-xs leading-relaxed text-foreground/50">
              {mod.description}
            </p>
          </Link>
        ))}
      </div>

      <div className="mt-10">
        <h2 className="mb-3 text-sm font-bold text-foreground">최근 활동</h2>
        <RecentActivity />
      </div>
    </div>
  );
}
