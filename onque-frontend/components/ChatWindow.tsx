'use client';

import { useEffect, useRef, useState } from 'react';
import { useAuth } from '@/components/AuthContext';
import { useWorkspace } from '@/components/WorkspaceContext';
import {
  getChatMessages,
  sendChatMessage,
  type ChatMessageRecord,
  type ChatRoomRecord,
} from '@/lib/api';

type ChatWindowProps = {
  room: ChatRoomRecord;
  onClose: () => void;
  /** 목록의 마지막 메시지 미리보기를 갱신하기 위해 부모에 알린다. */
  onMessageSent: (roomId: number, message: ChatMessageRecord) => void;
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
}

export function ChatWindow({ room, onClose, onMessageSent }: ChatWindowProps) {
  const { user } = useAuth();
  const { applySnapshot } = useWorkspace();
  const senderName = user?.name ?? '나';

  const [messages, setMessages] = useState<ChatMessageRecord[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    getChatMessages(room.id)
      .then((next) => {
        if (!cancelled) setMessages(next);
      })
      .catch(() => {
        if (!cancelled) setErrorMsg('대화 이력을 불러오지 못했습니다.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [room.id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    inputRef.current?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const handleSend = async () => {
    const content = input.trim();
    if (!content || sending) return;

    setSending(true);
    setErrorMsg('');
    setInput('');

    try {
      const result = await sendChatMessage(room.id, senderName, content);
      setMessages((prev) => [
        ...prev,
        result.message,
        ...(result.bot_message ? [result.bot_message] : []),
      ]);
      applySnapshot(result.todos, result.schedules);
      onMessageSent(room.id, result.bot_message ?? result.message);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : '메시지 전송에 실패했습니다.');
      // 실패한 입력을 되돌려줘야 사용자가 다시 타이핑하지 않는다.
      setInput(content);
    } finally {
      setSending(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-0 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="chat-window-title"
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="채팅창 닫기"
        className="absolute inset-0 bg-black/70 backdrop-blur-sm [animation:fade-in_0.2s_ease-out]"
      />

      <div className="relative flex h-full w-full flex-col overflow-hidden border border-white/10 bg-surface shadow-2xl [animation:chat-pop_0.28s_cubic-bezier(0.16,1,0.3,1)] sm:h-[min(85vh,720px)] sm:max-w-lg sm:rounded-2xl">
        <div
          className="pointer-events-none absolute -top-24 left-1/2 h-56 w-56 -translate-x-1/2 rounded-full bg-brand/25 blur-[90px]"
          aria-hidden
        />

        <header className="relative flex items-center justify-between gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <h2 id="chat-window-title" className="truncate text-sm font-bold text-foreground">
              {room.name}
            </h2>
            <p className="mt-0.5 flex items-center gap-1.5 font-mono text-[11px] text-foreground/40">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" aria-hidden />
              비서 대기 중
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-lg p-2 text-foreground/40 transition-colors hover:bg-foreground/5 hover:text-foreground"
            aria-label="닫기"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.8}
              strokeLinecap="round"
              className="h-4 w-4"
              aria-hidden
            >
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </header>

        <div className="relative flex-1 space-y-3 overflow-y-auto px-5 py-5">
          {loading && <p className="text-sm text-foreground/40">불러오는 중...</p>}

          {!loading && messages.length === 0 && (
            <div className="rounded-xl border border-dashed border-border px-5 py-8 text-center">
              <p className="text-sm text-foreground/50">아직 대화가 없습니다.</p>
              <p className="mt-2 text-xs leading-relaxed text-foreground/35">
                &quot;@비서 내일까지 견적서 제출해야 하는데 일정 잡아줘&quot; 처럼 말을 걸면
                <br />할 일과 일정이 자동으로 정리됩니다.
              </p>
            </div>
          )}

          {messages.map((m) => {
            const isMine = !m.is_bot && m.sender === senderName;
            return (
              <div
                key={m.id}
                className={`flex [animation:bubble-in_0.3s_ease-out_backwards] ${
                  isMine ? 'justify-end' : 'justify-start'
                }`}
              >
                <div className={`max-w-[80%] ${isMine ? 'text-right' : ''}`}>
                  <p className="mb-1 text-[11px] text-foreground/35">
                    {m.is_bot ? '비서' : m.sender} · {formatTime(m.created_at)}
                  </p>
                  <div
                    className={`inline-block whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-left text-sm leading-relaxed ${
                      m.is_bot
                        ? 'border border-brand/30 bg-brand/[0.08] text-foreground/90'
                        : isMine
                          ? 'bg-brand font-medium text-brand-foreground'
                          : 'border border-border bg-background text-foreground/90'
                    }`}
                  >
                    {m.content}
                  </div>
                </div>
              </div>
            );
          })}

          <div ref={bottomRef} />
        </div>

        {errorMsg && (
          <p role="alert" className="px-5 pb-2 text-xs text-red-300">
            {errorMsg}
          </p>
        )}

        <div className="relative border-t border-border p-3">
          <div className="flex items-end gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="메시지를 입력하세요. @비서 를 붙이면 답합니다."
              disabled={sending}
              className="flex-1 rounded-xl border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-foreground/30 focus:border-brand focus:outline-none disabled:opacity-60"
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={sending || !input.trim()}
              className={`shrink-0 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all ${
                sending || !input.trim()
                  ? 'cursor-not-allowed bg-foreground/10 text-foreground/30'
                  : 'bg-brand text-brand-foreground hover:-translate-y-px hover:brightness-110'
              }`}
            >
              {sending ? '전송 중' : '전송'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
