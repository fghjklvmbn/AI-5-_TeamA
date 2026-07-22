from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# All services share the ignored repository-root .env. Keep the legacy Gateway
# file as a temporary fallback for existing installations.
ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"
LEGACY_GATEWAY_ENV = Path(__file__).resolve().parents[1] / ".env"
ACTIVE_ENV = ROOT_ENV if ROOT_ENV.exists() else LEGACY_GATEWAY_ENV
# Deployment/runtime process variables are authoritative. In particular,
# run.ps1 injects the generated Gateway-to-Archive credential after reading a
# blank example value; reloading .env must not erase that secret.
load_dotenv(ACTIVE_ENV, override=False)


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


def _path(name: str, default: str) -> Path:
    value = Path(os.getenv(name, default))
    return value if value.is_absolute() else (ACTIVE_ENV.parent / value).resolve()


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    database_url: str
    database_pool_min_size: int
    database_pool_max_size: int
    database_schema: str
    redis_url: str
    redis_prefix: str
    task_queue_mode: str
    admin_emails: tuple[str, ...]
    jwt_secret: str
    jwt_minutes: int
    cors_origins: tuple[str, ...]
    root_path: str
    stt_url: str
    llm_url: str
    llm_api_key: str
    llm_default_model: str
    llm_companion_model: str
    llm_embedding_model: str
    tts_url: str
    tts_public_url: str
    archive_url: str
    archive_service_token: str
    archive_registration_cleanup_delay_seconds: int
    default_voice_id: str
    request_timeout_seconds: float
    web_search_max_results: int


def load_settings() -> Settings:
    database_pool_min_size = max(
        1, int(os.getenv("MEMORYPAL_DATABASE_POOL_MIN_SIZE", "2")),
    )
    database_pool_max_size = max(
        database_pool_min_size,
        int(os.getenv("MEMORYPAL_DATABASE_POOL_MAX_SIZE", "20")),
    )
    return Settings(
        database_path=_path("MEMORYPAL_DATABASE_PATH", "./data/memorypal.db"),
        database_url=os.getenv("MEMORYPAL_DATABASE_URL", "").strip(),
        database_pool_min_size=database_pool_min_size,
        database_pool_max_size=database_pool_max_size,
        database_schema=os.getenv(
            "MEMORYPAL_DATABASE_SCHEMA", "memorypal_gateway",
        ).strip() or "memorypal_gateway",
        redis_url=os.getenv("MEMORYPAL_REDIS_URL", "").strip(),
        redis_prefix=os.getenv("MEMORYPAL_REDIS_PREFIX", "memorypal").strip() or "memorypal",
        task_queue_mode=os.getenv("MEMORYPAL_TASK_QUEUE_MODE", "local").strip().lower(),
        admin_emails=tuple(
            email.casefold() for email in _csv("MEMORYPAL_ADMIN_EMAILS", "")
        ),
        jwt_secret=os.getenv("MEMORYPAL_JWT_SECRET") or secrets.token_urlsafe(48),
        jwt_minutes=int(os.getenv("MEMORYPAL_JWT_MINUTES", "720")),
        cors_origins=_csv(
            "MEMORYPAL_CORS_ORIGINS",
            "http://localhost:8081,http://localhost:8082,"
            "http://127.0.0.1:8081,http://127.0.0.1:8082,http://localhost:19006",
        ),
        root_path=os.getenv("MEMORYPAL_ROOT_PATH", "").rstrip("/"),
        stt_url=os.getenv("MEMORYPAL_STT_URL", "http://127.0.0.1:8001").rstrip("/"),
        llm_url=os.getenv("MEMORYPAL_LLM_URL", "http://127.0.0.1:8002").rstrip("/"),
        llm_api_key=os.getenv("MEMORYPAL_LLM_API_KEY", "lm-studio"),
        llm_default_model=os.getenv("MEMORYPAL_DEFAULT_LLM_MODEL", "qwen/qwen3.5-9b"),
        llm_companion_model=os.getenv("MEMORYPAL_COMPANION_LLM_MODEL", "memorypal_ai"),
        llm_embedding_model=os.getenv(
            "MEMORYPAL_EMBEDDING_MODEL", "text-embedding-nomic-embed-text-v1.5",
        ),
        tts_url=os.getenv("MEMORYPAL_TTS_URL", "http://127.0.0.1:8003").rstrip("/"),
        tts_public_url=os.getenv("MEMORYPAL_TTS_PUBLIC_URL", "").rstrip("/"),
        archive_url=os.getenv("MEMORYPAL_ARCHIVE_URL", "http://127.0.0.1:8004").rstrip("/"),
        archive_service_token=os.getenv("MEMORYPAL_ARCHIVE_SERVICE_TOKEN", "").strip(),
        archive_registration_cleanup_delay_seconds=max(
            60,
            int(os.getenv("MEMORYPAL_ARCHIVE_REGISTRATION_CLEANUP_DELAY", "1200")),
        ),
        default_voice_id=os.getenv(
            "MEMORYPAL_DEFAULT_VOICE_ID",
            "00000000-0000-0000-0000-000000000001",
        ),
        request_timeout_seconds=float(os.getenv("MEMORYPAL_REQUEST_TIMEOUT", "300")),
        web_search_max_results=max(1, min(6, int(os.getenv("MEMORYPAL_WEB_SEARCH_MAX_RESULTS", "4")))),
    )
