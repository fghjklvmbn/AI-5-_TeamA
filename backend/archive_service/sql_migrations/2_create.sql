CREATE SCHEMA IF NOT EXISTS memorypal_archive;
SET search_path TO memorypal_archive, public;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;

--------------------------------------------------
-- sessions
--------------------------------------------------

CREATE TABLE IF NOT EXISTS sessions (

    id UUID PRIMARY KEY
    DEFAULT public.uuid_generate_v4(),

    user_id UUID,

    session_name VARCHAR(255)
    NOT NULL,

    created_at TIMESTAMP
    NOT NULL
    DEFAULT CURRENT_TIMESTAMP

);

--------------------------------------------------
-- voice_profiles
--------------------------------------------------

CREATE TABLE IF NOT EXISTS voice_profiles (

    id UUID PRIMARY KEY
    DEFAULT public.uuid_generate_v4(),

    voice_name VARCHAR(255)
    NOT NULL,

    audio_path TEXT
    NOT NULL,

    reference_text TEXT
    NOT NULL,

    description TEXT,

    owner_ref VARCHAR(64),

    registration_token_hash VARCHAR(64)
    UNIQUE,

    registration_state VARCHAR(16)
    NOT NULL
    DEFAULT 'active'
    CHECK (registration_state IN ('pending', 'active')),

    expires_at TIMESTAMPTZ,

    legacy_source_path TEXT,

    created_at TIMESTAMP
    NOT NULL
    DEFAULT CURRENT_TIMESTAMP

);

--------------------------------------------------
-- conversations
--------------------------------------------------

CREATE TABLE IF NOT EXISTS conversations (

    id UUID PRIMARY KEY
    DEFAULT public.uuid_generate_v4(),

    session_id UUID
    NOT NULL,

    user_text TEXT
    NOT NULL,

    assistant_text TEXT
    NOT NULL,

    input_audio_path TEXT,

    output_audio_path TEXT,

    voice_id UUID,

    created_at TIMESTAMP
    NOT NULL
    DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_conversation_session
    FOREIGN KEY (session_id)
    REFERENCES sessions(id)
    ON DELETE CASCADE,

    CONSTRAINT fk_conversation_voice
    FOREIGN KEY (voice_id)
    REFERENCES voice_profiles(id)
    ON DELETE SET NULL

);

--------------------------------------------------
-- memories
--------------------------------------------------

CREATE TABLE IF NOT EXISTS memories (

    id UUID PRIMARY KEY
    DEFAULT public.uuid_generate_v4(),

    session_id UUID
    NOT NULL,

    memory_type VARCHAR(50)

    CHECK (

        memory_type IN (

            'preference',
            'profile',
            'fact',
            'schedule',
            'relationship'

        )

    ),

    content TEXT
    NOT NULL,

    confidence FLOAT,

    created_at TIMESTAMP
    NOT NULL
    DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_memory_session
    FOREIGN KEY (session_id)
    REFERENCES sessions(id)
    ON DELETE CASCADE

);

CREATE TABLE IF NOT EXISTS voice_owner_states (
    owner_ref VARCHAR(64) PRIMARY KEY,
    state VARCHAR(16) NOT NULL DEFAULT 'active'
        CHECK (state IN ('active', 'purged')),
    created_at TIMESTAMPTZ NOT NULL,
    purged_at TIMESTAMPTZ
);
