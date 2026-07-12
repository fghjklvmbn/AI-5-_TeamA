from database.models import (
    VoiceProfile
)


class VoiceRepository:

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
        db
    ):
        from database.models import (
            VoiceProfile
        )

        return (
            db.query(
                VoiceProfile
            )
            .all()
        )


    @staticmethod
    def get_by_id(
        db,
        id
    ):

        from database.models import (
            VoiceProfile
        )

        return (

            db.query(
                VoiceProfile
            )

            .filter(
                VoiceProfile.id
                == id
            )

            .first()
        )