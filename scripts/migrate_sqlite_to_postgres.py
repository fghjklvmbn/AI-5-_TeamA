from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import uuid
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
    "attachments",
    "session_working_memory",
    "portraits",
    "portrait_session_features",
    "operation_states",
    "operation_state_transitions",
    "user_transaction_events",
    "admin_audit_events",
    "event_outbox",
    "rag_embeddings",
)


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


def copy_table(
    source: sqlite3.Connection,
    target: PostgresDatabase,
    table: str,
    batch_size: int,
) -> tuple[int, int]:
    columns = table_columns(source, table)
    if not columns:
        return 0, 0
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    insert_sql = (
        f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders}) '
        "ON CONFLICT DO NOTHING"
    )
    cursor = source.execute(f'SELECT {quoted_columns} FROM "{table}"')
    source_count = 0
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        with target.transaction() as db:
            for row in rows:
                values = list(row)
                if table == "users" and "is_admin" in columns:
                    values[columns.index("is_admin")] = bool(
                        values[columns.index("is_admin")]
                    )
                if table == "users" and "admin_ref" in columns:
                    admin_ref_index = columns.index("admin_ref")
                    values[admin_ref_index] = values[admin_ref_index] or str(uuid.uuid4())
                db.execute(insert_sql, tuple(values))
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
        f"file:{sqlite_path.as_posix()}?mode=ro", uri=True, timeout=30,
    )
    source.row_factory = sqlite3.Row
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
                print(f"  {table}: source table does not exist; skipped")
                continue
            source_count, target_count = copy_table(source, target, table, batch_size)
            print(
                f"  {table}: source={source_count:,}, target={target_count:,}",
                flush=True,
            )
            if target_count < source_count:
                failures.append(
                    f"{table} target count {target_count} is below source count {source_count}"
                )
    finally:
        source.close()
        target.close()

    if failures:
        raise SystemExit("Migration verification failed:\n- " + "\n- ".join(failures))
    print(
        "Copy and row-count verification completed. Keep the SQLite file as a "
        "rollback backup until application smoke tests pass."
    )


if __name__ == "__main__":
    main()
