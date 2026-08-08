from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "backend" / "gateway"
sys.path.insert(0, str(GATEWAY))

from memorypal_api.postgres_database import PostgresDatabase  # noqa: E402


TABLES = (
    "users",
    "revoked_tokens",
    "chat_sessions",
    "conversations",
    "memories",
    "user_voice_profiles",
    "archive_voice_cleanup_jobs",
    "attachments",
    "session_working_memory",
    "portraits",
    "portrait_session_features",
    "operation_states",
    "operation_state_transitions",
    "user_transaction_events",
    "admin_audit_events",
    "admin_account_events",
    "event_outbox",
    "rag_embeddings",
)

ADMIN_REF_NAMESPACE = uuid.UUID("7129fd82-86cb-4ce5-a095-25168ca67293")
JSON_COLUMNS = {
    ("portrait_session_features", "vector_json"),
    ("operation_states", "metadata_json"),
    ("user_transaction_events", "metadata_json"),
    ("event_outbox", "payload_json"),
    ("rag_embeddings", "metadata_json"),
    ("rag_embeddings", "vector_json"),
}
PRIMARY_KEY_OVERRIDES = {
    # PostgreSQL partitions by occurred_at and therefore uses the composite
    # key even though the SQLite development table historically used event_id.
    "user_transaction_events": ["event_id", "occurred_at"],
}


class MigrationConflictError(RuntimeError):
    """An existing PostgreSQL row conflicts with the SQLite source row."""


