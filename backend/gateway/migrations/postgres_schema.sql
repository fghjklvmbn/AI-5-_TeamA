CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    created_at TEXT NOT NULL,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    admin_ref TEXT NOT NULL UNIQUE DEFAULT gen_random_uuid()::text,
    auth_version INTEGER NOT NULL DEFAULT 1
        CONSTRAINT ck_users_auth_version CHECK (auth_version >= 1),
    account_status TEXT NOT NULL DEFAULT 'active' CONSTRAINT ck_users_account_status CHECK (
        account_status IN ('active','suspended','deactivated')
    ),
    status_version INTEGER NOT NULL DEFAULT 1
        CONSTRAINT ck_users_status_version CHECK (status_version >= 1),
    status_changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    suspended_at TIMESTAMPTZ,
    deactivated_at TIMESTAMPTZ
);
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_ref TEXT DEFAULT gen_random_uuid()::text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE users ADD COLUMN IF NOT EXISTS account_status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE users ADD COLUMN IF NOT EXISTS status_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE users ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS suspended_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS deactivated_at TIMESTAMPTZ;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'users'::regclass
          AND conname IN ('users_auth_version_check', 'ck_users_auth_version')
    ) THEN
        ALTER TABLE users ADD CONSTRAINT ck_users_auth_version
            CHECK (auth_version >= 1) NOT VALID;
        ALTER TABLE users VALIDATE CONSTRAINT ck_users_auth_version;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'users'::regclass
          AND conname IN ('users_account_status_check', 'ck_users_account_status')
    ) THEN
        ALTER TABLE users ADD CONSTRAINT ck_users_account_status
            CHECK (account_status IN ('active','suspended','deactivated')) NOT VALID;
        ALTER TABLE users VALIDATE CONSTRAINT ck_users_account_status;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'users'::regclass
          AND conname IN ('users_status_version_check', 'ck_users_status_version')
    ) THEN
        ALTER TABLE users ADD CONSTRAINT ck_users_status_version
            CHECK (status_version >= 1) NOT VALID;
        ALTER TABLE users VALIDATE CONSTRAINT ck_users_status_version;
    END IF;
END
$$;
UPDATE users SET status_changed_at = created_at::timestamptz
WHERE status_changed_at IS NULL;
ALTER TABLE users ALTER COLUMN status_changed_at SET NOT NULL;
ALTER TABLE users ALTER COLUMN status_changed_at SET DEFAULT CURRENT_TIMESTAMP;
UPDATE users SET admin_ref = gen_random_uuid()::text
WHERE admin_ref IS NULL OR admin_ref = '';
ALTER TABLE users ALTER COLUMN admin_ref SET DEFAULT gen_random_uuid()::text;
ALTER TABLE users ALTER COLUMN admin_ref SET NOT NULL;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'users'::regclass
          AND conname = 'ck_users_admin_ref_nonblank'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT ck_users_admin_ref_nonblank
            CHECK (btrim(admin_ref) <> '') NOT VALID;
        ALTER TABLE users VALIDATE CONSTRAINT ck_users_admin_ref_nonblank;
    END IF;
END
$$;
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_ci ON users (lower(email));
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_admin_ref ON users (admin_ref);
CREATE INDEX IF NOT EXISTS idx_users_created_admin_ref
    ON users(created_at DESC, admin_ref DESC);
CREATE INDEX IF NOT EXISTS idx_users_account_status_created
    ON users(account_status, created_at DESC, admin_ref DESC);

CREATE TABLE IF NOT EXISTS revoked_tokens (
    jti TEXT PRIMARY KEY,
    expires_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (id, user_id)
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_text TEXT NOT NULL,
    assistant_text TEXT NOT NULL,
    input_audio_path TEXT,
    output_audio_path TEXT,
    attachment_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id, user_id)
        REFERENCES chat_sessions(id, user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id TEXT REFERENCES chat_sessions(id) ON DELETE SET NULL,
    memory_type TEXT NOT NULL CHECK (
        memory_type IN ('preference','profile','fact','schedule','relationship')
    ),
    content TEXT NOT NULL,
    normalized_content TEXT NOT NULL,
    keywords TEXT NOT NULL DEFAULT '',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.7,
    importance DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_accessed_at TEXT,
    UNIQUE(user_id, normalized_content)
);

CREATE TABLE IF NOT EXISTS user_voice_profiles (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    voice_id TEXT NOT NULL,
    owner_ref TEXT,
    registration_state TEXT NOT NULL DEFAULT 'active' CHECK (
        registration_state IN ('provisional','active')
    ),
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, voice_id)
);
ALTER TABLE user_voice_profiles ADD COLUMN IF NOT EXISTS owner_ref TEXT;
ALTER TABLE user_voice_profiles ADD COLUMN IF NOT EXISTS registration_state TEXT
    NOT NULL DEFAULT 'active';

