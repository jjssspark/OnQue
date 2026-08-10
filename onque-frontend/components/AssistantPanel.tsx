'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { sendAssistantMessage, type AssistantAction, type AssistantTurn } from '@/lib/api';
import { useWorkspace } from '@/components/WorkspaceContext';

type Message = {
  role: 'user' | 'assistant';
  content: string;
  actions: AssistantAction[];
};

export function AssistantPanel() {
  const { currentGroupId } = useWorkspace();
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  // WorkspaceContext.tsx의 requestSeqRef와 같은 이유. 그룹을 바꾼 뒤 이전
  // 그룹으로 보낸 요청의 응답이 뒤늦게 도착해 새 그룹 대화를 덮지 못하게 막는다.
  const groupSeqRef = useRef(0);

  // 그룹을 바꾸면 이전 그룹 대화를 이어가지 않는다. 맥락이 섞이면 비서가
  // 지금 그룹에 없는 데이터를 참조한다.
  useEffect(() => {
    groupSeqRef.current += 1;
    setMessages([]);
    setError(null);
    setPending(false);
  }, [currentGroupId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
  }, [messages, pending]);

  const send = useCallback(async () => {
    const text = draft.trim();
    if (!text || pending || currentGroupId === null) return;

    const groupId = currentGroupId;
    const seq = groupSeqRef.current;

    const history: AssistantTurn[] = messages.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    setMessages((prev) => [...prev, { role: 'user', content: text, actions: [] }]);
    setDraft('');
    setPending(true);
    setError(null);

    try {
      const reply = await sendAssistantMessage(groupId, text, history);
      if (groupSeqRef.current !== seq) return; // 그룹이 바뀐 뒤 도착한 응답은 버린다
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: reply.reply, actions: reply.actions },
      ]);
    } catch (err) {
      if (groupSeqRef.current !== seq) return; // 그룹이 바뀐 뒤 도착한 실패도 새 그룹에 반영하지 않는다
      // 친 문장을 입력창에 되돌려 놓는다. 날리면 다시 타이핑해야 한다.
      setDraft(text);
      setMessages((prev) => prev.slice(0, -1));
      setError(err instanceof Error ? err.message : '비서가 응답하지 못했습니다.');
    } finally {
      if (groupSeqRef.current === seq) setPending(false);
    }
  }, [draft, pending, currentGroupId, messages]);

  if (currentGroupId === null) return null;

  return (
    <section className="flex min-h-0 flex-1 flex-col border-t border-border">
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4">
        {messages.length === 0 && !pending && (
          <p className="text-xs leading-relaxed text-foreground/40">
            약속·할 일·일정에 대해 물어보세요. 예: A사한테 뭐 약속했더라?
          </p>
        )}

        {messages.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'text-right' : ''}>
            <p
              className={`inline-block max-w-[92%] whitespace-pre-wrap rounded-lg px-3 py-2 text-xs leading-relaxed ${
                m.role === 'user'
                  ? 'bg-accent/[0.12] text-foreground'
                  : 'bg-foreground/[0.04] text-foreground/90'
              }`}
            >
              {m.content}
            </p>
          </div>
        ))}

        {pending && <p className="text-xs text-foreground/40">비서가 확인하는 중입니다…</p>}

        {error && (
          <p role="alert" className="text-xs leading-relaxed text-red-300">
            {error}
          </p>
        )}

        <div ref={endRef} />
      </div>

      <div className="border-t border-border px-4 py-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
          className="flex items-center gap-2"
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="무엇이든 물어보세요"
            aria-label="비서에게 물어보기"
            className="min-w-0 flex-1 rounded-lg border border-border bg-transparent px-3 py-2 text-xs text-foreground outline-none placeholder:text-foreground/30 focus:border-accent/50"
          />
          <button
            type="submit"
            disabled={pending || !draft.trim()}
            className="shrink-0 rounded-lg border border-accent/40 px-3 py-2 text-xs font-bold text-accent transition hover:bg-accent/[0.12] disabled:opacity-30"
          >
            보내기
          </button>
        </form>
      </div>
    </section>
  );
}
