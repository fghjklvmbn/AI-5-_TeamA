from sqlalchemy.orm import declarative_base

from sqlalchemy import (
    CheckConstraint,
    Column,
    String,
    Text,
    DateTime,
    ForeignKey,
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

    __table_args__ = (
        CheckConstraint(
            "registration_state IN ('pending', 'active')",
            name="ck_voice_profiles_registration_state",
        ),
    )

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

    # New Gateway-managed voices are private Archive records.  Legacy voices
    # keep these fields NULL and remain visible through the compatibility API.
    owner_ref = Column(
        String(64),
        nullable=True,
        index=True,
    )

    registration_token_hash = Column(
        String(64),
        nullable=True,
        unique=True,
    )

    registration_state = Column(
        String(16),
        nullable=False,
        default="active",
        server_default="active",
        index=True,
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    legacy_source_path = Column(
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime
    )


class VoiceOwnerState(Base):
    """Permanent owner guard serializing registration with hard deletion."""

    __tablename__ = "voice_owner_states"

    __table_args__ = (
        CheckConstraint(
            "state IN ('active', 'purged')",
            name="ck_voice_owner_states_state",
        ),
    )

    owner_ref = Column(String(64), primary_key=True)
    state = Column(
        String(16), nullable=False, default="active", server_default="active",
    )
    created_at = Column(DateTime(timezone=True), nullable=False)
    purged_at = Column(DateTime(timezone=True), nullable=True)
