from __future__ import annotations

import pytest

from memorypal_api.config import SettingsError, load_settings


@pytest.mark.parametrize(
    ("name", "attribute"),
    (
        ("MEMORYPAL_JWT_SECRET", "jwt_secret"),
        ("MEMORYPAL_MODEL_SERVICE_TOKEN", "model_service_token"),
    ),
)
def test_required_secret_accepts_direct_or_file_value(monkeypatch, tmp_path, name, attribute):
    direct = f"{name.casefold()}-direct-" + "d" * 48
    monkeypatch.setenv(name, direct)
    monkeypatch.delenv(f"{name}_FILE", raising=False)
    assert getattr(load_settings(), attribute) == direct

    secret_file = tmp_path / f"{name.casefold()}.secret"
    from_file = f"{name.casefold()}-file-" + "f" * 48
    secret_file.write_text(from_file + "\n", encoding="utf-8")
    monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(f"{name}_FILE", str(secret_file))
    assert getattr(load_settings(), attribute) == from_file


@pytest.mark.parametrize(
    "value",
    ("", "too-short", "replace-with-a-random-secret-value-of-32-characters"),
)
@pytest.mark.parametrize(
    "name",
    ("MEMORYPAL_JWT_SECRET", "MEMORYPAL_MODEL_SERVICE_TOKEN"),
)
def test_required_secret_rejects_missing_short_and_placeholder_values(
    monkeypatch, name, value,
):
    monkeypatch.setenv(name, value)
    monkeypatch.delenv(f"{name}_FILE", raising=False)
    with pytest.raises(SettingsError, match=name):
        load_settings()


@pytest.mark.parametrize(
    "name",
    ("MEMORYPAL_JWT_SECRET", "MEMORYPAL_MODEL_SERVICE_TOKEN"),
)
def test_required_secret_rejects_ambiguous_or_unreadable_file(monkeypatch, tmp_path, name):
    monkeypatch.setenv(name, "direct-secret-" + "d" * 48)
    monkeypatch.setenv(f"{name}_FILE", str(tmp_path / "secret"))
    with pytest.raises(SettingsError, match="Set only one"):
        load_settings()

    monkeypatch.delenv(name)
    with pytest.raises(SettingsError, match=f"Unable to read {name}_FILE"):
        load_settings()


def test_optional_archive_secret_accepts_blank_direct_or_file(monkeypatch, tmp_path):
    name = "MEMORYPAL_ARCHIVE_SERVICE_TOKEN"
    monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(f"{name}_FILE", raising=False)
    assert load_settings().archive_service_token == ""

    direct = "archive-direct-service-token-" + "d" * 48
    monkeypatch.setenv(name, direct)
    assert load_settings().archive_service_token == direct

    secret_file = tmp_path / "archive-service-token"
    from_file = "archive-file-service-token-" + "f" * 48
    secret_file.write_text(from_file + "\n", encoding="utf-8")
    monkeypatch.delenv(name)
    monkeypatch.setenv(f"{name}_FILE", str(secret_file))
    assert load_settings().archive_service_token == from_file


@pytest.mark.parametrize(
    "value",
    (
        "too-short",
        "replace-with-a-random-archive-service-token",
    ),
)
def test_optional_archive_secret_rejects_unsafe_configured_values(monkeypatch, value):
    name = "MEMORYPAL_ARCHIVE_SERVICE_TOKEN"
    monkeypatch.setenv(name, value)
    monkeypatch.delenv(f"{name}_FILE", raising=False)
    with pytest.raises(SettingsError, match=name):
        load_settings()


def test_optional_archive_secret_rejects_ambiguous_or_unreadable_file(
    monkeypatch,
    tmp_path,
):
    name = "MEMORYPAL_ARCHIVE_SERVICE_TOKEN"
    monkeypatch.setenv(name, "archive-direct-service-token-" + "d" * 48)
    monkeypatch.setenv(f"{name}_FILE", str(tmp_path / "missing-secret"))
    with pytest.raises(SettingsError, match="Set only one"):
        load_settings()

    monkeypatch.delenv(name)
    with pytest.raises(SettingsError, match=f"Unable to read {name}_FILE"):
        load_settings()


@pytest.mark.parametrize(
    "origins",
    (
        "*",
        "https://example.com/*",
        "https://user:secret@example.com",
        "https://example.com/api",
        "null",
        "",
    ),
)
def test_cors_requires_exact_http_origins(monkeypatch, origins):
    monkeypatch.setenv("MEMORYPAL_CORS_ORIGINS", origins)
    with pytest.raises(SettingsError, match="exact"):
        load_settings()


def test_cors_normalizes_trailing_slash_and_deduplicates(monkeypatch):
    monkeypatch.setenv(
        "MEMORYPAL_CORS_ORIGINS",
        "https://example.com/,https://example.com,http://127.0.0.1:8081",
    )
    assert load_settings().cors_origins == (
        "https://example.com",
        "http://127.0.0.1:8081",
    )


def test_default_voice_fallback_is_loaded_from_environment():
    settings = load_settings()
    assert settings.default_voice_id == "00000000-0000-0000-0000-000000000001"
    assert settings.default_voice_audio_url.endswith(".wav")
    assert settings.default_voice_reference_text
