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

export type ReasoningEffort = 'low' | 'medium' | 'high';

export type PortraitStatus = 'empty' | 'queued' | 'analyzing' | 'complete' | 'failed';

export type PortraitResponse = {
  status: PortraitStatus;
  title?: string | null;
  summary?: string | null;
  accuracy_percent?: number | null;
  analyzed_sessions?: number;
  analyzed_messages?: number;
  progress_percent?: number;
  created_at?: string | null;
  updated_at?: string | null;
  error?: string | null;
  persona?: Persona | null;
  vector_method?: string | null;
};

export type VoiceStatus = {
  id: string;
  voice_id: string;
  status: 'uploaded' | 'registered' | 'provisional';
  created_at: string;
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
