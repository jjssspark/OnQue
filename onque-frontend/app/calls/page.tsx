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
