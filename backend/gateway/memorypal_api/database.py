from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


OPERATION_TRANSITIONS = {
    "queued": {"running", "failed", "cancelled"},
    "running": {"retrying", "succeeded", "failed", "cancelled"},
    "retrying": {"queued", "running", "failed", "cancelled"},
    "succeeded": set(),
    "failed": set(),
    "cancelled": set(),
}


class DatabaseIntegrityError(RuntimeError):
    """Backend-neutral constraint violation used at the API boundary."""


class AccountStateTransitionError(RuntimeError):
    """Stable API-facing failure code for a rejected account status transition."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class AccountAccessFenceError(RuntimeError):
    """Raised when a write was started with stale or disabled account authority."""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()

    @property
    def backend_name(self) -> str:
        return "sqlite"

    def close(self) -> None:
        """SQLite connections are short-lived, so there is no shared pool to close."""

    # 연결, SQLite3 사용해서 하나의 파일로 저장됨(위 __init__ 연계)
    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def transaction(self):
        """Open one atomic write unit; production adapters override connection pooling."""
        with self._lock, closing(self.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    def _require_account_fence(
        self,
        db,
        user_id: str,
        expected_auth_version: int,
        *,
        lock_mode: str = "share",
    ) -> None:
        # PostgreSQL row locks linearize an in-flight write with an administrator's
        # FOR UPDATE transition. SQLite is already serialized by BEGIN IMMEDIATE.
        if lock_mode not in {"share", "update"}:
            raise ValueError("account fence lock_mode must be 'share' or 'update'")
        lock_suffix = ""
        if self.backend_name == "postgresql+pgvector":
            lock_suffix = " FOR UPDATE" if lock_mode == "update" else " FOR SHARE"
        row = db.execute(
            "SELECT 1 FROM users WHERE id = ? AND account_status = 'active' "
            "AND auth_version = ?" + lock_suffix,
            (user_id, expected_auth_version),
        ).fetchone()
        if row is None:
            raise AccountAccessFenceError("account_authority_changed")

    def is_account_fence_valid(self, user_id: str, expected_auth_version: int) -> bool:
        return self.fetch_one(
            "SELECT 1 FROM users WHERE id = ? AND account_status = 'active' "
            "AND auth_version = ?",
            (user_id, expected_auth_version),
        ) is not None

    # 테이블 생성 및 인덱스 생성
    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, closing(self.connect()) as db:
            db.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1)),
                    admin_ref TEXT UNIQUE,
                    auth_version INTEGER NOT NULL DEFAULT 1 CHECK (auth_version >= 1),
                    account_status TEXT NOT NULL DEFAULT 'active' CHECK (
                        account_status IN ('active','suspended','deactivated')
                    ),
                    status_version INTEGER NOT NULL DEFAULT 1 CHECK (status_version >= 1),
                    status_changed_at TEXT NOT NULL,
                    suspended_at TEXT,
                    deactivated_at TEXT
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
                CREATE TABLE IF NOT EXISTS archive_voice_cleanup_jobs (
                    id TEXT PRIMARY KEY,
                    job_key TEXT NOT NULL UNIQUE,
                    owner_ref TEXT NOT NULL CHECK (length(owner_ref) = 64),
                    voice_id TEXT,
                    status TEXT NOT NULL DEFAULT 'pending' CHECK (
                        status IN ('pending','running')
                    ),
                    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
                    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
                    available_at TEXT NOT NULL,
                    lease_owner TEXT,
                    lease_token TEXT,
                    lease_expires_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    text_content TEXT NOT NULL,
                    created_at TEXT NOT NULL
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
                    status TEXT NOT NULL CHECK (
                        status IN ('empty','queued','analyzing','complete','failed')
                    ),
                    persona TEXT NOT NULL DEFAULT 'default' CHECK (
                        persona IN ('default','emotional_companion')
                    ),
                    title TEXT CHECK (title IS NULL OR length(title) = 2),
                    summary TEXT CHECK (summary IS NULL OR length(summary) <= 500),
                    accuracy_percent INTEGER NOT NULL DEFAULT 0 CHECK (
                        accuracy_percent BETWEEN 0 AND 100
                    ),
                    analyzed_sessions INTEGER NOT NULL DEFAULT 0,
                    analyzed_messages INTEGER NOT NULL DEFAULT 0,
                    progress_percent INTEGER NOT NULL DEFAULT 0 CHECK (
                        progress_percent BETWEEN 0 AND 100
                    ),
                    vector_method TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL,
                    error TEXT,
                    worker_id TEXT,
                    lease_expires_at TEXT
                );
                CREATE TABLE IF NOT EXISTS portrait_session_features (
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    generation_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    total_messages INTEGER NOT NULL,
                    relevant_messages INTEGER NOT NULL,
                    weight REAL NOT NULL,
                    summary TEXT NOT NULL,
                    vector_json TEXT NOT NULL DEFAULT '[]',
                    vector_method TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
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
                    progress_percent INTEGER NOT NULL DEFAULT 0 CHECK (
                        progress_percent BETWEEN 0 AND 100
                    ),
                    version INTEGER NOT NULL DEFAULT 1,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
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
                    event_id TEXT PRIMARY KEY,
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
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    occurred_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS admin_audit_events (
                    id TEXT PRIMARY KEY,
                    admin_ref TEXT,
                    request_id TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    http_method TEXT NOT NULL,
                    http_path TEXT NOT NULL,
                    http_status INTEGER NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    action TEXT,
                    target_admin_ref TEXT,
                    before_status TEXT,
                    after_status TEXT,
                    occurred_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS admin_account_events (
                    id TEXT PRIMARY KEY,
                    actor_admin_ref TEXT NOT NULL,
                    target_admin_ref TEXT NOT NULL,
                    action TEXT NOT NULL CHECK (
                        action IN ('admin_user_suspend','admin_user_unsuspend',
                                   'admin_user_deactivate')
                    ),
                    before_status TEXT NOT NULL,
                    after_status TEXT NOT NULL,
                    status_version INTEGER NOT NULL,
                    request_id TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS event_outbox (
                    event_id TEXT PRIMARY KEY REFERENCES user_transaction_events(event_id) ON DELETE CASCADE,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending' CHECK (
                        status IN ('pending','publishing','published','failed')
                    ),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT,
                    locked_by TEXT,
                    locked_until TEXT,
                    created_at TEXT NOT NULL,
                    published_at TEXT
                );
                CREATE TABLE IF NOT EXISTS rag_embeddings (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    vector_json TEXT NOT NULL,
                    vector_dimensions INTEGER NOT NULL,
                    embedding_model TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, namespace, source_id, embedding_model)
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user_updated
                    ON chat_sessions(user_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_conversations_session_created
                    ON conversations(session_id, created_at ASC);
                CREATE INDEX IF NOT EXISTS idx_conversations_user_created
                    ON conversations(user_id, created_at DESC);
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
                CREATE INDEX IF NOT EXISTS idx_outbox_status_retry
                    ON event_outbox(status, next_attempt_at, created_at);
                CREATE INDEX IF NOT EXISTS idx_rag_embeddings_scope
                    ON rag_embeddings(user_id, namespace, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_archive_voice_cleanup_claim
                    ON archive_voice_cleanup_jobs(status, available_at, lease_expires_at);
                """
            )
            # Additive bootstrap for databases created by an earlier release.
            outbox_columns = {
                row[1] for row in db.execute("PRAGMA table_info(event_outbox)").fetchall()
            }
            if "locked_by" not in outbox_columns:
                db.execute("ALTER TABLE event_outbox ADD COLUMN locked_by TEXT")
            if "locked_until" not in outbox_columns:
                db.execute("ALTER TABLE event_outbox ADD COLUMN locked_until TEXT")
            user_columns = {
                row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()
            }
            if "is_admin" not in user_columns:
                db.execute(
                    "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0 "
                    "CHECK (is_admin IN (0, 1))"
                )
            if "admin_ref" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN admin_ref TEXT")
            if "auth_version" not in user_columns:
                db.execute(
                    "ALTER TABLE users ADD COLUMN auth_version INTEGER NOT NULL DEFAULT 1 "
                    "CHECK (auth_version >= 1)"
                )
            if "account_status" not in user_columns:
                db.execute(
                    "ALTER TABLE users ADD COLUMN account_status TEXT NOT NULL "
                    "DEFAULT 'active' CHECK ("
                    "account_status IN ('active','suspended','deactivated'))"
                )
            if "status_changed_at" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN status_changed_at TEXT")
            if "status_version" not in user_columns:
                db.execute(
                    "ALTER TABLE users ADD COLUMN status_version INTEGER NOT NULL DEFAULT 1 "
                    "CHECK (status_version >= 1)"
                )
            if "suspended_at" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN suspended_at TEXT")
            if "deactivated_at" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN deactivated_at TEXT")
            voice_columns = {
                row[1] for row in db.execute(
                    "PRAGMA table_info(user_voice_profiles)"
                ).fetchall()
            }
            if "owner_ref" not in voice_columns:
                db.execute("ALTER TABLE user_voice_profiles ADD COLUMN owner_ref TEXT")
            if "registration_state" not in voice_columns:
                db.execute(
                    "ALTER TABLE user_voice_profiles ADD COLUMN registration_state "
                    "TEXT NOT NULL DEFAULT 'active' CHECK ("
                    "registration_state IN ('provisional','active'))"
                )
            db.execute(
                "UPDATE users SET status_changed_at = created_at "
                "WHERE status_changed_at IS NULL OR status_changed_at = ''"
            )
            audit_columns = {
                row[1] for row in db.execute("PRAGMA table_info(admin_audit_events)").fetchall()
            }
            for column in ("action", "target_admin_ref", "before_status", "after_status"):
                if column not in audit_columns:
                    db.execute(f"ALTER TABLE admin_audit_events ADD COLUMN {column} TEXT")
            portrait_columns = {
                row[1] for row in db.execute("PRAGMA table_info(portraits)").fetchall()
            }
            if "account_auth_version" not in portrait_columns:
                db.execute(
                    "ALTER TABLE portraits ADD COLUMN account_auth_version "
                    "INTEGER NOT NULL DEFAULT 1"
                )
            db.execute(
                "UPDATE portraits SET account_auth_version = COALESCE(("
                "SELECT auth_version FROM users WHERE users.id = portraits.user_id"
                "), account_auth_version) WHERE status NOT IN ('queued','analyzing')"
            )
            for row in db.execute(
                "SELECT id FROM users WHERE admin_ref IS NULL OR admin_ref = ''"
            ).fetchall():
                db.execute(
                    "UPDATE users SET admin_ref = ? WHERE id = ?",
                    (str(uuid.uuid4()), row["id"]),
                )
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_admin_ref ON users(admin_ref)"
            )
            db.execute(
                "CREATE TRIGGER IF NOT EXISTS trg_users_admin_ref_required_insert "
                "BEFORE INSERT ON users FOR EACH ROW "
                "WHEN NEW.admin_ref IS NULL OR NEW.admin_ref = '' "
                "BEGIN SELECT RAISE(ABORT, 'users.admin_ref is required'); END"
            )
            db.execute(
                "CREATE TRIGGER IF NOT EXISTS trg_users_admin_ref_required_update "
                "BEFORE UPDATE OF admin_ref ON users FOR EACH ROW "
                "WHEN NEW.admin_ref IS NULL OR NEW.admin_ref = '' "
                "BEGIN SELECT RAISE(ABORT, 'users.admin_ref is required'); END"
            )
            db.execute(
                "CREATE TRIGGER IF NOT EXISTS trg_users_admin_ref_nonblank_insert "
                "BEFORE INSERT ON users FOR EACH ROW "
                "WHEN NEW.admin_ref IS NULL OR trim(NEW.admin_ref) = '' "
                "BEGIN SELECT RAISE(ABORT, 'users.admin_ref is required'); END"
            )
            db.execute(
                "CREATE TRIGGER IF NOT EXISTS trg_users_admin_ref_nonblank_update "
                "BEFORE UPDATE OF admin_ref ON users FOR EACH ROW "
                "WHEN NEW.admin_ref IS NULL OR trim(NEW.admin_ref) = '' "
                "BEGIN SELECT RAISE(ABORT, 'users.admin_ref is required'); END"
            )
            db.execute(
                "CREATE TRIGGER IF NOT EXISTS trg_users_status_changed_at_required_insert "
                "BEFORE INSERT ON users FOR EACH ROW "
                "WHEN NEW.status_changed_at IS NULL OR trim(NEW.status_changed_at) = '' "
                "BEGIN SELECT RAISE(ABORT, 'users.status_changed_at is required'); END"
            )
            db.execute(
                "CREATE TRIGGER IF NOT EXISTS trg_users_status_changed_at_required_update "
                "BEFORE UPDATE OF status_changed_at ON users FOR EACH ROW "
                "WHEN NEW.status_changed_at IS NULL OR trim(NEW.status_changed_at) = '' "
                "BEGIN SELECT RAISE(ABORT, 'users.status_changed_at is required'); END"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_users_created_admin_ref "
                "ON users(created_at DESC, admin_ref DESC)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_users_account_status_created "
                "ON users(account_status, created_at DESC, admin_ref DESC)"
            )
            db.commit()
    # 하나의 값만 새로고침
    def fetch_one(self, query: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock, closing(self.connect()) as db:
            return db.execute(query, tuple(params)).fetchone()

    # 모든 값을 새로고침
    def fetch_all(self, query: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock, closing(self.connect()) as db:
            return db.execute(query, tuple(params)).fetchall()

    # DB 반영
    def execute(self, query: str, params: Iterable[Any] = ()) -> int:
        with self._lock, closing(self.connect()) as db:
            cursor = db.execute(query, tuple(params))
            db.commit()
            return cursor.rowcount

    # 사용자 생성
    def create_user(
        self,
        email: str,
        display_name: str,
        password_hash: str,
        password_salt: str,
    ) -> sqlite3.Row:
        user_id = str(uuid.uuid4())
        now = utc_now()
        self.execute(
            "INSERT INTO users (id, email, display_name, password_hash, password_salt, "
            "created_at, is_admin, admin_ref, auth_version, account_status, "
            "status_version, status_changed_at, suspended_at, deactivated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'active', 1, ?, NULL, NULL)",
            (
                user_id, email.lower(), display_name, password_hash, password_salt,
                now, False, str(uuid.uuid4()), now,
            ),
        )
        return self.get_user_by_id(user_id)  # type: ignore[return-value]

    def is_admin_user(self, user_id: str) -> bool:
        row = self.fetch_one("SELECT is_admin FROM users WHERE id = ?", (user_id,))
        return row is not None and bool(row["is_admin"])

    def get_user_by_admin_ref(self, admin_ref: str):
        return self.fetch_one("SELECT * FROM users WHERE admin_ref = ?", (admin_ref,))

    def transition_admin_account_status(
        self,
        *,
        actor_user_id: str,
        actor_admin_ref: str,
        actor_expected_auth_version: int,
        target_admin_ref: str,
        action: str,
        expected_version: int,
        protected_admin_emails: Iterable[str],
        request_id: str,
        correlation_id: str,
    ) -> tuple[Any, bool, str]:
        transitions = {
            "admin_user_suspend": ("suspended", {"active"}),
            "admin_user_unsuspend": ("active", {"suspended"}),
            "admin_user_deactivate": ("deactivated", {"active", "suspended"}),
        }
        if action not in transitions:
            raise ValueError(f"unsupported admin account action: {action}")
        desired_status, allowed_from = transitions[action]
        protected = {str(email).casefold() for email in protected_admin_emails}
        lock_suffix = " FOR UPDATE" if self.backend_name == "postgresql+pgvector" else ""
        with self.transaction() as db:
            # Lock actor and target in one stable id order. Two administrators
            # targeting each other can no longer acquire the same rows in reverse
            # order and deadlock PostgreSQL.
            locked_rows = db.execute(
                "SELECT * FROM users WHERE id = ? OR admin_ref = ? "
                "ORDER BY id" + lock_suffix,
                (actor_user_id, target_admin_ref),
            ).fetchall()
            actor = next(
                (row for row in locked_rows if str(row["id"]) == actor_user_id),
                None,
            )
            if (
                actor is None
                or str(actor["admin_ref"]) != actor_admin_ref
                or str(actor["account_status"]) != "active"
                or int(actor["auth_version"]) != actor_expected_auth_version
                or not (
                    bool(actor["is_admin"])
                    or str(actor["email"]).casefold() in protected
                )
            ):
                raise AccountStateTransitionError("actor_forbidden")
            current = next(
                (
                    row for row in locked_rows
                    if str(row["admin_ref"] or "") == target_admin_ref
                ),
                None,
            )
            if current is None:
                raise AccountStateTransitionError("target_not_found")
            if str(current["id"]) == actor_user_id:
                raise AccountStateTransitionError("self_target")
            if bool(current["is_admin"]) or str(current["email"]).casefold() in protected:
                raise AccountStateTransitionError("protected_admin")
            before_status = str(current["account_status"])
            if before_status == desired_status:
                return current, False, before_status
            if int(current["status_version"]) != expected_version:
                raise AccountStateTransitionError("version_conflict")
            if before_status == "deactivated":
                raise AccountStateTransitionError("deactivated_terminal")
            if before_status not in allowed_from:
                raise AccountStateTransitionError("invalid_transition")

            now = utc_now()
            next_version = int(current["status_version"]) + 1
            suspended_at = now if desired_status == "suspended" else None
            deactivated_at = now if desired_status == "deactivated" else None
            cursor = db.execute(
                "UPDATE users SET account_status = ?, status_version = ?, "
                "status_changed_at = ?, suspended_at = ?, deactivated_at = ?, "
                "auth_version = auth_version + 1 WHERE id = ? AND account_status = ? "
                "AND status_version = ? AND is_admin = ?",
                (
                    desired_status, next_version, now, suspended_at, deactivated_at,
                    current["id"], before_status, expected_version, False,
                ),
            )
            if cursor.rowcount != 1:
                raise AccountStateTransitionError("version_conflict")
            if desired_status != "active":
                db.execute(
                    "UPDATE portraits SET status = 'failed', error = 'account_inactive', "
                    "completed_at = ?, updated_at = ?, worker_id = NULL, "
                    "lease_expires_at = NULL WHERE user_id = ? "
                    "AND status IN ('queued','analyzing')",
                    (now, now, current["id"]),
                )
            db.execute(
                "INSERT INTO admin_account_events (id, actor_admin_ref, target_admin_ref, "
                "action, before_status, after_status, status_version, request_id, "
                "correlation_id, occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()), actor_admin_ref, target_admin_ref, action,
                    before_status, desired_status, next_version, request_id,
                    correlation_id, now,
                ),
            )
            updated = db.execute(
                "SELECT * FROM users WHERE id = ?", (current["id"],),
            ).fetchone()
        return updated, True, before_status

    def update_user_display_name(
        self, user_id: str, display_name: str, *, expected_auth_version: int,
    ):
        with self.transaction() as db:
            self._require_account_fence(
                db, user_id, expected_auth_version, lock_mode="update",
            )
            cursor = db.execute(
                "UPDATE users SET display_name = ? WHERE id = ? AND auth_version = ?",
                (display_name, user_id, expected_auth_version),
            )
            if cursor.rowcount != 1:
                return None
            return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def change_user_password(
        self,
        user_id: str,
        *,
        expected_hash: str,
        expected_salt: str,
        expected_auth_version: int,
        password_hash: str,
        password_salt: str,
        token_jti: str,
        token_expires_at: int,
    ) -> bool:
        """Rotate credentials, invalidate every JWT version, and revoke this token atomically."""
        with self.transaction() as db:
            self._require_account_fence(
                db, user_id, expected_auth_version, lock_mode="update",
            )
            cursor = db.execute(
                "UPDATE users SET password_hash = ?, password_salt = ?, "
                "auth_version = auth_version + 1 WHERE id = ? "
                "AND password_hash = ? AND password_salt = ? AND auth_version = ?",
                (
                    password_hash, password_salt, user_id,
                    expected_hash, expected_salt, expected_auth_version,
                ),
            )
            if cursor.rowcount != 1:
                return False
            db.execute(
                "INSERT INTO revoked_tokens (jti, expires_at) VALUES (?, ?) "
                "ON CONFLICT(jti) DO UPDATE SET expires_at = excluded.expires_at",
                (token_jti, token_expires_at),
            )
            db.execute("DELETE FROM revoked_tokens WHERE expires_at < ?", (int(time.time()),))
        return True

    def delete_user_account(
        self,
        user_id: str,
        *,
        expected_hash: str,
        expected_salt: str,
        expected_auth_version: int,
        token_jti: str,
        token_expires_at: int,
        archive_owner_ref: str | None = None,
        archive_default_voice_id: str | None = None,
    ) -> bool:
        """Delete the account graph and retain only the current token revocation marker."""
        with self.transaction() as db:
            # Acquire the final lock mode immediately. Upgrading FOR SHARE to
            # FOR UPDATE can deadlock with an administrator status transition.
            self._require_account_fence(
                db, user_id, expected_auth_version, lock_mode="update",
            )
            current = db.execute(
                "SELECT 1 FROM users WHERE id = ? "
                "AND password_hash = ? AND password_salt = ?",
                (user_id, expected_hash, expected_salt),
            ).fetchone()
            if current is None:
                return False
            if archive_owner_ref is not None:
                current_owner_ref = self._validate_archive_owner_ref(archive_owner_ref)
                owner_refs = {current_owner_ref}
                legacy_voice_ids = {
                    str(item["voice_id"])
                    for item in db.execute(
                        "SELECT voice_id FROM user_voice_profiles "
                        "WHERE user_id = ? AND owner_ref IS NULL",
                        (user_id,),
                    ).fetchall()
                    if str(item["voice_id"]) != archive_default_voice_id
                }
                owner_refs.update(
                    self._validate_archive_owner_ref(str(item["owner_ref"]))
                    for item in db.execute(
                        "SELECT DISTINCT owner_ref FROM user_voice_profiles "
                        "WHERE user_id = ? AND owner_ref IS NOT NULL",
                        (user_id,),
                    ).fetchall()
                )
                for owner_ref in owner_refs:
                    self._enqueue_archive_voice_cleanup_in_transaction(
                        db, owner_ref=owner_ref,
                    )
                for voice_id in legacy_voice_ids:
                    self._enqueue_archive_voice_cleanup_in_transaction(
                        db, owner_ref=current_owner_ref, voice_id=voice_id,
                    )
            cursor = db.execute(
                "DELETE FROM users WHERE id = ? AND password_hash = ? AND password_salt = ?",
                (user_id, expected_hash, expected_salt),
            )
            if cursor.rowcount != 1:
                return False
            # Foreign keys remove the account graph. Explicit cleanup covers
            # stores and operational history that intentionally have no user FK.
            db.execute("DELETE FROM rag_embeddings WHERE user_id = ?", (user_id,))
            db.execute(
                "DELETE FROM event_outbox WHERE event_id IN ("
                "SELECT event_id FROM user_transaction_events WHERE user_id = ?)",
                (user_id,),
            )
            db.execute(
                "DELETE FROM event_outbox WHERE aggregate_id IN ("
                "SELECT id FROM operation_states WHERE user_id = ?)",
                (user_id,),
            )
            db.execute(
                "DELETE FROM user_transaction_events WHERE user_id = ?",
                (user_id,),
            )
            db.execute(
                "DELETE FROM operation_states WHERE user_id = ?",
                (user_id,),
            )
            # Administrative audit/domain events retain only the pseudonymous
            # admin_ref and must outlive a user's product-data hard deletion.
            db.execute(
                "INSERT INTO revoked_tokens (jti, expires_at) VALUES (?, ?) "
                "ON CONFLICT(jti) DO UPDATE SET expires_at = excluded.expires_at",
                (token_jti, token_expires_at),
            )
            db.execute("DELETE FROM revoked_tokens WHERE expires_at < ?", (int(time.time()),))
        return True

    @staticmethod
    def _validate_archive_owner_ref(owner_ref: str) -> str:
        normalized = owner_ref.strip().casefold()
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("archive owner reference must be 64 lowercase hex characters")
        return normalized

    def _enqueue_archive_voice_cleanup_in_transaction(
        self,
        db,
        *,
        owner_ref: str,
        voice_id: str | None = None,
        delay_seconds: float = 0,
    ) -> str:
        owner_ref = self._validate_archive_owner_ref(owner_ref)
        job_key = f"{owner_ref}:{voice_id or '*'}"
        now = datetime.now(UTC)
        available_at = (now + timedelta(seconds=max(0, delay_seconds))).isoformat()
        job_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO archive_voice_cleanup_jobs ("
            "id, job_key, owner_ref, voice_id, status, attempt_count, version, "
            "available_at, lease_owner, lease_token, lease_expires_at, last_error, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, 'pending', 0, 1, ?, "
            "NULL, NULL, NULL, NULL, ?, ?) ON CONFLICT(job_key) DO NOTHING",
            (
                job_id, job_key, owner_ref, voice_id, available_at,
                now.isoformat(), now.isoformat(),
            ),
        )
        # A newly discovered immediate failure must accelerate an older
        # provisional-TTL job without stealing a live worker lease.
        if delay_seconds <= 0:
            db.execute(
                "UPDATE archive_voice_cleanup_jobs SET available_at = ?, "
                "updated_at = ?, last_error = NULL WHERE job_key = ? "
                "AND status = 'pending'",
                (available_at, now.isoformat(), job_key),
            )
        return job_key

    def enqueue_archive_voice_cleanup(
        self,
        *,
        owner_ref: str,
        voice_id: str | None = None,
        delay_seconds: float = 0,
    ) -> str:
        with self.transaction() as db:
            return self._enqueue_archive_voice_cleanup_in_transaction(
                db,
                owner_ref=owner_ref,
                voice_id=voice_id,
                delay_seconds=delay_seconds,
            )

    def claim_archive_voice_cleanup(
        self,
        worker_id: str,
        *,
        lease_seconds: float = 30,
        owner_ref: str | None = None,
    ):
        now = datetime.now(UTC)
        now_value = now.isoformat()
        lease_expires_at = (
            now + timedelta(seconds=max(1, lease_seconds))
        ).isoformat()
        params: list[Any] = [now_value, now_value]
        owner_clause = ""
        if owner_ref is not None:
            owner_clause = " AND owner_ref = ?"
            params.append(self._validate_archive_owner_ref(owner_ref))
        lock_suffix = (
            " FOR UPDATE SKIP LOCKED"
            if self.backend_name == "postgresql+pgvector"
            else ""
        )
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM archive_voice_cleanup_jobs WHERE ("
                "(status = 'pending' AND available_at <= ?) OR "
                "(status = 'running' AND lease_expires_at <= ?))"
                + owner_clause
                + " ORDER BY available_at ASC, created_at ASC LIMIT 1"
                + lock_suffix,
                tuple(params),
            ).fetchone()
            if row is None:
                return None
            lease_token = str(uuid.uuid4())
            updated = db.execute(
                "UPDATE archive_voice_cleanup_jobs SET status = 'running', "
                "attempt_count = attempt_count + 1, version = version + 1, "
                "lease_owner = ?, lease_token = ?, lease_expires_at = ?, "
                "updated_at = ? WHERE id = ? AND version = ?",
                (
                    worker_id, lease_token, lease_expires_at, now_value,
                    row["id"], row["version"],
                ),
            ).rowcount
            if updated != 1:
                return None
            return db.execute(
                "SELECT * FROM archive_voice_cleanup_jobs WHERE id = ?",
                (row["id"],),
            ).fetchone()

    def retry_archive_voice_cleanup(
        self,
        job_id: str,
        lease_token: str,
        *,
        error: str,
        delay_seconds: float,
    ) -> bool:
        now = datetime.now(UTC)
        available_at = (
            now + timedelta(seconds=max(1, delay_seconds))
        ).isoformat()
        with self.transaction() as db:
            return db.execute(
                "UPDATE archive_voice_cleanup_jobs SET status = 'pending', "
                "version = version + 1, available_at = ?, lease_owner = NULL, "
                "lease_token = NULL, lease_expires_at = NULL, last_error = ?, "
                "updated_at = ? WHERE id = ? AND status = 'running' "
                "AND lease_token = ?",
                (available_at, error[:500], now.isoformat(), job_id, lease_token),
            ).rowcount == 1

    def complete_archive_voice_cleanup(
        self,
        job_id: str,
        lease_token: str,
    ) -> bool:
        with self.transaction() as db:
            row = db.execute(
                "SELECT owner_ref, voice_id FROM archive_voice_cleanup_jobs "
                "WHERE id = ? AND status = 'running' AND lease_token = ?",
                (job_id, lease_token),
            ).fetchone()
            if row is None:
                return False
            if row["voice_id"] is not None:
                db.execute(
                    "DELETE FROM user_voice_profiles WHERE owner_ref = ? AND voice_id = ?",
                    (row["owner_ref"], row["voice_id"]),
                )
            return db.execute(
                "DELETE FROM archive_voice_cleanup_jobs WHERE id = ? "
                "AND status = 'running' AND lease_token = ?",
                (job_id, lease_token),
            ).rowcount == 1

    def complete_archive_voice_cleanup_scope(
        self, owner_ref: str, voice_id: str,
    ) -> None:
        owner_ref = self._validate_archive_owner_ref(owner_ref)
        job_key = f"{owner_ref}:{voice_id}"
        with self.transaction() as db:
            db.execute(
                "DELETE FROM user_voice_profiles WHERE owner_ref = ? AND voice_id = ?",
                (owner_ref, voice_id),
            )
            db.execute(
                "DELETE FROM archive_voice_cleanup_jobs WHERE job_key = ?",
                (job_key,),
            )

    def get_archive_voice_cleanup_job(
        self, owner_ref: str, voice_id: str | None = None,
    ):
        return self.fetch_one(
            "SELECT * FROM archive_voice_cleanup_jobs WHERE job_key = ?",
            (f"{self._validate_archive_owner_ref(owner_ref)}:{voice_id or '*'}",),
        )

    # 이메일 로드(대소문자 구분 X)
    def get_user_by_email(self, email: str) -> sqlite3.Row | None:
        return self.fetch_one("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,))

    # 유저 일련번호 로드
    def get_user_by_id(self, user_id: str) -> sqlite3.Row | None:
        return self.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))

    # JWT 토큰 재할당(revoke)
    def revoke_token(self, jti: str, expires_at: int) -> None:
        self.execute("INSERT OR REPLACE INTO revoked_tokens VALUES (?, ?)", (jti, expires_at))
        self.execute("DELETE FROM revoked_tokens WHERE expires_at < strftime('%s', 'now')")

    # 토큰 재할당 체크
    def is_token_revoked(self, jti: str) -> bool:
        return self.fetch_one("SELECT jti FROM revoked_tokens WHERE jti = ?", (jti,)) is not None

    # 세션 생성
    def create_session(
        self,
        user_id: str,
        title: str = "새로운 대화",
        expected_auth_version: int | None = None,
    ) -> sqlite3.Row:
        session_id = str(uuid.uuid4())
        now = utc_now()
        with self.transaction() as db:
            if expected_auth_version is not None:
                self._require_account_fence(db, user_id, expected_auth_version)
            db.execute(
                "INSERT INTO chat_sessions VALUES (?, ?, ?, ?, ?)",
                (session_id, user_id, title.strip() or "새로운 대화", now, now),
            )
            return db.execute(
                "SELECT * FROM chat_sessions WHERE id = ? AND user_id = ?",
                (session_id, user_id),
            ).fetchone()

    # 세션 조회(채팅)
    def get_session(self, user_id: str, session_id: str) -> sqlite3.Row | None:
        return self.fetch_one(
            "SELECT * FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )

    # 현재 세션 리스트 조회(최신순, 채팅)
    def list_sessions(self, user_id: str) -> list[sqlite3.Row]:
        return self.fetch_all(
            "SELECT * FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        )
    
    # 세션 제거(채팅 제거)
    def delete_session(
        self,
        user_id: str,
        session_id: str,
        expected_auth_version: int | None = None,
    ) -> bool:
        with self.transaction() as db:
            if expected_auth_version is not None:
                self._require_account_fence(db, user_id, expected_auth_version)
            return db.execute(
                "DELETE FROM chat_sessions WHERE id = ? AND user_id = ?",
                (session_id, user_id),
            ).rowcount > 0

    # RAG를 위한 첨부파일 생성
    def create_attachment(
        self, user_id: str, session_id: str, filename: str, content_type: str,
        size_bytes: int, text_content: str, expected_auth_version: int | None = None,
    ) -> sqlite3.Row:
        attachment_id = str(uuid.uuid4())
        with self.transaction() as db:
            if expected_auth_version is not None:
                self._require_account_fence(db, user_id, expected_auth_version)
            db.execute(
                "INSERT INTO attachments VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    attachment_id, user_id, session_id, filename, content_type,
                    size_bytes, text_content, utc_now(),
                ),
            )
            return db.execute(
                "SELECT * FROM attachments WHERE id = ? AND user_id = ?",
                (attachment_id, user_id),
            ).fetchone()

    # 첨부파일 로드
    def get_attachment(self, user_id: str, attachment_id: str) -> sqlite3.Row | None:
        return self.fetch_one(
            "SELECT * FROM attachments WHERE id = ? AND user_id = ?", (attachment_id, user_id)
        )

    # 첨부파일 조회
    def list_attachments(self, user_id: str, session_id: str) -> list[sqlite3.Row]:
        return self.fetch_all(
            "SELECT * FROM attachments WHERE user_id = ? AND session_id = ? ORDER BY created_at ASC",
            (user_id, session_id),
        )

    # 첨부파일 삭제
    def delete_attachment(
        self, user_id: str, attachment_id: str, expected_auth_version: int | None = None,
    ) -> bool:
        with self.transaction() as db:
            if expected_auth_version is not None:
                self._require_account_fence(db, user_id, expected_auth_version)
            return db.execute(
                "DELETE FROM attachments WHERE id = ? AND user_id = ?",
                (attachment_id, user_id),
            ).rowcount > 0

    # 채팅 문자열 모두 저장
    def save_conversation(
        self,
        user_id: str,
        session_id: str,
        user_text: str,
        assistant_text: str,
        input_audio_path: str | None = None,
        output_audio_path: str | None = None,
        expected_auth_version: int | None = None,
    ) -> sqlite3.Row:
        conversation_id = str(uuid.uuid4())
        now = utc_now()
        with self._lock, closing(self.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            if expected_auth_version is not None:
                self._require_account_fence(db, user_id, expected_auth_version)
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
            conversation = db.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,),
            ).fetchone()
            db.commit()
        return conversation  # type: ignore[return-value]

    # 채팅 히스토리 조회
    def get_history(self, user_id: str, session_id: str, limit: int = 50) -> list[sqlite3.Row]:
        return self.fetch_all(
            "SELECT * FROM (SELECT * FROM conversations WHERE user_id = ? AND session_id = ? "
            "ORDER BY created_at DESC LIMIT ?) ORDER BY created_at ASC",
            (user_id, session_id, limit),
        )

    # 채팅 히스토리 조회(사용자 조회)
    def get_conversation(self, user_id: str, conversation_id: str) -> sqlite3.Row | None:
        return self.fetch_one(
            "SELECT * FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id)
        )

    # 채팅 히스토리 조회(10턴)(gateway 프롬프트 반영용)
    def get_history_before(
        self, user_id: str, session_id: str, created_at: str, limit: int = 10,
    ) -> list[sqlite3.Row]:
        return self.fetch_all(
            "SELECT * FROM (SELECT * FROM conversations WHERE user_id = ? AND session_id = ? "
            "AND created_at < ? ORDER BY created_at DESC LIMIT ?) ORDER BY created_at ASC",
            (user_id, session_id, created_at, limit),
        )

    # 채팅 상태 확인 조회
    def get_session_working_memory(self, user_id: str, session_id: str) -> str:
        row = self.fetch_one(
            "SELECT context FROM session_working_memory WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )
        return str(row["context"]) if row is not None else ""

    # 채팅 상태 체크 후 반영(upsert)
    def upsert_session_working_memory(
        self, user_id: str, session_id: str, context: str, turn_count: int,
        expected_auth_version: int | None = None,
    ) -> None:
        # DB 내용 : 세션 생성 SQL문, 만약 이미세션이 있을경우, 값 업데이트
        with self.transaction() as db:
            if expected_auth_version is not None:
                self._require_account_fence(db, user_id, expected_auth_version)
            db.execute(
                """
                INSERT INTO session_working_memory (session_id, user_id, context, turn_count, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    context = excluded.context,
                    turn_count = excluded.turn_count,
                    updated_at = excluded.updated_at
                WHERE session_working_memory.user_id = excluded.user_id
                """,
                (session_id, user_id, context, turn_count, utc_now()),
            )

    # (재시도)출력값 재반영
    def update_conversation_response(
        self, user_id: str, conversation_id: str, assistant_text: str,
        output_audio_path: str | None,
        expected_auth_version: int | None = None,
    ) -> sqlite3.Row | None:
        with self.transaction() as db:
            if expected_auth_version is not None:
                self._require_account_fence(db, user_id, expected_auth_version)
            updated = db.execute(
                "UPDATE conversations SET assistant_text = ?, output_audio_path = ? "
                "WHERE id = ? AND user_id = ?",
                (assistant_text, output_audio_path, conversation_id, user_id),
            ).rowcount
            if not updated:
                return None
            conversation = db.execute(
                "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
            if conversation is not None:
                db.execute(
                    "UPDATE chat_sessions SET updated_at = ? WHERE id = ? AND user_id = ?",
                    (utc_now(), conversation["session_id"], user_id),
                )
            return conversation

    def update_conversation_audio_if_current(
        self, user_id: str, conversation_id: str, assistant_text: str,
        output_audio_path: str,
        expected_auth_version: int | None = None,
    ) -> sqlite3.Row | None:
        """Attach audio only when the synthesized answer is still current."""
        with self.transaction() as db:
            if expected_auth_version is not None:
                self._require_account_fence(db, user_id, expected_auth_version)
            updated = db.execute(
                "UPDATE conversations SET output_audio_path = ? "
                "WHERE id = ? AND user_id = ? AND assistant_text = ? AND output_audio_path IS NULL",
                (output_audio_path, conversation_id, user_id, assistant_text),
            ).rowcount
            conversation = db.execute(
                "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
            if conversation is None:
                return None
            if not updated and (
                conversation["assistant_text"] != assistant_text
                or not conversation["output_audio_path"]
            ):
                return None
            return conversation

    # 음성 등록
    # 음성 등록을 할때 필요한 값을 넣음, 있으면 ignore 처리(무시)
    def get_next_legacy_voice_mapping(self, default_voice_id: str):
        return self.fetch_one(
            "SELECT uv.user_id, uv.voice_id FROM user_voice_profiles uv "
            "JOIN users u ON u.id = uv.user_id "
            "WHERE uv.owner_ref IS NULL AND uv.voice_id <> ? "
            "ORDER BY uv.created_at ASC, uv.user_id ASC, uv.voice_id ASC LIMIT 1",
            (default_voice_id,),
        )

    def mark_legacy_voice_adopted(
        self, user_id: str, voice_id: str, owner_ref: str,
    ) -> bool:
        owner_ref = self._validate_archive_owner_ref(owner_ref)
        with self.transaction() as db:
            return db.execute(
                "UPDATE user_voice_profiles SET owner_ref = ?, "
                "registration_state = 'active' WHERE user_id = ? AND voice_id = ? "
                "AND owner_ref IS NULL",
                (owner_ref, user_id, voice_id),
            ).rowcount == 1

    def add_user_voice(
        self,
        user_id: str,
        voice_id: str,
        expected_auth_version: int | None = None,
        *,
        owner_ref: str | None = None,
        provisional_cleanup_delay_seconds: float | None = None,
    ) -> None:
        with self.transaction() as db:
            if expected_auth_version is not None:
                self._require_account_fence(db, user_id, expected_auth_version)
            normalized_owner = (
                self._validate_archive_owner_ref(owner_ref)
                if owner_ref is not None else None
            )
            registration_state = (
                "provisional"
                if provisional_cleanup_delay_seconds is not None
                else "active"
            )
            db.execute(
                "INSERT OR IGNORE INTO user_voice_profiles ("
                "user_id, voice_id, owner_ref, registration_state, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, voice_id, normalized_owner, registration_state, utc_now()),
            )
            if normalized_owner is not None and provisional_cleanup_delay_seconds is not None:
                self._enqueue_archive_voice_cleanup_in_transaction(
                    db,
                    owner_ref=normalized_owner,
                    voice_id=voice_id,
                    delay_seconds=provisional_cleanup_delay_seconds,
                )

    def activate_user_voice(
        self,
        user_id: str,
        voice_id: str,
        owner_ref: str,
        *,
        expected_auth_version: int,
    ) -> bool:
        owner_ref = self._validate_archive_owner_ref(owner_ref)
        with self.transaction() as db:
            self._require_account_fence(db, user_id, expected_auth_version)
            cleanup_removed = db.execute(
                "DELETE FROM archive_voice_cleanup_jobs WHERE job_key = ? "
                "AND status = 'pending'",
                (f"{owner_ref}:{voice_id}",),
            ).rowcount
            if cleanup_removed != 1:
                return False
            updated = db.execute(
                "UPDATE user_voice_profiles SET registration_state = 'active' "
                "WHERE user_id = ? AND voice_id = ? AND owner_ref = ? "
                "AND registration_state = 'provisional'",
                (user_id, voice_id, owner_ref),
            ).rowcount
            return updated == 1

    def compensate_user_voice(
        self, user_id: str, voice_id: str, owner_ref: str,
    ) -> None:
        """Atomically hide the provisional mapping and retain remote cleanup."""
        owner_ref = self._validate_archive_owner_ref(owner_ref)
        with self.transaction() as db:
            db.execute(
                "DELETE FROM user_voice_profiles WHERE user_id = ? AND voice_id = ?",
                (user_id, voice_id),
            )
            self._enqueue_archive_voice_cleanup_in_transaction(
                db, owner_ref=owner_ref, voice_id=voice_id,
            )

    def remove_user_voice(self, user_id: str, voice_id: str) -> bool:
        """Remove a provisional ownership mapping during saga compensation."""
        return bool(self.execute(
            "DELETE FROM user_voice_profiles WHERE user_id = ? AND voice_id = ?",
            (user_id, voice_id),
        ))

    # 등록 음성 조회
    # 음성 목록을 로드함(사용자가 보유한것만)
    def list_user_voice_ids(self, user_id: str) -> set[str]:
        return {
            row["voice_id"]
            for row in self.fetch_all(
                "SELECT voice_id FROM user_voice_profiles WHERE user_id = ? "
                "AND registration_state = 'active'", (user_id,)
            )
        }
    
    # 1개로 지정하고 조회, 유저 음성을 조회
    def user_has_voice(self, user_id: str, voice_id: str) -> bool:
        return self.fetch_one(
            "SELECT 1 FROM user_voice_profiles WHERE user_id = ? AND voice_id = ? "
            "AND registration_state = 'active'", (user_id, voice_id)
        ) is not None

    # 메모리 생성 및 반영(사실상 메모리 엔진의 한부분)
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
        expected_auth_version: int | None = None,
    ) -> sqlite3.Row:
        memory_id = str(uuid.uuid4())
        now = utc_now()
        with self.transaction() as db:
            if expected_auth_version is not None:
                self._require_account_fence(db, user_id, expected_auth_version)
            db.execute(
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
                    memory_id, user_id, session_id, memory_type, content,
                    normalized_content, keywords, confidence, importance, now, now,
                ),
            )
            return db.execute(
                "SELECT * FROM memories WHERE user_id = ? AND normalized_content = ?",
                (user_id, normalized_content),
            ).fetchone()

    # 메모리(기억)을 로드하고 리스트
    def list_memories(self, user_id: str, limit: int = 200) -> list[sqlite3.Row]:
        return self.fetch_all(
            "SELECT * FROM memories WHERE user_id = ? ORDER BY importance DESC, updated_at DESC LIMIT ?",
            (user_id, limit),
        )

    # 메모리 접촉 및 업데이트
    def touch_memories(self, user_id: str, memory_ids: list[str]) -> None:
        if not memory_ids:
            return
        placeholders = ",".join("?" for _ in memory_ids)
        self.execute(
            f"UPDATE memories SET last_accessed_at = ? WHERE user_id = ? AND id IN ({placeholders})",
            (utc_now(), user_id, *memory_ids),
        )

    # 메모리 삭제
    def delete_memory(
        self, user_id: str, memory_id: str, expected_auth_version: int | None = None,
    ) -> bool:
        with self.transaction() as db:
            if expected_auth_version is not None:
                self._require_account_fence(db, user_id, expected_auth_version)
            return bool(db.execute(
                "DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id),
            ).rowcount)

    def get_all_history(self, user_id: str, session_id: str) -> list[sqlite3.Row]:
        """Return every stored turn for one owned session in chronological order."""
        return self.fetch_all(
            "SELECT * FROM conversations WHERE user_id = ? AND session_id = ? "
            "ORDER BY created_at ASC",
            (user_id, session_id),
        )

    def get_portrait(self, user_id: str) -> sqlite3.Row | None:
        return self.fetch_one("SELECT * FROM portraits WHERE user_id = ?", (user_id,))

    def begin_portrait_generation(
        self, user_id: str, persona: str, expected_auth_version: int | None = None,
    ) -> tuple[sqlite3.Row, bool]:
        """Atomically claim a portrait run, preventing duplicates across workers."""
        generation_id = str(uuid.uuid4())
        now = utc_now()
        with self._lock, closing(self.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            if expected_auth_version is None:
                user_row = db.execute(
                    "SELECT auth_version FROM users WHERE id = ? AND account_status = 'active'",
                    (user_id,),
                ).fetchone()
                if user_row is None:
                    db.rollback()
                    raise AccountAccessFenceError("account_authority_changed")
                expected_auth_version = int(user_row["auth_version"])
            self._require_account_fence(db, user_id, expected_auth_version)
            current = db.execute(
                "SELECT * FROM portraits WHERE user_id = ?", (user_id,),
            ).fetchone()
            if (
                current is not None
                and current["status"] in {"queued", "analyzing"}
                and int(current["account_auth_version"]) == expected_auth_version
            ):
                db.rollback()
                return current, False
            db.execute(
                """
                INSERT INTO portraits (
                    user_id, generation_id, account_auth_version, status, persona, title, summary,
                    accuracy_percent, analyzed_sessions, analyzed_messages,
                    progress_percent, vector_method, started_at, completed_at,
                    updated_at, error, worker_id, lease_expires_at
                ) VALUES (?, ?, ?, 'queued', ?, NULL, NULL, 0, 0, 0, 0, NULL, ?, NULL, ?, NULL, NULL, NULL)
                ON CONFLICT(user_id) DO UPDATE SET
                    generation_id = excluded.generation_id,
                    account_auth_version = excluded.account_auth_version,
                    status = 'queued',
                    persona = excluded.persona,
                    title = NULL,
                    summary = NULL,
                    accuracy_percent = 0,
                    analyzed_sessions = 0,
                    analyzed_messages = 0,
                    progress_percent = 0,
                    vector_method = NULL,
                    started_at = excluded.started_at,
                    completed_at = NULL,
                    updated_at = excluded.updated_at,
                    error = NULL,
                    worker_id = NULL,
                    lease_expires_at = NULL
                """,
                (user_id, generation_id, expected_auth_version, persona, now, now),
            )
            db.execute("DELETE FROM portrait_session_features WHERE user_id = ?", (user_id,))
            db.commit()
            row = db.execute(
                "SELECT * FROM portraits WHERE user_id = ?", (user_id,),
            ).fetchone()
        return row, True  # type: ignore[return-value]

    def list_active_portraits(self) -> list[sqlite3.Row]:
        return self.fetch_all(
            "SELECT * FROM portraits WHERE status IN ('queued', 'analyzing') "
            "ORDER BY updated_at ASC"
        )

    def claim_portrait_generation(
        self, user_id: str, generation_id: str, worker_id: str, lease_seconds: int = 120,
    ) -> bool:
        """Claim a queued job or an expired lease so interrupted work can resume."""
        now = utc_now()
        lease_expires_at = (datetime.now(UTC) + timedelta(seconds=lease_seconds)).isoformat()
        return bool(self.execute(
            """
            UPDATE portraits SET status = 'analyzing', progress_percent = MAX(progress_percent, 1),
                worker_id = ?, lease_expires_at = ?, updated_at = ?
            WHERE user_id = ? AND generation_id = ?
              AND status IN ('queued', 'analyzing')
              AND EXISTS (
                SELECT 1 FROM users
                WHERE users.id = portraits.user_id
                  AND users.account_status = 'active'
                  AND users.auth_version = portraits.account_auth_version
              )
              AND (
                status = 'queued' OR worker_id = ? OR lease_expires_at IS NULL
                OR lease_expires_at <= ?
              )
            """,
            (
                worker_id, lease_expires_at, now, user_id, generation_id,
                worker_id, now,
            ),
        ))

    def renew_portrait_lease(
        self, user_id: str, generation_id: str, worker_id: str, lease_seconds: int = 120,
    ) -> bool:
        lease_expires_at = (datetime.now(UTC) + timedelta(seconds=lease_seconds)).isoformat()
        return bool(self.execute(
            "UPDATE portraits SET lease_expires_at = ?, updated_at = ? "
            "WHERE user_id = ? AND generation_id = ? AND status = 'analyzing' "
            "AND worker_id = ? AND EXISTS (SELECT 1 FROM users WHERE "
            "users.id = portraits.user_id AND users.account_status = 'active' "
            "AND users.auth_version = portraits.account_auth_version)",
            (lease_expires_at, utc_now(), user_id, generation_id, worker_id),
        ))

    def release_portrait_lease(
        self, user_id: str, generation_id: str, worker_id: str,
    ) -> bool:
        """Return an interrupted job to the queue so the next app can resume it."""
        return bool(self.execute(
            "UPDATE portraits SET status = 'queued', worker_id = NULL, "
            "lease_expires_at = NULL, updated_at = ? "
            "WHERE user_id = ? AND generation_id = ? AND status = 'analyzing' "
            "AND worker_id = ?",
            (utc_now(), user_id, generation_id, worker_id),
        ))

    def update_portrait_progress(
        self,
        user_id: str,
        generation_id: str,
        worker_id: str,
        analyzed_sessions: int,
        analyzed_messages: int,
        progress_percent: int,
    ) -> bool:
        return bool(self.execute(
            "UPDATE portraits SET analyzed_sessions = ?, analyzed_messages = ?, "
            "progress_percent = ?, updated_at = ? WHERE user_id = ? AND generation_id = ? "
            "AND status = 'analyzing' AND worker_id = ? AND EXISTS (SELECT 1 FROM users "
            "WHERE users.id = portraits.user_id AND users.account_status = 'active' "
            "AND users.auth_version = portraits.account_auth_version)",
            (
                analyzed_sessions,
                analyzed_messages,
                max(1, min(94, progress_percent)),
                utc_now(),
                user_id,
                generation_id,
                worker_id,
            ),
        ))

    def save_portrait_session_feature(
        self,
        user_id: str,
        generation_id: str,
        session_id: str,
        total_messages: int,
        relevant_messages: int,
        weight: float,
        summary: str,
        worker_id: str,
    ) -> bool:
        now = utc_now()
        with self.transaction() as db:
            owner = db.execute(
                "SELECT 1 FROM portraits WHERE user_id = ? AND generation_id = ? "
                "AND status = 'analyzing' AND worker_id = ? "
                "AND lease_expires_at > ? AND EXISTS (SELECT 1 FROM users WHERE "
                "users.id = portraits.user_id AND users.account_status = 'active' "
                "AND users.auth_version = portraits.account_auth_version)",
                (user_id, generation_id, worker_id, now),
            ).fetchone()
            if owner is None:
                return False
            db.execute(
                """
                INSERT INTO portrait_session_features (
                    user_id, generation_id, session_id, total_messages, relevant_messages,
                    weight, summary, vector_json, vector_method, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', 'pending', ?, ?)
                ON CONFLICT(user_id, generation_id, session_id) DO UPDATE SET
                    total_messages = excluded.total_messages,
                    relevant_messages = excluded.relevant_messages,
                    weight = excluded.weight,
                    summary = excluded.summary,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id, generation_id, session_id, total_messages, relevant_messages,
                    max(0.0, min(1.0, weight)), summary, now, now,
                ),
            )
            return True

    def update_portrait_session_vector(
        self,
        user_id: str,
        generation_id: str,
        session_id: str,
        vector_json: str,
        vector_method: str,
        worker_id: str,
    ) -> bool:
        now = utc_now()
        with self.transaction() as db:
            owner = db.execute(
                "SELECT 1 FROM portraits WHERE user_id = ? AND generation_id = ? "
                "AND status = 'analyzing' AND worker_id = ? "
                "AND lease_expires_at > ? AND EXISTS (SELECT 1 FROM users WHERE "
                "users.id = portraits.user_id AND users.account_status = 'active' "
                "AND users.auth_version = portraits.account_auth_version)",
                (user_id, generation_id, worker_id, now),
            ).fetchone()
            if owner is None:
                return False
            return bool(db.execute(
                "UPDATE portrait_session_features SET vector_json = ?, vector_method = ?, "
                "updated_at = ? WHERE user_id = ? AND generation_id = ? AND session_id = ?",
                (vector_json, vector_method, now, user_id, generation_id, session_id),
            ).rowcount)

    def list_portrait_session_features(
        self, user_id: str, generation_id: str,
    ) -> list[sqlite3.Row]:
        return self.fetch_all(
            "SELECT * FROM portrait_session_features WHERE user_id = ? AND generation_id = ? "
            "ORDER BY created_at ASC",
            (user_id, generation_id),
        )

    def complete_portrait(
        self,
        user_id: str,
        generation_id: str,
        worker_id: str,
        title: str,
        summary: str,
        accuracy_percent: int,
        analyzed_sessions: int,
        analyzed_messages: int,
        vector_method: str,
    ) -> bool:
        now = utc_now()
        return bool(self.execute(
            """
            UPDATE portraits SET status = 'complete', title = ?, summary = ?,
                accuracy_percent = ?, analyzed_sessions = ?, analyzed_messages = ?,
                progress_percent = 100, vector_method = ?, completed_at = ?,
                updated_at = ?, error = NULL, worker_id = NULL, lease_expires_at = NULL
            WHERE user_id = ? AND generation_id = ? AND status = 'analyzing'
                AND worker_id = ? AND EXISTS (SELECT 1 FROM users WHERE
                    users.id = portraits.user_id AND users.account_status = 'active'
                    AND users.auth_version = portraits.account_auth_version)
            """,
            (
                title, summary, max(0, min(100, accuracy_percent)), analyzed_sessions,
                analyzed_messages, vector_method, now, now, user_id, generation_id, worker_id,
            ),
        ))

    def fail_portrait(
        self, user_id: str, generation_id: str, worker_id: str, error: str,
    ) -> bool:
        return bool(self.execute(
            "UPDATE portraits SET status = 'failed', error = ?, completed_at = ?, "
            "updated_at = ?, worker_id = NULL, lease_expires_at = NULL "
            "WHERE user_id = ? AND generation_id = ? AND status = 'analyzing' "
            "AND worker_id = ?",
            (error[:1000], utc_now(), utc_now(), user_id, generation_id, worker_id),
        ))

    def requeue_failed_portrait(self, user_id: str, generation_id: str) -> bool:
        return bool(self.execute(
            "UPDATE portraits SET status = 'queued', error = NULL, completed_at = NULL, "
            "worker_id = NULL, lease_expires_at = NULL, updated_at = ? "
            "WHERE user_id = ? AND generation_id = ? AND status = 'failed'",
            (utc_now(), user_id, generation_id),
        ))

    def fail_expired_portrait(
        self, user_id: str, generation_id: str, error: str,
    ) -> bool:
        """Reconcile a Redis terminal failure after the DB worker lease expired."""
        now = utc_now()
        return bool(self.execute(
            "UPDATE portraits SET status = 'failed', error = ?, completed_at = ?, "
            "updated_at = ?, worker_id = NULL, lease_expires_at = NULL "
            "WHERE user_id = ? AND generation_id = ? "
            "AND status IN ('queued', 'analyzing') "
            "AND (lease_expires_at IS NULL OR lease_expires_at <= ?)",
            (error[:1000], now, now, user_id, generation_id, now),
        ))

    def begin_operation(
        self,
        operation_type: str,
        request_id: str,
        correlation_id: str,
        *,
        user_id: str | None = None,
        resource_id: str | None = None,
        status: str = "running",
        metadata: dict[str, Any] | None = None,
    ):
        """Create a state-machine snapshot and its first immutable transition."""
        if status not in OPERATION_TRANSITIONS:
            raise ValueError(f"unsupported operation status: {status}")
        operation_id = str(uuid.uuid4())
        now = utc_now()
        progress = 100 if status == "succeeded" else 0
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":"))
        with self.transaction() as db:
            cursor = db.execute(
                """
                INSERT INTO operation_states (
                    id, user_id, request_id, correlation_id, operation_type, resource_id,
                    status, progress_percent, version, metadata_json, error_code,
                    created_at, updated_at, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, NULL, ?, ?, ?, ?)
                ON CONFLICT(request_id, operation_type) DO NOTHING
                """,
                (
                    operation_id, user_id, request_id, correlation_id, operation_type,
                    resource_id, status, progress, metadata_json, now, now,
                    now if status == "running" else None,
                    now if status in {"succeeded", "failed", "cancelled"} else None,
                ),
            )
            if cursor.rowcount == 1:
                db.execute(
                    "INSERT INTO operation_state_transitions "
                    "VALUES (?, ?, NULL, ?, 1, ?, ?, ?)",
                    (
                        str(uuid.uuid4()), operation_id, status, progress,
                        "operation_created", now,
                    ),
                )
                return db.execute(
                    "SELECT * FROM operation_states WHERE id = ?", (operation_id,),
                ).fetchone()
            return db.execute(
                "SELECT * FROM operation_states WHERE request_id = ? AND operation_type = ?",
                (request_id, operation_type),
            ).fetchone()

    def get_operation(self, operation_id: str):
        return self.fetch_one("SELECT * FROM operation_states WHERE id = ?", (operation_id,))

    def get_operation_for_resource(self, operation_type: str, resource_id: str):
        return self.fetch_one(
            "SELECT * FROM operation_states WHERE operation_type = ? AND resource_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (operation_type, resource_id),
        )

    def list_operations(
        self,
        *,
        user_id: str | None = None,
        status: str | None = None,
        operation_type: str | None = None,
        correlation_id: str | None = None,
        limit: int = 100,
    ) -> list:
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("user_id", user_id),
            ("status", status),
            ("operation_type", operation_type),
            ("correlation_id", correlation_id),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(1000, limit)))
        return self.fetch_all(
            f"SELECT * FROM operation_states{where} ORDER BY updated_at DESC LIMIT ?",
            params,
        )

    def transition_operation(
        self,
        operation_id: str,
        to_status: str,
        *,
        progress_percent: int | None = None,
        expected_version: int | None = None,
        user_id: str | None = None,
        error_code: str | None = None,
        reason: str | None = None,
    ):
        """Apply an optimistic, monotonic and terminal-safe state transition."""
        if to_status not in OPERATION_TRANSITIONS:
            raise ValueError(f"unsupported operation status: {to_status}")
        now = utc_now()
        with self.transaction() as db:
            current = db.execute(
                "SELECT * FROM operation_states WHERE id = ?", (operation_id,),
            ).fetchone()
            if current is None:
                raise KeyError(operation_id)
            current_version = int(current["version"])
            if expected_version is not None and current_version != expected_version:
                raise RuntimeError("operation version conflict")
            from_status = str(current["status"])
            current_progress = int(current["progress_percent"])
            if from_status in {"succeeded", "failed", "cancelled"}:
                if from_status == to_status:
                    return current
                raise ValueError(f"invalid operation transition: {from_status} -> {to_status}")
            if (
                from_status == to_status
                and (progress_percent is None or progress_percent <= current_progress)
                and user_id is None
                and error_code is None
            ):
                return current
            if from_status != to_status and to_status not in OPERATION_TRANSITIONS[from_status]:
                raise ValueError(f"invalid operation transition: {from_status} -> {to_status}")
            requested_progress = current_progress if progress_percent is None else progress_percent
            progress = max(current_progress, min(100, max(0, requested_progress)))
            if to_status == "succeeded":
                progress = 100
            version = current_version + 1
            started_at = current["started_at"] or (now if to_status == "running" else None)
            completed_at = now if to_status in {"succeeded", "failed", "cancelled"} else None
            cursor = db.execute(
                """
                UPDATE operation_states SET status = ?, progress_percent = ?, version = ?,
                    user_id = COALESCE(?, user_id), error_code = ?, updated_at = ?,
                    started_at = ?, completed_at = ?
                WHERE id = ? AND version = ?
                """,
                (
                    to_status, progress, version, user_id, error_code, now,
                    started_at, completed_at, operation_id, current_version,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("operation version conflict")
            db.execute(
                "INSERT INTO operation_state_transitions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()), operation_id, from_status, to_status, version,
                    progress, (reason or "")[:500] or None, now,
                ),
            )
            return db.execute(
                "SELECT * FROM operation_states WHERE id = ?", (operation_id,),
            ).fetchone()

    def record_transaction_event(
        self,
        *,
        user_id: str | None,
        operation_id: str | None,
        request_id: str,
        correlation_id: str,
        event_type: str,
        status: str,
        http_method: str | None = None,
        http_path: str | None = None,
        http_status: int | None = None,
        latency_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Persist an append-only audit event and outbox row in one transaction."""
        event_id = str(uuid.uuid4())
        occurred_at = utc_now()
        safe_metadata = metadata or {}
        metadata_json = json.dumps(
            safe_metadata, ensure_ascii=False, separators=(",", ":"), default=str,
        )
        payload = {
            "event_id": event_id,
            "user_id": user_id,
            "operation_id": operation_id,
            "request_id": request_id,
            "correlation_id": correlation_id,
            "event_type": event_type,
            "status": status,
            "http_method": http_method,
            "http_path": http_path,
            "http_status": http_status,
            "latency_ms": latency_ms,
            "metadata": safe_metadata,
            "occurred_at": occurred_at,
        }
        payload_json = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), default=str,
        )
        with self.transaction() as db:
            db.execute(
                """
                INSERT INTO user_transaction_events (
                    event_id, user_id, operation_id, request_id, correlation_id,
                    event_type, status, http_method, http_path, http_status,
                    latency_ms, metadata_json, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, user_id, operation_id, request_id, correlation_id,
                    event_type, status, http_method, http_path, http_status,
                    latency_ms, metadata_json, occurred_at,
                ),
            )
            db.execute(
                """
                INSERT INTO event_outbox (
                    event_id, aggregate_type, aggregate_id, event_type, payload_json,
                    status, attempts, next_attempt_at, created_at, published_at
                ) VALUES (?, 'operation', ?, ?, ?, 'pending', 0, NULL, ?, NULL)
                """,
                (event_id, operation_id or request_id, event_type, payload_json, occurred_at),
            )
        return event_id

    def finish_operation_with_event(
        self,
        *,
        operation_id: str,
        user_id: str | None,
        request_id: str,
        correlation_id: str,
        status: str,
        error_code: str | None,
        event_type: str,
        http_method: str | None,
        http_path: str | None,
        http_status: int | None,
        latency_ms: int | None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[Any, str]:
        """Atomically finish an operation and append its audit/outbox event."""
        if status not in {"succeeded", "failed", "cancelled"}:
            raise ValueError("finish_operation_with_event requires a terminal status")
        now = utc_now()
        event_id = str(uuid.uuid4())
        safe_metadata = metadata or {}
        metadata_json = json.dumps(
            safe_metadata, ensure_ascii=False, separators=(",", ":"), default=str,
        )
        payload = {
            "event_id": event_id,
            "user_id": user_id,
            "operation_id": operation_id,
            "request_id": request_id,
            "correlation_id": correlation_id,
            "event_type": event_type,
            "status": status,
            "http_method": http_method,
            "http_path": http_path,
            "http_status": http_status,
            "latency_ms": latency_ms,
            "metadata": safe_metadata,
            "occurred_at": now,
        }
        payload_json = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), default=str,
        )
        with self.transaction() as db:
            current = db.execute(
                "SELECT * FROM operation_states WHERE id = ?", (operation_id,),
            ).fetchone()
            if current is None:
                raise KeyError(operation_id)
            from_status = str(current["status"])
            if from_status in {"succeeded", "failed", "cancelled"}:
                raise ValueError(f"operation is already terminal: {from_status}")
            if status not in OPERATION_TRANSITIONS[from_status]:
                raise ValueError(f"invalid operation transition: {from_status} -> {status}")
            version = int(current["version"]) + 1
            progress = 100 if status == "succeeded" else int(current["progress_percent"])
            cursor = db.execute(
                "UPDATE operation_states SET status = ?, progress_percent = ?, version = ?, "
                "user_id = COALESCE(?, user_id), error_code = ?, updated_at = ?, "
                "completed_at = ? WHERE id = ? AND version = ?",
                (
                    status, progress, version, user_id, error_code, now, now,
                    operation_id, current["version"],
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("operation version conflict")
            db.execute(
                "INSERT INTO operation_state_transitions "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()), operation_id, from_status, status, version,
                    progress, "http_response", now,
                ),
            )
            db.execute(
                """
                INSERT INTO user_transaction_events (
                    event_id, user_id, operation_id, request_id, correlation_id,
                    event_type, status, http_method, http_path, http_status,
                    latency_ms, metadata_json, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, user_id, operation_id, request_id, correlation_id,
                    event_type, status, http_method, http_path, http_status,
                    latency_ms, metadata_json, now,
                ),
            )
            db.execute(
                """
                INSERT INTO event_outbox (
                    event_id, aggregate_type, aggregate_id, event_type, payload_json,
                    status, attempts, next_attempt_at, locked_by, locked_until,
                    created_at, published_at
                ) VALUES (?, 'operation', ?, ?, ?, 'pending', 0, NULL, NULL, NULL, ?, NULL)
                """,
                (event_id, operation_id, event_type, payload_json, now),
            )
            updated = db.execute(
                "SELECT * FROM operation_states WHERE id = ?", (operation_id,),
            ).fetchone()
        return updated, event_id

    @staticmethod
    def _outbox_claimable_sql() -> str:
        return (
            "((status IN ('pending', 'failed') "
            "AND (next_attempt_at IS NULL OR next_attempt_at <= ?)) "
            "OR (status = 'publishing' AND locked_until IS NOT NULL "
            "AND locked_until <= ?))"
        )

    def claim_outbox_event(
        self,
        event_id: str,
        worker_id: str,
        *,
        lease_seconds: int = 30,
    ) -> bool:
        now = datetime.now(UTC)
        locked_until = (now + timedelta(
            seconds=max(5, min(300, int(lease_seconds))),
        )).isoformat()
        now_value = now.isoformat()
        return bool(self.execute(
            "UPDATE event_outbox SET status = 'publishing', locked_by = ?, "
            "locked_until = ?, attempts = attempts + 1 WHERE event_id = ? AND "
            + self._outbox_claimable_sql(),
            (worker_id, locked_until, event_id, now_value, now_value),
        ))

    def claim_outbox_events(
        self,
        worker_id: str,
        *,
        limit: int = 100,
        lease_seconds: int = 30,
    ) -> list:
        """Claim due envelopes; expired claims are safely recoverable."""
        now = datetime.now(UTC)
        now_value = now.isoformat()
        locked_until = (now + timedelta(
            seconds=max(5, min(300, int(lease_seconds))),
        )).isoformat()
        claimed: list = []
        with self.transaction() as db:
            candidates = db.execute(
                "SELECT event_id FROM event_outbox WHERE "
                + self._outbox_claimable_sql()
                + " ORDER BY created_at ASC LIMIT ?",
                (now_value, now_value, max(1, min(1000, limit))),
            ).fetchall()
            for candidate in candidates:
                cursor = db.execute(
                    "UPDATE event_outbox SET status = 'publishing', locked_by = ?, "
                    "locked_until = ?, attempts = attempts + 1 "
                    "WHERE event_id = ? AND " + self._outbox_claimable_sql(),
                    (
                        worker_id, locked_until, candidate["event_id"],
                        now_value, now_value,
                    ),
                )
                if cursor.rowcount == 1:
                    claimed.append(db.execute(
                        "SELECT * FROM event_outbox WHERE event_id = ?",
                        (candidate["event_id"],),
                    ).fetchone())
        return claimed

    def mark_outbox_published(self, event_id: str, worker_id: str) -> bool:
        now = utc_now()
        return bool(self.execute(
            "UPDATE event_outbox SET status = 'published', published_at = ?, "
            "next_attempt_at = NULL, locked_by = NULL, locked_until = NULL "
            "WHERE event_id = ? AND status = 'publishing' AND locked_by = ?",
            (now, event_id, worker_id),
        ))

    def mark_outbox_failed(
        self,
        event_id: str,
        worker_id: str,
        *,
        retry_seconds: int = 5,
    ) -> bool:
        delay = max(1, min(300, int(retry_seconds)))
        next_attempt = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat()
        return bool(self.execute(
            "UPDATE event_outbox SET status = 'failed', next_attempt_at = ?, "
            "locked_by = NULL, locked_until = NULL WHERE event_id = ? "
            "AND status = 'publishing' AND locked_by = ?",
            (next_attempt, event_id, worker_id),
        ))

    def list_transaction_events(
        self,
        *,
        user_id: str | None = None,
        correlation_id: str | None = None,
        operation_id: str | None = None,
        event_type: str | None = None,
        status: str | None = None,
        occurred_from: str | None = None,
        occurred_to: str | None = None,
        limit: int = 100,
    ) -> list:
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("user_id", user_id),
            ("correlation_id", correlation_id),
            ("operation_id", operation_id),
            ("event_type", event_type),
            ("status", status),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        if occurred_from is not None:
            clauses.append("occurred_at >= ?")
            params.append(occurred_from)
        if occurred_to is not None:
            clauses.append("occurred_at < ?")
            params.append(occurred_to)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(1000, limit)))
        return self.fetch_all(
            f"SELECT * FROM user_transaction_events{where} ORDER BY occurred_at DESC LIMIT ?",
            params,
        )

    def record_admin_audit_event(
        self,
        *,
        admin_ref: str | None,
        request_id: str,
        correlation_id: str,
        http_method: str,
        http_path: str,
        http_status: int,
        latency_ms: int,
        action: str | None = None,
        target_admin_ref: str | None = None,
        before_status: str | None = None,
        after_status: str | None = None,
    ) -> str:
        """Append metadata-only access evidence for the excluded admin API."""
        event_id = str(uuid.uuid4())
        self.execute(
            "INSERT INTO admin_audit_events (id, admin_ref, request_id, correlation_id, "
            "http_method, http_path, http_status, latency_ms, action, target_admin_ref, "
            "before_status, after_status, occurred_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id, admin_ref, request_id, correlation_id, http_method,
                http_path, int(http_status), max(0, int(latency_ms)), action,
                target_admin_ref, before_status, after_status, utc_now(),
            ),
        )
        return event_id

    def summarize_transaction_events(
        self,
        *,
        user_id: str | None = None,
        occurred_from: str | None = None,
        occurred_to: str | None = None,
    ) -> list:
        """Build the privacy-safe read model needed by a future admin page."""
        clauses: list[str] = []
        params: list[Any] = []
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        if occurred_from is not None:
            clauses.append("occurred_at >= ?")
            params.append(occurred_from)
        if occurred_to is not None:
            clauses.append("occurred_at < ?")
            params.append(occurred_to)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.fetch_all(
            "SELECT event_type, status, COALESCE(http_path, '') AS http_path, "
            "COUNT(*) AS transaction_count, COUNT(DISTINCT user_id) AS user_count, "
            "ROUND(AVG(latency_ms), 2) AS average_latency_ms, "
            "MAX(latency_ms) AS maximum_latency_ms "
            f"FROM user_transaction_events{where} "
            "GROUP BY event_type, status, http_path "
            "ORDER BY transaction_count DESC, event_type ASC",
            params,
        )

    @staticmethod
    def _admin_time_filter(
        column: str,
        occurred_from: str | None,
        occurred_to: str | None,
    ) -> tuple[list[str], list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if occurred_from is not None:
            clauses.append(f"{column} >= ?")
            params.append(occurred_from)
        if occurred_to is not None:
            clauses.append(f"{column} < ?")
            params.append(occurred_to)
        return clauses, params

    def admin_overview(
        self,
        *,
        occurred_from: str | None = None,
        occurred_to: str | None = None,
    ) -> dict[str, Any]:
        """Return aggregate-only operational metrics; no user content is selected."""
        event_clauses, event_params = self._admin_time_filter(
            "occurred_at", occurred_from, occurred_to,
        )
        event_where = f" WHERE {' AND '.join(event_clauses)}" if event_clauses else ""
        event_row = self.fetch_one(
            "SELECT COUNT(*) AS transaction_count, "
            "COUNT(DISTINCT user_id) AS active_user_count, "
            "SUM(CASE WHEN status = 'succeeded' THEN 1 ELSE 0 END) AS succeeded_count, "
            "SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count, "
            "ROUND(AVG(latency_ms), 2) AS average_latency_ms, "
            "MAX(latency_ms) AS maximum_latency_ms "
            f"FROM user_transaction_events{event_where}",
            event_params,
        )
        operation_clauses, operation_params = self._admin_time_filter(
            "updated_at", occurred_from, occurred_to,
        )
        operation_where = (
            f" WHERE {' AND '.join(operation_clauses)}" if operation_clauses else ""
        )
        operation_rows = self.fetch_all(
            "SELECT status, COUNT(*) AS operation_count FROM operation_states"
            f"{operation_where} GROUP BY status",
            operation_params,
        )
        outbox_rows = self.fetch_all(
            "SELECT status, COUNT(*) AS event_count FROM event_outbox "
            "WHERE status <> 'published' GROUP BY status"
        )
        total_users = self.fetch_one("SELECT COUNT(*) AS user_count FROM users")
        return {
            "total_user_count": int(total_users["user_count"] if total_users else 0),
            "transaction_count": int(event_row["transaction_count"] if event_row else 0),
            "active_user_count": int(event_row["active_user_count"] if event_row else 0),
            "succeeded_count": int((event_row["succeeded_count"] if event_row else 0) or 0),
            "failed_count": int((event_row["failed_count"] if event_row else 0) or 0),
            "average_latency_ms": float(
                (event_row["average_latency_ms"] if event_row else 0) or 0
            ),
            "maximum_latency_ms": int(
                (event_row["maximum_latency_ms"] if event_row else 0) or 0
            ),
            "operations": {
                str(row["status"]): int(row["operation_count"]) for row in operation_rows
            },
            "outbox": {
                str(row["status"]): int(row["event_count"]) for row in outbox_rows
            },
        }

    def list_admin_transactions(
        self,
        *,
        user_ref: str | None = None,
        status: str | None = None,
        correlation_id: str | None = None,
        event_type: str | None = None,
        occurred_from: str | None = None,
        occurred_to: str | None = None,
        before: str | None = None,
        before_id: str | None = None,
        limit: int = 100,
    ) -> list:
        clauses, params = self._admin_time_filter(
            "e.occurred_at", occurred_from, occurred_to,
        )
        for column, value in (
            ("u.admin_ref", user_ref),
            ("e.status", status),
            ("e.correlation_id", correlation_id),
            ("e.event_type", event_type),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        if before is not None:
            if before_id is None:
                clauses.append("e.occurred_at < ?")
                params.append(before)
            else:
                clauses.append("(e.occurred_at < ? OR (e.occurred_at = ? AND e.event_id < ?))")
                params.extend((before, before, before_id))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(200, limit)))
        return self.fetch_all(
            "SELECT e.event_id, u.admin_ref AS user_id, e.operation_id, e.request_id, "
            "e.correlation_id, e.event_type, e.status, e.http_method, e.http_path, "
            "e.http_status, e.latency_ms, e.occurred_at "
            "FROM user_transaction_events e LEFT JOIN users u ON u.id = e.user_id"
            f"{where} ORDER BY e.occurred_at DESC, e.event_id DESC LIMIT ?",
            params,
        )

    def list_admin_operations(
        self,
        *,
        user_ref: str | None = None,
        status: str | None = None,
        operation_type: str | None = None,
        correlation_id: str | None = None,
        occurred_from: str | None = None,
        occurred_to: str | None = None,
        before: str | None = None,
        before_id: str | None = None,
        limit: int = 100,
    ) -> list:
        clauses, params = self._admin_time_filter(
            "o.updated_at", occurred_from, occurred_to,
        )
        for column, value in (
            ("u.admin_ref", user_ref),
            ("o.status", status),
            ("o.operation_type", operation_type),
            ("o.correlation_id", correlation_id),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        if before is not None:
            if before_id is None:
                clauses.append("o.updated_at < ?")
                params.append(before)
            else:
                clauses.append("(o.updated_at < ? OR (o.updated_at = ? AND o.id < ?))")
                params.extend((before, before, before_id))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(200, limit)))
        return self.fetch_all(
            "SELECT o.id, u.admin_ref AS user_id, o.request_id, o.correlation_id, "
            "o.operation_type, o.status, o.progress_percent, o.version, o.error_code, "
            "o.created_at, o.updated_at, o.started_at, o.completed_at "
            "FROM operation_states o LEFT JOIN users u ON u.id = o.user_id"
            f"{where} ORDER BY o.updated_at DESC, o.id DESC LIMIT ?",
            params,
        )

    def list_admin_operation_transitions(self, operation_id: str, *, limit: int = 200) -> list:
        return self.fetch_all(
            "SELECT t.id, t.operation_id, t.from_status, t.to_status, t.version, "
            "t.progress_percent, t.occurred_at FROM operation_state_transitions t "
            "WHERE t.operation_id = ? ORDER BY t.occurred_at ASC LIMIT ?",
            (operation_id, max(1, min(1000, limit))),
        )

    def list_admin_users(
        self,
        *,
        account_status: str | None = None,
        occurred_from: str | None = None,
        occurred_to: str | None = None,
        before: str | None = None,
        before_id: str | None = None,
        limit: int = 100,
    ) -> list:
        event_clauses, event_params = self._admin_time_filter(
            "occurred_at", occurred_from, occurred_to,
        )
        event_clauses.append("user_id IN (SELECT id FROM page_users)")
        event_where = f" WHERE {' AND '.join(event_clauses)}"
        user_clauses: list[str] = ["u.admin_ref IS NOT NULL"]
        user_params: list[Any] = []
        if account_status is not None:
            user_clauses.append("u.account_status = ?")
            user_params.append(account_status)
        if before is not None:
            if before_id is None:
                user_clauses.append("u.created_at < ?")
                user_params.append(before)
            else:
                user_clauses.append(
                    "(u.created_at < ? OR (u.created_at = ? AND u.admin_ref < ?))"
                )
                user_params.extend((before, before, before_id))
        user_where = f" WHERE {' AND '.join(user_clauses)}"
        # API pagination requests one look-ahead row to distinguish a full final
        # page from a page that genuinely has more data.
        page_limit = max(1, min(201, limit))
        params = [*user_params, page_limit, *event_params]
        return self.fetch_all(
            "WITH page_users AS ("
            "SELECT u.id, u.admin_ref, u.created_at, u.account_status, "
            "u.status_version, u.status_changed_at, u.suspended_at, u.deactivated_at, "
            "u.is_admin, u.email FROM users u"
            f"{user_where} ORDER BY u.created_at DESC, u.admin_ref DESC LIMIT ?"
            "), "
            "session_metrics AS (SELECT user_id, COUNT(*) AS session_count "
            "FROM chat_sessions WHERE user_id IN (SELECT id FROM page_users) GROUP BY user_id), "
            "message_metrics AS (SELECT user_id, COUNT(*) AS message_count "
            "FROM conversations WHERE user_id IN (SELECT id FROM page_users) GROUP BY user_id), "
            "memory_metrics AS (SELECT user_id, COUNT(*) AS memory_count "
            "FROM memories WHERE user_id IN (SELECT id FROM page_users) GROUP BY user_id), "
            "event_metrics AS (SELECT user_id, COUNT(*) AS transaction_count, "
            "SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count, "
            f"MAX(occurred_at) AS last_seen_at FROM user_transaction_events{event_where} "
            "GROUP BY user_id) "
            "SELECT u.admin_ref AS user_id, u.created_at, u.account_status, "
            "u.status_version, u.status_changed_at, u.suspended_at, u.deactivated_at, "
            "u.is_admin AS _is_admin, u.email AS _admin_email, "
            "COALESCE(s.session_count, 0) AS session_count, "
            "COALESCE(c.message_count, 0) AS message_count, "
            "COALESCE(m.memory_count, 0) AS memory_count, "
            "COALESCE(e.transaction_count, 0) AS transaction_count, "
            "COALESCE(e.failed_count, 0) AS failed_count, e.last_seen_at "
            "FROM page_users u "
            "LEFT JOIN session_metrics s ON s.user_id = u.id "
            "LEFT JOIN message_metrics c ON c.user_id = u.id "
            "LEFT JOIN memory_metrics m ON m.user_id = u.id "
            "LEFT JOIN event_metrics e ON e.user_id = u.id "
            "ORDER BY u.created_at DESC, u.admin_ref DESC",
            params,
        )

    def upsert_rag_embedding(
        self,
        *,
        user_id: str,
        namespace: str,
        source_id: str,
        content: str,
        vector: list[float],
        embedding_model: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = utc_now()
        self.execute(
            """
            INSERT INTO rag_embeddings (
                id, user_id, namespace, source_id, content, metadata_json,
                vector_json, vector_dimensions, embedding_model, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, namespace, source_id, embedding_model) DO UPDATE SET
                content = excluded.content,
                metadata_json = excluded.metadata_json,
                vector_json = excluded.vector_json,
                vector_dimensions = excluded.vector_dimensions,
                updated_at = excluded.updated_at
            """,
            (
                str(uuid.uuid4()), user_id, namespace, source_id, content,
                json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":")),
                json.dumps(vector, separators=(",", ":")), len(vector), embedding_model,
                now, now,
            ),
        )

