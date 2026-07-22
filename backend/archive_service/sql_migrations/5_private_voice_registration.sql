ALTER TABLE voice_profiles
    ADD COLUMN IF NOT EXISTS owner_ref VARCHAR(64),
    ADD COLUMN IF NOT EXISTS registration_token_hash VARCHAR(64),
    ADD COLUMN IF NOT EXISTS registration_state VARCHAR(16) NOT NULL DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS legacy_source_path TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_voice_profiles_registration_token_hash
    ON voice_profiles(registration_token_hash);

CREATE INDEX IF NOT EXISTS idx_voice_profiles_private_state_expiry
    ON voice_profiles(registration_state, expires_at);

CREATE TABLE IF NOT EXISTS voice_owner_states (
    owner_ref VARCHAR(64) PRIMARY KEY,
    state VARCHAR(16) NOT NULL DEFAULT 'active'
        CHECK (state IN ('active', 'purged')),
    created_at TIMESTAMPTZ NOT NULL,
    purged_at TIMESTAMPTZ
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_voice_profiles_registration_state'
    ) THEN
        ALTER TABLE voice_profiles
            ADD CONSTRAINT ck_voice_profiles_registration_state
            CHECK (registration_state IN ('pending', 'active'));
    END IF;
END
$$;
