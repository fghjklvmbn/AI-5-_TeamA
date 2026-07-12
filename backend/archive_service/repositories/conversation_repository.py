from database.models import (
    Conversation
)


class ConversationRepository:

    @staticmethod
    def save(
        db,
        conversation
    ):

        db.add(
            conversation
        )

        db.commit()

        db.refresh(
            conversation
        )

        return conversation

    @staticmethod
    def find_by_session_id(
        db,
        session_id
    ):

        from database.models import (
            Conversation
        )

        return (

            db.query(
                Conversation
            )

            .filter(
                Conversation.session_id
                == session_id
            )

            .order_by(
                Conversation.created_at.asc()
            )

            .all()
        )