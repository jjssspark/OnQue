import { UploadPanel } from '@/components/UploadPanel';

export default function DocumentsPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-brand">Document Summary</p>
      <h1 className="mt-1 text-2xl font-bold text-foreground">📄 문서·회의록 요약</h1>
      <p className="mt-2 text-sm text-foreground/60">
        회의록, 보고서 등 텍스트 문서를 업로드하면 Gemini AI가 핵심만 정리해드립니다.
      </p>

      <div className="mt-6">
        <UploadPanel
          accept=".pdf,.txt,.md"
          acceptHint="지원 형식: pdf, txt, md"
          historyType="document"
          submitLabel="요약 시작하기 ✨"
          loadingLabel="AI 분석 중입니다..."
          loadingHint="⏳ 문서 분량에 따라 약 10~30초 정도 소요됩니다."
          emptySelectionMessage="문서 파일을 먼저 선택해주세요!"
        />
      </div>
    </div>
  );
}
