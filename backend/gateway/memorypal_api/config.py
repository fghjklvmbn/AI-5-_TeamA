from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


# All services share the ignored repository-root .env. Keep the legacy Gateway
# file as a temporary fallback for existing installations.
ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"
LEGACY_GATEWAY_ENV = Path(__file__).resolve().parents[1] / ".env"
ACTIVE_ENV = ROOT_ENV if ROOT_ENV.exists() else LEGACY_GATEWAY_ENV
# Deployment/runtime process variables are authoritative. In particular,
# run.ps1 injects the generated Gateway-to-Archive credential after reading a
# blank example value; reloading .env must not erase that secret.
_blocked_secret_sources: list[str] = []
for _secret_name in (
    "MEMORYPAL_JWT_SECRET",
    "MEMORYPAL_MODEL_SERVICE_TOKEN",
    "MEMORYPAL_ARCHIVE_SERVICE_TOKEN",
):
    _file_name = f"{_secret_name}_FILE"
    _direct_is_injected = bool(os.environ.get(_secret_name, "").strip())
    _file_is_injected = bool(os.environ.get(_file_name, "").strip())
    if _direct_is_injected and not _file_is_injected:
        os.environ[_file_name] = ""
        _blocked_secret_sources.append(_file_name)
    elif _file_is_injected and not _direct_is_injected:
        os.environ[_secret_name] = ""
        _blocked_secret_sources.append(_secret_name)
load_dotenv(ACTIVE_ENV, override=False)
for _blocked_name in _blocked_secret_sources:
    os.environ.pop(_blocked_name, None)


class SettingsError(RuntimeError):
    """Raised when a required runtime setting is missing or unsafe."""


_SECRET_PLACEHOLDER_MARKERS = (
    "change-me",
    "changeme",
    "placeholder",
    "replace-with",
)


def _secret_value(name: str, *, required: bool) -> str:
    """Load NAME or NAME_FILE and reject ambiguous or weak configured values."""
    direct_value = os.getenv(name, "").strip()
    file_setting = os.getenv(f"{name}_FILE", "").strip()
    if direct_value and file_setting:
        raise SettingsError(f"Set only one of {name} or {name}_FILE")

    value = direct_value
    if file_setting:
        secret_path = Path(file_setting).expanduser()
        if not secret_path.is_absolute():
            secret_path = (ACTIVE_ENV.parent / secret_path).resolve()
        try:
            value = secret_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            raise SettingsError(f"Unable to read {name}_FILE") from exc

    normalized = value.casefold().replace("_", "-")
    if not value and not required:
        return ""
    if not value:
        raise SettingsError(f"{name} is required")
    if len(value) < 32:
        raise SettingsError(f"{name} must contain at least 32 characters")
    if any(marker in normalized for marker in _SECRET_PLACEHOLDER_MARKERS):
        raise SettingsError(f"{name} must not use a placeholder value")
    return value


def _required_secret(name: str) -> str:
    return _secret_value(name, required=True)


def _optional_secret(name: str) -> str:
    return _secret_value(name, required=False)


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


