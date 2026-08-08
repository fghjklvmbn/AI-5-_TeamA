import { Platform } from 'react-native';

import type {
  Attachment,
  AuthResponse,
  ChatResponse,
  MemoryItem,
  Message,
  Persona,
  PortraitResponse,
  ReasoningEffort,
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
    this.name = 'ApiError';
  }
}

type UnauthorizedHandler = (token: string) => void;

let unauthorizedHandler: UnauthorizedHandler | undefined;

/** Register the auth boundary that invalidates the matching local session on any authenticated 401. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler): () => void {
  unauthorizedHandler = handler;
  return () => {
    if (unauthorizedHandler === handler) unauthorizedHandler = undefined;
  };
}

async function throwStreamingResponseError(response: Response, token: string): Promise<never> {
  const fallback = '요청을 처리하지 못했어요.';
  let message = fallback;
  try {
    const data = await response.json();
    message = errorMessage(data.detail, fallback);
  } catch {
    // Keep the friendly fallback when a proxy returns a non-JSON error page.
  }
  if (response.status === 401) {
    try {
      unauthorizedHandler?.(token);
    } catch {
      // An auth-state listener must never hide the API error from the caller.
    }
  }
  throw new ApiError(message, response.status);
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
    if (response.status === 401 && token) {
      try {
        unauthorizedHandler?.(token);
      } catch {
        // An auth-state listener must never hide the API error from the caller.
      }
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json() as T;
  return data;
}

type ChatStreamEvent = {
  type?: unknown;
  delta?: unknown;
  detail?: unknown;
  status?: unknown;
  response?: unknown;
};

async function streamingChatRequest(
  token: string,
  payload: Record<string, unknown>,
  onDelta: (delta: string) => void,
): Promise<ChatResponse> {
  const response = await fetch(`${API_URL}/chat/messages/stream`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      Accept: 'application/x-ndjson',
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) return throwStreamingResponseError(response, token);

  let completed: ChatResponse | undefined;
  const processLine = (line: string) => {
    if (!line.trim()) return;
    const event = JSON.parse(line) as ChatStreamEvent;
    if (event.type === 'delta' && typeof event.delta === 'string') {
      onDelta(event.delta);
      return;
    }
    if (event.type === 'complete' && event.response && typeof event.response === 'object') {
      completed = event.response as ChatResponse;
      return;
    }
    if (event.type === 'error') {
      const status = typeof event.status === 'number' ? event.status : 500;
      throw new ApiError(errorMessage(event.detail, '답변을 생성하지 못했어요.'), status);
    }
  };

  const streamBody = response.body as unknown as {
    getReader?: () => {
      read: () => Promise<{ done: boolean; value?: Uint8Array }>;
      releaseLock?: () => void;
    };
  } | null;
  if (streamBody?.getReader && typeof TextDecoder !== 'undefined') {
    const reader = streamBody.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        lines.forEach(processLine);
      }
      buffer += decoder.decode();
      if (buffer.trim()) processLine(buffer);
    } finally {
      reader.releaseLock?.();
    }
  } else {
    // Some native fetch implementations do not expose a readable body. They still
    // receive the same response correctly, but apply its events after buffering.
    (await response.text()).split(/\r?\n/).forEach(processLine);
  }

  if (!completed) throw new ApiError('스트리밍 응답이 완료되기 전에 연결이 종료됐어요.', 502);
  return completed;
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
  me(token: string, signal?: AbortSignal) {
    return request<User>('/auth/me', { signal }, token);
  },
  logout(token: string, signal?: AbortSignal) {
    return request<void>('/auth/logout', { method: 'POST', signal }, token);
  },
  updateProfile(token: string, displayName: string) {
    return request<User>(
      '/auth/profile',
      { method: 'PATCH', body: JSON.stringify({ display_name: displayName }) },
      token,
    );
  },
  changePassword(token: string, currentPassword: string, newPassword: string) {
    return request<void>(
      '/auth/password',
      {
        method: 'POST',
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      },
      token,
    );
  },
  deleteAccount(token: string, currentPassword: string) {
    return request<void>(
      '/auth/account',
      {
        method: 'DELETE',
        body: JSON.stringify({ current_password: currentPassword, confirmation: 'DELETE' }),
      },
      token,
    );
  },
  sessions(token: string, signal?: AbortSignal) {
    return request<Session[]>('/sessions', { signal }, token);
  },
  createSession(token: string, title = '새로운 대화') {
    return request<Session>('/sessions', { method: 'POST', body: JSON.stringify({ title }) }, token);
  },
  deleteSession(token: string, sessionId: string) {
    return request<void>(`/sessions/${sessionId}`, { method: 'DELETE' }, token);
  },
  history(token: string, sessionId: string, signal?: AbortSignal) {
    return request<Message[]>(`/sessions/${sessionId}/messages`, { signal }, token);
  },
  attachments(token: string, sessionId: string, signal?: AbortSignal) {
    return request<Attachment[]>(`/sessions/${sessionId}/attachments`, { signal }, token);
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
    internetEnabled = false,
    thinkingMode = false,
    reasoningEffort: ReasoningEffort = 'medium',
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
          internet_enabled: internetEnabled,
          thinking_mode: thinkingMode,
          reasoning_effort: reasoningEffort,
        }),
      },
      token,
    );
  },
  chatStream(
    token: string,
    text: string,
    onDelta: (delta: string) => void,
    sessionId?: string,
    voiceId?: string,
    speak = true,
    casualMode = false,
    persona: Persona = 'default',
    internetEnabled = false,
    thinkingMode = false,
    reasoningEffort: ReasoningEffort = 'medium',
  ) {
    return streamingChatRequest(token, {
      text,
      session_id: sessionId,
      voice_id: voiceId,
      speak,
      casual_mode: casualMode,
      persona,
      internet_enabled: internetEnabled,
      thinking_mode: thinkingMode,
      reasoning_effort: reasoningEffort,
    }, onDelta);
  },
  regenerate(
    token: string,
    messageId: string,
    voiceId?: string,
    speak = true,
    casualMode = false,
    persona: Persona = 'default',
    internetEnabled = false,
    thinkingMode = false,
    reasoningEffort: ReasoningEffort = 'medium',
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
          internet_enabled: internetEnabled,
          thinking_mode: thinkingMode,
          reasoning_effort: reasoningEffort,
        }),
      },
      token,
    );
  },
  messageAudio(token: string, messageId: string, voiceId?: string) {
    return request<Message>(
      `/chat/messages/${messageId}/audio`,
      {
        method: 'POST',
        body: JSON.stringify({ voice_id: voiceId }),
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
  portrait(token: string) {
    return request<PortraitResponse>('/portrait', {}, token);
  },
  generatePortrait(token: string, persona: Persona) {
    return request<PortraitResponse>(
      '/portrait/generate',
      { method: 'POST', body: JSON.stringify({ persona }) },
      token,
    );
  },
  voices(token: string, signal?: AbortSignal) {
    return request<Voice[]>('/voices', { signal }, token);
  },
  voiceStatus(token: string, signal?: AbortSignal) {
    return request<VoiceStatus>('/voices/status', { signal }, token);
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
  async transcribe(token: string, uri: string, signal?: AbortSignal): Promise<string> {
    const extension = uri.split('.').pop()?.toLowerCase() ?? 'm4a';
    const mime = extension === 'webm' ? 'audio/webm' : extension === 'wav' ? 'audio/wav' : 'audio/mp4';
    const form = new FormData();
    if (Platform.OS === 'web') {
      const blob = await (await fetch(uri, { signal })).blob();
      form.append('audio', blob, `segment.${extension}`);
    } else {
      form.append('audio', { uri, name: `segment.${extension}`, type: mime } as unknown as Blob);
    }
    const result = await request<{ text: string }>('/voice/transcribe', { method: 'POST', body: form, signal }, token);
    return result.text;
  },
};
