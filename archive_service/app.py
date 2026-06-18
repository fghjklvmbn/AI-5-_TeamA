from fastapi import FastAPI, UploadFile, File
from fastapi.staticfiles import StaticFiles

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
import uuid
import shutil

app = FastAPI()

UPLOAD_DIR = Path(
    "voice_uploads"
)

UPLOAD_DIR.mkdir(
    exist_ok=True
)

app.mount(
    "/voice_uploads",
    StaticFiles(directory="voice_uploads"),
    name="voice_uploads"
)


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
            voice.audio_path,

            "reference_text":
            voice.reference_text,

            "description":
            voice.description
        }
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
        str(save_path),

        "audio_url":
        (
            "https://developark.duckdns.org"
            "/api_memoripal/archive"
            f"/voice_uploads/{filename}"
        )
    }