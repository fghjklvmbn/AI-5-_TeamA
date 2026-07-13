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
};

