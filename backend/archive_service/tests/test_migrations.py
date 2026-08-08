from __future__ import annotations

import os
from pathlib import Path

import pytest

from database import postgres
from database.postgres import archive_migration_manifest, ordered_archive_migrations
from migrate import validate_archive_migration_preflight


MIGRATION_ROOT = Path(__file__).resolve().parents[1] / "sql_migrations"


def test_archive_dotenv_does_not_mix_injected_token_sources(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MEMORYPAL_ARCHIVE_SERVICE_TOKEN=\n"
        "MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE=./archive-token\n"
        "MEMORYPAL_JWT_SECRET=must-not-be-loaded\n",
        encoding="utf-8",
    )
    direct = "archive-injected-service-token-" + "d" * 48
    monkeypatch.setenv("MEMORYPAL_ARCHIVE_SERVICE_TOKEN", direct)
    monkeypatch.delenv("MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE", raising=False)
    monkeypatch.delenv("MEMORYPAL_JWT_SECRET", raising=False)

    postgres._load_archive_dotenv(env_file)

    assert os.environ["MEMORYPAL_ARCHIVE_SERVICE_TOKEN"] == direct
    assert "MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE" not in os.environ
    assert "MEMORYPAL_JWT_SECRET" not in os.environ


def test_archive_dotenv_loads_one_file_source_when_not_injected(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MEMORYPAL_ARCHIVE_SERVICE_TOKEN=\n"
        "MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE=./archive-token\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("MEMORYPAL_ARCHIVE_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE", raising=False)

    postgres._load_archive_dotenv(env_file)

    assert os.environ["MEMORYPAL_ARCHIVE_SERVICE_TOKEN"] == ""
    assert os.environ["MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE"] == "./archive-token"


def test_archive_migrations_are_non_destructive_and_schema_scoped():
    migrations = {
        path.name: path.read_text(encoding="utf-8")
        for path in MIGRATION_ROOT.glob("*.sql")
    }
    assert migrations
    for sql in migrations.values():
        assert "DROP TABLE" not in sql.upper()
        assert "memorypal_archive" in sql
        assert "SET search_path TO memorypal_archive, public" in sql

    assert "INSERT INTO" not in migrations["4_test_data.sql"].upper()


def test_archive_create_and_index_migrations_are_idempotent():
    create_sql = (MIGRATION_ROOT / "2_create.sql").read_text(encoding="utf-8")
    index_sql = (MIGRATION_ROOT / "3_indexes.sql").read_text(encoding="utf-8")
    assert create_sql.count("CREATE TABLE IF NOT EXISTS") == 5
    assert index_sql.count("CREATE INDEX IF NOT EXISTS") == 5


def test_archive_manifest_uses_prefixed_versions_and_sha256_checksums():
    manifest = archive_migration_manifest()
    assert set(manifest) == {
        f"archive_{path.name}" for path in MIGRATION_ROOT.glob("*.sql")
    }
    assert all(len(checksum) == 64 for checksum in manifest.values())


def test_archive_migrations_use_natural_consecutive_numeric_order(tmp_path):
    for order in range(1, 11):
        (tmp_path / f"{order}_migration.sql").write_text("SELECT 1;", encoding="utf-8")
    assert [path.name for path in ordered_archive_migrations(tmp_path)] == [
        f"{order}_migration.sql" for order in range(1, 11)
    ]


def test_archive_migrations_reject_missing_duplicate_and_invalid_prefixes(tmp_path):
    (tmp_path / "1_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "3_third.sql").write_text("SELECT 3;", encoding="utf-8")
    with pytest.raises(RuntimeError, match="consecutive"):
        ordered_archive_migrations(tmp_path)

    (tmp_path / "3_third.sql").unlink()
    (tmp_path / "1_duplicate.sql").write_text("SELECT 2;", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Duplicate"):
        ordered_archive_migrations(tmp_path)

    (tmp_path / "1_duplicate.sql").unlink()
    (tmp_path / "bad.sql").write_text("SELECT 4;", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Invalid"):
        ordered_archive_migrations(tmp_path)


class _LedgerResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _LedgerConnection:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _statement):
        return _LedgerResult(self._rows)


def test_archive_ledger_rejects_an_applied_migration_missing_from_source(monkeypatch):
    expected = {
        "archive_1_first.sql": "a" * 64,
        "archive_2_second.sql": "b" * 64,
    }
    monkeypatch.setattr(postgres, "archive_migration_manifest", lambda: expected)
    connection = _LedgerConnection([
        {"version": "archive_1_first.sql", "checksum": "a" * 64},
        {"version": "archive_2_second.sql", "checksum": "b" * 64},
        {"version": "archive_3_deleted.sql", "checksum": "c" * 64},
    ])

    with pytest.raises(RuntimeError, match="deleted or unknown files"):
        postgres._verify_archive_migration_ledger(connection)


def test_archive_migration_cli_preflights_drift_before_pending_ddl():
    manifest = {
        "archive_1_first.sql": "a" * 64,
        "archive_2_pending.sql": "b" * 64,
    }
    assert validate_archive_migration_preflight(
        manifest,
        [{"version": "archive_1_first.sql", "checksum": "a" * 64}],
    ) == {"archive_1_first.sql": "a" * 64}

    with pytest.raises(RuntimeError, match="deleted or unknown files"):
        validate_archive_migration_preflight(manifest, [
            {"version": "archive_1_first.sql", "checksum": "a" * 64},
            {"version": "archive_3_deleted.sql", "checksum": "c" * 64},
        ])
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        validate_archive_migration_preflight(manifest, [
            {"version": "archive_1_first.sql", "checksum": "x" * 64},
        ])


def test_archive_runtime_schema_check_contains_no_ddl():
    runtime = (MIGRATION_ROOT.parent / "database" / "postgres.py").read_text(
        encoding="utf-8"
    ).upper()
    for statement in ("ALTER TABLE", "CREATE TABLE", "CREATE INDEX"):
        assert statement not in runtime


def test_archive_runner_is_transactional_and_uses_the_shared_ledger():
    runner = (MIGRATION_ROOT.parent / "migrate.py").read_text(encoding="utf-8")
    assert "with engine.begin() as connection" in runner
    assert "pg_advisory_xact_lock" in runner
    assert "memorypal_meta.schema_migrations" in runner
    assert "checksum mismatch" in runner
