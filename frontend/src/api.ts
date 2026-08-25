import { Platform } from 'react-native';

import type {
  Attachment,
  AuthResponse,
  ChatResponse,
  MemoryItem,
  Message,
  HuggingFaceModel,
  LocalModel,
  ModelDownloadJob,
  ModelDownloadLedger,
  ModelManagerStatus,
  ModelReasoningCapabilities,
  Persona,
  PortraitResponse,
  ReasoningEffort,
  Session,
  User,
  Voice,
  VoiceStatus,
} from './types';

const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://127.0.0.1:8010/v1').replace(/\/$/, '');

export type AIPipelineStage = 'stt' | 'llm' | 'tts';
export type AIPipelineTrace = { correlationId: string; stages: AIPipelineStage[] };

export function createAIPipelineTrace(stages: AIPipelineStage[]): AIPipelineTrace {
  const correlationId = typeof globalThis.crypto?.randomUUID === 'function'
    ? globalThis.crypto.randomUUID()
    : `pipeline-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return { correlationId, stages };
}

function pipelineHeaders(trace?: AIPipelineTrace): Record<string, string> {
  return trace ? {
    'X-Correlation-ID': trace.correlationId,
    'X-AI-Pipeline-Stages': trace.stages.join(','),
  } : {};
}

const AUDIO_EXTENSION_BY_MIME: Record<string, string> = {
  'audio/aac': 'aac',
  'audio/flac': 'flac',
  'audio/mp4': 'm4a',
  'audio/mpeg': 'mp3',
  'audio/ogg': 'ogg',
  'audio/wav': 'wav',
  'audio/webm': 'webm',
  'audio/x-m4a': 'm4a',
  'audio/x-wav': 'wav',
};

function audioUploadMetadata(uri: string, blobType?: string) {
  const normalizedBlobType = blobType?.split(';', 1)[0]?.trim().toLowerCase() ?? '';
  const mimeExtension = AUDIO_EXTENSION_BY_MIME[normalizedBlobType];
  const uriExtension = uri.match(/\.([a-z0-9]+)(?:[?#]|$)/i)?.[1]?.toLowerCase();
  const knownUriExtension = uriExtension && Object.values(AUDIO_EXTENSION_BY_MIME).includes(uriExtension)
    ? uriExtension
    : undefined;
  const extension = mimeExtension ?? knownUriExtension ?? (Platform.OS === 'web' ? 'webm' : 'm4a');
  const mime = normalizedBlobType || (
    extension === 'webm' ? 'audio/webm'
      : extension === 'wav' ? 'audio/wav'
        : extension === 'mp3' ? 'audio/mpeg'
          : extension === 'ogg' ? 'audio/ogg'
            : extension === 'flac' ? 'audio/flac'
              : extension === 'aac' ? 'audio/aac'
                : 'audio/mp4'
  );
  return { extension, mime };
}

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
  trace?: AIPipelineTrace,
): Promise<ChatResponse> {
  const response = await fetch(`${API_URL}/chat/messages/stream`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      Accept: 'application/x-ndjson',
      ...pipelineHeaders(trace),
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
  async openAttachment(token: string, attachment: Attachment) {
    const response = await fetch(`${API_URL}/attachments/${encodeURIComponent(attachment.id)}/content`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error('첨부파일을 열지 못했어요.');
    if (Platform.OS !== 'web') throw new Error('첨부파일 열기는 현재 웹에서 지원해요.');
    const objectUrl = URL.createObjectURL(await response.blob());
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = attachment.filename;
    anchor.rel = 'noopener noreferrer';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 30_000);
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
    reasoningEffort?: ReasoningEffort,
    modelKey?: string,
    trace?: AIPipelineTrace,
  ) {
    return request<ChatResponse>(
      '/chat/messages',
      {
        method: 'POST',
        headers: pipelineHeaders(trace),
        body: JSON.stringify({
          text,
          session_id: sessionId,
          voice_id: voiceId,
          speak,
          casual_mode: casualMode,
          persona,
          internet_enabled: internetEnabled,
          thinking_mode: persona === 'emotional_companion' ? false : thinkingMode,
          reasoning_effort: persona === 'emotional_companion' ? undefined : reasoningEffort,
          model_key: persona !== 'emotional_companion' ? modelKey : undefined,
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
    reasoningEffort?: ReasoningEffort,
    modelKey?: string,
    trace?: AIPipelineTrace,
  ) {
    return streamingChatRequest(token, {
      text,
      session_id: sessionId,
      voice_id: voiceId,
      speak,
      casual_mode: casualMode,
      persona,
      internet_enabled: internetEnabled,
      thinking_mode: persona === 'emotional_companion' ? false : thinkingMode,
      reasoning_effort: persona === 'emotional_companion' ? undefined : reasoningEffort,
      model_key: persona !== 'emotional_companion' ? modelKey : undefined,
    }, onDelta, trace);
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
    reasoningEffort?: ReasoningEffort,
    modelKey?: string,
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
          thinking_mode: persona === 'emotional_companion' ? false : thinkingMode,
          reasoning_effort: persona === 'emotional_companion' ? undefined : reasoningEffort,
          model_key: persona !== 'emotional_companion' ? modelKey : undefined,
        }),
      },
      token,
    );
  },
  messageAudio(
    token: string, messageId: string, voiceId?: string,
    trace?: AIPipelineTrace, force = false,
  ) {
    return request<Message>(
      `/chat/messages/${messageId}/audio`,
      {
        method: 'POST',
        headers: pipelineHeaders(trace),
        body: JSON.stringify({ voice_id: voiceId, force }),
      },
      token,
    );
  },
  memories(
    token: string,
    options: { query?: string; memoryType?: MemoryItem['memory_type']; signal?: AbortSignal } = {},
  ) {
    const params = new URLSearchParams();
    if (options.query?.trim()) params.set('q', options.query.trim());
    if (options.memoryType) params.set('memory_type', options.memoryType);
    const suffix = params.toString() ? `?${params.toString()}` : '';
    return request<MemoryItem[]>(`/memories${suffix}`, { signal: options.signal }, token);
  },
  modelCapabilities(token: string, persona: Persona, signal?: AbortSignal, modelKey?: string) {
    const selected = persona !== 'emotional_companion' && modelKey
      ? `&model_key=${encodeURIComponent(modelKey)}`
      : '';
    return request<ModelReasoningCapabilities>(
      `/model-capabilities?persona=${encodeURIComponent(persona)}${selected}`,
      { signal },
      token,
    );
  },
  modelManagerStatus(token: string, signal?: AbortSignal) {
    return request<ModelManagerStatus>('/model-manager/status?persona=none', { signal }, token);
  },
  searchModels(token: string, query: string, signal?: AbortSignal) {
    return request<{ models: HuggingFaceModel[] }>(
      `/model-manager/search?persona=none&q=${encodeURIComponent(query)}`,
      { signal }, token,
    );
  },
  localModels(token: string, signal?: AbortSignal) {
    return request<{ models: LocalModel[] }>('/model-manager/models?persona=none', { signal }, token);
  },
  modelSelection(token: string, persona: Persona = 'default', signal?: AbortSignal) {
    return request<{ model_key?: string | null; display_name?: string; loaded?: boolean }>(
      `/model-manager/selection?persona=${encodeURIComponent(persona)}`, { signal }, token,
    );
  },
  activatePersona(token: string, persona: Persona) {
    return request<{ model_key: string; display_name: string; loaded: boolean }>(
      '/model-manager/persona/activate', {
        method: 'POST', body: JSON.stringify({ persona }),
      }, token,
    );
  },
  selectModel(token: string, modelKey?: string, persona: 'default' | 'none' = 'none') {
    return request<{ model_key?: string | null; display_name?: string; loaded?: boolean }>('/model-manager/selection', {
      method: 'PUT', body: JSON.stringify({ persona, model_key: modelKey || null }),
    }, token);
  },
  downloadModel(token: string, model: string, quantization?: string) {
    return request<ModelDownloadJob>('/model-manager/downloads', {
      method: 'POST', body: JSON.stringify({ persona: 'none', model, quantization }),
    }, token);
  },
  modelDownloads(token: string, signal?: AbortSignal) {
    return request<ModelDownloadLedger>('/model-manager/downloads?persona=none', { signal }, token);
  },
  modelDownloadStatus(token: string, jobId: string, signal?: AbortSignal) {
    return request<ModelDownloadJob>(
      `/model-manager/downloads/${encodeURIComponent(jobId)}?persona=none`, { signal }, token,
    );
  },
  dismissModelDownload(token: string, jobId: string) {
    return request<{ dismissed: boolean; job_id: string }>(
      `/model-manager/downloads/${encodeURIComponent(jobId)}?persona=none`,
      { method: 'DELETE' },
      token,
    );
  },
  loadModel(token: string, modelKey: string, contextLength = 40960) {
    return request<Record<string, unknown>>('/model-manager/load', {
      method: 'POST', body: JSON.stringify({ persona: 'none', model_key: modelKey, context_length: contextLength }),
    }, token);
  },
  unloadModel(token: string, instanceId: string) {
    return request<Record<string, unknown>>('/model-manager/unload', {
      method: 'POST', body: JSON.stringify({ persona: 'none', instance_id: instanceId }),
    }, token);
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
  deleteVoice(token: string, voiceId: string) {
    return request<void>(`/voices/${voiceId}`, { method: 'DELETE' }, token);
  },
  async createVoice(
    token: string,
    uri: string,
    voiceName: string,
    referenceText: string,
    description: string,
  ) {
    const form = new FormData();
    form.append('voice_name', voiceName);
    form.append('reference_text', referenceText);
    form.append('description', description);
    if (Platform.OS === 'web') {
      const blob = await (await fetch(uri)).blob();
      const { extension } = audioUploadMetadata(uri, blob.type);
      form.append('audio', blob, `voice-sample.${extension}`);
    } else {
      const { extension, mime } = audioUploadMetadata(uri);
      form.append('audio', { uri, name: `voice-sample.${extension}`, type: mime } as unknown as Blob);
    }
    const voice = await request<Voice>('/voices', { method: 'POST', body: form }, token);
    return voice;
  },
  async transcribe(token: string, uri: string, signal?: AbortSignal, trace?: AIPipelineTrace): Promise<string> {
    const form = new FormData();
    if (Platform.OS === 'web') {
      const blob = await (await fetch(uri, { signal })).blob();
      const { extension } = audioUploadMetadata(uri, blob.type);
      form.append('audio', blob, `segment.${extension}`);
    } else {
      const { extension, mime } = audioUploadMetadata(uri);
      form.append('audio', { uri, name: `segment.${extension}`, type: mime } as unknown as Blob);
    }
    const result = await request<{ text: string }>('/voice/transcribe', {
      method: 'POST', body: form, signal, headers: pipelineHeaders(trace),
    }, token);
    return result.text;
  },
};
