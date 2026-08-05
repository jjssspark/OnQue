'use client';

import { useCallback, useEffect, useState } from 'react';
import { ChatWindow } from '@/components/ChatWindow';
import { useWorkspace } from '@/components/WorkspaceContext';
import {
  createChatRoom,
  deleteChatRoom,
  listChatRooms,
  type ChatMessageRecord,
  type ChatRoomRecord,
} from '@/lib/api';

function formatRelative(iso: string): string {
  const then = new Date(iso);
  const diffMinutes = Math.floor((Date.now() - then.getTime()) / 60000);
  if (diffMinutes < 1) return '방금';
  if (diffMinutes < 60) return `${diffMinutes}분 전`;
  if (diffMinutes < 60 * 24) return `${Math.floor(diffMinutes / 60)}시간 전`;
  return then.toLocaleDateString('ko-KR', { month: 'numeric', day: 'numeric' });
}

/** 방 이름에서 만든 이니셜. 목록에서 방을 눈으로 빨리 구분하게 해준다. */
function initial(name: string): string {
  return name.trim().slice(0, 1) || '#';
}

export default function ChatPage() {
  const { currentGroupId } = useWorkspace();
  const [rooms, setRooms] = useState<ChatRoomRecord[]>([]);
  const [openRoom, setOpenRoom] = useState<ChatRoomRecord | null>(null);
  const [newRoomName, setNewRoomName] = useState('');
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');

  const load = useCallback(async (groupId: number) => {
    try {
      setRooms(await listChatRooms(groupId));
      setErrorMsg('');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '채팅방을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (currentGroupId === null) {
      setRooms([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    load(currentGroupId);
  }, [currentGroupId, load]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = newRoomName.trim();
    if (!name || creating || currentGroupId === null) return;

    setCreating(true);
    setErrorMsg('');
    try {
      const room = await createChatRoom(currentGroupId, name);
      setRooms((prev) => [...prev, room]);
      setNewRoomName('');
      setOpenRoom(room);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '채팅방 생성에 실패했습니다.');
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (room: ChatRoomRecord) => {
    setErrorMsg('');
    try {
      await deleteChatRoom(room.id);
      setRooms((prev) => prev.filter((r) => r.id !== room.id));
      if (openRoom?.id === room.id) setOpenRoom(null);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '채팅방 삭제에 실패했습니다.');
    }
  };

  const handleMessageSent = useCallback(
    (roomId: number, message: ChatMessageRecord, aiMode: boolean) => {
      setRooms((prev) =>
        prev.map((r) => (r.id === roomId ? { ...r, last_message: message, ai_mode: aiMode } : r)),
      );
    },
    [],
  );

  if (currentGroupId === null) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-10 text-sm text-foreground/60">
        아직 소속된 그룹이 없습니다. 관리자가 그룹에 초대하면 이용할 수 있습니다.
      </div>
    );
  }

  return (
    <div className="relative mx-auto max-w-3xl px-6 py-10">
      <div
        className="pointer-events-none absolute -top-20 left-1/3 h-72 w-72 rounded-full bg-brand/10 blur-[120px]"
        aria-hidden
      />

      <div className="relative">
        <p className="font-mono text-xs uppercase tracking-widest text-brand">Team Chat</p>
        <h1 className="mt-1 text-2xl font-bold text-foreground">팀 채팅</h1>
        <p className="mt-2 text-sm leading-relaxed text-foreground/55">
          주제별로 방을 나눠 팀원과 대화하세요. AI는 평소엔 끼어들지 않고,{' '}
          <span className="font-mono text-brand">/help</span> 로 부를 때만 들어와 요약·문서 작성·할
          일 등록을 대신합니다.
        </p>

        <form onSubmit={handleCreate} className="mt-6 flex gap-2">
          <input
            type="text"
            value={newRoomName}
            onChange={(e) => setNewRoomName(e.target.value)}
            placeholder="새 채팅방 이름 (예: 디자인 리뷰)"
            className="flex-1 rounded-xl border border-border bg-surface px-4 py-2.5 text-sm text-foreground placeholder:text-foreground/30 focus:border-brand focus:outline-none sm:max-w-xs"
          />
          <button
            type="submit"
            disabled={creating || !newRoomName.trim()}
            className={`shrink-0 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all ${
              creating || !newRoomName.trim()
                ? 'cursor-not-allowed bg-foreground/10 text-foreground/30'
                : 'bg-brand text-brand-foreground hover:-translate-y-px hover:brightness-110'
            }`}
          >
            방 만들기
          </button>
        </form>

        {errorMsg && (
          <p role="alert" className="mt-4 text-sm text-red-300">
            {errorMsg}
          </p>
        )}

        <div className="mt-6 space-y-2">
          {loading && <p className="text-sm text-foreground/40">불러오는 중...</p>}

          {!loading && rooms.length === 0 && (
            <div className="rounded-2xl border border-dashed border-border p-10 text-center">
              <p className="text-sm text-foreground/50">아직 채팅방이 없습니다.</p>
              <p className="mt-1.5 text-xs text-foreground/35">
                위에서 첫 방을 만들어 대화를 시작하세요.
              </p>
            </div>
          )}

          {rooms.map((room, i) => (
            <div
              key={room.id}
              className="group relative flex items-center gap-3 overflow-hidden rounded-2xl border border-border bg-surface transition-all hover:-translate-y-0.5 hover:border-brand/40 [animation:summary-in_0.4s_ease-out_backwards]"
              style={{ animationDelay: `${i * 50}ms` }}
            >
              <button
                type="button"
                onClick={() => setOpenRoom(room)}
                className="flex min-w-0 flex-1 items-center gap-3.5 px-4 py-3.5 text-left"
              >
                <span
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand/[0.12] text-base font-bold text-brand ring-1 ring-brand/20 transition-transform group-hover:scale-105"
                  aria-hidden
                >
                  {initial(room.name)}
                </span>

                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline justify-between gap-2">
                    <span className="flex min-w-0 items-center gap-1.5">
                      <span className="truncate text-sm font-semibold text-foreground">
                        {room.name}
                      </span>
                      {room.ai_mode && (
                        <span className="shrink-0 rounded-full bg-brand/15 px-1.5 py-0.5 font-mono text-[10px] font-bold text-brand ring-1 ring-brand/25">
                          AI
                        </span>
                      )}
                    </span>
                    {room.last_message && (
                      <span className="shrink-0 font-mono text-[11px] text-foreground/30">
                        {formatRelative(room.last_message.created_at)}
                      </span>
                    )}
                  </span>
                  <span className="mt-0.5 block truncate text-xs text-foreground/45">
                    {room.last_message ? (
                      <>
                        {room.last_message.is_bot && (
                          <span className="mr-1 font-semibold text-brand">비서</span>
                        )}
                        {room.last_message.content.replace(/\n/g, ' ')}
                      </>
                    ) : (
                      <span className="text-foreground/25">대화를 시작해보세요</span>
                    )}
                  </span>
                </span>
              </button>

              <button
                type="button"
                onClick={() => handleDelete(room)}
                className="mr-3 shrink-0 rounded-lg px-2 py-1 text-[11px] text-foreground/25 opacity-0 transition-all hover:bg-red-500/10 hover:text-red-300 focus-visible:opacity-100 group-hover:opacity-100"
              >
                삭제
              </button>
            </div>
          ))}
        </div>
      </div>

      {openRoom && (
        <ChatWindow
          key={openRoom.id}
          room={openRoom}
          onClose={() => setOpenRoom(null)}
          onMessageSent={handleMessageSent}
        />
      )}
    </div>
  );
}
