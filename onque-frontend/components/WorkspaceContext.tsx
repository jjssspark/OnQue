'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import {
  deleteSchedule as apiDeleteSchedule,
  deleteTodo as apiDeleteTodo,
  updateTodo as apiUpdateTodo,
  getSchedules,
  getTodos,
  type ScheduleItem,
  type Todo,
} from '@/lib/api';
import { useAuth } from '@/components/AuthContext';

const CURRENT_GROUP_KEY = 'onque_current_group_id';

type WorkspaceContextValue = {
  todos: Todo[];
  schedules: ScheduleItem[];
  loading: boolean;
  /** 조회 실패 사유. 빈 목록과 실패를 화면에서 구분하기 위해 필요하다. */
  error: string | null;
  currentGroupId: number | null;
  setCurrentGroupId: (id: number) => void;
  refresh: () => Promise<void>;
  applySnapshot: (todos: Todo[], schedules: ScheduleItem[]) => void;
  toggleTodo: (id: number, isDone: boolean) => Promise<void>;
  removeTodo: (id: number) => Promise<void>;
  removeSchedule: (id: number) => Promise<void>;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const { groups } = useAuth();
  const [todos, setTodos] = useState<Todo[]>([]);
  const [schedules, setSchedules] = useState<ScheduleItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentGroupId, setCurrentGroupIdState] = useState<number | null>(null);

  useEffect(() => {
    if (groups.length === 0) {
      setCurrentGroupIdState(null);
      return;
    }
    const saved = typeof window !== 'undefined' ? window.localStorage.getItem(CURRENT_GROUP_KEY) : null;
    const savedId = saved ? Number(saved) : null;
    const stillMember = savedId !== null && groups.some((g) => g.id === savedId);
    setCurrentGroupIdState(stillMember ? savedId : groups[0].id);
  }, [groups]);

  const setCurrentGroupId = useCallback((id: number) => {
    window.localStorage.setItem(CURRENT_GROUP_KEY, String(id));
    setCurrentGroupIdState(id);
  }, []);

  const refresh = useCallback(async () => {
    if (currentGroupId === null) {
      setTodos([]);
      setSchedules([]);
      setError(null);
      setLoading(false);
      return;
    }
    try {
      const [nextTodos, nextSchedules] = await Promise.all([
        getTodos(currentGroupId),
        getSchedules(currentGroupId),
      ]);
      setTodos(nextTodos);
      setSchedules(nextSchedules);
      setError(null);
    } catch (err) {
      // 조용히 넘기면 "데이터 없음"과 구분되지 않아 서버 장애가 화면상 정상으로 보인다.
      setError(err instanceof Error ? err.message : '업무 데이터를 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [currentGroupId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const applySnapshot = useCallback((nextTodos: Todo[], nextSchedules: ScheduleItem[]) => {
    setTodos(nextTodos);
    setSchedules(nextSchedules);
  }, []);

  const toggleTodo = useCallback(async (id: number, isDone: boolean) => {
    const updated = await apiUpdateTodo(id, { is_done: isDone });
    setTodos((prev) => prev.map((t) => (t.id === id ? updated : t)));
  }, []);

  const removeTodo = useCallback(async (id: number) => {
    await apiDeleteTodo(id);
    setTodos((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const removeSchedule = useCallback(async (id: number) => {
    await apiDeleteSchedule(id);
    setSchedules((prev) => prev.filter((s) => s.id !== id));
  }, []);

  return (
    <WorkspaceContext.Provider
      value={{
        todos,
        schedules,
        loading,
        error,
        currentGroupId,
        setCurrentGroupId,
        refresh,
        applySnapshot,
        toggleTodo,
        removeTodo,
        removeSchedule,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error('useWorkspace는 WorkspaceProvider 내부에서만 사용할 수 있습니다.');
  return ctx;
}
