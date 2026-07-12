from database.models import (
    Session
)


class SessionRepository:

    @staticmethod
    def save(
        db,
        session
    ):

        db.add(session)

        db.commit()

        db.refresh(session)

        return session

    @staticmethod
    def find_all(
        db
    ):

        return (

            db.query(
                Session
            )

            .order_by(
                Session.created_at.desc()
            )

            .all()
        )
    
    @staticmethod
    def find_by_id(
        db,
        session_id
    ):

        return (

            db.query(
                Session
            )

            .filter(
                Session.id
                == session_id
            )

            .first()
        )