from fastapi import FastAPI

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

app = FastAPI()


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

    session = (
        SessionService.create(
            db,
            payload
        )
    )

    return {
        "id": session.id
    }


@app.post("/conversation")
def create_conversation(
    payload: ConversationCreate
):

    db = SessionLocal()

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

@app.get(
    "/conversation/history/{session_id}"
)

def get_history(
    session_id: str
):

    db = SessionLocal()

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


@app.get(
    "/session/list"
)
def get_session_list():

    db = SessionLocal()

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


@app.get(
    "/session/{session_id}"
)
def get_session(
    session_id: str
):

    db = SessionLocal()

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