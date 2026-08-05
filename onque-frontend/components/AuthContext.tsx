'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  getMe,
  login as apiLogin,
  signup as apiSignup,
  type AuthUser,
  type GroupSummary,
} from '@/lib/api';
import { clearToken, getToken, setToken } from '@/lib/auth-storage';

type AuthContextValue = {
  user: AuthUser | null;
  groups: GroupSummary[];
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, name: string) => Promise<void>;
  logout: () => void;
  refreshMe: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const refreshMe = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setGroups([]);
      setLoading(false);
      return;
    }
    try {
      const me = await getMe();
      setUser(me.user);
      setGroups(me.groups);
    } catch {
      clearToken();
      setUser(null);
      setGroups([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshMe();
  }, [refreshMe]);

  const login = useCallback(
    async (email: string, password: string) => {
      const result = await apiLogin(email, password);
      setToken(result.token);
      await refreshMe();
      router.push('/');
    },
    [refreshMe, router]
  );

  const signup = useCallback(
    async (email: string, password: string, name: string) => {
      const result = await apiSignup(email, password, name);
      setToken(result.token);
      await refreshMe();
      router.push('/');
    },
    [refreshMe, router]
  );

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    setGroups([]);
    router.push('/login');
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, groups, loading, login, signup, logout, refreshMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth는 AuthProvider 내부에서만 사용할 수 있습니다.');
  return ctx;
}
