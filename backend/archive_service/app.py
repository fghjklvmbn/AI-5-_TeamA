import asyncio
import logging
import os
import re
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from schemas.voice_create import (
    VoiceCreate
)

from services.voice_service import (
    VoiceService
)

from database.postgres import (
    SessionLocal,
    ensure_voice_registration_schema,
)

from schemas.session_create import (
    SessionCreate
)

from schemas.conversation_create import (
    ConversationCreate
)

from services.session_service import (
    SessionService
)

from services.conversation_service import (
    ConversationService
)

logger = logging.getLogger(__name__)

ARCHIVE_PUBLIC_URL = os.getenv(
    "MEMORYPAL_ARCHIVE_PUBLIC_URL",
    "http://127.0.0.1:8004",
).rstrip("/")
SERVICE_ROOT = Path(__file__).resolve().parent
LEGACY_UPLOAD_DIR = Path("voice_uploads")
DEFAULT_VOICE_ID = os.getenv(
    "MEMORYPAL_DEFAULT_VOICE_ID",
    "00000000-0000-0000-0000-000000000001",
).strip()
PRIVATE_UPLOAD_DIR = Path(
    os.getenv(
        "MEMORYPAL_ARCHIVE_PRIVATE_UPLOAD_DIR",
        str(SERVICE_ROOT / "private_voice_uploads"),
    )
).resolve()
PENDING_TTL_SECONDS = max(
    60,
    int(os.getenv("MEMORYPAL_ARCHIVE_PENDING_TTL_SECONDS", "900")),
)
REAPER_INTERVAL_SECONDS = max(
    5,
    int(os.getenv("MEMORYPAL_ARCHIVE_REAPER_INTERVAL_SECONDS", "60")),
)
MAX_PRIVATE_VOICE_BYTES = 20 * 1024 * 1024
OWNER_REF_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_AUDIO_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".webm"}
CONTENT_TYPE_SUFFIXES = {
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
    "audio/x-wav": ".wav",
}


def _archive_service_token() -> str:
    # Never share or silently fall back to the end-user JWT signing key.
    return os.getenv("MEMORYPAL_ARCHIVE_SERVICE_TOKEN", "").strip()


