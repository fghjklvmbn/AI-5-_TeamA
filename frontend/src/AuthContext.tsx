import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { api } from './api';
import { tokenStorage } from './tokenStorage';
import type { User } from './types';

type AuthContextValue = {
  loading: boolean;
  token: string | null;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => Promise<void>;
  updateProfile: (displayName: string) => Promise<User>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  deleteAccount: (currentPassword: string) => Promise<void>;
  notice: string;
  clearNotice: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: React.PropsWithChildren) {
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    void (async () => {
      const saved = await tokenStorage.get();
      if (saved) {
        try {
          setUser(await api.me(saved));
          setToken(saved);
        } catch {
          await tokenStorage.remove();
        }
      }
      setLoading(false);
    })();
  }, []);

  const accept = useCallback(async (nextToken: string, nextUser: User) => {
    await tokenStorage.set(nextToken);
    setToken(nextToken);
    setUser(nextUser);
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      setNotice('');
      const response = await api.login(email, password);
      await accept(response.access_token, response.user);
    },
    [accept],
  );

  const register = useCallback(
    async (email: string, password: string, displayName: string) => {
      setNotice('');
      const response = await api.register(email, password, displayName);
      await accept(response.access_token, response.user);
    },
    [accept],
  );

  const logout = useCallback(async () => {
    const current = token;
    setToken(null);
    setUser(null);
    await tokenStorage.remove();
    if (current) {
      try {
        await api.logout(current);
      } catch {
        // Local logout must still succeed if the API is temporarily unreachable.
      }
    }
  }, [token]);

  const clearLocalSession = useCallback(async () => {
    setToken(null);
    setUser(null);
    await tokenStorage.remove();
  }, []);

  const updateProfile = useCallback(async (displayName: string) => {
    if (!token) throw new Error('로그인이 필요합니다.');
    const updated = await api.updateProfile(token, displayName);
    setUser(updated);
    return updated;
  }, [token]);

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    if (!token) throw new Error('로그인이 필요합니다.');
    await api.changePassword(token, currentPassword, newPassword);
    setNotice('비밀번호가 변경되었습니다. 새 비밀번호로 다시 로그인해 주세요.');
    await clearLocalSession();
  }, [token, clearLocalSession]);

  const deleteAccount = useCallback(async (currentPassword: string) => {
    if (!token) throw new Error('로그인이 필요합니다.');
    await api.deleteAccount(token, currentPassword);
    try {
      if (user?.id) {
        await AsyncStorage.multiRemove([
          `memorypal.casualMode.${user.id}`,
          `memorypal.persona.${user.id}`,
          `memorypal.voiceReplyEnabled.${user.id}`,
          `memorypal.internetEnabled.${user.id}`,
          `memorypal.thinkingMode.${user.id}`,
          `memorypal.reasoningEffort.${user.id}`,
        ]);
      }
    } catch {
      // Account deletion must still clear credentials if preference cleanup fails.
    } finally {
      setNotice('계정 접근이 종료되었습니다. 연계 데이터는 삭제 절차에 따라 처리됩니다.');
      await clearLocalSession();
    }
  }, [token, user?.id, clearLocalSession]);

  const clearNotice = useCallback(() => setNotice(''), []);

  const value = useMemo(
    () => ({ loading, token, user, login, register, logout, updateProfile, changePassword, deleteAccount, notice, clearNotice }),
    [loading, token, user, login, register, logout, updateProfile, changePassword, deleteAccount, notice, clearNotice],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
