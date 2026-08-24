ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS attachment_refs_json TEXT NOT NULL DEFAULT '[]';

ALTER TABLE attachments
    ADD COLUMN IF NOT EXISTS file_content BYTEA;
