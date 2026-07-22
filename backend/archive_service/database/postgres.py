import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)

DATABASE_URL = os.getenv(
    "MEMORYPAL_ARCHIVE_DATABASE_URL",
    "postgresql://postgres@localhost:5432/memoripal"
)

engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("MEMORYPAL_ARCHIVE_SQL_ECHO", "").strip().casefold()
    in {"1", "true", "yes", "on"},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def ensure_voice_registration_schema() -> None:
    """Add the private-registration columns to an existing Archive database."""
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text(
                "SELECT pg_advisory_xact_lock(hashtextextended("
                "'memorypal_archive_voice_schema', 0))"
            ))
        inspector = inspect(connection)
        if "voice_profiles" not in inspector.get_table_names():
            raise RuntimeError(
                "Archive schema is not ready: voice_profiles is missing. "
                "Apply the Archive SQL migrations before starting the service."
            )
        columns = {
            str(column["name"])
            for column in inspector.get_columns("voice_profiles")
        }
        timestamp_type = (
            "TIMESTAMPTZ"
            if connection.dialect.name == "postgresql"
            else "TIMESTAMP"
        )
        additions = {
            "owner_ref": "VARCHAR(64)",
            "registration_token_hash": "VARCHAR(64)",
            "registration_state": "VARCHAR(16) NOT NULL DEFAULT 'active'",
            "expires_at": timestamp_type,
            "legacy_source_path": "TEXT",
        }
        for column, ddl in additions.items():
            if column not in columns:
                connection.execute(text(
                    f"ALTER TABLE voice_profiles ADD COLUMN {column} {ddl}"
                ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "uq_voice_profiles_registration_token_hash "
            "ON voice_profiles(registration_token_hash)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_voice_profiles_private_state_expiry "
            "ON voice_profiles(registration_state, expires_at)"
        ))
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS voice_owner_states ("
            "owner_ref VARCHAR(64) PRIMARY KEY, "
            "state VARCHAR(16) NOT NULL DEFAULT 'active' "
            "CHECK (state IN ('active','purged')), "
            f"created_at {timestamp_type} NOT NULL, "
            f"purged_at {timestamp_type})"
        ))
