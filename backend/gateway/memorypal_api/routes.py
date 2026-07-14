from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from .dependencies import CurrentUser, get_current_user
from .schemas import (
    AttachmentResponse,
    ChatRequest,
    ChatResponse,
    LoginRequest,
    MemoryCreate,
    MemoryResponse,
    MessageResponse,
    RegenerateRequest,
    RegisterRequest,
    SessionCreate,
    SessionResponse,
    TokenResponse,
    TranscriptResponse,
    UserResponse,
    VoiceResponse,
    VoiceStatusResponse,
)
from .security import create_access_token, hash_password, verify_password
from .services.document_engine import DocumentExtractionError
from .services.memory_engine import MemoryCandidate
from .services.pipeline import PipelineUnavailable


router = APIRouter(prefix="/v1")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
SAVE_REQUEST_RE = re.compile(
    r"(?:저장|기억|메모)(?:해|해\s*줘|해\s*주세요|해\s*둬|해둘래|할래|해라|해줘요)", re.IGNORECASE,
)
SHORT_CONFIRM_RE = re.compile(r"^(?:어|응|그래|좋아|네|예|ㅇㅇ|알겠어|해줘)[.!?\s]*$", re.IGNORECASE)
SAVE_OFFER_RE = re.compile(r"(?:저장|기억|메모).*(?:할까|할까요|해둘까|해드릴까|원해)", re.IGNORECASE)
NOTE_DIRECTIVE_RE = re.compile(
    r"(?:\s|\n)*(?:이\s*글|이\s*내용|위\s*내용|이걸)(?:을|를)?\s*"
    r"(?:(?P<title>[0-9A-Za-z가-힣 _-]{1,40}?)\s*(?:로|라는\s*이름으로))?\s*"
    r"(?:저장|기억|메모).*$",
    re.IGNORECASE | re.DOTALL,
)
TRAILING_SAVE_RE = re.compile(
    r"(?:저장|기억|메모)(?:해|해\s*줘|해\s*주세요|해\s*둬|해둘래|할래|해라|해줘요).*$",
    re.IGNORECASE | re.DOTALL,
)


def user_response(row) -> UserResponse:
    return UserResponse(id=row["id"], email=row["email"], display_name=row["display_name"])


