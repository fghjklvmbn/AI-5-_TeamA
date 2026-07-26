from fastapi import FastAPI, UploadFile, File, Request, HTTPException, Response, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from schemas.voice_create import (
    VoiceCreate
)

from services.voice_service import (
    VoiceService
)

from database.postgres import (
    SessionLocal
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

from pathlib import Path
import os
import uuid
import shutil

app = FastAPI()


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

ARCHIVE_PUBLIC_URL = os.getenv(
    "MEMORYPAL_ARCHIVE_PUBLIC_URL",
    "http://127.0.0.1:8004",
).rstrip("/")

ARCHIVE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(
    ARCHIVE_DIR,
    "private_voice_uploads"
)

UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True
)

app.mount(
    "/voice_uploads",
    StaticFiles(directory=str(UPLOAD_DIR)),
    name="voice_uploads"
)


def resolved_audio_path(audio_path: str) -> str:
    path = Path(audio_path)
    if not path.is_absolute():
        path = ARCHIVE_DIR / path
    return str(path.resolve())


@app.get("/health")
def health():

    return {
        "status": "ok"
    }


@app.post("/session")
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


@app.post("/conversation")
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
    "/conversation/history/{session_id}"
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
    "/session/list"
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
    "/session/{session_id}"
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

@app.post("/voice")
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

@app.get("/voice/list")
def get_voice_list():

    db = SessionLocal()

    try:
        voices = (
            VoiceService.get_all(
                db
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
                resolved_audio_path(item.audio_path),

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
                voice_id
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
            resolved_audio_path(voice.audio_path),

            "reference_text":
            voice.reference_text,

            "description":
            voice.description
        }
    finally:
        db.close()


@app.delete("/voice/{voice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_voice(
    voice_id: str,
    request: Request
):
    configured_token = os.getenv(
        "MEMORYPAL_ARCHIVE_SERVICE_TOKEN",
        ""
    ).strip()
    provided_token = request.headers.get(
        "X-MemoryPal-Archive-Token",
        ""
    )
    client_host = request.client.host if request.client else ""

    if configured_token:
        import secrets

        if not secrets.compare_digest(
            configured_token,
            provided_token
        ):
            raise HTTPException(
                status_code=403,
                detail="Archive 내부 삭제 권한이 없습니다."
            )
    elif client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(
            status_code=403,
            detail="서비스 토큰이 없는 삭제 요청은 로컬 연결만 허용됩니다."
        )

    default_voice_id = os.getenv(
        "MEMORYPAL_DEFAULT_VOICE_ID",
        "00000000-0000-0000-0000-000000000001"
    )
    if voice_id == default_voice_id:
        raise HTTPException(
            status_code=409,
            detail="공용 기본 음성은 삭제할 수 없습니다."
        )

    db = SessionLocal()

    try:
        try:
            deleted = VoiceService.delete(
                db,
                voice_id,
                UPLOAD_DIR,
                ARCHIVE_DIR
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail=str(exc)
            ) from exc

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail="음성을 찾을 수 없습니다."
            )

        return Response(
            status_code=status.HTTP_204_NO_CONTENT
        )
    finally:
        db.close()
    

@app.post("/upload/audio")
def upload_audio(
    file: UploadFile = File(...)
):

    extension = (
        Path(file.filename)
        .suffix
    )

    filename = (
        f"{uuid.uuid4()}{extension}"
    )

    save_path = (
        UPLOAD_DIR
        /
        filename
    )

    with open(
        save_path,
        "wb"
    ) as buffer:

        shutil.copyfileobj(
            file.file,
            buffer
        )

    return {
        "audio_path":
        save_path.relative_to(ARCHIVE_DIR).as_posix(),

        "audio_url":
        f"{ARCHIVE_PUBLIC_URL}/voice_uploads/{filename}"
    }