def _cors_origins(name: str, default: str) -> tuple[str, ...]:
    origins: list[str] = []
    for raw_origin in _csv(name, default):
        origin = raw_origin.rstrip("/")
        parsed = urlsplit(origin)
        if (
            "*" in origin
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise SettingsError(
                f"{name} must contain only exact HTTP(S) origins without paths or wildcards"
            )
        if origin not in origins:
            origins.append(origin)
    if not origins:
        raise SettingsError(f"{name} must contain at least one exact origin")
    return tuple(origins)


def _path(name: str, default: str) -> Path:
    value = Path(os.getenv(name, default))
    return value if value.is_absolute() else (ACTIVE_ENV.parent / value).resolve()


def _optional_http_url(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        return ""
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise SettingsError(f"{name} must be an HTTP(S) URL without credentials or a fragment")
    return value


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
    model_service_token: str
    jwt_minutes: int
    cors_origins: tuple[str, ...]
    root_path: str
    stt_url: str
    llm_url: str
    llm_resource_url: str
    llm_api_key: str
    llm_default_model: str
    llm_companion_model: str
    llm_embedding_model: str
    llm_character_cue_enabled: bool
    lmstudio_model_root: Path | None
    lmstudio_cli: str
    huggingface_token: str
    tts_url: str
    tts_public_url: str
    archive_url: str
    archive_service_token: str
    archive_registration_cleanup_delay_seconds: int
    default_voice_id: str
    default_voice_audio_url: str
    default_voice_reference_text: str
    request_timeout_seconds: float
    web_search_max_results: int
    hardware_monitor_interval_seconds: int
    hardware_monitor_log_path: Path
    monitor_stt_url: str
    monitor_llm_url: str
    monitor_tts_url: str
    monitor_gateway_url: str
    monitor_archive_url: str


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
        jwt_secret=_required_secret("MEMORYPAL_JWT_SECRET"),
        model_service_token=_required_secret("MEMORYPAL_MODEL_SERVICE_TOKEN"),
        jwt_minutes=int(os.getenv("MEMORYPAL_JWT_MINUTES", "720")),
        cors_origins=_cors_origins(
            "MEMORYPAL_CORS_ORIGINS",
            "http://localhost:8081,http://localhost:8082,"
            "http://127.0.0.1:8081,http://127.0.0.1:8082,http://localhost:19006",
        ),
        root_path=os.getenv("MEMORYPAL_ROOT_PATH", "").rstrip("/"),
        stt_url=os.getenv("MEMORYPAL_STT_URL", "http://127.0.0.1:8001").rstrip("/"),
        llm_url=os.getenv("MEMORYPAL_LLM_URL", "http://127.0.0.1:8002").rstrip("/"),
        llm_resource_url=_optional_http_url("MEMORYPAL_LLM_RESOURCE_URL").rstrip("/"),
        llm_api_key=os.getenv("MEMORYPAL_LLM_API_KEY", "lm-studio"),
        llm_default_model=os.getenv("MEMORYPAL_DEFAULT_LLM_MODEL", "qwen3.5-4b"),
        llm_companion_model=os.getenv("MEMORYPAL_COMPANION_LLM_MODEL", "memorypal_ai"),
        llm_embedding_model=os.getenv(
            "MEMORYPAL_EMBEDDING_MODEL", "text-embedding-nomic-embed-text-v1.5",
        ),
        llm_character_cue_enabled=os.getenv(
            "MEMORYPAL_LLM_CHARACTER_CUE_ENABLED", "true",
        ).strip().casefold() not in {"0", "false", "no", "off"},
        lmstudio_model_root=(
            _path("MEMORYPAL_LMSTUDIO_MODEL_ROOT", os.getenv("MEMORYPAL_LMSTUDIO_MODEL_ROOT", ""))
            if os.getenv("MEMORYPAL_LMSTUDIO_MODEL_ROOT", "").strip()
            else None
        ),
        lmstudio_cli=os.getenv("MEMORYPAL_LMSTUDIO_CLI", "lms").strip() or "lms",
        huggingface_token=os.getenv("MEMORYPAL_HUGGINGFACE_TOKEN", "").strip(),
        tts_url=os.getenv("MEMORYPAL_TTS_URL", "http://127.0.0.1:8003").rstrip("/"),
        tts_public_url=os.getenv("MEMORYPAL_TTS_PUBLIC_URL", "").rstrip("/"),
        archive_url=os.getenv("MEMORYPAL_ARCHIVE_URL", "http://127.0.0.1:8004").rstrip("/"),
        archive_service_token=_optional_secret("MEMORYPAL_ARCHIVE_SERVICE_TOKEN"),
        archive_registration_cleanup_delay_seconds=max(
            60,
            int(os.getenv("MEMORYPAL_ARCHIVE_REGISTRATION_CLEANUP_DELAY", "1200")),
        ),
        default_voice_id=os.getenv(
            "MEMORYPAL_DEFAULT_VOICE_ID",
            "00000000-0000-0000-0000-000000000001",
        ),
        default_voice_audio_url=_optional_http_url("MEMORYPAL_DEFAULT_VOICE_AUDIO_URL"),
        default_voice_reference_text=os.getenv(
            "MEMORYPAL_DEFAULT_VOICE_REFERENCE_TEXT", "",
        ).strip(),
        request_timeout_seconds=float(os.getenv("MEMORYPAL_REQUEST_TIMEOUT", "300")),
        web_search_max_results=max(1, min(6, int(os.getenv("MEMORYPAL_WEB_SEARCH_MAX_RESULTS", "4")))),
        hardware_monitor_interval_seconds=max(5, int(os.getenv("MEMORYPAL_HARDWARE_MONITOR_INTERVAL", "15"))),
        hardware_monitor_log_path=_path("MEMORYPAL_HARDWARE_MONITOR_LOG_PATH", "./data/hardware_metrics.jsonl"),
        monitor_stt_url=os.getenv("MEMORYPAL_MONITOR_STT_URL", "http://127.0.0.1:8100").rstrip("/"),
        monitor_llm_url=os.getenv("MEMORYPAL_MONITOR_LLM_URL", "http://192.168.2.41:8101").rstrip("/"),
        monitor_tts_url=os.getenv("MEMORYPAL_MONITOR_TTS_URL", "http://127.0.0.1:8102").rstrip("/"),
        monitor_gateway_url=os.getenv("MEMORYPAL_MONITOR_GATEWAY_URL", "http://127.0.0.1:8103").rstrip("/"),
        monitor_archive_url=os.getenv("MEMORYPAL_MONITOR_ARCHIVE_URL", "http://127.0.0.1:8104").rstrip("/"),
    )