def session_response(row) -> SessionResponse:
    return SessionResponse(
        id=row["id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def attachment_response(row) -> AttachmentResponse:
    return AttachmentResponse(
        id=row["id"], session_id=row["session_id"], filename=row["filename"],
        content_type=row["content_type"], size_bytes=row["size_bytes"], created_at=row["created_at"],
    )


def session_working_context(rows) -> str:
    """Build a bounded, session-only transcript for roughly ten conversation turns."""
    turns = [
        f"사용자: {row['user_text']}\nMemoryPal: {row['assistant_text']}"
        for row in rows[-10:]
    ]
    return "\n\n".join(turns)[-6000:]


def session_memory_promotion_requested(user_text: str, history_rows) -> bool:
    if SAVE_REQUEST_RE.search(user_text):
        return True
    if not SHORT_CONFIRM_RE.fullmatch(user_text.strip()) or not history_rows:
        return False
    return bool(SAVE_OFFER_RE.search(str(history_rows[-1]["assistant_text"])))


def direct_user_note(user_text: str) -> tuple[str, str]:
    """Return user-authored note text and an optional requested title."""
    title = ""
    match = NOTE_DIRECTIVE_RE.search(user_text)
    if match:
        title = (match.group("title") or "").strip()
        source = user_text[:match.start()].strip()
    else:
        source = TRAILING_SAVE_RE.sub("", user_text).strip()
    source = source.strip(" \n\t,.;:!?。")
    if len(source) < 6 or SHORT_CONFIRM_RE.fullmatch(source):
        return "", title
    return source, title


def note_matches_source(candidate: MemoryCandidate, source_text: str) -> bool:
    generic = {"레시피", "메모", "내용", "저장", "기억", "사용자", "요약"}
    source_tokens = set(re.findall(r"[0-9A-Za-z가-힣]{2,}", source_text.lower())) - generic
    note_tokens = set(re.findall(r"[0-9A-Za-z가-힣]{2,}", candidate.content.lower())) - generic
    required = min(2, len(source_tokens))
    return required > 0 and len(source_tokens & note_tokens) >= required


def fallback_session_memory(history_rows) -> MemoryCandidate | None:
    for row in reversed(history_rows):
        content = re.sub(
            r"(?:원하시면|원하면|필요하시면|필요하면).{0,80}(?:저장|기억|메모).*$",
            "", str(row["assistant_text"]), flags=re.DOTALL,
        ).strip()
        if len(content) >= 2:
            return MemoryCandidate("fact", content, 0.9, 0.82)
    return None


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
        "pipeline": [
            "whisper-turbo", request.app.state.settings.llm_default_model,
            request.app.state.settings.llm_companion_model, "qwen3-tts",
        ],
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


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    if not request.app.state.db.delete_session(user.id, session_id):
        raise HTTPException(status_code=404, detail="대화 세션을 찾을 수 없습니다.")


@router.get("/sessions/{session_id}/attachments", response_model=list[AttachmentResponse])
def list_attachments(session_id: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    if request.app.state.db.get_session(user.id, session_id) is None:
        raise HTTPException(status_code=404, detail="대화 세션을 찾을 수 없습니다.")
    return [attachment_response(row) for row in request.app.state.db.list_attachments(user.id, session_id)]


@router.post("/sessions/{session_id}/attachments", response_model=AttachmentResponse, status_code=201)
async def create_attachment(
    session_id: str, request: Request, file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
):
    db = request.app.state.db
    if db.get_session(user.id, session_id) is None:
        raise HTTPException(status_code=404, detail="대화 세션을 찾을 수 없습니다.")
    content = await file.read(10 * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(status_code=422, detail="첨부파일이 비어 있습니다.")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="첨부파일은 10MB까지 업로드할 수 있습니다.")
    filename = Path(file.filename or "document.txt").name
    try:
        text_content = await run_in_threadpool(request.app.state.document_engine.extract, filename, content)
    except DocumentExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return attachment_response(db.create_attachment(
        user.id, session_id, filename, file.content_type or "application/octet-stream", len(content), text_content
    ))


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    if not request.app.state.db.delete_attachment(user.id, attachment_id):
        raise HTTPException(status_code=404, detail="첨부파일을 찾을 수 없습니다.")


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
def history(session_id: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    if request.app.state.db.get_session(user.id, session_id) is None:
        raise HTTPException(status_code=404, detail="대화 세션을 찾을 수 없습니다.")
    pipeline = request.app.state.pipeline
    return [
        MessageResponse(
            id=row["id"],
            user_text=row["user_text"],
            assistant_text=row["assistant_text"],
            audio_url=pipeline.public_audio_url(row["output_audio_path"]),
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
    if (
        payload.voice_id and payload.voice_id != request.app.state.settings.default_voice_id
        and not db.user_has_voice(user.id, payload.voice_id)
    ):
        raise HTTPException(status_code=403, detail="이 계정에서 사용할 수 없는 개인화 음성입니다.")
    session = session or db.create_session(user.id)
    memories = engine.retrieve(user.id, payload.text)
    history_rows = db.get_history(user.id, session["id"], limit=10)
    session_context = db.get_session_working_memory(user.id, session["id"])
    if not session_context and history_rows:
        session_context = session_working_context(history_rows)
    document_context = request.app.state.document_engine.retrieve_context(user.id, session["id"], payload.text)
    try:
        answer = await pipeline.generate(
            payload.text, engine.as_prompt(memories), history_rows,
            casual_mode=payload.casual_mode, persona=payload.persona, document_context=document_context,
            session_context=session_context,
        )
    except PipelineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    audio_url = await pipeline.synthesize(answer, payload.voice_id) if payload.speak else None
    conversation = db.save_conversation(
        user.id, session["id"], payload.text, answer, output_audio_path=audio_url
    )
    working_rows = db.get_history(user.id, session["id"], limit=10)
    db.upsert_session_working_memory(
        user.id, session["id"], session_working_context(working_rows), len(working_rows)
    )
    promotion_requested = session_memory_promotion_requested(payload.text, history_rows)
    note_source, note_title = direct_user_note(payload.text) if promotion_requested else ("", "")
    if note_source:
        candidates = engine.extract_rule_candidates(note_source)
        promoted = await pipeline.summarize_user_note(note_source, note_title)
        promoted = [candidate for candidate in promoted if note_matches_source(candidate, note_source)]
        if not promoted:
            prefix = f"{note_title}: " if note_title else ""
            promoted = [MemoryCandidate("fact", (prefix + note_source)[:1000], 0.96, 0.9)]
        candidates.extend(promoted)
    elif promotion_requested and session_context:
        candidates = engine.extract_rule_candidates(payload.text)
        promoted = await pipeline.extract_session_memories(session_context, payload.text)
        if not promoted:
            fallback = fallback_session_memory(history_rows)
            promoted = [fallback] if fallback is not None else []
        candidates.extend(promoted)
    else:
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
@router.post("/chat/messages/{message_id}/regenerate", response_model=ChatResponse)
async def regenerate_message(
    message_id: str, payload: RegenerateRequest, request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    db, pipeline = request.app.state.db, request.app.state.pipeline
    conversation = db.get_conversation(user.id, message_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="재생성할 메시지를 찾을 수 없습니다.")
    if (
        payload.voice_id and payload.voice_id != request.app.state.settings.default_voice_id
        and not db.user_has_voice(user.id, payload.voice_id)
    ):
        raise HTTPException(status_code=403, detail="이 계정에서 사용할 수 없는 개인화 음성입니다.")
    session = db.get_session(user.id, conversation["session_id"])
    if session is None:
        raise HTTPException(status_code=404, detail="대화 세션을 찾을 수 없습니다.")
    memories = request.app.state.memory_engine.retrieve(user.id, conversation["user_text"])
    history_rows = db.get_history_before(user.id, session["id"], conversation["created_at"], limit=10)
    session_context = session_working_context(history_rows)
    document_context = request.app.state.document_engine.retrieve_context(
        user.id, session["id"], conversation["user_text"]
    )
    try:
        answer = await pipeline.generate(
            conversation["user_text"], request.app.state.memory_engine.as_prompt(memories), history_rows,
            casual_mode=payload.casual_mode, persona=payload.persona, document_context=document_context,
            session_context=session_context,
        )
    except PipelineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    audio_url = await pipeline.synthesize(answer, payload.voice_id) if payload.speak else None
    updated = db.update_conversation_response(user.id, message_id, answer, audio_url)
    if updated is None:
        raise HTTPException(status_code=409, detail="재생성 중 대화가 변경되었습니다. 다시 시도해 주세요.")
    working_rows = db.get_history(user.id, session["id"], limit=10)
    db.upsert_session_working_memory(
        user.id, session["id"], session_working_context(working_rows), len(working_rows)
    )
    session = db.get_session(user.id, conversation["session_id"])
    if session is None:
        raise HTTPException(status_code=404, detail="대화 세션을 찾을 수 없습니다.")
    return ChatResponse(
        session=session_response(session),
        message=MessageResponse(
            id=updated["id"], user_text=updated["user_text"], assistant_text=updated["assistant_text"],
            audio_url=updated["output_audio_path"], created_at=updated["created_at"],
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


@router.get("/voices", response_model=list[VoiceResponse])
async def voices(request: Request, user: CurrentUser = Depends(get_current_user)):
    default_id = request.app.state.settings.default_voice_id
    owned_ids = request.app.state.db.list_user_voice_ids(user.id)
    result = []
    for voice in await request.app.state.pipeline.list_voices():
        voice_id = str(voice.get("id", ""))
        if voice_id != default_id and voice_id not in owned_ids:
            continue
        result.append({**voice, "is_default": voice_id == default_id, "is_personalized": voice_id in owned_ids})
    return sorted(result, key=lambda voice: not voice["is_default"])


@router.get("/voices/status", response_model=VoiceStatusResponse)
def voice_status(request: Request, user: CurrentUser = Depends(get_current_user)):
    count = len(request.app.state.db.list_user_voice_ids(user.id))
    return VoiceStatusResponse(has_personalized_voice=count > 0, personalized_voice_count=count)


@router.post("/voices", response_model=VoiceResponse, status_code=201)
async def create_voice(
    request: Request, audio: UploadFile = File(...), voice_name: str = Form(...),
    reference_text: str = Form(...), description: str = Form(""),
    user: CurrentUser = Depends(get_current_user),
):
    name, reference = voice_name.strip(), reference_text.strip()
    if not 1 <= len(name) <= 60:
        raise HTTPException(status_code=422, detail="음성 이름은 1~60자로 입력해 주세요.")
    if not 2 <= len(reference) <= 500:
        raise HTTPException(status_code=422, detail="참조 문장은 2~500자로 입력해 주세요.")
    content = await audio.read(20 * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(status_code=422, detail="녹음된 음성 파일이 비어 있습니다.")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="음성 샘플은 20MB까지 등록할 수 있습니다.")
    try:
        voice = await request.app.state.pipeline.register_voice(
            content, audio.filename or "voice-sample.m4a", audio.content_type or "audio/mp4",
            name, reference, description.strip() or None,
        )
        request.app.state.db.add_user_voice(user.id, voice["id"])
        return {**voice, "is_default": False, "is_personalized": True}
    except PipelineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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
