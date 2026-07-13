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
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: React.PropsWithChildren) {
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);

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
      const response = await api.login(email, password);
      await accept(response.access_token, response.user);
    },
    [accept],
  );

  const register = useCallback(
    async (email: string, password: string, displayName: string) => {
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

  const value = useMemo(
    () => ({ loading, token, user, login, register, logout }),
    [loading, token, user, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
