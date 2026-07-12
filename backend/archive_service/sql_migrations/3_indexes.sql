CREATE INDEX idx_sessions_created
ON sessions(created_at);

CREATE INDEX idx_conversations_session
ON conversations(session_id);

CREATE INDEX idx_conversations_created
ON conversations(created_at);

CREATE INDEX idx_memories_session
ON memories(session_id);

CREATE INDEX idx_memories_created
ON memories(created_at);