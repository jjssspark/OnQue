'use client';

import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/components/AuthContext';
import {
  inviteRoomMember,
  listGroupMembers,
  listRoomMembers,
  removeRoomMember,
  type ChatRoomMember,
  type ChatRoomRecord,
  type GroupMember,
} from '@/lib/api';

type RoomMembersProps = {
  room: ChatRoomRecord;
  /** 멤버 수가 바뀌면 방 목록의 배지를 맞춰야 한다. */
  onCountChange: (roomId: number, count: number) => void;
  /** 본인이 방을 나가 더 이상 볼 수 없게 됐을 때. */
  onLeft: (roomId: number) => void;
};

export function RoomMembers({ room, onCountChange, onLeft }: RoomMembersProps) {
  const { user } = useAuth();
  const [members, setMembers] = useState<ChatRoomMember[]>([]);
  const [groupMembers, setGroupMembers] = useState<GroupMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [errorMsg, setErrorMsg] = useState('');

  const load = useCallback(async () => {
    try {
      const [inRoom, inGroup] = await Promise.all([
        listRoomMembers(room.id),
        listGroupMembers(room.group_id),
      ]);
      setMembers(inRoom);
      setGroupMembers(inGroup);
      onCountChange(room.id, inRoom.length);
      setErrorMsg('');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '멤버를 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [room.id, room.group_id, onCountChange]);

  useEffect(() => {
    load();
  }, [load]);

  const amOwner = members.some((m) => m.id === user?.id && m.is_owner);
  const memberIds = new Set(members.map((m) => m.id));
  const invitable = groupMembers.filter((g) => !memberIds.has(g.id));

  const handleInvite = async (target: GroupMember) => {
    setBusyId(target.id);
    setErrorMsg('');
    try {
      const added = await inviteRoomMember(room.id, target.id);
      const next = [...members, added];
      setMembers(next);
      onCountChange(room.id, next.length);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '초대에 실패했습니다.');
    } finally {
      setBusyId(null);
    }
  };

  const handleRemove = async (target: ChatRoomMember) => {
    setBusyId(target.id);
    setErrorMsg('');
    try {
      await removeRoomMember(room.id, target.id);
      if (target.id === user?.id) {
        onLeft(room.id);
        return;
      }
      const next = members.filter((m) => m.id !== target.id);
      setMembers(next);
      onCountChange(room.id, next.length);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '처리에 실패했습니다.');
    } finally {
      setBusyId(null);
    }
  };

  if (loading) {
    return <p className="px-5 py-4 text-xs text-foreground/40">멤버를 불러오는 중...</p>;
  }

  return (
    <div className="max-h-64 overflow-y-auto border-b border-border bg-background/60 px-5 py-4 [animation:summary-in_0.25s_ease-out]">
      {errorMsg && (
        <p role="alert" className="mb-3 text-xs text-red-300">
          {errorMsg}
        </p>
      )}

      <p className="font-mono text-[10px] uppercase tracking-widest text-foreground/35">
        참여 중 {members.length}
      </p>
      <ul className="mt-2 space-y-1">
        {members.map((m) => {
          const isMe = m.id === user?.id;
          const canRemove = isMe || amOwner;
          return (
            <li key={m.id} className="flex items-center gap-2.5 rounded-lg px-1 py-1.5">
              <span
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand/[0.12] text-[11px] font-bold text-brand ring-1 ring-brand/20"
                aria-hidden
              >
                {m.name.slice(0, 1)}
              </span>
              <span className="min-w-0 flex-1 truncate text-xs text-foreground/80">
                {m.name}
                {isMe && <span className="ml-1 text-foreground/35">(나)</span>}
                {m.is_owner && (
                  <span className="ml-1.5 rounded bg-foreground/10 px-1 py-0.5 font-mono text-[9px] text-foreground/50">
                    방장
                  </span>
                )}
              </span>
              {canRemove && (
                <button
                  type="button"
                  onClick={() => handleRemove(m)}
                  disabled={busyId === m.id}
                  className="shrink-0 rounded px-1.5 py-0.5 text-[11px] text-foreground/30 transition-colors hover:bg-red-500/10 hover:text-red-300 disabled:opacity-40"
                >
                  {isMe ? '나가기' : '내보내기'}
                </button>
              )}
            </li>
          );
        })}
      </ul>

      <p className="mt-4 font-mono text-[10px] uppercase tracking-widest text-foreground/35">
        초대 가능
      </p>
      {invitable.length === 0 ? (
        <p className="mt-2 text-[11px] leading-relaxed text-foreground/35">
          이 그룹 사람은 모두 방에 있습니다. 다른 팀 사람이 필요하면 그룹 관리에서 먼저 그룹에
          초대하세요.
        </p>
      ) : (
        <ul className="mt-2 space-y-1">
          {invitable.map((g) => (
            <li key={g.id} className="flex items-center gap-2.5 rounded-lg px-1 py-1.5">
              <span
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-foreground/[0.06] text-[11px] font-bold text-foreground/40"
                aria-hidden
              >
                {g.name.slice(0, 1)}
              </span>
              <span className="min-w-0 flex-1 truncate text-xs text-foreground/55">{g.name}</span>
              <button
                type="button"
                onClick={() => handleInvite(g)}
                disabled={busyId === g.id}
                className="shrink-0 rounded-lg bg-brand/15 px-2 py-1 text-[11px] font-semibold text-brand ring-1 ring-brand/25 transition-colors hover:bg-brand/25 disabled:opacity-40"
              >
                {busyId === g.id ? '초대 중' : '초대'}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