def parse_args() -> argparse.Namespace:
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(
        description=(
            "Copy the current MemoryPal SQLite data into PostgreSQL without "
            "deleting or modifying the source database. Stop the Gateway first."
        ),
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=Path(os.getenv(
            "MEMORYPAL_DATABASE_PATH",
            ROOT / "backend" / "gateway" / "data" / "memorypal.db",
        )),
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("MEMORYPAL_DATABASE_URL", ""),
        help="PostgreSQL URL. Defaults to MEMORYPAL_DATABASE_URL.",
    )
    parser.add_argument(
        "--schema",
        default=os.getenv("MEMORYPAL_DATABASE_SCHEMA", "memorypal_gateway"),
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    return parser.parse_args()


def source_tables(source: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in source.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def table_columns(source: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in source.execute(f'PRAGMA table_info("{table}")')]


def primary_key_columns(source: sqlite3.Connection, table: str) -> list[str]:
    columns = [
        (int(row[5]), str(row[1]))
        for row in source.execute(f'PRAGMA table_info("{table}")')
        if int(row[5]) > 0
    ]
    return [name for _position, name in sorted(columns)]


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def prepared_values(table: str, columns: list[str], row: sqlite3.Row) -> list[object]:
    values = list(row)
    if table == "users" and "is_admin" in columns:
        index = columns.index("is_admin")
        values[index] = bool(values[index])
    if table == "users" and "admin_ref" in columns:
        index = columns.index("admin_ref")
        if not values[index]:
            user_id = str(values[columns.index("id")])
            # A stable value makes a retry compare equal instead of inventing a
            # second identity after a partially completed migration.
            values[index] = str(uuid.uuid5(ADMIN_REF_NAMESPACE, user_id))
    return values


def _json_value(value: object) -> object:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _utc_datetime(value: object) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
        str(value).replace("Z", "+00:00")
    )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def values_equal(table: str, column: str, source_value: object, target_value: object) -> bool:
    if source_value is None or target_value is None:
        return source_value is None and target_value is None
    if (table, column) in JSON_COLUMNS:
        try:
            return _json_value(source_value) == _json_value(target_value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
    if table == "users" and column == "is_admin":
        return bool(source_value) is bool(target_value)
    if isinstance(target_value, datetime):
        try:
            return _utc_datetime(source_value) == _utc_datetime(target_value)
        except (TypeError, ValueError):
            return False
    if isinstance(target_value, Decimal):
        try:
            return Decimal(str(source_value)) == target_value
        except (ValueError, ArithmeticError):
            return False
    if isinstance(target_value, float) or isinstance(source_value, float):
        try:
            return math.isclose(
                float(source_value), float(target_value), rel_tol=1e-12, abs_tol=1e-12,
            )
        except (TypeError, ValueError):
            return False
    if isinstance(target_value, memoryview):
        target_value = target_value.tobytes()
    return source_value == target_value


def verify_existing_row(
    db,
    *,
    table: str,
    columns: list[str],
    primary_keys: list[str],
    values: list[object],
) -> None:
    key_clauses = " AND ".join(
        f"{quote_identifier(column)} IS NOT DISTINCT FROM ?" for column in primary_keys
    )
    key_values = tuple(values[columns.index(column)] for column in primary_keys)
    quoted_columns = ", ".join(quote_identifier(column) for column in columns)
    existing = db.execute(
        f"SELECT {quoted_columns} FROM {quote_identifier(table)} WHERE {key_clauses}",
        key_values,
    ).fetchone()
    if existing is None:
        raise MigrationConflictError(
            f"{table}: a non-primary unique constraint conflicts with source data"
        )
    mismatched = [
        column
        for column, source_value in zip(columns, values)
        if not values_equal(table, column, source_value, existing[column])
    ]
    if mismatched:
        raise MigrationConflictError(
            f"{table}: existing primary-key row differs in columns "
            + ", ".join(mismatched)
        )


def copy_table(
    source: sqlite3.Connection,
    target: PostgresDatabase,
    table: str,
    batch_size: int,
) -> tuple[int, int]:
    columns = table_columns(source, table)
    if not columns:
        return 0, 0
    primary_keys = PRIMARY_KEY_OVERRIDES.get(table) or primary_key_columns(source, table)
    if any(column not in columns for column in primary_keys):
        raise MigrationConflictError(
            f"{table}: source is missing a required migration key column"
        )
    if not primary_keys:
        raise MigrationConflictError(
            f"{table}: source table has no primary key, so safe idempotent copy is impossible"
        )
    quoted_columns = ", ".join(quote_identifier(column) for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    insert_sql = (
        f"INSERT INTO {quote_identifier(table)} ({quoted_columns}) VALUES ({placeholders}) "
        "ON CONFLICT DO NOTHING"
    )
    cursor = source.execute(
        f"SELECT {quoted_columns} FROM {quote_identifier(table)} "
        f"ORDER BY {', '.join(quote_identifier(column) for column in primary_keys)}"
    )
    source_count = 0
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        with target.transaction() as db:
            for row in rows:
                values = prepared_values(table, columns, row)
                inserted = db.execute(insert_sql, tuple(values)).rowcount
                if inserted == 0:
                    verify_existing_row(
                        db,
                        table=table,
                        columns=columns,
                        primary_keys=primary_keys,
                        values=values,
                    )
                elif inserted != 1:
                    raise MigrationConflictError(
                        f"{table}: PostgreSQL returned an unexpected insert row count"
                    )
        source_count += len(rows)
        print(f"  {table}: copied/checked {source_count:,} rows", flush=True)

    target_row = target.fetch_one(f'SELECT count(*) AS count FROM "{table}"')
    return source_count, int(target_row["count"])


def main() -> None:
    args = parse_args()
    sqlite_path = args.sqlite.expanduser().resolve()
    if not sqlite_path.is_file():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")
    if not args.database_url:
        raise SystemExit(
            "MEMORYPAL_DATABASE_URL or --database-url is required. "
            "The URL is never printed by this script."
        )
    batch_size = max(1, min(10_000, int(args.batch_size)))

    source = sqlite3.connect(
        f"{sqlite_path.as_uri()}?mode=ro", uri=True, timeout=30,
    )
    source.row_factory = sqlite3.Row
    # Pin every table read to one SQLite snapshot. Stopping Gateway is still
    # required for a clean cutover, but a stray writer can no longer make the
    # copied tables represent different points in time.
    source.execute("BEGIN")
    target = PostgresDatabase(
        args.database_url,
        schema=args.schema,
        pool_min_size=1,
        pool_max_size=4,
    )
    failures: list[str] = []
    try:
        target.initialize()
        existing_tables = source_tables(source)
        print("Starting idempotent SQLite -> PostgreSQL copy.")
        for table in TABLES:
            if table not in existing_tables:
                target_row = target.fetch_one(
                    f"SELECT count(*) AS count FROM {quote_identifier(table)}"
                )
                target_count = int(target_row["count"])
                failures.append(
                    f"{table} is missing from SQLite (PostgreSQL has {target_count} rows); "
                    "start the current Gateway once in SQLite mode before cutover"
                )
                print(f"  {table}: required source table is missing", flush=True)
                continue
            source_count, target_count = copy_table(source, target, table, batch_size)
            print(
                f"  {table}: source={source_count:,}, target={target_count:,}",
                flush=True,
            )
            if target_count != source_count:
                failures.append(
                    f"{table} target count {target_count} does not equal source count {source_count}"
                )
    finally:
        source.rollback()
        source.close()
        target.close()

    if failures:
        raise SystemExit("Migration verification failed:\n- " + "\n- ".join(failures))
    print(
        "Copy, conflict comparison, and exact row-count verification completed. "
        "Keep the SQLite file as a "
        "rollback backup until application smoke tests pass."
    )


if __name__ == "__main__":
    main()
