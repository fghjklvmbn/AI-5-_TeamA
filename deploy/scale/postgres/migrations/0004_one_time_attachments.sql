ALTER TABLE attachments
    ADD COLUMN IF NOT EXISTS consumed_at TEXT;

CREATE INDEX IF NOT EXISTS idx_attachments_active_session
    ON attachments(user_id, session_id, created_at ASC)
    WHERE consumed_at IS NULL;
