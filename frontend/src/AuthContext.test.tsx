import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react-native';

jest.mock('./api', () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(...args: [string, number]) {
      super(args[0]);
      this.status = args[1];
    }
  },
  api: {
    me: jest.fn(),
    login: jest.fn(),
    register: jest.fn(),
    logout: jest.fn(),
    updateProfile: jest.fn(),
    changePassword: jest.fn(),
    deleteAccount: jest.fn(),
  },
  setUnauthorizedHandler: jest.fn(() => jest.fn()),
}));
jest.mock('./tokenStorage', () => ({
  tokenStorage: { get: jest.fn(), set: jest.fn(), remove: jest.fn() },
}));

import { api, setUnauthorizedHandler } from './api';
import { AuthProvider, useAuth } from './AuthContext';
import { tokenStorage } from './tokenStorage';

const mockApi = api as jest.Mocked<typeof api>;
const mockTokenStorage = tokenStorage as jest.Mocked<typeof tokenStorage>;
const mockSetUnauthorizedHandler = setUnauthorizedHandler as jest.MockedFunction<typeof setUnauthorizedHandler>;

const user = { id: 'u1', email: 'test@test.com', display_name: 'Tester', created_at: '2026-08-20' };
const wrapper = ({ children }: React.PropsWithChildren) => <AuthProvider>{children}</AuthProvider>;

describe('AuthProvider public behavior', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockTokenStorage.get.mockResolvedValue(null);
    mockTokenStorage.set.mockResolvedValue(undefined);
    mockTokenStorage.remove.mockResolvedValue(undefined);
    mockApi.logout.mockResolvedValue(undefined);
  });

  it('finishes startup without a stored token', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.token).toBeNull();
  });

  it('restores a verified stored session', async () => {
    mockTokenStorage.get.mockResolvedValue('stored-token');
    mockApi.me.mockResolvedValue(user);
    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(result.current.user).toEqual(user));
    expect(result.current.token).toBe('stored-token');
    expect(mockApi.me).toHaveBeenCalledWith('stored-token', expect.any(AbortSignal));
  });

  it('persists a successful login through the context boundary', async () => {
    mockApi.login.mockResolvedValue({ access_token: 'new-token', user });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => result.current.login('test@test.com', 'password'));
    expect(mockTokenStorage.set).toHaveBeenCalledWith('new-token');
    expect(result.current.token).toBe('new-token');
    expect(result.current.user).toEqual(user);
  });

  it('clears both local and server state on logout', async () => {
    mockApi.login.mockResolvedValue({ access_token: 'new-token', user });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => result.current.login('test@test.com', 'password'));

    await act(async () => result.current.logout());
    expect(mockTokenStorage.remove).toHaveBeenCalled();
    expect(mockApi.logout).toHaveBeenCalledWith('new-token', expect.any(AbortSignal));
    expect(result.current.token).toBeNull();
  });

  it('ignores a delayed 401 for an older token', async () => {
    mockApi.login.mockResolvedValue({ access_token: 'current-token', user });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => result.current.login('test@test.com', 'password'));

    const handler = mockSetUnauthorizedHandler.mock.calls.at(-1)?.[0];
    act(() => handler?.('old-token'));
    expect(result.current.token).toBe('current-token');
    expect(mockTokenStorage.remove).not.toHaveBeenCalled();
  });
});
