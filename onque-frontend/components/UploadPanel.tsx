'use client';

import { useState } from 'react';
import { useWorkspace } from '@/components/WorkspaceContext';
import { summarizeCall, summarizeDocument, type SummaryResponse } from '@/lib/api';

type UploadKind = 'call' | 'document';

const SUMMARIZE_FN: Record<UploadKind, (groupId: number, file: File) => Promise<SummaryResponse>> = {
  call: summarizeCall,
  document: summarizeDocument,
};

type UploadPanelProps = {
  accept: string;
  acceptHint: string;
  historyType: UploadKind;
  submitLabel: string;
  loadingLabel: string;
  loadingHint: string;
  emptySelectionMessage: string;
};

export function UploadPanel({
  accept,
  acceptHint,
  historyType,
  submitLabel,
  loadingLabel,
  loadingHint,
  emptySelectionMessage,
}: UploadPanelProps) {
  const { currentGroupId } = useWorkspace();
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setSummary(null);
      setErrorMsg('');
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setErrorMsg(emptySelectionMessage);
      return;
    }
    if (currentGroupId === null) return;

    setLoading(true);
    setSummary(null);
    setErrorMsg('');

    try {
      const data = await SUMMARIZE_FN[historyType](currentGroupId, file);
      setSummary(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '요약 처리 중 오류가 발생했습니다.';
      setErrorMsg(message);
    } finally {
      setLoading(false);
    }
  };

  if (currentGroupId === null) {
    return (
      <p className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-foreground/40">
        아직 소속된 그룹이 없습니다. 관리자가 그룹에 초대하면 이용할 수 있습니다.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border bg-surface p-5 shadow-sm">
        <label className="text-sm font-semibold text-foreground">파일 선택</label>
        <p className="mt-1 text-xs text-foreground/50">{acceptHint}</p>

        <input
          type="file"
          accept={accept}
          onChange={handleFileChange}
          className="mt-3 w-full rounded-lg border border-border bg-background p-2 text-sm cursor-pointer"
        />

        {file && (
          <p className="mt-2 w-fit rounded-md border border-border bg-background px-3 py-1 text-xs text-foreground/60">
            {file.name}
          </p>
        )}

        <button
          onClick={handleUpload}
          disabled={loading || !file}
          className={`mt-4 w-full rounded-lg py-2.5 text-sm font-semibold text-brand-foreground transition ${
            loading || !file
              ? 'cursor-not-allowed bg-foreground/20'
              : 'bg-brand hover:brightness-110'
          }`}
        >
          {loading ? loadingLabel : submitLabel}
        </button>

        {loading && (
          <p className="mt-3 text-center text-xs text-foreground/40">{loadingHint}</p>
        )}

        {errorMsg && <p className="mt-3 text-sm text-red-500">{errorMsg}</p>}
      </div>

      {summary && (
        <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-bold text-foreground">요약 리포트</h2>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-brand/10 px-2 py-0.5 text-[11px] font-semibold text-brand">
                {summary.category}
              </span>
              <span className="font-mono text-xs text-foreground/40">{summary.filename}</span>
            </div>
          </div>
          <hr className="my-4 border-border" />
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-foreground/90">
            {summary.summary}
          </pre>
        </div>
      )}
    </div>
  );
}
