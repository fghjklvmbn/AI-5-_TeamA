from __future__ import annotations

import asyncio
import logging
import re
import secrets
import sqlite3
import unicodedata
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from .dependencies import CurrentUser, get_current_user
from .database import AccountAccessFenceError, DatabaseIntegrityError
from .schemas import (
    AccountDeleteRequest,
    AttachmentResponse,
    ChatRequest,
    ChatResponse,
    LoginRequest,
    MemoryCreate,
    MemoryResponse,
    MessageAudioRequest,
    MessageResponse,
    PortraitGenerateRequest,
    PortraitResponse,
    PasswordChangeRequest,
    ProfileUpdateRequest,
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
from .services.archive_cleanup import run_immediate_archive_cleanup
from .services.memory_engine import MemoryCandidate
from .services.pipeline import PipelineUnavailable


router = APIRouter(prefix="/v1")
logger = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
DISALLOWED_NAME_BIDI = {
    "LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI",
}


def require_write_fence(request: Request, user: CurrentUser) -> None:
    """Reject persistence completed under authority that changed mid-request."""
    if not request.app.state.db.is_account_fence_valid(user.id, user.auth_version):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="계정 상태 또는 인증 정보가 변경되어 결과를 저장하지 않았습니다.",
        )

# 메모리 저장을 위한 순수 정규표현식 노가다
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

# 노트매치 체크(레시피 제외)
def note_matches_source(candidate: MemoryCandidate, source_text: str) -> bool:
    generic = {"메모", "내용", "저장", "기억", "사용자", "요약"}
    source_tokens = set(re.findall(r"[0-9A-Za-z가-힣]{2,}", source_text.lower())) - generic
    note_tokens = set(re.findall(r"[0-9A-Za-z가-힣]{2,}", candidate.content.lower())) - generic
    required = min(2, len(source_tokens))
    return required > 0 and len(source_tokens & note_tokens) >= required

# 세션 메모리 저장 fallback 로직(저장 실패시) -> "어" 나 "그래" 같은 답변을 유도함
def fallback_session_memory(history_rows) -> MemoryCandidate | None:
    for row in reversed(history_rows):
        content = re.sub(
            r"(?:원하시면|원하면|필요하시면|필요하면).{0,80}(?:저장|기억|메모).*$",
            "", str(row["assistant_text"]), flags=re.DOTALL,
        ).strip()
        if len(content) >= 2:
            return MemoryCandidate("fact", content, 0.9, 0.82)
    return None

# 메모리 응답(참조)
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


