export type User = {
  id: string;
  email: string;
  display_name: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: 'bearer';
  expires_at: number;
  user: User;
};

export type Session = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type Message = {
  id: string;
  user_text: string;
  assistant_text: string;
  audio_url?: string | null;
  created_at: string;
  character_cue?: CharacterCue | null;
  attachments?: Attachment[];
};

export type ChatResponse = {
  session: Session;
  message: Message;
  memories_used: string[];
};

export type MemoryItem = {
  id: string;
  memory_type: 'preference' | 'profile' | 'fact' | 'schedule' | 'relationship';
  content: string;
  confidence: number;
  importance: number;
  created_at: string;
  updated_at: string;
};

export type Voice = {
  id: string;
  voice_name: string;
  description?: string | null;
  is_default: boolean;
  is_personalized: boolean;
};

export type Attachment = {
  id: string;
  session_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
};

export type Persona = 'default' | 'emotional_companion' | 'none';

export type ConversationMode = 'live' | 'chat' | 'hybrid';

export type { CharacterId } from './character/ids';

export type CharacterActivity = 'idle' | 'listening' | 'thinking' | 'speaking';

export type CharacterCue = {
  emotion: 'neutral' | 'happy' | 'sad' | 'concerned' | 'excited';
  intensity: number;
  gesture: 'idle' | 'nod' | 'comfort' | 'celebrate';
  voice_style: 'calm' | 'warm' | 'bright';
};

export type ReasoningEffort = 'low' | 'medium' | 'high';

export type ModelReasoningCapabilities = {
  model: string;
  available: boolean;
  thinking_supported: boolean;
  reasoning_efforts: ReasoningEffort[];
  default_reasoning?: 'off' | 'on' | ReasoningEffort | null;
  source: 'lmstudio-native' | 'openai-compatible' | 'unavailable';
};

export type ModelManagerStatus = {
  server_online: boolean;
  model_count: number;
  checked_at: string;
  error?: string | null;
  gpu_metrics_available?: boolean;
  gpu_name?: string;
  gpu_count?: number;
  vram_total_bytes?: number;
  vram_used_bytes?: number;
  vram_free_bytes?: number;
  gpu_metrics_source?: 'llm-server';
};

export type HuggingFaceModel = {
  id: string;
  author: string;
  downloads: number;
  likes: number;
  last_modified?: string | null;
  pipeline_tag?: string | null;
  tags: string[];
  url: string;
  parameter_billions?: number;
};

export type ModelDownloadLedger = { jobs: ModelDownloadJob[]; quota_bytes: number; used_bytes: number };

export type LoadedModelInstance = {
  id: string;
  context_length?: number;
};

export type LocalModel = {
  key: string;
  display_name?: string;
  type?: string;
  publisher?: string;
  quantization?: string | { name?: string; bits_per_weight?: number };
  size_bytes?: number;
  max_context_length?: number;
  format?: string;
  loaded_instances?: LoadedModelInstance[];
  processing?: boolean;
};

export type ModelDownloadJob = {
  job_id: string;
  model?: string;
  status?: string;
  downloaded_bytes?: number;
  total_size_bytes?: number;
  bytes_per_second?: number;
  estimated_completion?: string | number | null;
  error?: string | null;
};

export type PortraitStatus = 'empty' | 'queued' | 'analyzing' | 'complete' | 'failed';

export type PortraitResponse = {
  status: PortraitStatus;
  title?: string | null;
  summary?: string | null;
  accuracy_percent?: number | null;
  analyzed_sessions?: number;
  analyzed_messages?: number;
  ready_for_generation?: boolean;
  readiness_sessions?: number;
  readiness_turns?: number;
  readiness_characters?: number;
  progress_percent?: number;
  created_at?: string | null;
  updated_at?: string | null;
  error?: string | null;
  persona?: Persona | null;
  vector_method?: string | null;
};

export type VoiceStatus = {
  has_personalized_voice: boolean;
  personalized_voice_count: number;
};

// API 타입
type ApiErrorDetail = {
  detail?: string;
  message?: string;
  loc?: unknown[];
  msg?: string;
};

export type ApiErrorMessage = string | (ApiErrorDetail & { loc?: unknown[] })[];

// UI 컴포넌트 Props
export type DropdownOption = { id: string; label: string; detail?: string };

export interface DropdownFieldProps {
  label: string;
  value: string;
  options: DropdownOption[];
  onSelect: (id: string) => void;
}

// Hook 타입
export type LiveRecorderResult = {
  recording: boolean;
  onRecordingStart: () => void;
  onRecordingEnd: () => void;
  onStop: () => void;
};
