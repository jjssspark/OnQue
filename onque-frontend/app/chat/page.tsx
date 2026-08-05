'use client';

import { useEffect, useRef, useState } from 'react';
import { useWorkspace } from '@/components/WorkspaceContext';
import { getChatMessages, sendChatMessage, type ChatMessageRecord } from '@/lib/api';

const SENDER_NAME = '나';

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
}

export default function ChatPage() {
  const { applySnapshot, currentGroupId } = useWorkspace();
  const [messages, setMessages] = useState<ChatMessageRecord[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (currentGroupId === null) return;
    getChatMessages(currentGroupId)
      .then(setMessages)
      .catch(() => setErrorMsg('대화 이력을 불러오지 못했습니다.'))
      .finally(() => setLoading(false));
  }, [currentGroupId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    const content = input.trim();
    if (!content || sending || currentGroupId === null) return;

    setSending(true);
    setErrorMsg('');
    setInput('');

    try {
      const result = await sendChatMessage(currentGroupId, SENDER_NAME, content);
      setMessages((prev) => [
        ...prev,
        result.message,
        ...(result.bot_message ? [result.bot_message] : []),
      ]);
      applySnapshot(result.todos, result.schedules);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '메시지 전송에 실패했습니다.';
      setErrorMsg(message);
    } finally {
      setSending(false);
    }
  };

  if (currentGroupId === null) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-10 text-sm text-foreground/60">
        아직 소속된 그룹이 없습니다. 관리자가 그룹에 초대하면 이용할 수 있습니다.
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-[calc(100vh-64px)] flex-col md:min-h-screen">
      <div className="border-b border-border px-6 py-5">
        <p className="font-mono text-xs uppercase tracking-widest text-brand">Team Chat</p>
        <h1 className="mt-1 text-2xl font-bold text-foreground">팀 채팅</h1>
        <p className="mt-2 text-sm text-foreground/60">
          메시지를 보내면 <span className="font-semibold text-brand">@비서</span>가 대화를 지켜보다가
          할 일·일정을 자동으로 정리합니다. <span className="font-mono">@비서</span>를 직접 불러 물어볼 수도 있어요.
        </p>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-6 py-6">
        {loading && <p className="text-sm text-foreground/40">불러오는 중...</p>}
        {!loading && messages.length === 0 && (
          <p className="text-sm text-foreground/40">
            아직 대화가 없습니다. &quot;@비서 내일까지 견적서 제출해야 하는데 일정 잡아줘&quot; 처럼 말을 걸어보세요.
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`flex ${m.is_bot ? 'justify-start' : 'justify-end'}`}>
            <div className={`max-w-[75%] ${m.is_bot ? '' : 'text-right'}`}>
              <p className="mb-1 text-[11px] text-foreground/40">
                {m.is_bot ? '비서' : m.sender} · {formatTime(m.created_at)}
              </p>
              <div
                className={`inline-block rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                  m.is_bot
                    ? 'bg-surface border border-border text-foreground/90'
                    : 'bg-brand text-brand-foreground'
                }`}
              >
                {m.content}
              </div>
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {errorMsg && <p className="px-6 pb-2 text-sm text-red-500">{errorMsg}</p>}

      <div className="border-t border-border p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="메시지를 입력하세요..."
            disabled={sending}
            className="flex-1 rounded-lg border border-border bg-surface px-4 py-2.5 text-sm"
          />
          <button
            onClick={handleSend}
            disabled={sending || !input.trim()}
            className={`rounded-lg px-5 py-2.5 text-sm font-semibold text-brand-foreground transition ${
              sending || !input.trim()
                ? 'cursor-not-allowed bg-foreground/20'
                : 'bg-brand hover:brightness-110'
            }`}
          >
            {sending ? '전송 중...' : '전송'}
          </button>
        </div>
      </div>
    </div>
  );
}
