from __future__ import annotations

import re

from sqlalchemy import text

from database.postgres import MIGRATION_ROOT, archive_migration_manifest, engine


VERSION_RE = re.compile(r"^archive_[A-Za-z0-9_.-]+$")


def validate_archive_migration_preflight(
    manifest: dict[str, str],
    rows: list[dict[str, object]],
) -> dict[str, str]:
    """Reject deleted or changed migrations before executing pending DDL."""
    applied = {
        str(row["version"]): str(row.get("checksum") or "")
        for row in rows
    }
    unexpected = sorted(set(applied) - set(manifest))
    mismatched = sorted(
        version
        for version, checksum in manifest.items()
        if version in applied and applied[version] and applied[version] != checksum
    )
    if unexpected:
        raise RuntimeError(
            "Archive migration ledger contains deleted or unknown files: "
            + ", ".join(unexpected)
        )
    if mismatched:
        raise RuntimeError(
            "Archive migration checksum mismatch: " + ", ".join(mismatched)
        )
    return applied


def apply_archive_migrations() -> list[str]:
    """Apply all Archive migrations and checksum them in one transaction."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Archive SQL migrations require PostgreSQL.")

    manifest = archive_migration_manifest()
    applied_versions: list[str] = []
    with engine.begin() as connection:
        connection.execute(text(
            "SELECT pg_advisory_xact_lock(hashtextextended("
            "'memorypal_archive_migrations', 0))"
        ))
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS memorypal_meta"))
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS memorypal_meta.schema_migrations ("
            "version text PRIMARY KEY, "
            "checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'), "
            "applied_at timestamptz NOT NULL DEFAULT clock_timestamp())"
        ))
        connection.execute(text(
            "ALTER TABLE memorypal_meta.schema_migrations "
            "ADD COLUMN IF NOT EXISTS checksum text"
        ))

        ledger_rows = connection.execute(text(
            "SELECT version, checksum FROM memorypal_meta.schema_migrations "
            "WHERE version LIKE 'archive\\_%' ESCAPE '\\'"
        )).mappings().all()
        applied = validate_archive_migration_preflight(manifest, ledger_rows)

        for version, checksum in manifest.items():
            if VERSION_RE.fullmatch(version) is None:
                raise RuntimeError(f"Invalid Archive migration version: {version}")
            if version in applied:
                recorded = applied[version]
                if not recorded:
                    connection.execute(
                        text(
                            "UPDATE memorypal_meta.schema_migrations "
                            "SET checksum = :checksum "
                            "WHERE version = :version AND checksum IS NULL"
                        ),
                        {"version": version, "checksum": checksum},
                    )
                    continue
                continue

            filename = version.removeprefix("archive_")
            migration_path = MIGRATION_ROOT / filename
            connection.exec_driver_sql(migration_path.read_text(encoding="utf-8"))
            connection.execute(
                text(
                    "INSERT INTO memorypal_meta.schema_migrations (version, checksum) "
                    "VALUES (:version, :checksum)"
                ),
                {"version": version, "checksum": checksum},
            )
            applied_versions.append(version)
    return applied_versions


def main() -> int:
    applied = apply_archive_migrations()
    if applied:
        for version in applied:
            print(f"Applied {version}")
    else:
        print("Archive schema is up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
