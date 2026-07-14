import { Platform } from 'react-native';

import type {
  Attachment,
  AuthResponse,
  ChatResponse,
  MemoryItem,
  Message,
  Persona,
  Session,
  User,
  Voice,
  VoiceStatus,
} from './types';

const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://127.0.0.1:8000/v1').replace(/\/$/, '');

function errorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.flatMap((item) => {
      if (!item || typeof item !== 'object') return [];
      const value = item as { loc?: unknown[]; msg?: unknown };
      if (typeof value.msg !== 'string') return [];
      const field = Array.isArray(value.loc) ? value.loc.at(-1) : undefined;
      return [typeof field === 'string' ? `${field}: ${value.msg}` : value.msg];
    });
    if (messages.length) return messages.join('\n');
  }
  if (detail && typeof detail === 'object') {
    const value = detail as { message?: unknown };
    if (typeof value.message === 'string' && value.message.trim()) return value.message;
  }
  return fallback;
}

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
    const fallback = '요청을 처리하지 못했어요.';
    let message = fallback;
    try {
      const data = await response.json();
      message = errorMessage(data.detail, fallback);
    } catch {
      // Keep the friendly fallback when a proxy returns a non-JSON error page.
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json() as T;
  return data;
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
  deleteSession(token: string, sessionId: string) {
    return request<void>(`/sessions/${sessionId}`, { method: 'DELETE' }, token);
  },
  history(token: string, sessionId: string) {
    return request<Message[]>(`/sessions/${sessionId}/messages`, {}, token);
  },
  attachments(token: string, sessionId: string) {
    return request<Attachment[]>(`/sessions/${sessionId}/attachments`, {}, token);
  },
  async uploadAttachment(
    token: string,
    sessionId: string,
    uri: string,
    filename: string,
    contentType = 'application/octet-stream',
  ) {
    const form = new FormData();
    if (Platform.OS === 'web') {
      const blob = await (await fetch(uri)).blob();
      form.append('file', blob, filename);
    } else {
      form.append('file', { uri, name: filename, type: contentType } as unknown as Blob);
    }
    return request<Attachment>(
      `/sessions/${sessionId}/attachments`,
      { method: 'POST', body: form },
      token,
    );
  },
  deleteAttachment(token: string, attachmentId: string) {
    return request<void>(`/attachments/${attachmentId}`, { method: 'DELETE' }, token);
  },
  chat(
    token: string,
    text: string,
    sessionId?: string,
    voiceId?: string,
    speak = true,
    casualMode = false,
    persona: Persona = 'default',
  ) {
    return request<ChatResponse>(
      '/chat/messages',
      {
        method: 'POST',
        body: JSON.stringify({
          text,
          session_id: sessionId,
          voice_id: voiceId,
          speak,
          casual_mode: casualMode,
          persona,
        }),
      },
      token,
    );
  },
  regenerate(
    token: string,
    messageId: string,
    voiceId?: string,
    speak = true,
    casualMode = false,
    persona: Persona = 'default',
  ) {
    return request<ChatResponse>(
      `/chat/messages/${messageId}/regenerate`,
      {
        method: 'POST',
        body: JSON.stringify({
          voice_id: voiceId,
          speak,
          casual_mode: casualMode,
          persona,
        }),
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
  voiceStatus(token: string) {
    return request<VoiceStatus>('/voices/status', {}, token);
  },
  async createVoice(
    token: string,
    uri: string,
    voiceName: string,
    referenceText: string,
    description: string,
  ) {
    const extension = uri.split('.').pop()?.toLowerCase() ?? 'm4a';
    const mime = extension === 'webm' ? 'audio/webm' : extension === 'wav' ? 'audio/wav' : 'audio/mp4';
    const form = new FormData();
    form.append('voice_name', voiceName);
    form.append('reference_text', referenceText);
    form.append('description', description);
    if (Platform.OS === 'web') {
      const blob = await (await fetch(uri)).blob();
      form.append('audio', blob, `voice-sample.${extension}`);
    } else {
      form.append('audio', { uri, name: `voice-sample.${extension}`, type: mime } as unknown as Blob);
    }
    const voice = await request<Voice>('/voices', { method: 'POST', body: form }, token);
    return voice;
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
