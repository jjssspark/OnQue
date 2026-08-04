import { UploadPanel } from '@/components/UploadPanel';

export default function CallsPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-brand">Call Summary</p>
      <h1 className="mt-1 text-2xl font-bold text-foreground">📞 통화 요약</h1>
      <p className="mt-2 text-sm text-foreground/60">
        통화 녹음 파일을 업로드하면 Gemini AI가 핵심 내용을 자동으로 정리해드립니다.
      </p>

      <div className="mt-6">
        <UploadPanel
          accept=".mp3,.m4a,.wav"
          acceptHint="지원 형식: mp3, m4a, wav"
          historyType="call"
          submitLabel="요약 시작하기 ✨"
          loadingLabel="AI 분석 중입니다..."
          loadingHint="⏳ 통화 길이에 따라 약 10~30초 정도 소요됩니다."
          emptySelectionMessage="통화 녹음 파일을 먼저 선택해주세요!"
        />
      </div>
    </div>
  );
}