def portrait_response(row) -> PortraitResponse:
    if row is None:
        return PortraitResponse(status="empty")
    return PortraitResponse(
        status=row["status"],
        persona=row["persona"],
        title=row["title"],
        summary=row["summary"],
        accuracy_percent=row["accuracy_percent"],
        analyzed_sessions=row["analyzed_sessions"],
        analyzed_messages=row["analyzed_messages"],
        progress_percent=row["progress_percent"],
        vector_method=row["vector_method"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        updated_at=row["updated_at"],
        error=row["error"],
    )


def portrait_operation_for(
    db,
    user_id: str,
    generation_id: str,
    *,
    correlation_id: str | None = None,
):
    existing = db.get_operation_for_resource("portrait_generation", generation_id)
    if existing is not None:
        return existing
    return db.begin_operation(
        "portrait_generation",
        f"portrait-{generation_id}",
        correlation_id or str(uuid.uuid4()),
        user_id=user_id,
        resource_id=generation_id,
        status="queued",
        metadata={"service": "portrait-worker"},
    )


def schedule_portrait_task(
    app,
    user_id: str,
    generation_id: str,
    persona: str,
    operation_id: str | None = None,
) -> None:
    """Keep a strong task reference and consume every background exception."""
    key = f"{user_id}:{generation_id}"
    current = app.state.portrait_tasks.get(key)
    if current is not None and not current.done():
        return

    async def run_serialized() -> None:
        async with app.state.portrait_generation_semaphore:
            await app.state.portrait_engine.generate(
                user_id, generation_id, persona, app.state.pipeline,
                operation_id=operation_id,
            )

    task = asyncio.create_task(run_serialized())
    app.state.portrait_tasks[key] = task

    def consume_result(done_task: asyncio.Task) -> None:
        if app.state.portrait_tasks.get(key) is done_task:
            app.state.portrait_tasks.pop(key, None)
        try:
            done_task.result()
        except asyncio.CancelledError:
            pass
        except (Exception, asyncio.CancelledError):
            logger.exception("Unhandled portrait background task error")

    task.add_done_callback(consume_result)


async def dispatch_portrait_task(
    app,
    user_id: str,
    generation_id: str,
    persona: str,
    operation,
) -> None:
    if app.state.settings.task_queue_mode == "redis":
        enqueue_result = await run_in_threadpool(
            app.state.task_queue.enqueue,
            "portrait",
            {
                "user_id": user_id,
                "generation_id": generation_id,
                "persona": persona,
                "operation_id": str(operation["id"]),
            },
            task_id=generation_id,
            dedupe_key=f"portrait:{user_id}:{generation_id}",
            request_id=str(operation["request_id"]),
            correlation_id=str(operation["correlation_id"]),
            max_attempts=3,
        )
        if not enqueue_result.created:
            progress = await run_in_threadpool(
                app.state.task_queue.get_progress, generation_id,
            )
            if progress is not None and progress.status == "failed":
                failed = await run_in_threadpool(
                    app.state.db.fail_expired_portrait,
                    user_id,
                    generation_id,
                    "자화상 worker 재시도 횟수를 모두 사용했습니다.",
                )
                if failed:
                    try:
                        await run_in_threadpool(
                            app.state.db.transition_operation,
                            str(operation["id"]),
                            "failed",
                            error_code="worker_retry_exhausted",
                            reason="redis_state_reconciled_on_dispatch",
                        )
                    except (KeyError, RuntimeError, ValueError):
                        logger.warning(
                            "Could not reconcile failed portrait operation: %s",
                            operation["id"],
                            exc_info=True,
                        )
        return
    schedule_portrait_task(
        app, user_id, generation_id, persona, str(operation["id"]),
    )

# 엔드포인트 시작
@router.get("/health")
def health(request: Request):
    return {
        "status": "ok",
        "database": request.app.state.db.backend_name,
        "task_queue": request.app.state.settings.task_queue_mode,
        "state_tracking": "operation+transaction+outbox",
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
    except (sqlite3.IntegrityError, DatabaseIntegrityError) as exc:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.") from exc
    token, claims = create_access_token(
        row["id"], row["email"], request.app.state.settings.jwt_secret,
        request.app.state.settings.jwt_minutes, int(row["auth_version"]),
    )
    request.state.user_id = str(row["id"])
    return TokenResponse(access_token=token, expires_at=claims.expires_at, user=user_response(row))


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request):
    row = request.app.state.db.get_user_by_email(payload.email.strip())
    if row is None or not verify_password(payload.password, row["password_hash"], row["password_salt"]):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    if str(row["account_status"]) != "active":
        raise HTTPException(status_code=403, detail="현재 이용할 수 없는 계정입니다.")
    token, claims = create_access_token(
        row["id"], row["email"], request.app.state.settings.jwt_secret,
        request.app.state.settings.jwt_minutes, int(row["auth_version"]),
    )
    request.state.user_id = str(row["id"])
    return TokenResponse(access_token=token, expires_at=claims.expires_at, user=user_response(row))


@router.post("/auth/logout", status_code=204)
def logout(request: Request, user: CurrentUser = Depends(get_current_user)):
    request.app.state.db.revoke_token(user.token_jti, user.token_expires_at)


@router.get("/auth/me", response_model=UserResponse)
def me(request: Request, user: CurrentUser = Depends(get_current_user)):
    return user_response(request.app.state.db.get_user_by_id(user.id))


@router.patch("/auth/profile", response_model=UserResponse)
def update_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    if any(
        unicodedata.category(character) == "Cc"
        or unicodedata.bidirectional(character) in DISALLOWED_NAME_BIDI
        for character in payload.display_name
    ):
        raise HTTPException(
            status_code=422,
            detail="닉네임에는 줄바꿈이나 제어 문자를 사용할 수 없습니다.",
        )
    display_name = " ".join(payload.display_name.split())
    if not display_name:
        raise HTTPException(status_code=422, detail="닉네임을 입력해 주세요.")
    row = request.app.state.db.update_user_display_name(
        user.id, display_name, expected_auth_version=user.auth_version,
    )
    if row is None:
        raise HTTPException(status_code=409, detail="계정 정보가 변경되었습니다.")
    return user_response(row)


@router.post("/auth/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    row = request.app.state.db.get_user_by_id(user.id)
    current_password = payload.current_password.get_secret_value()
    new_password = payload.new_password.get_secret_value()
    if row is None or not verify_password(
        current_password, row["password_hash"], row["password_salt"],
    ):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다.")
    if current_password == new_password:
        raise HTTPException(status_code=422, detail="새 비밀번호는 현재 비밀번호와 달라야 합니다.")
    password_hash, password_salt = hash_password(new_password)
    changed = request.app.state.db.change_user_password(
        user.id,
        expected_hash=row["password_hash"],
        expected_salt=row["password_salt"],
        expected_auth_version=user.auth_version,
        password_hash=password_hash,
        password_salt=password_salt,
        token_jti=user.token_jti,
        token_expires_at=user.token_expires_at,
    )
    if not changed:
        raise HTTPException(status_code=409, detail="계정 정보가 변경되었습니다. 다시 시도해 주세요.")


@router.delete("/auth/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    payload: AccountDeleteRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    row = request.app.state.db.get_user_by_id(user.id)
    if row is None:
        raise HTTPException(status_code=409, detail="계정 정보가 변경되었습니다.")
    if (
        str(row["email"]).casefold() in request.app.state.settings.admin_emails
        or request.app.state.db.is_admin_user(user.id)
    ):
        raise HTTPException(
            status_code=403,
            detail="관리자 계정은 일반 회원탈퇴 기능으로 삭제할 수 없습니다.",
        )
    current_password = payload.current_password.get_secret_value()
    if not verify_password(
        current_password, row["password_hash"], row["password_salt"],
    ):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다.")
    # Fail before the irreversible local transaction if Archive service auth
    # cannot derive the pseudonymous owner reference.
    try:
        archive_owner_ref = request.app.state.pipeline.archive_owner_ref(user.id)
    except PipelineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    deleted = request.app.state.db.delete_user_account(
        user.id,
        expected_hash=row["password_hash"],
        expected_salt=row["password_salt"],
        expected_auth_version=user.auth_version,
        token_jti=user.token_jti,
        token_expires_at=user.token_expires_at,
        archive_owner_ref=archive_owner_ref,
        archive_default_voice_id=request.app.state.settings.default_voice_id,
    )
    if not deleted:
        raise HTTPException(status_code=409, detail="계정 정보가 변경되었습니다. 다시 시도해 주세요.")
    request.state.user_id = None
    await run_immediate_archive_cleanup(request.app, archive_owner_ref)


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(request: Request, user: CurrentUser = Depends(get_current_user)):
    return [session_response(row) for row in request.app.state.db.list_sessions(user.id)]


@router.post("/sessions", response_model=SessionResponse, status_code=201)
def create_session(
    payload: SessionCreate,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    return session_response(request.app.state.db.create_session(
        user.id, payload.title, expected_auth_version=user.auth_version,
    ))


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    if not request.app.state.db.delete_session(
        user.id, session_id, expected_auth_version=user.auth_version,
    ):
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
        user.id, session_id, filename, file.content_type or "application/octet-stream",
        len(content), text_content, expected_auth_version=user.auth_version,
    ))


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    if not request.app.state.db.delete_attachment(
        user.id, attachment_id, expected_auth_version=user.auth_version,
    ):
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
    session = session or db.create_session(
        user.id, expected_auth_version=user.auth_version,
    )
    memories = engine.retrieve(user.id, payload.text)
    history_rows = db.get_history(user.id, session["id"], limit=10)
    session_context = db.get_session_working_memory(user.id, session["id"])
    if not session_context and history_rows:
        session_context = session_working_context(history_rows)
    document_context = request.app.state.document_engine.retrieve_context(user.id, session["id"], payload.text)
    web_context = ""
    if payload.internet_enabled:
        web_context = await request.app.state.web_search_engine.retrieve_context(payload.text, history_rows)
    try:
        answer = await pipeline.generate(
            payload.text, engine.as_prompt(memories), history_rows,
            casual_mode=payload.casual_mode, persona=payload.persona, document_context=document_context,
            session_context=session_context,
            web_context=web_context,
            thinking_mode=payload.thinking_mode,
            reasoning_effort=payload.reasoning_effort,
            max_answer_chars=200 if payload.speak else None,
        )
    except PipelineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    audio_url = await pipeline.synthesize(answer, payload.voice_id) if payload.speak else None
    try:
        conversation = db.save_conversation(
            user.id, session["id"], payload.text, answer,
            output_audio_path=audio_url,
            expected_auth_version=user.auth_version,
        )
    except AccountAccessFenceError as exc:
        require_write_fence(request, user)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    working_rows = db.get_history(user.id, session["id"], limit=10)
    db.upsert_session_working_memory(
        user.id, session["id"], session_working_context(working_rows), len(working_rows),
        expected_auth_version=user.auth_version,
    )
    promotion_requested = session_memory_promotion_requested(payload.text, history_rows)
    note_source, note_title = direct_user_note(payload.text) if promotion_requested else ("", "")
    if note_source:
        candidates = engine.extract_rule_candidates(note_source)
        promoted = await pipeline.summarize_user_note(
            note_source, note_title, persona=payload.persona
        )
        promoted = [candidate for candidate in promoted if note_matches_source(candidate, note_source)]
        if not promoted:
            prefix = f"{note_title}: " if note_title else ""
            promoted = [MemoryCandidate("fact", (prefix + note_source)[:1000], 0.96, 0.9)]
        candidates.extend(promoted)
    elif promotion_requested and session_context:
        candidates = engine.extract_rule_candidates(payload.text)
        promoted = await pipeline.extract_session_memories(
            session_context, payload.text, persona=payload.persona
        )
        if not promoted:
            fallback = fallback_session_memory(history_rows)
            promoted = [fallback] if fallback is not None else []
        candidates.extend(promoted)
    else:
        candidates = engine.extract_rule_candidates(payload.text)
        candidates.extend(await pipeline.extract_memories(payload.text, persona=payload.persona))
    require_write_fence(request, user)
    try:
        engine.remember_many(
            user.id, session["id"], candidates,
            expected_auth_version=user.auth_version,
        )
    except AccountAccessFenceError as exc:
        require_write_fence(request, user)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
    web_context = ""
    if payload.internet_enabled:
        web_context = await request.app.state.web_search_engine.retrieve_context(
            conversation["user_text"], history_rows
        )
    try:
        answer = await pipeline.generate(
            conversation["user_text"], request.app.state.memory_engine.as_prompt(memories), history_rows,
            casual_mode=payload.casual_mode, persona=payload.persona, document_context=document_context,
            session_context=session_context,
            web_context=web_context,
            thinking_mode=payload.thinking_mode,
            reasoning_effort=payload.reasoning_effort,
            max_answer_chars=200 if payload.speak else None,
        )
    except PipelineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    audio_url = await pipeline.synthesize(answer, payload.voice_id) if payload.speak else None
    try:
        updated = db.update_conversation_response(
            user.id, message_id, answer, audio_url,
            expected_auth_version=user.auth_version,
        )
    except AccountAccessFenceError as exc:
        require_write_fence(request, user)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=409, detail="재생성 중 대화가 변경되었습니다. 다시 시도해 주세요.")
    working_rows = db.get_history(user.id, session["id"], limit=10)
    db.upsert_session_working_memory(
        user.id, session["id"], session_working_context(working_rows), len(working_rows),
        expected_auth_version=user.auth_version,
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


@router.post("/chat/messages/{message_id}/audio", response_model=MessageResponse)
async def synthesize_message_audio(
    message_id: str, payload: MessageAudioRequest, request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    db, pipeline = request.app.state.db, request.app.state.pipeline
    lock_key = f"{user.id}:{message_id}"
    audio_locks = request.app.state.message_audio_locks
    lock = audio_locks.get(lock_key)
    if lock is None:
        lock = asyncio.Lock()
        audio_locks[lock_key] = lock
    async with lock:
        # Re-read after acquiring the lock so concurrent clicks reuse the first
        # generated file instead of running duplicate GPU synthesis jobs.
        conversation = db.get_conversation(user.id, message_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="음성을 만들 메시지를 찾을 수 없습니다.")
        if (
            payload.voice_id and payload.voice_id != request.app.state.settings.default_voice_id
            and not db.user_has_voice(user.id, payload.voice_id)
        ):
            raise HTTPException(status_code=403, detail="이 계정에서 사용할 수 없는 개인화 음성입니다.")
        if conversation["output_audio_path"]:
            return MessageResponse(
                id=conversation["id"], user_text=conversation["user_text"],
                assistant_text=conversation["assistant_text"],
                audio_url=pipeline.public_audio_url(conversation["output_audio_path"]),
                created_at=conversation["created_at"],
            )
        assistant_text = str(conversation["assistant_text"] or "").strip()
        if not assistant_text:
            raise HTTPException(status_code=409, detail="답변 생성이 끝난 뒤 음성을 만들어 주세요.")
        audio_url = await pipeline.synthesize(assistant_text, payload.voice_id)
        if not audio_url:
            raise HTTPException(status_code=503, detail="음성을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요.")
        try:
            updated = db.update_conversation_audio_if_current(
                user.id, message_id, assistant_text, audio_url,
                expected_auth_version=user.auth_version,
            )
        except AccountAccessFenceError as exc:
            require_write_fence(request, user)
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if updated is None:
            raise HTTPException(status_code=409, detail="답변이 변경되었습니다. 새 답변에서 다시 시도해 주세요.")
        return MessageResponse(
            id=updated["id"], user_text=updated["user_text"],
            assistant_text=updated["assistant_text"],
            audio_url=pipeline.public_audio_url(updated["output_audio_path"]),
            created_at=updated["created_at"],
        )


@router.post("/voice/transcribe", response_model=TranscriptResponse)
async def transcribe(
    request: Request,
    audio: UploadFile = File(...),
    _user: CurrentUser = Depends(get_current_user),
):
    # 음성 입력 데이터 15메가 제한 로직 및 예외처리
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
    # 필수값 지정
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
    pipeline = request.app.state.pipeline
    db = request.app.state.db
    registration_token = secrets.token_urlsafe(48)
    try:
        owner_ref = pipeline.archive_owner_ref(user.id)
        require_write_fence(request, user)
        voice = await pipeline.register_voice(
            content, audio.filename or "voice-sample.m4a", audio.content_type or "audio/mp4",
            name, reference, description.strip() or None,
            owner_ref=owner_ref,
            registration_token=registration_token,
        )
        mapping_added = False
        try:
            db.add_user_voice(
                user.id,
                voice["id"],
                expected_auth_version=user.auth_version,
                owner_ref=owner_ref,
                provisional_cleanup_delay_seconds=(
                    request.app.state.settings.archive_registration_cleanup_delay_seconds
                ),
            )
            mapping_added = True
            require_write_fence(request, user)
            await pipeline.confirm_voice_registration(
                voice["id"],
                owner_ref=owner_ref,
                registration_token=registration_token,
            )
            # Close the final race between the remote confirmation and the
            # response.  An authority change compensates both stores.
            require_write_fence(request, user)
            if not db.activate_user_voice(
                user.id,
                voice["id"],
                owner_ref,
                expected_auth_version=user.auth_version,
            ):
                raise AccountAccessFenceError("voice_mapping_changed")
        except (Exception, asyncio.CancelledError):
            if mapping_added:
                try:
                    db.compensate_user_voice(user.id, voice["id"], owner_ref)
                except Exception:
                    logger.exception("Could not persist provisional voice compensation")
            try:
                await asyncio.shield(
                    pipeline.delete_voice_registration(
                        voice["id"],
                        owner_ref=owner_ref,
                        registration_token=registration_token,
                    )
                )
                db.complete_archive_voice_cleanup_scope(owner_ref, voice["id"])
            except (PipelineUnavailable, asyncio.CancelledError):
                # Archive pending TTL is the durable crash/network safety net.
                logger.warning(
                    "Archive voice compensation deferred to TTL reaper: %s",
                    voice["id"],
                    exc_info=True,
                )
            raise
        return {**voice, "is_default": False, "is_personalized": True}
    except AccountAccessFenceError as exc:
        require_write_fence(request, user)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
        expected_auth_version=user.auth_version,
    )
    if row is None:
        raise HTTPException(status_code=422, detail="민감정보는 장기 기억으로 저장할 수 없습니다.")
    return memory_response(row)


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(memory_id: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    if not request.app.state.db.delete_memory(
        user.id, memory_id, expected_auth_version=user.auth_version,
    ):
        raise HTTPException(status_code=404, detail="기억을 찾을 수 없습니다.")


@router.get("/portrait", response_model=PortraitResponse)
def get_portrait(request: Request, user: CurrentUser = Depends(get_current_user)):
    return portrait_response(request.app.state.db.get_portrait(user.id))


@router.post("/portrait/generate", response_model=PortraitResponse, status_code=202)
async def generate_portrait(
    payload: PortraitGenerateRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    try:
        row, _started = request.app.state.db.begin_portrait_generation(
            user.id, payload.persona, expected_auth_version=user.auth_version,
        )
    except AccountAccessFenceError as exc:
        require_write_fence(request, user)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    operation = portrait_operation_for(
        request.app.state.db,
        user.id,
        row["generation_id"],
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    # Dispatching an existing durable job is intentional: Redis dedupe and the
    # database fencing lease prevent duplicate GPU work after a process crash.
    await dispatch_portrait_task(
        request.app, user.id, row["generation_id"], row["persona"], operation,
    )
    return portrait_response(row)
