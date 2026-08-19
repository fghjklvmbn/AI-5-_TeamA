import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

import { ApiError, api, setUnauthorizedHandler } from './api';
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

function withTimeout<T>(task: Promise<T>, timeoutMillis: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => reject(new Error('startup_timeout')), timeoutMillis);
    task.then(
      (value) => { clearTimeout(timeoutId); resolve(value); },
      (reason) => { clearTimeout(timeoutId); reject(reason); },
    );
  });
}

export function AuthProvider({ children }: React.PropsWithChildren) {
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [notice, setNotice] = useState('');
  const tokenRef = useRef<string | null>(null);
  const authTransitionGenerationRef = useRef(0);

  const clearLocalSession = useCallback(async (nextNotice = '') => {
    const transitionGeneration = ++authTransitionGenerationRef.current;
    tokenRef.current = null;
    setToken(null);
    setUser(null);
    setNotice(nextNotice);
    try {
      await tokenStorage.remove();
    } catch {
      if (!tokenRef.current && authTransitionGenerationRef.current === transitionGeneration) {
        const cleanupWarning = '기기의 로그인 정보 정리가 지연되고 있어요. 앱을 다시 열기 전에 잠시 후 재시도해 주세요.';
        setNotice(nextNotice ? `${nextNotice}\n${cleanupWarning}` : `로그아웃은 완료됐지만 ${cleanupWarning}`);
      }
    }
  }, []);

  useEffect(() => setUnauthorizedHandler((failedToken) => {
    // A delayed 401 from an older request must not sign out a newly-created session.
    if (tokenRef.current !== failedToken) return;
    void clearLocalSession('로그인이 만료되었어요. 다시 로그인해 주세요.');
  }), [clearLocalSession]);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    void (async () => {
      try {
        const saved = await withTimeout(tokenStorage.get(), 10_000);
        if (!saved) return;
        try {
          const savedUser = await withTimeout(api.me(saved, controller.signal), 15_000);
          if (!active) return;
          tokenRef.current = saved;
          setToken(saved);
          setUser(savedUser);
        } catch (reason) {
          if (reason instanceof ApiError && reason.status === 401) {
            try {
              await tokenStorage.remove();
            } catch {
              if (active) setNotice('만료된 로그인 정보를 기기에서 정리하지 못했어요. 다시 로그인하면 새 정보로 교체됩니다.');
            }
          } else if (active) {
            // Offline and server failures do not prove that the saved token is invalid.
            setNotice('서버에 연결하지 못해 저장된 로그인을 확인할 수 없었어요. 로그인 정보는 유지되어 다음 실행 때 다시 확인합니다.');
          }
        }
      } catch {
        if (active) setNotice('기기에 저장된 로그인 정보를 읽지 못했어요. 잠시 후 앱을 다시 실행해 주세요.');
      } finally {
        controller.abort();
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  const accept = useCallback(async (nextToken: string, nextUser: User, transitionGeneration: number) => {
    if (authTransitionGenerationRef.current !== transitionGeneration) return;
    try {
      await tokenStorage.set(nextToken);
    } catch (reason) {
      // A timed-out native write can still finish late; a newer removal generation heals it.
      if (authTransitionGenerationRef.current === transitionGeneration) {
        try { await tokenStorage.remove(); } catch { /* The original persistence error is more useful. */ }
      }
      throw reason;
    }
    if (authTransitionGenerationRef.current !== transitionGeneration) return;
    tokenRef.current = nextToken;
    setToken(nextToken);
    setUser(nextUser);
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const transitionGeneration = ++authTransitionGenerationRef.current;
      setNotice('');
      const response = await api.login(email, password);
      if (authTransitionGenerationRef.current !== transitionGeneration) return;
      await accept(response.access_token, response.user, transitionGeneration);
    },
    [accept],
  );

  const register = useCallback(
    async (email: string, password: string, displayName: string) => {
      const transitionGeneration = ++authTransitionGenerationRef.current;
      setNotice('');
      const response = await api.register(email, password, displayName);
      if (authTransitionGenerationRef.current !== transitionGeneration) return;
      await accept(response.access_token, response.user, transitionGeneration);
    },
    [accept],
  );

  const logout = useCallback(async () => {
    const transitionGeneration = ++authTransitionGenerationRef.current;
    const current = tokenRef.current;
    const controller = new AbortController();
    tokenRef.current = null;
    setToken(null);
    setUser(null);
    setNotice('');
    const removeResult = tokenStorage.remove().catch(() => {
      if (!tokenRef.current && authTransitionGenerationRef.current === transitionGeneration) {
        setNotice('현재 화면에서는 로그아웃됐지만 기기의 로그인 정보 정리가 지연되고 있어요. 앱을 다시 실행한 뒤 로그아웃을 재시도해 주세요.');
      }
    });
    const revokeResult = current
      ? withTimeout(api.logout(current, controller.signal), 5_000).catch(() => undefined)
      : Promise.resolve();
    // Credential removal and server revocation are independent; always attempt both.
    try {
      await Promise.all([removeResult, revokeResult]);
    } finally {
      controller.abort();
    }
  }, []);

  const updateProfile = useCallback(async (displayName: string) => {
    if (!token) throw new Error('로그인이 필요합니다.');
    const requestToken = token;
    const updated = await api.updateProfile(requestToken, displayName);
    if (tokenRef.current !== requestToken) throw new Error('로그인 상태가 변경되어 이전 요청 결과를 적용하지 않았어요.');
    setUser(updated);
    return updated;
  }, [token]);

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    if (!token) throw new Error('로그인이 필요합니다.');
    const requestToken = token;
    await api.changePassword(requestToken, currentPassword, newPassword);
    if (tokenRef.current !== requestToken) throw new Error('로그인 상태가 변경되어 이전 요청 결과를 적용하지 않았어요.');
    await clearLocalSession('비밀번호가 변경되었습니다. 새 비밀번호로 다시 로그인해 주세요.');
  }, [token, clearLocalSession]);

  const deleteAccount = useCallback(async (currentPassword: string) => {
    if (!token) throw new Error('로그인이 필요합니다.');
    const requestToken = token;
    await api.deleteAccount(requestToken, currentPassword);
    if (tokenRef.current !== requestToken) throw new Error('로그인 상태가 변경되어 이전 요청 결과를 적용하지 않았어요.');
    const clearSessionTask = clearLocalSession('계정 접근이 종료되었습니다. 연계 데이터는 삭제 절차에 따라 처리됩니다.');
    const preferenceCleanupTask = user?.id
      ? withTimeout(
        AsyncStorage.multiRemove([
          `memorypal.casualMode.${user.id}`,
          `memorypal.persona.${user.id}`,
          `memorypal.voiceReplyEnabled.${user.id}`,
          `memorypal.internetEnabled.${user.id}`,
          `memorypal.thinkingMode.${user.id}`,
          `memorypal.reasoningEffort.${user.id}`,
        ]),
        5_000,
      ).catch(() => undefined)
      : Promise.resolve();
    // Credential clearing starts synchronously and cannot be held hostage by a native preference-store hang.
    await Promise.all([clearSessionTask, preferenceCleanupTask]);
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
