from __future__ import annotations

from .config import Settings
from .database import Database


def create_database(settings: Settings):
    """Select the local SQLite adapter or the production PostgreSQL adapter."""
    if not settings.database_url:
        return Database(settings.database_path)

    scheme = settings.database_url.split(":", 1)[0].lower()
    if scheme not in {"postgres", "postgresql"}:
        raise ValueError("MEMORYPAL_DATABASE_URL currently supports PostgreSQL only")
    from .postgres_database import PostgresDatabase

    return PostgresDatabase(
        settings.database_url,
        schema=settings.database_schema,
        pool_min_size=settings.database_pool_min_size,
        pool_max_size=settings.database_pool_max_size,
    )
