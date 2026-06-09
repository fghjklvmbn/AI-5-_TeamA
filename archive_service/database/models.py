from sqlalchemy.orm import declarative_base

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    ForeignKey
)

Base = declarative_base()


class Session(Base):

    __tablename__ = "sessions"

    id = Column(
        String,
        primary_key=True
    )

    session_name = Column(
        String
    )

    created_at = Column(
        DateTime
    )


class Conversation(Base):

    __tablename__ = "conversations"

    id = Column(
        String,
        primary_key=True
    )

    session_id = Column(
        String,
        ForeignKey(
            "sessions.id"
        )
    )

    user_text = Column(
        Text
    )

    assistant_text = Column(
        Text
    )

    input_audio_path = Column(
        Text
    )

    output_audio_path = Column(
        Text
    )

    voice_id = Column(
        String
    )

    created_at = Column(
        DateTime
    )

class VoiceProfile(Base):

    __tablename__ = "voice_profiles"

    id = Column(
        String,
        primary_key=True
    )

    voice_name = Column(
        String
    )

    audio_path = Column(
        Text
    )

    reference_text = Column(
        Text
    )

    description = Column(
        Text
    )

    created_at = Column(
        DateTime
    )