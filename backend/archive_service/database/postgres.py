import hashlib
import os
import re
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"
# Archive must not import unrelated Gateway/model credentials from the shared
# root dotenv file. Preserve local/manual startup compatibility by loading only
# the settings this service owns.
ARCHIVE_ENV_NAMES = {
    "MEMORYPAL_ARCHIVE_DATABASE_URL",
    "MEMORYPAL_ARCHIVE_PENDING_TTL_SECONDS",
    "MEMORYPAL_ARCHIVE_PRIVATE_UPLOAD_DIR",
    "MEMORYPAL_ARCHIVE_PUBLIC_URL",
    "MEMORYPAL_ARCHIVE_REAPER_INTERVAL_SECONDS",
    "MEMORYPAL_ARCHIVE_SERVICE_TOKEN",
    "MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE",
    "MEMORYPAL_ARCHIVE_SQL_ECHO",
    "MEMORYPAL_DEFAULT_VOICE_ID",
}
ARCHIVE_TOKEN_ENV_NAMES = {
    "MEMORYPAL_ARCHIVE_SERVICE_TOKEN",
    "MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE",
}


def _load_archive_dotenv(path: Path) -> None:
    if not path.exists():
        return
    # Treat the direct/file pair as one setting. If the parent process already
    # selected either source, loading the other half from .env would create an
    # artificial ambiguity and make authenticated readiness fail closed.
    token_source_is_injected = any(
        os.getenv(name, "").strip() for name in ARCHIVE_TOKEN_ENV_NAMES
    )
    for name, value in dotenv_values(path).items():
        if name not in ARCHIVE_ENV_NAMES or value is None:
            continue
        if token_source_is_injected and name in ARCHIVE_TOKEN_ENV_NAMES:
            continue
        os.environ.setdefault(name, value)


_load_archive_dotenv(ROOT_ENV)

DATABASE_URL = os.getenv(
    "MEMORYPAL_ARCHIVE_DATABASE_URL",
    "postgresql://postgres@localhost:5432/memoripal"
)
ARCHIVE_SCHEMA = "memorypal_archive"
MIGRATION_ROOT = Path(__file__).resolve().parents[1] / "sql_migrations"
REQUIRED_TABLES = {
    "sessions",
    "voice_profiles",
    "conversations",
    "memories",
    "voice_owner_states",
}
REQUIRED_VOICE_COLUMNS = {
    "owner_ref",
    "registration_token_hash",
    "registration_state",
    "expires_at",
    "legacy_source_path",
}
REQUIRED_VOICE_INDEXES = {
    "uq_voice_profiles_registration_token_hash",
    "idx_voice_profiles_private_state_expiry",
}
ARCHIVE_MIGRATION_NAME_RE = re.compile(r"^(?P<order>[1-9][0-9]*)_[A-Za-z0-9_.-]+\.sql$")

engine_options: dict[str, object] = {}
if DATABASE_URL.startswith("postgresql"):
    # Keep Archive objects out of public and other service schemas regardless
    # of the database user's role-level defaults.
    engine_options["connect_args"] = {
        "options": f"-csearch_path={ARCHIVE_SCHEMA},public",
    }

engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("MEMORYPAL_ARCHIVE_SQL_ECHO", "").strip().casefold()
    in {"1", "true", "yes", "on"},
    **engine_options,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def ordered_archive_migrations(root: Path | None = None) -> list[Path]:
    root = MIGRATION_ROOT if root is None else root
    indexed: list[tuple[int, Path]] = []
    seen_orders: set[int] = set()
    for path in root.glob("*.sql"):
        match = ARCHIVE_MIGRATION_NAME_RE.fullmatch(path.name)
        if match is None:
            raise RuntimeError(f"Invalid Archive migration filename: {path.name}")
        order = int(match.group("order"))
        if order in seen_orders:
            raise RuntimeError(f"Duplicate Archive migration prefix: {order}")
        seen_orders.add(order)
        indexed.append((order, path))

    indexed.sort(key=lambda item: item[0])
    actual_orders = [order for order, _path in indexed]
    expected_orders = list(range(1, len(indexed) + 1))
    if actual_orders != expected_orders:
        raise RuntimeError(
            "Archive migration prefixes must be consecutive starting at 1: "
            f"found {actual_orders}"
        )
    return [path for _order, path in indexed]


def archive_migration_manifest() -> dict[str, str]:
    migrations = ordered_archive_migrations()
    if not migrations:
        raise RuntimeError("No Archive SQL migrations were found.")
    return {
        f"archive_{path.name}": hashlib.sha256(path.read_bytes()).hexdigest()
        for path in migrations
    }


def _verify_archive_migration_ledger(connection) -> None:
    expected = archive_migration_manifest()
    try:
        rows = connection.execute(
            text(
                "SELECT version, checksum FROM memorypal_meta.schema_migrations "
                "WHERE version LIKE 'archive\\_%' ESCAPE '\\'"
            )
        ).mappings().all()
    except Exception as exc:
        raise RuntimeError(
            "Archive migration ledger is unavailable. Run the versioned migration job."
        ) from exc
    applied = {str(row["version"]): str(row["checksum"] or "") for row in rows}
    missing = sorted(set(expected) - set(applied))
    unexpected = sorted(set(applied) - set(expected))
    mismatched = sorted(
        version
        for version, checksum in expected.items()
        if version in applied and applied[version] != checksum
    )
    if missing:
        raise RuntimeError("Archive migrations are pending: " + ", ".join(missing))
    if unexpected:
        raise RuntimeError(
            "Archive migration ledger contains deleted or unknown files: "
            + ", ".join(unexpected)
        )
    if mismatched:
        raise RuntimeError("Archive migration checksum mismatch: " + ", ".join(mismatched))


def ensure_voice_registration_schema() -> None:
    """Verify the migrated Archive schema without executing runtime DDL."""
    with engine.connect() as connection:
        if connection.dialect.name == "postgresql":
            current_schema = connection.execute(text("SELECT current_schema()"))
            if current_schema.scalar_one() != ARCHIVE_SCHEMA:
                raise RuntimeError(
                    f"Archive database search_path must start with {ARCHIVE_SCHEMA}"
                )
            _verify_archive_migration_ledger(connection)
        inspector = inspect(connection)
        schema = ARCHIVE_SCHEMA if connection.dialect.name == "postgresql" else None
        tables = set(inspector.get_table_names(schema=schema))
        missing_tables = sorted(REQUIRED_TABLES - tables)
        if missing_tables:
            raise RuntimeError(
                "Archive schema is incomplete; missing tables: " + ", ".join(missing_tables)
            )
        columns = {
            str(column["name"])
            for column in inspector.get_columns("voice_profiles", schema=schema)
        }
        missing_columns = sorted(REQUIRED_VOICE_COLUMNS - columns)
        if missing_columns:
            raise RuntimeError(
                "Archive voice schema is incomplete; missing columns: "
                + ", ".join(missing_columns)
            )
        indexes = {
            str(index["name"])
            for index in inspector.get_indexes("voice_profiles", schema=schema)
        }
        missing_indexes = sorted(REQUIRED_VOICE_INDEXES - indexes)
        if missing_indexes:
            raise RuntimeError(
                "Archive voice schema is incomplete; missing indexes: "
                + ", ".join(missing_indexes)
            )