def require_archive_service(
    authorization: str | None = Header(default=None),
) -> None:
    expected = _archive_service_token()
    if len(expected) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Archive internal API is not configured.",
        )
    scheme, _, credential = (authorization or "").partition(" ")
    if scheme.casefold() != "bearer" or not secrets.compare_digest(credential, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Archive service credential.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _registration_credentials(
    _service: None = Depends(require_archive_service),
    owner_ref: str = Header(alias="X-MemoryPal-Owner-Ref"),
    registration_token: str = Header(alias="X-MemoryPal-Registration-Token"),
) -> tuple[str, str]:
    normalized_owner = owner_ref.strip().casefold()
    if not OWNER_REF_RE.fullmatch(normalized_owner):
        raise HTTPException(status_code=422, detail="Invalid owner reference.")
    if not 32 <= len(registration_token) <= 256:
        raise HTTPException(status_code=422, detail="Invalid registration token.")
    return normalized_owner, registration_token


def _owner_credentials(
    _service: None = Depends(require_archive_service),
    owner_ref: str = Header(alias="X-MemoryPal-Owner-Ref"),
) -> str:
    normalized_owner = owner_ref.strip().casefold()
    if not OWNER_REF_RE.fullmatch(normalized_owner):
        raise HTTPException(status_code=422, detail="Invalid owner reference.")
    return normalized_owner


def _voice_payload(voice) -> dict:
    return {
        "id": str(voice.id),
        "voice_name": str(voice.voice_name),
        "audio_path": str(voice.audio_path),
        "reference_text": str(voice.reference_text),
        "description": voice.description,
    }


def _private_audio_suffix(filename: str | None, content_type: str | None) -> str:
    suffix = Path(filename or "").suffix.casefold()
    if suffix in ALLOWED_AUDIO_SUFFIXES:
        return suffix
    mapped = CONTENT_TYPE_SUFFIXES.get((content_type or "").split(";", 1)[0].casefold())
    if mapped is None:
        raise HTTPException(status_code=415, detail="Unsupported audio format.")
    return mapped


def run_archive_cleanup_once() -> int:
    db = SessionLocal()
    try:
        removed = VoiceService.cleanup_expired(db, PRIVATE_UPLOAD_DIR)
        removed += VoiceService.cleanup_unreferenced_files(
            db,
            PRIVATE_UPLOAD_DIR,
            older_than_seconds=PENDING_TTL_SECONDS,
        )
        return removed
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    legacy_root = LEGACY_UPLOAD_DIR.resolve()
    if (
        PRIVATE_UPLOAD_DIR == legacy_root
        or PRIVATE_UPLOAD_DIR.is_relative_to(legacy_root)
        or legacy_root.is_relative_to(PRIVATE_UPLOAD_DIR)
        or PRIVATE_UPLOAD_DIR == SERVICE_ROOT
        or SERVICE_ROOT.is_relative_to(PRIVATE_UPLOAD_DIR)
    ):
        raise RuntimeError(
            "MEMORYPAL_ARCHIVE_PRIVATE_UPLOAD_DIR must be a dedicated directory "
            "outside the public voice_uploads tree and must not contain the service root."
        )
    ensure_voice_registration_schema()
    PRIVATE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    async def reap() -> None:
        while True:
            await asyncio.sleep(REAPER_INTERVAL_SECONDS)
            try:
                await asyncio.to_thread(run_archive_cleanup_once)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Archive pending voice cleanup failed")

    reaper = asyncio.create_task(reap())
    try:
        yield
    finally:
        reaper.cancel()
        try:
            await reaper
        except asyncio.CancelledError:
            pass


app = FastAPI(lifespan=lifespan)


@app.exception_handler(UnicodeDecodeError)
async def handle_database_encoding_error(request: Request, exc: UnicodeDecodeError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Archive database connection failed. Check PostgreSQL and MEMORYPAL_ARCHIVE_DATABASE_URL."},
    )


@app.exception_handler(SQLAlchemyError)
async def handle_database_error(request: Request, exc: SQLAlchemyError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Archive database is unavailable. Check PostgreSQL and MEMORYPAL_ARCHIVE_DATABASE_URL."},
    )

LEGACY_UPLOAD_DIR.mkdir(
    exist_ok=True
)

@app.get("/health")
def health():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    finally:
        db.close()


@app.post("/session", dependencies=[Depends(require_archive_service)])
def create_session(
    payload: SessionCreate
):

    db = SessionLocal()

    try:
        session = (
            SessionService.create(
                db,
                payload
            )
        )

        return {
            "id": session.id
        }
    finally:
        db.close()


@app.post("/conversation", dependencies=[Depends(require_archive_service)])
def create_conversation(
    payload: ConversationCreate
):
    db = SessionLocal()
    
    try:
        conversation = (
            ConversationService.create(
                db,
                payload
            )
        )

        return {
            "id":
            conversation.id
        }
    finally:
        db.close()

@app.get(
    "/conversation/history/{session_id}",
    dependencies=[Depends(require_archive_service)],
)

def get_history(
    session_id: str
):

    db = SessionLocal()

    try:
        conversations = (
            ConversationService
            .get_history(
                db,
                session_id
            )
        )

        result = []

        for item in conversations:

            result.append({

                "id":
                item.id,

                "user_text":
                item.user_text,

                "assistant_text":
                item.assistant_text,

                "input_audio_path":
                item.input_audio_path,

                "output_audio_path":
                item.output_audio_path,

                "voice_id":
                item.voice_id,

                "created_at":
                item.created_at
            })

        return result
    finally:
        db.close()


@app.get(
    "/session/list",
    dependencies=[Depends(require_archive_service)],
)
def get_session_list():

    db = SessionLocal()

    try:
        sessions = (

            SessionService
            .get_all(
                db
            )
        )

        result = []

        for item in sessions:

            result.append({

                "id":
                item.id,

                "session_name":
                item.session_name,

                "created_at":
                item.created_at
            })

        return result
    finally:
        db.close()


@app.get(
    "/session/{session_id}",
    dependencies=[Depends(require_archive_service)],
)
def get_session(
    session_id: str
):
    db = SessionLocal()

    try:
        session = (

            SessionService
            .get_by_id(
                db,
                session_id
            )
        )

        if session is None:

            return {
                "error":
                "session not found"
            }

        return {

            "id":
            session.id,

            "session_name":
            session.session_name,

            "created_at":
            session.created_at
        }
    finally:
        db.close()

@app.post("/voice", dependencies=[Depends(require_archive_service)])
def create_voice(
    payload: VoiceCreate
):
    db = SessionLocal()

    try:
        voice = (
            VoiceService.create(
                db,
                payload
            )
        )

        return {

            "id":
            voice.id
        }
    finally:
        db.close()


@app.post("/internal/voices", status_code=status.HTTP_201_CREATED)
async def register_internal_voice(
    file: UploadFile = File(...),
    voice_name: str = Form(...),
    reference_text: str = Form(...),
    description: str = Form(""),
    credentials: tuple[str, str] = Depends(_registration_credentials),
):
    owner_ref, registration_token = credentials
    name = voice_name.strip()
    reference = reference_text.strip()
    if not 1 <= len(name) <= 60:
        raise HTTPException(status_code=422, detail="Voice name must be 1 to 60 characters.")
    if not 2 <= len(reference) <= 500:
        raise HTTPException(status_code=422, detail="Reference text must be 2 to 500 characters.")
    content = await file.read(MAX_PRIVATE_VOICE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=422, detail="Voice sample is empty.")
    if len(content) > MAX_PRIVATE_VOICE_BYTES:
        raise HTTPException(status_code=413, detail="Voice sample must not exceed 20MB.")

    suffix = _private_audio_suffix(file.filename, file.content_type)
    PRIVATE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    audio_path = PRIVATE_UPLOAD_DIR / f"{uuid.uuid4()}{suffix}"
    try:
        with audio_path.open("xb") as output:
            output.write(content)
        db = SessionLocal()
        try:
            voice, created = VoiceService.create_pending(
                db,
                owner_ref=owner_ref,
                registration_token=registration_token,
                voice_name=name,
                audio_path=audio_path,
                reference_text=reference,
                description=description.strip() or None,
                ttl_seconds=PENDING_TTL_SECONDS,
            )
        finally:
            db.close()
    except ValueError as exc:
        audio_path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        audio_path.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail="Could not store private voice sample.") from exc
    return {
        **_voice_payload(voice),
        "registration_state": str(voice.registration_state),
        "created": created,
    }


