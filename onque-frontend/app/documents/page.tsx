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
