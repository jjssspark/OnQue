'use client';

import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/components/AuthContext';
import { SkeletonList } from '@/components/ui/Skeleton';
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
    return (
      <div className="border-b border-rule bg-paper px-5 py-4">
        <SkeletonList rows={3} rowClassName="h-8" label="멤버 불러오는 중" />
      </div>
    );
  }

  return (
    <div className="max-h-64 overflow-y-auto border-b border-rule bg-paper px-5 py-4 [animation:summary-in_0.25s_ease-out]">
      {errorMsg && (
        <p role="alert" className="mb-3 text-xs text-late">
          {errorMsg}
        </p>
      )}

      <p className="font-mono text-[10px] uppercase tracking-widest text-ink-2">
        참여 중 {members.length}
      </p>
      <ul className="mt-2 space-y-1">
        {members.map((m) => {
          const isMe = m.id === user?.id;
          const canRemove = isMe || amOwner;
          return (
            <li key={m.id} className="flex items-center gap-2.5 rounded-lg px-1 py-1.5">
              <span
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-blue-wash text-[11px] font-bold text-blue ring-1 ring-blue/20"
                aria-hidden
              >
                {m.name.slice(0, 1)}
              </span>
              <span className="min-w-0 flex-1 truncate text-xs text-ink-2">
                {m.name}
                {isMe && <span className="ml-1 text-ink-2">(나)</span>}
                {m.is_owner && (
                  <span className="ml-1.5 rounded bg-rule px-1 py-0.5 font-mono text-[9px] text-ink-2">
                    방장
                  </span>
                )}
              </span>
              {canRemove && (
                <button
                  type="button"
                  onClick={() => handleRemove(m)}
                  disabled={busyId === m.id}
                  className="shrink-0 rounded px-1.5 py-0.5 text-[11px] text-ink-2 transition-colors hover:bg-late-wash hover:text-late disabled:opacity-40"
                >
                  {isMe ? '나가기' : '내보내기'}
                </button>
              )}
            </li>
          );
        })}
      </ul>

      <p className="mt-4 font-mono text-[10px] uppercase tracking-widest text-ink-2">
        초대 가능
      </p>
      {invitable.length === 0 ? (
        <p className="mt-2 text-[11px] leading-relaxed text-ink-2">
          이 그룹 사람은 모두 방에 있습니다. 다른 팀 사람이 필요하면 그룹 관리에서 먼저 그룹에
          초대하세요.
        </p>
      ) : (
        <ul className="mt-2 space-y-1">
          {invitable.map((g) => (
            <li key={g.id} className="flex items-center gap-2.5 rounded-lg px-1 py-1.5">
              <span
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-rule text-[11px] font-bold text-ink-2"
                aria-hidden
              >
                {g.name.slice(0, 1)}
              </span>
              <span className="min-w-0 flex-1 truncate text-xs text-ink-2">{g.name}</span>
              <button
                type="button"
                onClick={() => handleInvite(g)}
                disabled={busyId === g.id}
                className="shrink-0 rounded-lg bg-blue-wash px-2 py-1 text-[11px] font-semibold text-blue ring-1 ring-blue/25 transition-colors hover:bg-blue hover:text-card-2 disabled:opacity-40"
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
