from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    jwt_secret: str
    jwt_minutes: int
    cors_origins: tuple[str, ...]
    stt_url: str
    llm_url: str
    llm_api_key: str
    llm_model: str
    tts_url: str
    archive_url: str
    default_voice_id: str
    request_timeout_seconds: float


def load_settings() -> Settings:
    return Settings(
        database_path=Path(os.getenv("MEMORYPAL_DATABASE_PATH", "./data/memorypal.db")),
        jwt_secret=os.getenv("MEMORYPAL_JWT_SECRET") or secrets.token_urlsafe(48),
        jwt_minutes=int(os.getenv("MEMORYPAL_JWT_MINUTES", "720")),
        cors_origins=_csv(
            "MEMORYPAL_CORS_ORIGINS",
            "http://localhost:8081,http://localhost:19006",
        ),
        stt_url=os.getenv("MEMORYPAL_STT_URL", "http://127.0.0.1:8001").rstrip("/"),
        llm_url=os.getenv("MEMORYPAL_LLM_URL", "http://127.0.0.1:8002/v1").rstrip("/"),
        llm_api_key=os.getenv("MEMORYPAL_LLM_API_KEY", "lm-studio"),
        llm_model=os.getenv("MEMORYPAL_LLM_MODEL", "Qwen/Qwen3.5-4B"),
        tts_url=os.getenv("MEMORYPAL_TTS_URL", "http://127.0.0.1:8003").rstrip("/"),
        archive_url=os.getenv("MEMORYPAL_ARCHIVE_URL", "http://127.0.0.1:8004").rstrip("/"),
        default_voice_id=os.getenv(
            "MEMORYPAL_DEFAULT_VOICE_ID",
            "00000000-0000-0000-0000-000000000001",
        ),
        request_timeout_seconds=float(os.getenv("MEMORYPAL_REQUEST_TIMEOUT", "90")),
    )
