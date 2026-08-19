from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from memorypal_api import postgres_database
from memorypal_api.postgres_database import (
    PostgresDatabase,
    PostgresMigrationError,
    postgres_migration_manifest,
    validate_postgres_migration_rows,
)


class _Cursor:
    def __init__(self, *, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _ValidationConnection:
    def __init__(self, migration_rows):
        self.migration_rows = migration_rows
        self.queries: list[str] = []
        self.rolled_back = False
        self.closed = False

    def execute(self, query, _params=()):
        self.queries.append(query)
        if "to_regnamespace" in query:
            return _Cursor(row={
                "schema_name": "memorypal_gateway",
                "vector_type": "vector",
                **{f"relation_{index}": relation for index, relation in enumerate(
                    (
                        "users", "chat_sessions", "conversations", "memories",
                        "operation_states", "event_outbox", "rag_embeddings",
                    )
                )},
            })
        return _Cursor(rows=self.migration_rows)

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class _RecordingConnection:
    def __init__(self):
        self.calls = []

    def execute(self, *args):
        self.calls.append(args)
        return _Cursor()


class _TransactionConnection(_RecordingConnection):
    def __init__(self):
        super().__init__()
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class _PreparingOwner:
    @staticmethod
    def _prepare(query):
        return query.replace("?", "%s")


def test_pooled_connection_omits_empty_params_for_literal_percent_queries():
    native = _RecordingConnection()
    connection = postgres_database._PooledConnection(_PreparingOwner(), native)

    connection.execute("SELECT 'archive\\_%'")
    connection.execute("SELECT ?", ("value",))

    assert native.calls == [
        ("SELECT 'archive\\_%'",),
        ("SELECT %s", ("value",)),
    ]


def test_postgres_transaction_relies_on_psycopg_implicit_begin():
    connection = _TransactionConnection()
    database = object.__new__(PostgresDatabase)
    database.connect = lambda: connection

    with PostgresDatabase.transaction(database) as db:
        db.execute("UPDATE example SET value = 1")

    assert connection.calls == [("UPDATE example SET value = 1",)]
    assert connection.committed
    assert not connection.rolled_back
    assert connection.closed


def test_postgres_read_transaction_sets_characteristics_without_second_begin():
    connection = _TransactionConnection()
    database = object.__new__(PostgresDatabase)
    database.connect = lambda: connection

    with PostgresDatabase.read_transaction(database):
        pass

    assert connection.calls == [
        ("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY",),
    ]
    assert connection.committed
    assert connection.closed


def test_postgres_migration_manifest_uses_runner_versions_and_sha256():
    root = Path(__file__).resolve().parents[3]
    manifest = postgres_migration_manifest()
    gateway_schema = root / "backend" / "gateway" / "migrations" / "postgres_schema.sql"
    assert manifest["gateway_postgres_schema.sql"] == hashlib.sha256(
        gateway_schema.read_bytes()
    ).hexdigest()
    assert "0001_operational_foundation.sql" in manifest
    assert "0002_vector_store.sql" in manifest
    assert all(len(checksum) == 64 for checksum in manifest.values())


def test_postgres_migration_state_requires_every_checksum_to_match():
    expected = {"001.sql": "a" * 64, "002.sql": "b" * 64}
    validate_postgres_migration_rows(expected, [
        {"version": "001.sql", "checksum": "a" * 64},
        {"version": "002.sql", "checksum": "b" * 64},
    ])

    with pytest.raises(PostgresMigrationError, match="pending: 002.sql"):
        validate_postgres_migration_rows(expected, [
            {"version": "001.sql", "checksum": "a" * 64},
        ])
    with pytest.raises(PostgresMigrationError, match="checksum mismatch: 002.sql"):
        validate_postgres_migration_rows(expected, [
            {"version": "001.sql", "checksum": "a" * 64},
            {"version": "002.sql", "checksum": "c" * 64},
        ])
    with pytest.raises(PostgresMigrationError, match="deleted or unknown files: 003.sql"):
        validate_postgres_migration_rows(expected, [
            {"version": "001.sql", "checksum": "a" * 64},
            {"version": "002.sql", "checksum": "b" * 64},
            {"version": "003.sql", "checksum": "c" * 64},
        ])


def test_postgres_runtime_initialize_only_reads_and_validates(monkeypatch):
    expected = {"gateway_postgres_schema.sql": "a" * 64}
    monkeypatch.setattr(
        postgres_database, "postgres_migration_manifest", lambda: expected,
    )
    connection = _ValidationConnection([
        {"version": "gateway_postgres_schema.sql", "checksum": "a" * 64},
    ])
    database = object.__new__(PostgresDatabase)
    database.schema = "memorypal_gateway"
    database.connect = lambda: connection

    PostgresDatabase.initialize(database)

    assert connection.rolled_back
    assert connection.closed
    assert connection.queries
    assert all(query.lstrip().startswith("SELECT") for query in connection.queries)


def test_compose_runner_checksums_and_atomically_records_migrations():
    root = Path(__file__).resolve().parents[3]
    compose = (root / "docker-compose.scale.yml").read_text(encoding="utf-8")
    assert "sha256sum" in compose
    assert "Migration checksum mismatch" in compose
    assert "--single-transaction" in compose
    assert "INSERT INTO memorypal_meta.schema_migrations (version, checksum)" in compose
    assert "find /archive-runtime" in compose
    assert "sort -V" in compose
    assert "Archive migration prefixes must be consecutive" in compose
    assert "Migration ledger contains deleted or unknown file" in compose
    assert compose.index("Migration ledger contains deleted or unknown file") < compose.index(
        "Applying migration"
    )
    assert compose.index("Migration checksum mismatch during preflight") < compose.index(
        "Applying migration"
    )

    migration_root = root / "deploy" / "scale" / "postgres" / "migrations"
    for migration in migration_root.glob("*.sql"):
        sql = migration.read_text(encoding="utf-8")
        assert "BEGIN;" not in sql
        assert "COMMIT;" not in sql
