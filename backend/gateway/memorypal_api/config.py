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
load_dotenv(ACTIVE_ENV, override=True)


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


def _path(name: str, default: str) -> Path:
    value = Path(os.getenv(name, default))
    return value if value.is_absolute() else (ACTIVE_ENV.parent / value).resolve()


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    jwt_secret: str
    jwt_minutes: int
    cors_origins: tuple[str, ...]
    root_path: str
    stt_url: str
    llm_url: str
    llm_api_key: str
    llm_default_model: str
    llm_companion_model: str
    tts_url: str
    tts_public_url: str
    archive_url: str
    archive_service_token: str
    default_voice_id: str
    request_timeout_seconds: float


def load_settings() -> Settings:
    return Settings(
        database_path=_path("MEMORYPAL_DATABASE_PATH", "./data/memorypal.db"),
        jwt_secret=os.getenv("MEMORYPAL_JWT_SECRET") or secrets.token_urlsafe(48),
        jwt_minutes=int(os.getenv("MEMORYPAL_JWT_MINUTES", "720")),
        cors_origins=_csv(
            "MEMORYPAL_CORS_ORIGINS",
            "http://localhost:8081,http://localhost:19006",
        ),
        root_path=os.getenv("MEMORYPAL_ROOT_PATH", "").rstrip("/"),
        stt_url=os.getenv("MEMORYPAL_STT_URL", "http://127.0.0.1:8001").rstrip("/"),
        llm_url=os.getenv("MEMORYPAL_LLM_URL", "http://127.0.0.1:8002").rstrip("/"),
        llm_api_key=os.getenv("MEMORYPAL_LLM_API_KEY", "lm-studio"),
        llm_default_model=os.getenv("MEMORYPAL_DEFAULT_LLM_MODEL", "qwen3.5-4b"),
        llm_companion_model=os.getenv("MEMORYPAL_COMPANION_LLM_MODEL", "memorypal_ai"),
        tts_url=os.getenv("MEMORYPAL_TTS_URL", "http://127.0.0.1:8003").rstrip("/"),
        tts_public_url=os.getenv("MEMORYPAL_TTS_PUBLIC_URL", "").rstrip("/"),
        archive_url=os.getenv("MEMORYPAL_ARCHIVE_URL", "http://127.0.0.1:8004").rstrip("/"),
        archive_service_token=os.getenv("MEMORYPAL_ARCHIVE_SERVICE_TOKEN", "").strip(),
        default_voice_id=os.getenv(
            "MEMORYPAL_DEFAULT_VOICE_ID",
            "00000000-0000-0000-0000-000000000001",
        ),
        request_timeout_seconds=float(os.getenv("MEMORYPAL_REQUEST_TIMEOUT", "300")),
    )
