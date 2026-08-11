'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { sendAssistantMessage, type AssistantAction, type AssistantTurn } from '@/lib/api';
import { useWorkspace } from '@/components/WorkspaceContext';
import { AssistantActionCard, applySafeAction } from '@/components/AssistantActionCard';

type Message = {
  role: 'user' | 'assistant';
  content: string;
  actions: AssistantAction[];
  /** safe 액션을 응답 직후 실행하며 만들어진 id. 취소할 때 쓴다. */
  createdIds: Record<string, number | null>;
  /** 응답 직후 실행이 실패한 safe 액션 id 목록. 카드 초기 상태를 'failed'로 준다. */
  failedIds: string[];
};

export function AssistantPanel() {
  const { currentGroupId, refresh } = useWorkspace();
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

    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text, actions: [], createdIds: {}, failedIds: [] },
    ]);
    setDraft('');
    setPending(true);
    setError(null);

    try {
      const reply = await sendAssistantMessage(groupId, text, history);
      if (groupSeqRef.current !== seq) return; // 그룹이 바뀐 뒤 도착한 응답은 버린다

      // safe 액션은 물어보지 않고 바로 실행한다. 되돌릴 수 있는 것만 여기 온다.
      const createdIds: Record<string, number | null> = {};
      const failedIds: string[] = [];
      for (const action of reply.actions) {
        if (action.risk !== 'safe') continue;
        try {
          createdIds[action.id] = await applySafeAction(action, groupId);
        } catch {
          // 실패해도 대화는 이어간다. 카드가 '다시 시도'를 보여준다.
          failedIds.push(action.id);
        }
      }
      // 실행 루프 동안 그룹이 바뀌었으면 이 응답을 새 그룹 대화에 반영하지 않는다.
      if (groupSeqRef.current !== seq) return;
      if (reply.actions.some((a) => a.risk === 'safe')) refresh();

      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: reply.reply, actions: reply.actions, createdIds, failedIds },
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
  }, [draft, pending, currentGroupId, messages, refresh]);

  if (currentGroupId === null) return null;

  return (
    <section className="flex min-h-0 flex-1 flex-col border-t border-border">
      {/* 답변은 사용자 조작 없이 비동기로 도착한다. 알리지 않으면 스크린리더
          사용자는 비서가 답했다는 사실 자체를 모른다. polite로 두어 타이핑
          중이면 끊지 않고 기다렸다 읽게 한다. */}
      <div
        aria-live="polite"
        className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4"
      >
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

            {m.actions.length > 0 && (
              <div className="mt-2 space-y-2 text-left">
                {m.actions.map((a) => (
                  <AssistantActionCard
                    key={a.id}
                    action={a}
                    groupId={currentGroupId}
                    createdId={m.createdIds[a.id] ?? null}
                    failed={m.failedIds.includes(a.id)}
                    onChanged={refresh}
                  />
                ))}
              </div>
            )}
          </div>
        ))}

        {pending && (
          <p role="status" className="text-xs text-foreground/40">
            비서가 확인하는 중입니다…
          </p>
        )}

        <div ref={endRef} />
      </div>

      {/* aria-live="polite" 컨테이너 밖에 둔다. 안에 있으면 가장 가까운 라이브
          리전이 polite라 role="alert"의 assertive가 무효가 되고, 목록에 노드가
          추가된 것으로도 잡혀 두 번 낭독될 수 있다. 실패는 대기열에 밀리면
          안 되는 소식이라 밖으로 뺐다. */}
      {error && (
        <p role="alert" className="px-5 py-2 text-xs leading-relaxed text-red-300">
          {error}
        </p>
      )}

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