@app.post("/internal/voices/{voice_id}/confirm")
def confirm_internal_voice(
    voice_id: str,
    credentials: tuple[str, str] = Depends(_registration_credentials),
):
    owner_ref, registration_token = credentials
    db = SessionLocal()
    try:
        try:
            voice = VoiceService.confirm(db, voice_id, owner_ref, registration_token)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if voice is None:
            raise HTTPException(status_code=404, detail="Voice registration not found.")
        return {
            **_voice_payload(voice),
            "registration_state": str(voice.registration_state),
        }
    finally:
        db.close()


@app.delete("/internal/voices/{voice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_internal_voice(
    voice_id: str,
    credentials: tuple[str, str] = Depends(_registration_credentials),
):
    owner_ref, registration_token = credentials
    db = SessionLocal()
    try:
        VoiceService.delete_owned(
            db,
            voice_id=voice_id,
            owner_ref=owner_ref,
            registration_token=registration_token,
            private_root=PRIVATE_UPLOAD_DIR,
        )
    finally:
        db.close()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete("/internal/owner-voices", status_code=status.HTTP_204_NO_CONTENT)
def purge_internal_owner_voices(
    owner_ref: str = Depends(_owner_credentials),
):
    db = SessionLocal()
    try:
        try:
            VoiceService.purge_owner(
                db,
                owner_ref=owner_ref,
                private_root=PRIVATE_UPLOAD_DIR,
                default_voice_id=DEFAULT_VOICE_ID,
                legacy_root=LEGACY_UPLOAD_DIR,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        db.close()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete(
    "/internal/owner-voices/{voice_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def purge_internal_owner_voice(
    voice_id: str,
    owner_ref: str = Depends(_owner_credentials),
):
    db = SessionLocal()
    try:
        try:
            VoiceService.purge_owner(
                db,
                owner_ref=owner_ref,
                voice_id=voice_id,
                private_root=PRIVATE_UPLOAD_DIR,
                default_voice_id=DEFAULT_VOICE_ID,
                legacy_root=LEGACY_UPLOAD_DIR,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        db.close()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/internal/legacy-voices/{voice_id}/adopt")
def adopt_internal_legacy_voice(
    voice_id: str,
    owner_ref: str = Depends(_owner_credentials),
):
    db = SessionLocal()
    try:
        try:
            voice = VoiceService.adopt_legacy(
                db,
                voice_id=voice_id,
                owner_ref=owner_ref,
                default_voice_id=DEFAULT_VOICE_ID,
                legacy_root=LEGACY_UPLOAD_DIR,
                private_root=PRIVATE_UPLOAD_DIR,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if voice is None:
            raise HTTPException(status_code=404, detail="Legacy voice not found.")
        return _voice_payload(voice)
    finally:
        db.close()


@app.get("/internal/voices", dependencies=[Depends(require_archive_service)])
def get_internal_voice_list():
    db = SessionLocal()
    try:
        return [_voice_payload(voice) for voice in VoiceService.get_internal_all(db)]
    finally:
        db.close()


@app.get("/internal/voices/{voice_id}", dependencies=[Depends(require_archive_service)])
def get_internal_voice(voice_id: str):
    db = SessionLocal()
    try:
        voice = VoiceService.get_internal_by_id(db, voice_id)
        if voice is None:
            raise HTTPException(status_code=404, detail="Voice not found.")
        return _voice_payload(voice)
    finally:
        db.close()

@app.get("/voice/list")
def get_voice_list():

    db = SessionLocal()

    try:
        voices = (
            VoiceService.get_all(
                db,
                DEFAULT_VOICE_ID,
            )
        )

        result = []

        for item in voices:

            result.append({

                "id":
                item.id,

                "voice_name":
                item.voice_name,

                "audio_path":
                item.audio_path,

                "reference_text":
                item.reference_text,

                "description":
                item.description
            })
        return result
    
    finally:
        db.close()


@app.get("/voice/{voice_id}")
def get_voice(
    voice_id: str
):

    db = SessionLocal()

    try:
        voice = (
            VoiceService.get_by_id(
                db,
                voice_id,
                DEFAULT_VOICE_ID,
            )
        )

        if voice is None:

            return {
                "error":
                "voice not found"
            }

        return {

            "id":
            voice.id,

            "voice_name":
            voice.voice_name,

            "audio_path":
            voice.audio_path,

            "reference_text":
            voice.reference_text,

            "description":
            voice.description
        }
    finally:
        db.close()
    

@app.post("/upload/audio", dependencies=[Depends(require_archive_service)])
async def upload_audio(
    file: UploadFile = File(...),
):
    extension = _private_audio_suffix(file.filename, file.content_type)
    content = await file.read(MAX_PRIVATE_VOICE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=422, detail="Voice sample is empty.")
    if len(content) > MAX_PRIVATE_VOICE_BYTES:
        raise HTTPException(status_code=413, detail="Voice sample must not exceed 20MB.")

    filename = (
        f"{uuid.uuid4()}{extension}"
    )

    save_path = (
        LEGACY_UPLOAD_DIR
        /
        filename
    )

    with save_path.open("xb") as buffer:
        buffer.write(content)

    return {
        "audio_path":
        str(save_path.resolve()),

        "audio_url":
        f"{ARCHIVE_PUBLIC_URL}/voice_uploads/{filename}"
    }


@app.get("/voice_uploads/{filename:path}")
def get_default_voice_audio(filename: str):
    db = SessionLocal()
    try:
        voice = VoiceService.get_by_id(db, DEFAULT_VOICE_ID, DEFAULT_VOICE_ID)
        if voice is None:
            raise HTTPException(status_code=404, detail="Default voice not found.")
        legacy_root = LEGACY_UPLOAD_DIR.resolve()
        requested = (legacy_root / filename).resolve()
        allowed = Path(str(voice.audio_path)).resolve()
        if (
            not requested.is_relative_to(legacy_root)
            or allowed != requested
            or not allowed.is_file()
        ):
            raise HTTPException(status_code=404, detail="Voice file not found.")
        return FileResponse(allowed)
    finally:
        db.close()
