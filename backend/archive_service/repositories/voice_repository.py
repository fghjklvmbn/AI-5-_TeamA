from database.models import (
    VoiceOwnerState,
    VoiceProfile,
)

from datetime import datetime
from sqlalchemy import text


class VoiceRepository:

    @staticmethod
    def lock_owner(db, owner_ref: str, now: datetime):
        db.execute(
            text(
                "INSERT INTO voice_owner_states "
                "(owner_ref, state, created_at, purged_at) "
                "VALUES (:owner_ref, 'active', :created_at, NULL) "
                "ON CONFLICT(owner_ref) DO NOTHING"
            ),
            {"owner_ref": owner_ref, "created_at": now},
        )
        return (
            db.query(VoiceOwnerState)
            .filter(VoiceOwnerState.owner_ref == owner_ref)
            .with_for_update()
            .one()
        )

    @staticmethod
    def create(
        db,
        VoiceProfile
    ):

        db.add(
            VoiceProfile
        )

        db.commit()

        db.refresh(
            VoiceProfile
        )

        return VoiceProfile


    @staticmethod
    def get_all(
        db,
        default_voice_id,
    ):
        from database.models import (
            VoiceProfile
        )

        return (
            db.query(
                VoiceProfile
            )
            .filter(
                VoiceProfile.owner_ref.is_(None),
                VoiceProfile.registration_state == "active",
                VoiceProfile.id == default_voice_id,
            )
            .all()
        )


    @staticmethod
    def get_by_id(
        db,
        id,
        default_voice_id,
    ):

        from database.models import (
            VoiceProfile
        )

        return (

            db.query(
                VoiceProfile
            )

            .filter(
                VoiceProfile.id == id,
                VoiceProfile.owner_ref.is_(None),
                VoiceProfile.registration_state == "active",
                VoiceProfile.id == default_voice_id,
            )

            .first()
        )

    @staticmethod
    def get_internal_all(db):
        return (
            db.query(VoiceProfile)
            .filter(VoiceProfile.registration_state == "active")
            .all()
        )

    @staticmethod
    def get_internal_by_id(db, voice_id):
        return (
            db.query(VoiceProfile)
            .filter(
                VoiceProfile.id == voice_id,
                VoiceProfile.registration_state == "active",
            )
            .first()
        )

    @staticmethod
    def get_by_registration_token(db, registration_token_hash):
        return (
            db.query(VoiceProfile)
            .filter(
                VoiceProfile.registration_token_hash == registration_token_hash,
            )
            .first()
        )

    @staticmethod
    def get_owned_registration(db, voice_id, owner_ref, registration_token_hash):
        return (
            db.query(VoiceProfile)
            .filter(
                VoiceProfile.id == voice_id,
                VoiceProfile.owner_ref == owner_ref,
                VoiceProfile.registration_token_hash == registration_token_hash,
            )
            .first()
        )

    @staticmethod
    def get_owned_voice(db, voice_id, owner_ref):
        return (
            db.query(VoiceProfile)
            .filter(
                VoiceProfile.id == voice_id,
                VoiceProfile.owner_ref == owner_ref,
            )
            .with_for_update()
            .first()
        )

    @staticmethod
    def get_owned_or_legacy_voice(db, voice_id, owner_ref):
        return (
            db.query(VoiceProfile)
            .filter(
                VoiceProfile.id == voice_id,
                (
                    (VoiceProfile.owner_ref == owner_ref)
                    | VoiceProfile.owner_ref.is_(None)
                ),
            )
            .with_for_update()
            .first()
        )

    @staticmethod
    def get_legacy_or_adopted_voice_for_update(db, voice_id, owner_ref):
        return VoiceRepository.get_owned_or_legacy_voice(db, voice_id, owner_ref)

    @staticmethod
    def list_owned_voices_for_update(db, owner_ref):
        return (
            db.query(VoiceProfile)
            .filter(VoiceProfile.owner_ref == owner_ref)
            .with_for_update()
            .all()
        )

    @staticmethod
    def activate(db, voice):
        voice.registration_state = "active"
        voice.expires_at = None
        db.commit()
        db.refresh(voice)
        return voice

    @staticmethod
    def delete(db, voice):
        db.delete(voice)
        db.commit()

    @staticmethod
    def list_expired_pending(db, now: datetime, limit: int = 100):
        return (
            db.query(VoiceProfile)
            .filter(
                VoiceProfile.registration_state == "pending",
                VoiceProfile.expires_at.is_not(None),
                VoiceProfile.expires_at <= now,
            )
            .order_by(VoiceProfile.expires_at.asc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def list_private_audio_paths(db):
        return {
            str(row[0])
            for row in db.query(VoiceProfile.audio_path)
            .filter(VoiceProfile.owner_ref.is_not(None))
            .all()
        }
