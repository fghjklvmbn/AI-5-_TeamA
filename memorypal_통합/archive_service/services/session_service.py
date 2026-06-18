import uuid

from datetime import datetime

from database.models import Session

from repositories.session_repository import (
    SessionRepository
)


class SessionService:

    @staticmethod
    def create(
        db,
        payload
    ):

        session = Session(

            id=str(
                uuid.uuid4()
            ),

            session_name=
            payload.session_name,

            created_at=
            datetime.now()
        )

        return (
            SessionRepository.save(
                db,
                session
            )
        )
    
    @staticmethod
    def get_all(
        db
    ):

        return (

            SessionRepository
            .find_all(
                db
            )
        )
    
    @staticmethod
    def get_by_id(
        db,
        session_id
    ):

        return (

            SessionRepository
            .find_by_id(
                db,
                session_id
            )
        )