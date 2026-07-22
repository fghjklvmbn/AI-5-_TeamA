from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, SecretStr


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=60)


class LoginRequest(BaseModel):
    email: str
    password: str


class ProfileUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=60)


class PasswordChangeRequest(BaseModel):
    current_password: SecretStr = Field(min_length=8, max_length=128)
    new_password: SecretStr = Field(min_length=8, max_length=128)


class AccountDeleteRequest(BaseModel):
    current_password: SecretStr = Field(min_length=8, max_length=128)
    confirmation: Literal["DELETE"]


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: int
    user: UserResponse


class SessionCreate(BaseModel):
    title: str = Field(default="새로운 대화", max_length=100)


class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class AttachmentResponse(BaseModel):
    id: str
    session_id: str
    filename: str
    content_type: str
    size_bytes: int
    created_at: str


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None
    voice_id: str | None = None
    speak: bool = True
    casual_mode: bool = False
    persona: Literal["default", "emotional_companion"] = "default"
    internet_enabled: bool = False
    thinking_mode: bool = False
    reasoning_effort: Literal["low", "medium", "high"] = "medium"


class RegenerateRequest(BaseModel):
    voice_id: str | None = None
    speak: bool = True
    casual_mode: bool = False
    persona: Literal["default", "emotional_companion"] = "default"
    internet_enabled: bool = False
    thinking_mode: bool = False
    reasoning_effort: Literal["low", "medium", "high"] = "medium"


class MessageAudioRequest(BaseModel):
    voice_id: str | None = Field(default=None, max_length=128)


class MessageResponse(BaseModel):
    id: str
    user_text: str
    assistant_text: str
    audio_url: str | None = None
    created_at: str


class ChatResponse(BaseModel):
    session: SessionResponse
    message: MessageResponse
    memories_used: list[str]


class MemoryResponse(BaseModel):
    id: str
    memory_type: Literal["preference", "profile", "fact", "schedule", "relationship"]
    content: str
    confidence: float
    importance: float
    created_at: str
    updated_at: str


class MemoryCreate(BaseModel):
    memory_type: Literal["preference", "profile", "fact", "schedule", "relationship"]
    content: str = Field(min_length=2, max_length=1000)
    importance: float = Field(default=0.7, ge=0, le=1)


class TranscriptResponse(BaseModel):
    text: str


class VoiceResponse(BaseModel):
    id: str
    voice_name: str
    audio_path: str
    reference_text: str
    description: str | None = None
    is_default: bool = False
    is_personalized: bool = False


class VoiceStatusResponse(BaseModel):
    has_personalized_voice: bool
    personalized_voice_count: int


class PortraitGenerateRequest(BaseModel):
    persona: Literal["default", "emotional_companion"] = "default"


class PortraitResponse(BaseModel):
    status: Literal["empty", "queued", "analyzing", "complete", "failed"]
    persona: Literal["default", "emotional_companion"] = "default"
    title: str | None = Field(default=None, min_length=2, max_length=2, pattern=r"^[가-힣]{2}$")
    summary: str | None = Field(default=None, max_length=500)
    accuracy_percent: int = Field(default=0, ge=0, le=100)
    analyzed_sessions: int = Field(default=0, ge=0)
    analyzed_messages: int = Field(default=0, ge=0)
    progress_percent: int = Field(default=0, ge=0, le=100)
    vector_method: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str | None = None
    error: str | None = None
