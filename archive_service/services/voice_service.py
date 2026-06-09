import uuid

from datetime import datetime

from database.models import (
    VoiceProfile
)

from repositories.voice_repository import (
    VoiceRepository
)


class VoiceService:

    @staticmethod
    def create(
        db,
        payload
    ):

        voice = VoiceProfile(

            id=str(
                uuid.uuid4()
            ),

            voice_name=
            payload.voice_name,

            audio_path=
            payload.audio_path,

            reference_text=
            payload.reference_text,

            description=
            payload.description,

            created_at=
            datetime.now()
        )

        return (
            VoiceRepository.create(
                db,
                voice
            )
        )

    @staticmethod
    def get_all(
        db
    ):

        return (
            VoiceRepository.get_all(
                db
            )
        )

    @staticmethod
    def get_by_id(
        db,
        voice_id
    ):

        return (
            VoiceRepository.get_by_id(
                db,
                voice_id
            )
        )