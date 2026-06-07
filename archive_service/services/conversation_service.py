import uuid

from datetime import datetime

from database.models import (
    Conversation
)

from repositories.conversation_repository import (
    ConversationRepository
)


class ConversationService:

    @staticmethod
    def create(
        db,
        payload
    ):

        conversation = Conversation(

            id=str(
                uuid.uuid4()
            ),

            session_id=
            payload.session_id,

            user_text=
            payload.user_text,

            assistant_text=
            payload.assistant_text,

            input_audio_path=
            payload.input_audio_path,

            output_audio_path=
            payload.output_audio_path,

            voice_id=
            payload.voice_id,

            created_at=
            datetime.now()
        )

        return (
            ConversationRepository.save(
                db,
                conversation
            )
        )
    
    @staticmethod
    def get_history(
        db,
        session_id
    ):

        return (
            ConversationRepository
            .find_by_session_id(
                db,
                session_id
            )
        )