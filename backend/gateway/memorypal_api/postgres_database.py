from __future__ import annotations

import hashlib
import json
import re
import uuid
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from .database import AccountAccessFenceError, Database, DatabaseIntegrityError, utc_now


_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DOLLAR_QUOTE_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")
_REQUIRED_SCHEMA_RELATIONS = (
    "users",
    "chat_sessions",
    "conversations",
    "memories",
    "operation_states",
    "event_outbox",
    "rag_embeddings",
)


def postgres_migration_manifest() -> dict[str, str]:
    """Return the filename-based migration versions and content checksums."""
    repository_root = Path(__file__).resolve().parents[3]
    gateway_files = sorted(
        (repository_root / "backend" / "gateway" / "migrations").glob("*.sql")
    )
    deploy_files = sorted(
        (repository_root / "deploy" / "scale" / "postgres" / "migrations").glob("*.sql")
    )
    manifest: dict[str, str] = {}
    for path in gateway_files:
        manifest[f"gateway_{path.name}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path in deploy_files:
        manifest[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not manifest:
        raise PostgresMigrationError("No PostgreSQL migrations were found")
    return manifest


def validate_postgres_migration_rows(
    expected: dict[str, str], applied_rows: Iterable[dict[str, Any]],
) -> None:
    """Fail when a required migration is absent or its recorded content drifted."""
    applied = {
        str(row["version"]): str(row.get("checksum") or "")
        for row in applied_rows
    }
    missing = sorted(set(expected) - set(applied))
    unexpected = sorted(set(applied) - set(expected))
    mismatched = sorted(
        version
        for version, checksum in expected.items()
        if version in applied and applied[version] != checksum
    )
    if missing:
        raise PostgresMigrationError(
            "PostgreSQL migrations are pending: " + ", ".join(missing)
        )
    if unexpected:
        raise PostgresMigrationError(
            "PostgreSQL migration ledger contains deleted or unknown files: "
            + ", ".join(unexpected)
        )
    if mismatched:
        raise PostgresMigrationError(
            "PostgreSQL migration checksum mismatch: " + ", ".join(mismatched)
        )


def split_postgres_statements(script: str) -> list[str]:
    """Split migration SQL without cutting quoted strings or DO dollar blocks."""
    statements: list[str] = []
    start = 0
    index = 0
    single_quoted = False
    double_quoted = False
    line_comment = False
    block_comment_depth = 0
    dollar_quote: str | None = None

    while index < len(script):
        if dollar_quote is not None:
            if script.startswith(dollar_quote, index):
                index += len(dollar_quote)
                dollar_quote = None
            else:
                index += 1
            continue

        character = script[index]
        following = script[index + 1] if index + 1 < len(script) else ""
        if line_comment:
            if character in "\r\n":
                line_comment = False
            index += 1
            continue
        if block_comment_depth:
            if character == "/" and following == "*":
                block_comment_depth += 1
                index += 2
            elif character == "*" and following == "/":
                block_comment_depth -= 1
                index += 2
            else:
                index += 1
            continue
        if single_quoted:
            if character == "'":
                if following == "'":
                    index += 2
                    continue
                single_quoted = False
            index += 1
            continue
        if double_quoted:
            if character == '"':
                if following == '"':
                    index += 2
                    continue
                double_quoted = False
            index += 1
            continue

        if character == "-" and following == "-":
            line_comment = True
            index += 2
        elif character == "/" and following == "*":
            block_comment_depth = 1
            index += 2
        elif character == "'":
            single_quoted = True
            index += 1
        elif character == '"':
            double_quoted = True
            index += 1
        elif character == "$":
            match = _DOLLAR_QUOTE_RE.match(script, index)
            if match is None:
                index += 1
            else:
                dollar_quote = match.group(0)
                index = match.end()
        elif character == ";":
            statement = script[start:index].strip()
            if statement:
                statements.append(statement)
            start = index + 1
            index += 1
        else:
            index += 1

    tail = script[start:].strip()
    if tail:
        statements.append(tail)
    return statements


class PostgresDependencyError(RuntimeError):
    pass


class PostgresMigrationError(RuntimeError):
    pass


class _PooledConnection:
    """Small DB-API proxy that returns psycopg connections to their pool."""

    def __init__(self, owner: "PostgresDatabase", connection):
        self._owner = owner
        self._connection = connection
        self._closed = False

    def execute(self, query: str, params: Iterable[Any] = ()):
        prepared = self._owner._prepare(query)
        bound_params = tuple(params)
        if not bound_params:
            # Passing an empty parameter sequence still enables psycopg's
            # placeholder parser. SQL containing a literal LIKE wildcard such
            # as `archive\_%` would then be rejected as an invalid `%` token.
            return self._connection.execute(prepared)
        return self._connection.execute(prepared, bound_params)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._owner._pool.putconn(self._connection)


class PostgresDatabase(Database):
    """PostgreSQL/pgvector adapter retaining the current mapping-row contract."""

    def __init__(
        self,
        database_url: str,
        *,
        schema: str = "memorypal_gateway",
        pool_min_size: int = 2,
        pool_max_size: int = 20,
    ):
        if not _SCHEMA_RE.fullmatch(schema):
            raise ValueError("MEMORYPAL_DATABASE_SCHEMA must be a simple SQL identifier")
        try:
            import psycopg
            from psycopg import ClientCursor
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
        except ImportError as exc:  # pragma: no cover - exercised only in scale deployments
            raise PostgresDependencyError(
                "PostgreSQL mode requires psycopg[binary,pool]. Run install-scale.cmd first."
            ) from exc

        super().__init__(Path("."))
        self.database_url = database_url
        self.schema = schema
        self._psycopg = psycopg

        def configure(connection) -> None:
            connection.execute(f'SET search_path TO "{self.schema}", public')
            connection.commit()

        self._pool = ConnectionPool(
            conninfo=database_url,
            min_size=max(1, pool_min_size),
            max_size=max(pool_min_size, pool_max_size),
            open=False,
            timeout=10,
            max_waiting=max(20, pool_max_size * 4),
            kwargs={"row_factory": dict_row, "cursor_factory": ClientCursor},
            configure=configure,
        )

    @property
    def backend_name(self) -> str:
        return "postgresql+pgvector"

    def _prepare(self, query: str) -> str:
        prepared = query.replace("BEGIN IMMEDIATE", "BEGIN")
        prepared = prepared.replace("?", "%s")
        prepared = prepared.replace(" COLLATE NOCASE", "")
        prepared = prepared.replace(
            "MAX(memories.confidence, excluded.confidence)",
            "GREATEST(memories.confidence, excluded.confidence)",
        )
        prepared = prepared.replace(
            "MAX(memories.importance, excluded.importance)",
            "GREATEST(memories.importance, excluded.importance)",
        )
        prepared = prepared.replace(
            "MAX(progress_percent, 1)", "GREATEST(progress_percent, 1)",
        )
        return prepared

    def initialize(self) -> None:
        try:
            expected_migrations = postgres_migration_manifest()
            state_expressions = [
                "to_regnamespace(?)::text AS schema_name",
                "to_regtype('public.vector')::text AS vector_type",
            ]
            state_params: list[str] = [self.schema]
            for index, relation in enumerate(_REQUIRED_SCHEMA_RELATIONS):
                state_expressions.append(f"to_regclass(?)::text AS relation_{index}")
                state_params.append(f"{self.schema}.{relation}")

            with closing(self.connect()) as db:
                try:
                    state = db.execute(
                        "SELECT " + ", ".join(state_expressions), state_params,
                    ).fetchone()
                    applied_rows = db.execute(
                        "SELECT version, checksum "
                        "FROM memorypal_meta.schema_migrations "
                        "WHERE version NOT LIKE 'archive\\_%' ESCAPE '\\'",
                    ).fetchall()
                finally:
                    db.rollback()

            if not state or not state.get("schema_name"):
                raise PostgresMigrationError(
                    f'PostgreSQL schema "{self.schema}" has not been migrated'
                )
            if not state.get("vector_type"):
                raise PostgresMigrationError("PostgreSQL extension public.vector is missing")
            missing_relations = [
                relation
                for index, relation in enumerate(_REQUIRED_SCHEMA_RELATIONS)
                if not state.get(f"relation_{index}")
            ]
            if missing_relations:
                raise PostgresMigrationError(
                    "PostgreSQL schema is incomplete; missing relations: "
                    + ", ".join(missing_relations)
                )
            validate_postgres_migration_rows(expected_migrations, applied_rows)
        except PostgresMigrationError:
            raise
        except Exception as exc:
            raise PostgresMigrationError(
                "PostgreSQL migration state could not be verified; run the scale migration job"
            ) from exc

    def connect(self) -> _PooledConnection:
        if self._pool.closed:
            self._pool.open(wait=True)
        return _PooledConnection(self, self._pool.getconn())

    @contextmanager
    def transaction(self):
        with closing(self.connect()) as db:
            # psycopg connections use autocommit=False and start a transaction
            # automatically before the first statement. Sending an explicit
            # BEGIN here would therefore produce PostgreSQL's recurring
            # "there is already a transaction in progress" warning.
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    @contextmanager
    def read_transaction(self):
        # PostgreSQL READ COMMITTED takes a new snapshot for every statement.
        # The admin overview is a multi-query read model, so pin one read-only
        # snapshot until totals, routes, and trend buckets are all complete.
        with closing(self.connect()) as db:
            # SET TRANSACTION is the first statement, so psycopg implicitly
            # opens the transaction and then applies these characteristics to
            # it without a second BEGIN.
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    def close(self) -> None:
        if not self._pool.closed:
            self._pool.close()

    def fetch_one(self, query: str, params: Iterable[Any] = ()):
        with closing(self.connect()) as db:
            row = db.execute(query, tuple(params)).fetchone()
            db.rollback()
            return row

    def fetch_all(self, query: str, params: Iterable[Any] = ()) -> list:
        with closing(self.connect()) as db:
            rows = db.execute(query, tuple(params)).fetchall()
            db.rollback()
            return rows

    def execute(self, query: str, params: Iterable[Any] = ()) -> int:
        try:
            with closing(self.connect()) as db:
                cursor = db.execute(query, tuple(params))
                db.commit()
                return cursor.rowcount
        except self._psycopg.errors.UniqueViolation as exc:
            raise DatabaseIntegrityError(str(exc)) from exc

    def claim_outbox_events(
        self,
        worker_id: str,
        *,
        limit: int = 100,
        lease_seconds: int = 30,
    ) -> list:
        """Claim independent relay batches without blocking other replicas."""
        now = datetime.now(UTC)
        now_value = now.isoformat()
        locked_until = (now + timedelta(
            seconds=max(5, min(300, int(lease_seconds))),
        )).isoformat()
        with self.transaction() as db:
            candidates = db.execute(
                "SELECT event_id FROM event_outbox WHERE "
                + self._outbox_claimable_sql()
                + " ORDER BY created_at ASC LIMIT ? FOR UPDATE SKIP LOCKED",
                (now_value, now_value, max(1, min(1000, limit))),
            ).fetchall()
            claimed = []
            for candidate in candidates:
                db.execute(
                    "UPDATE event_outbox SET status = 'publishing', locked_by = ?, "
                    "locked_until = ?, attempts = attempts + 1 WHERE event_id = ?",
                    (worker_id, locked_until, candidate["event_id"]),
                )
                claimed.append(db.execute(
                    "SELECT * FROM event_outbox WHERE event_id = ?",
                    (candidate["event_id"],),
                ).fetchone())
            return claimed

    def get_user_by_email(self, email: str):
        return self.fetch_one("SELECT * FROM users WHERE lower(email) = lower(?)", (email,))

    def revoke_token(self, jti: str, expires_at: int) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO revoked_tokens VALUES (?, ?) "
                "ON CONFLICT(jti) DO UPDATE SET expires_at = excluded.expires_at",
                (jti, expires_at),
            )
            db.execute(
                "DELETE FROM revoked_tokens WHERE expires_at < EXTRACT(EPOCH FROM now())",
            )

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
                "INSERT INTO user_voice_profiles ("
                "user_id, voice_id, owner_ref, registration_state, created_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                (user_id, voice_id, normalized_owner, registration_state, utc_now()),
            )
            if normalized_owner is not None and provisional_cleanup_delay_seconds is not None:
                self._enqueue_archive_voice_cleanup_in_transaction(
                    db,
                    owner_ref=normalized_owner,
                    voice_id=voice_id,
                    delay_seconds=provisional_cleanup_delay_seconds,
                )

    def save_conversation(
        self,
        user_id: str,
        session_id: str,
        user_text: str,
        assistant_text: str,
        input_audio_path: str | None = None,
        output_audio_path: str | None = None,
        expected_auth_version: int | None = None,
    ):
        conversation_id = str(uuid.uuid4())
        now = utc_now()
        with self.transaction() as db:
            if expected_auth_version is not None:
                self._require_account_fence(db, user_id, expected_auth_version)
            db.execute(
                "INSERT INTO conversations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    conversation_id, session_id, user_id, user_text, assistant_text,
                    input_audio_path, output_audio_path, now,
                ),
            )
            db.execute(
                "UPDATE chat_sessions SET updated_at = ?, title = CASE "
                "WHEN title = '새로운 대화' THEN ? ELSE title END "
                "WHERE id = ? AND user_id = ?",
                (now, user_text[:32], session_id, user_id),
            )
            return db.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,),
            ).fetchone()

    def begin_portrait_generation(
        self, user_id: str, persona: str, expected_auth_version: int | None = None,
    ):
        generation_id = str(uuid.uuid4())
        now = utc_now()
        with self.transaction() as db:
            # The advisory lock also covers the first request, when no portrait row
            # exists yet and SELECT FOR UPDATE alone cannot prevent a duplicate.
            db.execute("SELECT pg_advisory_xact_lock(hashtextextended(?, 0))", (user_id,))
            if expected_auth_version is None:
                user_row = db.execute(
                    "SELECT auth_version FROM users WHERE id = ? AND account_status = 'active'",
                    (user_id,),
                ).fetchone()
                if user_row is None:
                    raise AccountAccessFenceError("account_authority_changed")
                expected_auth_version = int(user_row["auth_version"])
            self._require_account_fence(db, user_id, expected_auth_version)
            current = db.execute(
                "SELECT * FROM portraits WHERE user_id = ? FOR UPDATE", (user_id,),
            ).fetchone()
            if (
                current is not None
                and current["status"] in {"queued", "analyzing"}
                and int(current["account_auth_version"]) == expected_auth_version
            ):
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
                    generation_id = excluded.generation_id, status = 'queued',
                    account_auth_version = excluded.account_auth_version,
                    persona = excluded.persona, title = NULL, summary = NULL,
                    accuracy_percent = 0, analyzed_sessions = 0, analyzed_messages = 0,
                    progress_percent = 0, vector_method = NULL,
                    started_at = excluded.started_at, completed_at = NULL,
                    updated_at = excluded.updated_at, error = NULL,
                    worker_id = NULL, lease_expires_at = NULL
                """,
                (user_id, generation_id, expected_auth_version, persona, now, now),
            )
            db.execute("DELETE FROM portrait_session_features WHERE user_id = ?", (user_id,))
            row = db.execute("SELECT * FROM portraits WHERE user_id = ?", (user_id,)).fetchone()
            return row, True

    def update_portrait_session_vector(
        self,
        user_id: str,
        generation_id: str,
        session_id: str,
        vector_json: str,
        vector_method: str,
        worker_id: str,
    ) -> bool:
        vector = json.loads(vector_json)
        now = utc_now()
        with self.transaction() as db:
            owner = db.execute(
                "SELECT 1 FROM portraits WHERE user_id = ? AND generation_id = ? "
                "AND status = 'analyzing' AND worker_id = ? AND lease_expires_at > ? "
                "AND EXISTS (SELECT 1 FROM users WHERE users.id = portraits.user_id "
                "AND users.account_status = 'active' "
                "AND users.auth_version = portraits.account_auth_version)",
                (user_id, generation_id, worker_id, now),
            ).fetchone()
            if owner is None:
                return False
            return bool(db.execute(
                "UPDATE portrait_session_features SET vector_json = ?::jsonb, "
                "embedding = ?::vector, vector_dimensions = ?, vector_method = ?, "
                "updated_at = ? WHERE user_id = ? AND generation_id = ? AND session_id = ?",
                (
                    vector_json, vector_json, len(vector), vector_method, now,
                    user_id, generation_id, session_id,
                ),
            ).rowcount)

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
        vector_json = json.dumps(vector, separators=(",", ":"))
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":"))
        self.execute(
            """
            INSERT INTO rag_embeddings (
                id, user_id, namespace, source_id, content, metadata_json,
                vector_json, vector_dimensions, embedding_model, created_at,
                updated_at, embedding
            ) VALUES (?, ?, ?, ?, ?, ?::jsonb, ?::jsonb, ?, ?, ?, ?, ?::vector)
            ON CONFLICT(user_id, namespace, source_id, embedding_model) DO UPDATE SET
                content = excluded.content, metadata_json = excluded.metadata_json,
                vector_json = excluded.vector_json, vector_dimensions = excluded.vector_dimensions,
                updated_at = excluded.updated_at, embedding = excluded.embedding
            """,
            (
                str(uuid.uuid4()), user_id, namespace, source_id, content, metadata_json,
                vector_json, len(vector), embedding_model, now, now, vector_json,
            ),
        )

    def search_rag_embeddings(
        self,
        *,
        user_id: str,
        namespace: str,
        vector: list[float],
        embedding_model: str,
        limit: int = 10,
    ) -> list:
        dimensions = len(vector)
        if dimensions not in {384, 768}:
            raise ValueError("indexed pgvector search supports 384 or 768 dimensions")
        vector_json = json.dumps(vector, separators=(",", ":"))
        distance = (
            f"embedding::vector({dimensions}) <=> ?::vector({dimensions})"
        )
        return self.fetch_all(
            f"SELECT *, 1 - ({distance}) AS similarity FROM rag_embeddings "
            "WHERE user_id = ? AND namespace = ? AND embedding_model = ? "
            "AND vector_dimensions = ? AND embedding IS NOT NULL "
            f"ORDER BY {distance} LIMIT ?",
            (
                vector_json, user_id, namespace, embedding_model, dimensions,
                vector_json, max(1, min(100, limit)),
            ),
        )
