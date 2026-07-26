import uuid

from datetime import datetime
from pathlib import Path

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

    @staticmethod
    def delete(
        db,
        voice_id,
        upload_dir,
        archive_dir=None
    ):
        voice = VoiceRepository.get_by_id(
            db,
            voice_id
        )

        if voice is None:
            return False

        upload_root = Path(upload_dir).resolve()
        audio_path = Path(voice.audio_path)
        if not audio_path.is_absolute():
            audio_path = Path(archive_dir or Path.cwd()) / audio_path
        audio_path = audio_path.resolve()

        try:
            audio_path.relative_to(upload_root)
        except ValueError as exc:
            raise ValueError(
                "관리되는 개인화 음성 파일 경로가 아닙니다."
            ) from exc

        tombstone = None
        if audio_path.exists():
            if not audio_path.is_file():
                raise ValueError(
                    "개인화 음성 경로가 파일이 아닙니다."
                )
            tombstone = audio_path.with_name(
                f".{audio_path.name}.{uuid.uuid4().hex}.deleting"
            )
            audio_path.replace(
                tombstone
            )

        try:
            VoiceRepository.delete(
                db,
                voice
            )
        except Exception:
            db.rollback()
            if tombstone is not None and tombstone.exists():
                tombstone.replace(
                    audio_path
                )
            raise

        if tombstone is not None:
            tombstone.unlink()

        return True
