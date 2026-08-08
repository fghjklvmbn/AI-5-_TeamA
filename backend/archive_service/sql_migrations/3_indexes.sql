CREATE SCHEMA IF NOT EXISTS memorypal_archive;
SET search_path TO memorypal_archive, public;

CREATE INDEX IF NOT EXISTS idx_sessions_created
ON sessions(created_at);

CREATE INDEX IF NOT EXISTS idx_conversations_session
ON conversations(session_id);

CREATE INDEX IF NOT EXISTS idx_conversations_created
ON conversations(created_at);

CREATE INDEX IF NOT EXISTS idx_memories_session
ON memories(session_id);

CREATE INDEX IF NOT EXISTS idx_memories_created
ON memories(created_at);