CREATE TABLE IF NOT EXISTS archive_voice_cleanup_jobs (
    id TEXT PRIMARY KEY,
    job_key TEXT NOT NULL UNIQUE,
    owner_ref TEXT NOT NULL CHECK (char_length(owner_ref) = 64),
    voice_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    available_at TIMESTAMPTZ NOT NULL,
    lease_owner TEXT,
    lease_token TEXT,
    lease_expires_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    text_content TEXT NOT NULL,
    file_content BYTEA,
    created_at TEXT NOT NULL,
    consumed_at TEXT,
    FOREIGN KEY (session_id, user_id)
        REFERENCES chat_sessions(id, user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS session_working_memory (
    session_id TEXT PRIMARY KEY REFERENCES chat_sessions(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    context TEXT NOT NULL,
    turn_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portraits (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    generation_id TEXT NOT NULL,
    account_auth_version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL CHECK (status IN ('empty','queued','analyzing','complete','failed')),
    persona TEXT NOT NULL DEFAULT 'default' CHECK (persona IN ('default','emotional_companion')),
    title TEXT CHECK (title IS NULL OR char_length(title) = 2),
    summary TEXT CHECK (summary IS NULL OR char_length(summary) <= 500),
    accuracy_percent INTEGER NOT NULL DEFAULT 0 CHECK (accuracy_percent BETWEEN 0 AND 100),
    analyzed_sessions INTEGER NOT NULL DEFAULT 0,
    analyzed_messages INTEGER NOT NULL DEFAULT 0,
    progress_percent INTEGER NOT NULL DEFAULT 0 CHECK (progress_percent BETWEEN 0 AND 100),
    vector_method TEXT,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    error TEXT,
    worker_id TEXT,
    lease_expires_at TEXT
);

ALTER TABLE portraits ADD COLUMN IF NOT EXISTS account_auth_version INTEGER NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS portrait_session_features (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    generation_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    total_messages INTEGER NOT NULL,
    relevant_messages INTEGER NOT NULL,
    weight DOUBLE PRECISION NOT NULL,
    summary TEXT NOT NULL,
    vector_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    vector_method TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    embedding VECTOR,
    vector_dimensions INTEGER,
    PRIMARY KEY (user_id, generation_id, session_id)
);

CREATE TABLE IF NOT EXISTS operation_states (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    request_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    resource_id TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('queued','running','retrying','succeeded','failed','cancelled')
    ),
    progress_percent INTEGER NOT NULL DEFAULT 0 CHECK (progress_percent BETWEEN 0 AND 100),
    version INTEGER NOT NULL DEFAULT 1,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    UNIQUE(request_id, operation_type)
);

CREATE TABLE IF NOT EXISTS operation_state_transitions (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL REFERENCES operation_states(id) ON DELETE CASCADE,
    from_status TEXT,
    to_status TEXT NOT NULL,
    version INTEGER NOT NULL,
    progress_percent INTEGER NOT NULL,
    reason TEXT,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_transaction_events (
    event_id TEXT NOT NULL,
    user_id TEXT,
    operation_id TEXT,
    request_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    http_method TEXT,
    http_path TEXT,
    http_status INTEGER,
    latency_ms INTEGER,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (event_id, occurred_at)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE IF NOT EXISTS admin_audit_events (
    id TEXT PRIMARY KEY,
    admin_ref TEXT,
    request_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    http_method TEXT NOT NULL,
    http_path TEXT NOT NULL,
    http_status INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL CHECK (latency_ms >= 0),
    action TEXT,
    target_admin_ref TEXT,
    before_status TEXT,
    after_status TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE admin_audit_events ADD COLUMN IF NOT EXISTS action TEXT;
ALTER TABLE admin_audit_events ADD COLUMN IF NOT EXISTS target_admin_ref TEXT;
ALTER TABLE admin_audit_events ADD COLUMN IF NOT EXISTS before_status TEXT;
ALTER TABLE admin_audit_events ADD COLUMN IF NOT EXISTS after_status TEXT;

CREATE TABLE IF NOT EXISTS admin_account_events (
    id TEXT PRIMARY KEY,
    actor_admin_ref TEXT NOT NULL,
    target_admin_ref TEXT NOT NULL,
    action TEXT NOT NULL CHECK (
        action IN ('admin_user_suspend','admin_user_unsuspend','admin_user_deactivate')
    ),
    before_status TEXT NOT NULL,
    after_status TEXT NOT NULL,
    status_version INTEGER NOT NULL,
    request_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_transaction_events_default
    PARTITION OF user_transaction_events DEFAULT;

CREATE TABLE IF NOT EXISTS event_outbox (
    event_id TEXT PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending','publishing','published','failed')
    ),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    locked_by TEXT,
    locked_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ
);
ALTER TABLE event_outbox ADD COLUMN IF NOT EXISTS locked_by TEXT;
ALTER TABLE event_outbox ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS rag_embeddings (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    namespace TEXT NOT NULL,
    source_id TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    vector_json JSONB NOT NULL,
    vector_dimensions INTEGER NOT NULL,
    embedding_model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    embedding VECTOR,
    UNIQUE(user_id, namespace, source_id, embedding_model)
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_updated
    ON chat_sessions(user_id, updated_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_conversations_session_created
    ON conversations(user_id, session_id, created_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_memories_user_updated
    ON memories(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_attachments_session_created
    ON attachments(user_id, session_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_portrait_features_user_generation
    ON portrait_session_features(user_id, generation_id);
CREATE INDEX IF NOT EXISTS idx_operations_user_updated
    ON operation_states(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_operations_correlation
    ON operation_states(correlation_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_operations_status_type_updated
    ON operation_states(status, operation_type, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_operations_updated_id
    ON operation_states(updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_operation_transitions_operation
    ON operation_state_transitions(operation_id, occurred_at ASC);
CREATE INDEX IF NOT EXISTS idx_transaction_events_user_time
    ON user_transaction_events(user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_transaction_events_correlation
    ON user_transaction_events(correlation_id, occurred_at ASC);
CREATE INDEX IF NOT EXISTS idx_transaction_events_operation
    ON user_transaction_events(operation_id, occurred_at ASC);
CREATE INDEX IF NOT EXISTS idx_transaction_events_path_status_time
    ON user_transaction_events(http_path, status, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_transaction_events_time_id
    ON user_transaction_events(occurred_at DESC, event_id DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_time
    ON admin_audit_events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_actor_time
    ON admin_audit_events(admin_ref, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_account_target_time
    ON admin_account_events(target_admin_ref, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_transaction_events_time_brin
    ON user_transaction_events USING brin(occurred_at);
CREATE INDEX IF NOT EXISTS idx_outbox_pending
    ON event_outbox(status, next_attempt_at, created_at)
    WHERE status IN ('pending', 'failed');
CREATE INDEX IF NOT EXISTS idx_outbox_claim_expiry
    ON event_outbox(locked_until)
    WHERE status = 'publishing';
CREATE INDEX IF NOT EXISTS idx_rag_embeddings_scope
    ON rag_embeddings(user_id, namespace, embedding_model, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_archive_voice_cleanup_claim
    ON archive_voice_cleanup_jobs(status, available_at, lease_expires_at);

CREATE INDEX IF NOT EXISTS idx_portrait_embedding_768_hnsw
    ON portrait_session_features
    USING hnsw ((embedding::vector(768)) vector_cosine_ops)
    WHERE embedding IS NOT NULL AND vector_dimensions = 768;
CREATE INDEX IF NOT EXISTS idx_portrait_embedding_384_hnsw
    ON portrait_session_features
    USING hnsw ((embedding::vector(384)) vector_cosine_ops)
    WHERE embedding IS NOT NULL AND vector_dimensions = 384;
CREATE INDEX IF NOT EXISTS idx_rag_embedding_768_hnsw
    ON rag_embeddings
    USING hnsw ((embedding::vector(768)) vector_cosine_ops)
    WHERE embedding IS NOT NULL AND vector_dimensions = 768;
CREATE INDEX IF NOT EXISTS idx_rag_embedding_384_hnsw
    ON rag_embeddings
    USING hnsw ((embedding::vector(384)) vector_cosine_ops)
    WHERE embedding IS NOT NULL AND vector_dimensions = 384;

CREATE OR REPLACE VIEW admin_transaction_hourly_metrics AS
SELECT
    date_trunc('hour', occurred_at) AS bucket_at,
    event_type,
    status,
    COALESCE(http_method, '') AS http_method,
    COALESCE(http_path, '') AS http_path,
    count(*) AS transaction_count,
    count(DISTINCT user_id) AS user_count,
    round(avg(latency_ms), 2) AS average_latency_ms,
    max(latency_ms) AS maximum_latency_ms
FROM user_transaction_events
GROUP BY 1, 2, 3, 4, 5;

CREATE OR REPLACE VIEW admin_operation_status_metrics AS
SELECT
    operation_type,
    status,
    count(*) AS operation_count,
    round(avg(progress_percent), 2) AS average_progress_percent,
    min(created_at) AS oldest_created_at,
    max(updated_at) AS latest_updated_at
FROM operation_states
GROUP BY operation_type, status;
