import { Platform } from 'react-native';

import type {
  AuthResponse,
  ChatResponse,
  MemoryItem,
  Message,
  Session,
  User,
  Voice,
} from './types';

const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://127.0.0.1:8000/v1').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    let message = '요청을 처리하지 못했어요.';
    try {
      const data = await response.json();
      message = data.detail ?? message;
    } catch {
      // Keep the friendly fallback when a proxy returns a non-JSON error page.
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  register(email: string, password: string, displayName: string) {
    return request<AuthResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, display_name: displayName }),
    });
  },
  login(email: string, password: string) {
    return request<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  },
  me(token: string) {
    return request<User>('/auth/me', {}, token);
  },
  logout(token: string) {
    return request<void>('/auth/logout', { method: 'POST' }, token);
  },
  sessions(token: string) {
    return request<Session[]>('/sessions', {}, token);
  },
  createSession(token: string, title = '새로운 대화') {
    return request<Session>('/sessions', { method: 'POST', body: JSON.stringify({ title }) }, token);
  },
  history(token: string, sessionId: string) {
    return request<Message[]>(`/sessions/${sessionId}/messages`, {}, token);
  },
  chat(token: string, text: string, sessionId?: string, voiceId?: string, speak = true) {
    return request<ChatResponse>(
      '/chat/messages',
      {
        method: 'POST',
        body: JSON.stringify({ text, session_id: sessionId, voice_id: voiceId, speak }),
      },
      token,
    );
  },
  memories(token: string) {
    return request<MemoryItem[]>('/memories', {}, token);
  },
  addMemory(token: string, memoryType: MemoryItem['memory_type'], content: string) {
    return request<MemoryItem>(
      '/memories',
      { method: 'POST', body: JSON.stringify({ memory_type: memoryType, content, importance: 0.8 }) },
      token,
    );
  },
  deleteMemory(token: string, id: string) {
    return request<void>(`/memories/${id}`, { method: 'DELETE' }, token);
  },
  voices(token: string) {
    return request<Voice[]>('/voices', {}, token);
  },
  async transcribe(token: string, uri: string): Promise<string> {
    const extension = uri.split('.').pop()?.toLowerCase() ?? 'm4a';
    const mime = extension === 'webm' ? 'audio/webm' : extension === 'wav' ? 'audio/wav' : 'audio/mp4';
    const form = new FormData();
    if (Platform.OS === 'web') {
      const blob = await (await fetch(uri)).blob();
      form.append('audio', blob, `segment.${extension}`);
    } else {
      form.append('audio', { uri, name: `segment.${extension}`, type: mime } as unknown as Blob);
    }
    const result = await request<{ text: string }>('/voice/transcribe', { method: 'POST', body: form }, token);
    return result.text;
  },
};
