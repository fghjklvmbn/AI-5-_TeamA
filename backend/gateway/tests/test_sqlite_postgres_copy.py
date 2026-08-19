from __future__ import annotations

import importlib.util
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "migrate_sqlite_to_postgres.py"
SPEC = importlib.util.spec_from_file_location("memorypal_sqlite_copy", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


class SQLiteTarget:
    """Small mapping-row target that exercises the copyer's portable SQL."""

    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row

    @contextmanager
    def transaction(self):
        self.connection.execute("BEGIN")
        try:
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def fetch_one(self, query, params=()):
        return self.connection.execute(query, tuple(params)).fetchone()


def source_connection() -> sqlite3.Connection:
    source = sqlite3.connect(":memory:")
    source.row_factory = sqlite3.Row
    return source


def test_copy_is_idempotent_and_rejects_divergent_primary_key_rows():
    source = source_connection()
    target = SQLiteTarget()
    try:
        source.execute("CREATE TABLE items (id TEXT PRIMARY KEY, value TEXT NOT NULL UNIQUE)")
        source.execute("INSERT INTO items VALUES ('source-id', 'source-value')")
        source.commit()
        target.connection.execute(
            "CREATE TABLE items (id TEXT PRIMARY KEY, value TEXT NOT NULL UNIQUE)"
        )
        target.connection.commit()

        assert migration.copy_table(source, target, "items", 10) == (1, 1)
        assert migration.copy_table(source, target, "items", 10) == (1, 1)

        target.connection.execute(
            "UPDATE items SET value = 'different-value' WHERE id = 'source-id'"
        )
        target.connection.commit()
        with pytest.raises(migration.MigrationConflictError, match="differs"):
            migration.copy_table(source, target, "items", 10)
    finally:
        source.close()
        target.connection.close()


def test_copy_rejects_non_primary_unique_collision_and_reports_extra_rows():
    source = source_connection()
    target = SQLiteTarget()
    try:
        source.execute("CREATE TABLE items (id TEXT PRIMARY KEY, value TEXT NOT NULL UNIQUE)")
        source.execute("INSERT INTO items VALUES ('source-id', 'duplicate')")
        source.commit()
        target.connection.execute(
            "CREATE TABLE items (id TEXT PRIMARY KEY, value TEXT NOT NULL UNIQUE)"
        )
        target.connection.execute("INSERT INTO items VALUES ('other-id', 'duplicate')")
        target.connection.commit()
        with pytest.raises(migration.MigrationConflictError, match="non-primary"):
            migration.copy_table(source, target, "items", 10)

        target.connection.execute("DELETE FROM items")
        target.connection.commit()
        assert migration.copy_table(source, target, "items", 10) == (1, 1)
        target.connection.execute("INSERT INTO items VALUES ('extra-id', 'extra')")
        target.connection.commit()
        assert migration.copy_table(source, target, "items", 10) == (1, 2)
    finally:
        source.close()
        target.connection.close()


def test_migration_manifest_covers_state_tables_and_comparisons_are_typed():
    assert "archive_voice_cleanup_jobs" in migration.TABLES
    assert "admin_account_events" in migration.TABLES
    assert migration.PRIMARY_KEY_OVERRIDES["user_transaction_events"] == [
        "event_id",
        "occurred_at",
    ]
    assert migration.values_equal(
        "operation_states", "metadata_json", '{"answer": 42}', {"answer": 42}
    )
    assert migration.values_equal(
        "user_transaction_events",
        "occurred_at",
        "2026-08-05T00:00:00+00:00",
        datetime(2026, 8, 5, tzinfo=UTC),
    )
