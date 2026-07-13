from __future__ import annotations

import re
import sqlite3

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from .dependencies import CurrentUser, get_current_user
from .schemas import (
    ChatRequest,
    ChatResponse,
    LoginRequest,
    MemoryCreate,
    MemoryResponse,
    MessageResponse,
    RegisterRequest,
    SessionCreate,
    SessionResponse,
    TokenResponse,
    TranscriptResponse,
    UserResponse,
)
from .security import create_access_token, hash_password, verify_password
from .services.memory_engine import MemoryCandidate
from .services.pipeline import PipelineUnavailable


router = APIRouter(prefix="/v1")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def user_response(row) -> UserResponse:
    return UserResponse(id=row["id"], email=row["email"], display_name=row["display_name"])


def session_response(row) -> SessionResponse:
    return SessionResponse(
        id=row["id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def memory_response(row) -> MemoryResponse:
    return MemoryResponse(
        id=row["id"],
        memory_type=row["memory_type"],
        content=row["content"],
        confidence=row["confidence"],
        importance=row["importance"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("/health")
def health(request: Request):
    return {
        "status": "ok",
        "pipeline": ["whisper-turbo", request.app.state.settings.llm_model, "qwen3-tts"],
    }


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, request: Request):
    if not EMAIL_RE.match(payload.email):
        raise HTTPException(status_code=422, detail="이메일 형식을 확인해 주세요.")
    try:
        password_hash, password_salt = hash_password(payload.password)
        row = request.app.state.db.create_user(
            payload.email.strip(), payload.display_name.strip(), password_hash, password_salt
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.") from exc
    token, claims = create_access_token(
        row["id"], row["email"], request.app.state.settings.jwt_secret, request.app.state.settings.jwt_minutes
    )
    return TokenResponse(access_token=token, expires_at=claims.expires_at, user=user_response(row))


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request):
    row = request.app.state.db.get_user_by_email(payload.email.strip())
    if row is None or not verify_password(payload.password, row["password_hash"], row["password_salt"]):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    token, claims = create_access_token(
        row["id"], row["email"], request.app.state.settings.jwt_secret, request.app.state.settings.jwt_minutes
    )
    return TokenResponse(access_token=token, expires_at=claims.expires_at, user=user_response(row))


@router.post("/auth/logout", status_code=204)
def logout(request: Request, user: CurrentUser = Depends(get_current_user)):
    request.app.state.db.revoke_token(user.token_jti, user.token_expires_at)


@router.get("/auth/me", response_model=UserResponse)
def me(request: Request, user: CurrentUser = Depends(get_current_user)):
    return user_response(request.app.state.db.get_user_by_id(user.id))


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(request: Request, user: CurrentUser = Depends(get_current_user)):
    return [session_response(row) for row in request.app.state.db.list_sessions(user.id)]


@router.post("/sessions", response_model=SessionResponse, status_code=201)
def create_session(
    payload: SessionCreate,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    return session_response(request.app.state.db.create_session(user.id, payload.title))


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
def history(session_id: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    if request.app.state.db.get_session(user.id, session_id) is None:
        raise HTTPException(status_code=404, detail="대화 세션을 찾을 수 없습니다.")
    return [
        MessageResponse(
            id=row["id"],
            user_text=row["user_text"],
            assistant_text=row["assistant_text"],
            audio_url=row["output_audio_path"],
            created_at=row["created_at"],
        )
        for row in request.app.state.db.get_history(user.id, session_id)
    ]


@router.post("/chat/messages", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request, user: CurrentUser = Depends(get_current_user)):
    db = request.app.state.db
    engine = request.app.state.memory_engine
    pipeline = request.app.state.pipeline
    session = db.get_session(user.id, payload.session_id) if payload.session_id else None
    if payload.session_id and session is None:
        raise HTTPException(status_code=404, detail="대화 세션을 찾을 수 없습니다.")
    session = session or db.create_session(user.id)
    memories = engine.retrieve(user.id, payload.text)
    history_rows = db.get_history(user.id, session["id"], limit=10)
    try:
        answer = await pipeline.generate(payload.text, engine.as_prompt(memories), history_rows)
    except PipelineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    audio_url = await pipeline.synthesize(answer, payload.voice_id) if payload.speak else None
    conversation = db.save_conversation(
        user.id, session["id"], payload.text, answer, output_audio_path=audio_url
    )
    candidates = engine.extract_rule_candidates(payload.text)
    candidates.extend(await pipeline.extract_memories(payload.text))
    engine.remember_many(user.id, session["id"], candidates)
    session = db.get_session(user.id, session["id"])
    return ChatResponse(
        session=session_response(session),
        message=MessageResponse(
            id=conversation["id"],
            user_text=conversation["user_text"],
            assistant_text=conversation["assistant_text"],
            audio_url=conversation["output_audio_path"],
            created_at=conversation["created_at"],
        ),
        memories_used=[row["content"] for row in memories],
    )


@router.post("/voice/transcribe", response_model=TranscriptResponse)
async def transcribe(
    request: Request,
    audio: UploadFile = File(...),
    _user: CurrentUser = Depends(get_current_user),
):
    content = await audio.read(15 * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(status_code=422, detail="녹음 데이터가 비어 있습니다.")
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="한 번에 보낼 수 있는 녹음은 15MB까지입니다.")
    try:
        text = await request.app.state.pipeline.transcribe(
            content,
            audio.filename or "segment.m4a",
            audio.content_type or "audio/mp4",
        )
    except PipelineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return TranscriptResponse(text=text)


@router.get("/voices")
async def voices(request: Request, _user: CurrentUser = Depends(get_current_user)):
    return await request.app.state.pipeline.list_voices()


@router.get("/memories", response_model=list[MemoryResponse])
def list_memories(request: Request, user: CurrentUser = Depends(get_current_user)):
    return [memory_response(row) for row in request.app.state.db.list_memories(user.id)]


@router.post("/memories", response_model=MemoryResponse, status_code=201)
def create_memory(
    payload: MemoryCreate,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    row = request.app.state.memory_engine.remember(
        user.id,
        None,
        MemoryCandidate(payload.memory_type, payload.content, 1.0, payload.importance),
    )
    if row is None:
        raise HTTPException(status_code=422, detail="민감정보는 장기 기억으로 저장할 수 없습니다.")
    return memory_response(row)


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(memory_id: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    if not request.app.state.db.delete_memory(user.id, memory_id):
        raise HTTPException(status_code=404, detail="기억을 찾을 수 없습니다.")
