from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.connect() as db:
            db.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS revoked_tokens (
                    jti TEXT PRIMARY KEY,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    user_text TEXT NOT NULL,
                    assistant_text TEXT NOT NULL,
                    input_audio_path TEXT,
                    output_audio_path TEXT,
                    created_at TEXT NOT NULL
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
                    confidence REAL NOT NULL DEFAULT 0.7,
                    importance REAL NOT NULL DEFAULT 0.5,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_accessed_at TEXT,
                    UNIQUE(user_id, normalized_content)
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user_updated
                    ON chat_sessions(user_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_conversations_session_created
                    ON conversations(session_id, created_at ASC);
                CREATE INDEX IF NOT EXISTS idx_memories_user_updated
                    ON memories(user_id, updated_at DESC);
                """
            )

    def fetch_one(self, query: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock, self.connect() as db:
            return db.execute(query, tuple(params)).fetchone()

    def fetch_all(self, query: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock, self.connect() as db:
            return db.execute(query, tuple(params)).fetchall()

    def execute(self, query: str, params: Iterable[Any] = ()) -> int:
        with self._lock, self.connect() as db:
            cursor = db.execute(query, tuple(params))
            db.commit()
            return cursor.rowcount

    def create_user(
        self,
        email: str,
        display_name: str,
        password_hash: str,
        password_salt: str,
    ) -> sqlite3.Row:
        user_id = str(uuid.uuid4())
        self.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, email.lower(), display_name, password_hash, password_salt, utc_now()),
        )
        return self.get_user_by_id(user_id)  # type: ignore[return-value]

    def get_user_by_email(self, email: str) -> sqlite3.Row | None:
        return self.fetch_one("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,))

    def get_user_by_id(self, user_id: str) -> sqlite3.Row | None:
        return self.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))

    def revoke_token(self, jti: str, expires_at: int) -> None:
        self.execute("INSERT OR REPLACE INTO revoked_tokens VALUES (?, ?)", (jti, expires_at))
        self.execute("DELETE FROM revoked_tokens WHERE expires_at < strftime('%s', 'now')")

    def is_token_revoked(self, jti: str) -> bool:
        return self.fetch_one("SELECT jti FROM revoked_tokens WHERE jti = ?", (jti,)) is not None

    def create_session(self, user_id: str, title: str = "새로운 대화") -> sqlite3.Row:
        session_id = str(uuid.uuid4())
        now = utc_now()
        self.execute(
            "INSERT INTO chat_sessions VALUES (?, ?, ?, ?, ?)",
            (session_id, user_id, title.strip() or "새로운 대화", now, now),
        )
        return self.get_session(user_id, session_id)  # type: ignore[return-value]

    def get_session(self, user_id: str, session_id: str) -> sqlite3.Row | None:
        return self.fetch_one(
            "SELECT * FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )

    def list_sessions(self, user_id: str) -> list[sqlite3.Row]:
        return self.fetch_all(
            "SELECT * FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        )

    def save_conversation(
        self,
        user_id: str,
        session_id: str,
        user_text: str,
        assistant_text: str,
        input_audio_path: str | None = None,
        output_audio_path: str | None = None,
    ) -> sqlite3.Row:
        conversation_id = str(uuid.uuid4())
        now = utc_now()
        with self._lock, self.connect() as db:
            db.execute(
                "INSERT INTO conversations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    conversation_id,
                    session_id,
                    user_id,
                    user_text,
                    assistant_text,
                    input_audio_path,
                    output_audio_path,
                    now,
                ),
            )
            db.execute(
                "UPDATE chat_sessions SET updated_at = ?, title = CASE WHEN title = '새로운 대화' "
                "THEN ? ELSE title END WHERE id = ? AND user_id = ?",
                (now, user_text[:32], session_id, user_id),
            )
            db.commit()
        return self.fetch_one("SELECT * FROM conversations WHERE id = ?", (conversation_id,))  # type: ignore[return-value]

    def get_history(self, user_id: str, session_id: str, limit: int = 50) -> list[sqlite3.Row]:
        return self.fetch_all(
            "SELECT * FROM (SELECT * FROM conversations WHERE user_id = ? AND session_id = ? "
            "ORDER BY created_at DESC LIMIT ?) ORDER BY created_at ASC",
            (user_id, session_id, limit),
        )

    def upsert_memory(
        self,
        user_id: str,
        session_id: str | None,
        memory_type: str,
        content: str,
        normalized_content: str,
        keywords: str,
        confidence: float,
        importance: float,
    ) -> sqlite3.Row:
        memory_id = str(uuid.uuid4())
        now = utc_now()
        self.execute(
            """
            INSERT INTO memories (
                id, user_id, session_id, memory_type, content, normalized_content,
                keywords, confidence, importance, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, normalized_content) DO UPDATE SET
                session_id = excluded.session_id,
                memory_type = excluded.memory_type,
                content = excluded.content,
                keywords = excluded.keywords,
                confidence = MAX(memories.confidence, excluded.confidence),
                importance = MAX(memories.importance, excluded.importance),
                updated_at = excluded.updated_at
            """,
            (
                memory_id,
                user_id,
                session_id,
                memory_type,
                content,
                normalized_content,
                keywords,
                confidence,
                importance,
                now,
                now,
            ),
        )
        return self.fetch_one(
            "SELECT * FROM memories WHERE user_id = ? AND normalized_content = ?",
            (user_id, normalized_content),
        )  # type: ignore[return-value]

    def list_memories(self, user_id: str, limit: int = 200) -> list[sqlite3.Row]:
        return self.fetch_all(
            "SELECT * FROM memories WHERE user_id = ? ORDER BY importance DESC, updated_at DESC LIMIT ?",
            (user_id, limit),
        )

    def touch_memories(self, user_id: str, memory_ids: list[str]) -> None:
        if not memory_ids:
            return
        placeholders = ",".join("?" for _ in memory_ids)
        self.execute(
            f"UPDATE memories SET last_accessed_at = ? WHERE user_id = ? AND id IN ({placeholders})",
            (utc_now(), user_id, *memory_ids),
        )

    def delete_memory(self, user_id: str, memory_id: str) -> bool:
        return bool(
            self.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id))
        )

