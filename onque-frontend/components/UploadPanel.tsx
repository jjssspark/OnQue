'use client';

import { useEffect, useId, useState } from 'react';
import { useWorkspace } from '@/components/WorkspaceContext';
import { SummaryReport } from '@/components/SummaryReport';
import { AnalyzingOverlay } from '@/components/AnalyzingOverlay';
import { BudgetNotice } from '@/components/ui/BudgetNotice';
import { budgetExhaustedText, isBudgetExhausted, isBudgetExhaustedError } from '@/lib/ai-budget';
import { summarizeCall, summarizeDocument, type SummaryResponse } from '@/lib/api';

type UploadKind = 'call' | 'document';

const SUMMARIZE_FN: Record<
  UploadKind,
  (groupId: number, file: File, autoTodo: boolean) => Promise<SummaryResponse>
> = {
  call: summarizeCall,
  document: summarizeDocument,
};

const STAGES = ['파일 업로드', 'AI 분석', '리포트 정리'] as const;

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
  const { currentGroupId, refresh, aiBudget } = useWorkspace();
  const budgetNoticeId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [autoTodo, setAutoTodo] = useState(false);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [stage, setStage] = useState(0);
  const [errorMsg, setErrorMsg] = useState('');

  // 서버가 진행률을 주지 않으므로 경과 시간으로 단계를 넘긴다. 정확한 진행률이
  // 아니라, 응답이 수십 초 걸리는 동안 화면이 멈춘 것처럼 보이지 않게 하는 장치다.
  useEffect(() => {
    if (!loading) {
      setStage(0);
      return;
    }
    const toAnalyzing = setTimeout(() => setStage(1), 1200);
    const toComposing = setTimeout(() => setStage(2), 6000);
    return () => {
      clearTimeout(toAnalyzing);
      clearTimeout(toComposing);
    };
  }, [loading]);

  const acceptedExtensions = accept.split(',').map((ext) => ext.trim().toLowerCase());
  const budgetExhausted = isBudgetExhausted(aiBudget);
  // 소진·미선택은 disabled로 잠그지 않는다. 비활성 버튼은 포커스를 받지 못해
  // 왜 못 쓰는지 설명한 안내(aria-describedby)에 키보드·스크린리더로 닿을 길이
  // 사라진다. 상태는 aria-disabled로 알리고, 눌리면 handleUpload가 이유를 말한다.
  const uploadBlocked = loading || !file || budgetExhausted;

  const selectFile = (next: File) => {
    const dot = next.name.lastIndexOf('.');
    const extension = dot >= 0 ? next.name.slice(dot).toLowerCase() : '';
    if (!acceptedExtensions.includes(extension)) {
      setErrorMsg(acceptHint);
      return;
    }
    setFile(next);
    setSummary(null);
    setErrorMsg('');
  };

  const handleUpload = async () => {
    if (budgetExhausted) {
      setErrorMsg(budgetExhaustedText(aiBudget));
      return;
    }
    if (!file) {
      setErrorMsg(emptySelectionMessage);
      return;
    }
    if (currentGroupId === null) return;

    setLoading(true);
    setSummary(null);
    setErrorMsg('');

    try {
      const data = await SUMMARIZE_FN[historyType](currentGroupId, file, autoTodo);
      setSummary(data);
      if (data.created_todos.length > 0) await refresh();
    } catch (err: unknown) {
      if (isBudgetExhaustedError(err)) {
        // 화면의 잔량은 마지막 조회 시점의 것이라 사전 차단이 새는 경우가 있다.
        // 서버가 거절한 지금이 진짜 소진 시점이므로 값을 다시 받아 버튼을 잠근다.
        setErrorMsg(budgetExhaustedText(aiBudget));
        refresh();
      } else {
        setErrorMsg(err instanceof Error ? err.message : '요약 처리 중 오류가 발생했습니다.');
      }
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
      <div className="relative overflow-hidden rounded-2xl border border-border bg-surface p-5 shadow-sm sm:p-6">
        <div
          className={`pointer-events-none absolute -top-24 left-1/2 h-64 w-64 -translate-x-1/2 rounded-full bg-brand/20 blur-[100px] transition-opacity duration-500 ${
            isDragging || loading ? 'opacity-100' : 'opacity-0'
          }`}
          aria-hidden
        />

        <label
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            const dropped = e.dataTransfer.files?.[0];
            if (dropped) selectFile(dropped);
          }}
          className={`relative flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-all ${
            isDragging
              ? 'scale-[1.01] border-brand bg-brand/[0.06]'
              : 'border-border hover:border-brand/50 hover:bg-foreground/[0.02]'
          }`}
        >
          <input
            type="file"
            accept={accept}
            onChange={(e) => {
              const picked = e.target.files?.[0];
              if (picked) selectFile(picked);
            }}
            className="sr-only"
          />
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            className={`h-8 w-8 transition-colors ${isDragging ? 'text-brand' : 'text-foreground/25'}`}
            aria-hidden
          >
            <path d="M12 16V4m0 0L8 8m4-4 4 4" />
            <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
          </svg>
          <p className="text-sm font-semibold text-foreground">
            파일을 끌어다 놓거나 <span className="text-brand">클릭해서 선택</span>
          </p>
          <p className="font-mono text-[11px] text-foreground/40">{acceptHint}</p>
        </label>

        {file && (
          <div className="mt-4 flex items-center justify-between gap-3 rounded-lg border border-border bg-background px-3 py-2">
            <span className="truncate text-xs text-foreground/70">{file.name}</span>
            <button
              type="button"
              onClick={() => {
                setFile(null);
                setSummary(null);
              }}
              className="shrink-0 text-[11px] text-foreground/30 transition-colors hover:text-red-500"
            >
              제거
            </button>
          </div>
        )}

        <label className="mt-4 flex items-center justify-between gap-3 rounded-lg border border-border bg-background px-3 py-2.5">
          <span className="min-w-0">
            <span className="block text-xs font-semibold text-foreground">
              액션 아이템 자동 등록
            </span>
            <span className="block text-[11px] text-foreground/40">
              요약에서 찾은 할 일을 바로 목록에 넣습니다
            </span>
          </span>
          <input
            type="checkbox"
            checked={autoTodo}
            onChange={(e) => setAutoTodo(e.target.checked)}
            className="peer sr-only"
          />
          <span
            className="relative h-5 w-9 shrink-0 rounded-full bg-foreground/15 transition-colors after:absolute after:left-0.5 after:top-0.5 after:h-4 after:w-4 after:rounded-full after:bg-white after:transition-transform peer-checked:bg-brand peer-checked:after:translate-x-4 peer-focus-visible:ring-2 peer-focus-visible:ring-brand/50"
            aria-hidden
          />
        </label>

        {/* 잔량이 있으면 BudgetNotice가 null이라 이 칸은 비어 있다.
            empty:hidden이 없으면 안 보이는 여백만 남는다. */}
        <div className="mt-4 empty:hidden">
          <BudgetNotice id={budgetNoticeId} />
        </div>

        <button
          type="button"
          onClick={handleUpload}
          disabled={loading}
          aria-disabled={!file || budgetExhausted}
          aria-describedby={budgetExhausted ? budgetNoticeId : undefined}
          className={`mt-4 w-full rounded-xl py-3 text-sm font-semibold text-brand-foreground transition-all ${
            uploadBlocked
              ? 'cursor-not-allowed bg-foreground/15'
              : 'bg-brand hover:-translate-y-px hover:brightness-110'
          }`}
        >
          {loading ? loadingLabel : submitLabel}
        </button>

        {errorMsg && (
          <p role="alert" className="mt-3 text-sm text-red-500">
            {errorMsg}
          </p>
        )}

        {loading && file && (
          <AnalyzingOverlay
            filename={file.name}
            stage={stage}
            stages={STAGES}
            hint={loadingHint}
          />
        )}
      </div>

      {summary && (
        <div className="rounded-2xl border border-border bg-surface p-6 shadow-sm sm:p-7">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
            <div className="min-w-0">
              <p className="font-mono text-[11px] uppercase tracking-widest text-brand">
                Summary Report
              </p>
              <p className="mt-1 truncate text-sm font-semibold text-foreground">
                {summary.filename}
              </p>
            </div>
            <span className="shrink-0 rounded-full bg-brand/10 px-2.5 py-1 text-[11px] font-semibold text-brand">
              {summary.category}
            </span>
          </div>

          {summary.created_todos.length > 0 && (
            <p className="mt-4 rounded-lg border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
              액션 아이템 {summary.created_todos.length}건을 할 일 목록에 등록했습니다.
            </p>
          )}

          <div className="mt-6">
            <SummaryReport
              key={summary.id}
              structured={summary.structured}
              plainText={summary.summary}
              registeredContents={summary.created_todos.map((t) => t.content)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
