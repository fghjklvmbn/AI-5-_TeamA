from __future__ import annotations

import asyncio
import hashlib
import hmac
from dataclasses import replace
from io import BytesIO

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from starlette.datastructures import Headers
from starlette.requests import Request

from memorypal_api.app import create_app
from memorypal_api.config import load_settings
from memorypal_api.dependencies import CurrentUser
from memorypal_api.routes import create_voice
from memorypal_api.services.pipeline import PipelineUnavailable


SERVICE_TOKEN = "archive-test-service-token-" + "a" * 48


def _app(tmp_path):
    return create_app(replace(
        load_settings(),
        database_path=tmp_path / "voice-registration.db",
        database_url="",
        root_path="",
        archive_service_token=SERVICE_TOKEN,
    ))


def _register_user(client: TestClient) -> tuple[str, str]:
    response = client.post("/v1/auth/register", json={
        "email": "voice-owner@example.com",
        "password": "password123",
        "display_name": "음성 사용자",
    })
    assert response.status_code == 201
    payload = response.json()
    return payload["user"]["id"], payload["access_token"]


def _post_voice(client: TestClient, token: str):
    return client.post(
        "/v1/voices",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "voice_name": "내 목소리",
            "reference_text": "안녕하세요. 음성 등록 테스트입니다.",
            "description": "테스트",
        },
        files={"audio": ("sample.wav", b"RIFF-test-audio", "audio/wav")},
    )


def test_voice_registration_confirms_after_fenced_mapping(tmp_path):
    app = _app(tmp_path)
    calls: dict[str, object] = {}

    async def register_voice(*_args, owner_ref: str, registration_token: str, **_kwargs):
        calls["owner_ref"] = owner_ref
        calls["registration_token"] = registration_token
        return {
            "id": "personal-voice-1",
            "voice_name": "내 목소리",
            "audio_path": "private/sample.wav",
            "reference_text": "안녕하세요. 음성 등록 테스트입니다.",
            "description": "테스트",
        }

    async def confirm(voice_id: str, **kwargs):
        calls["confirmed"] = (voice_id, kwargs)

    async def delete(*_args, **_kwargs):
        calls["deleted"] = True

    app.state.pipeline.register_voice = register_voice
    app.state.pipeline.confirm_voice_registration = confirm
    app.state.pipeline.delete_voice_registration = delete

    with TestClient(app) as client:
        user_id, token = _register_user(client)
        response = _post_voice(client, token)

    assert response.status_code == 201
    assert app.state.db.user_has_voice(user_id, "personal-voice-1")
    expected_owner = hmac.new(
        SERVICE_TOKEN.encode(), user_id.encode(), hashlib.sha256,
    ).hexdigest()
    assert calls["owner_ref"] == expected_owner
    assert len(str(calls["registration_token"])) >= 64
    assert calls["confirmed"][0] == "personal-voice-1"
    assert "deleted" not in calls


def test_confirm_failure_removes_mapping_and_compensates_archive(tmp_path):
    app = _app(tmp_path)
    deleted: list[str] = []

    async def register_voice(*_args, **_kwargs):
        return {
            "id": "personal-voice-failed",
            "voice_name": "내 목소리",
            "audio_path": "private/sample.wav",
            "reference_text": "안녕하세요. 음성 등록 테스트입니다.",
            "description": None,
        }

    async def confirm(*_args, **_kwargs):
        raise PipelineUnavailable("confirm unavailable")

    async def delete(voice_id: str, **_kwargs):
        deleted.append(voice_id)

    app.state.pipeline.register_voice = register_voice
    app.state.pipeline.confirm_voice_registration = confirm
    app.state.pipeline.delete_voice_registration = delete

    with TestClient(app) as client:
        user_id, token = _register_user(client)
        response = _post_voice(client, token)

    assert response.status_code == 503
    assert not app.state.db.user_has_voice(user_id, "personal-voice-failed")
    assert deleted == ["personal-voice-failed"]


def test_confirmed_compensation_outage_leaves_durable_voice_cleanup(tmp_path):
    app = _app(tmp_path)

    async def register_voice(*_args, **_kwargs):
        return {
            "id": "personal-voice-durable-cleanup",
            "voice_name": "durable cleanup",
            "audio_path": "private/sample.wav",
            "reference_text": "durable cleanup boundary",
            "description": None,
        }

    async def confirm(*_args, **_kwargs):
        raise PipelineUnavailable("confirmation failed")

    async def delete(*_args, **_kwargs):
        raise PipelineUnavailable("compensation unavailable")

    async def purge(*_args, **_kwargs):
        raise PipelineUnavailable("archive unavailable")

    app.state.pipeline.register_voice = register_voice
    app.state.pipeline.confirm_voice_registration = confirm
    app.state.pipeline.delete_voice_registration = delete
    app.state.pipeline.purge_owner_voices = purge

    with TestClient(app) as client:
        user_id, token = _register_user(client)
        response = _post_voice(client, token)
        owner_ref = app.state.pipeline.archive_owner_ref(user_id)
        job = app.state.db.get_archive_voice_cleanup_job(
            owner_ref, "personal-voice-durable-cleanup",
        )

    assert response.status_code == 503
    assert job is not None
    assert not app.state.db.user_has_voice(user_id, "personal-voice-durable-cleanup")


def test_authority_change_after_confirm_compensates_both_stores(tmp_path):
    app = _app(tmp_path)
    deleted: list[str] = []

    async def register_voice(*_args, **_kwargs):
        return {
            "id": "personal-voice-raced",
            "voice_name": "내 목소리",
            "audio_path": "private/sample.wav",
            "reference_text": "안녕하세요. 음성 등록 테스트입니다.",
            "description": None,
        }

    async def confirm(_voice_id: str, **_kwargs):
        app.state.db.execute(
            "UPDATE users SET account_status = 'suspended', "
            "auth_version = auth_version + 1 WHERE email = ?",
            ("voice-owner@example.com",),
        )

    async def delete(voice_id: str, **_kwargs):
        deleted.append(voice_id)

    app.state.pipeline.register_voice = register_voice
    app.state.pipeline.confirm_voice_registration = confirm
    app.state.pipeline.delete_voice_registration = delete

    with TestClient(app) as client:
        user_id, token = _register_user(client)
        response = _post_voice(client, token)

    assert response.status_code == 403
    assert not app.state.db.user_has_voice(user_id, "personal-voice-raced")
    assert deleted == ["personal-voice-raced"]


def test_confirmed_voice_cleanup_is_durable_when_compensation_endpoint_is_down(tmp_path):
    app = _app(tmp_path)

    async def register_voice(*_args, **_kwargs):
        return {
            "id": "personal-voice-confirmed-outage",
            "voice_name": "confirmed outage",
            "audio_path": "private/sample.wav",
            "reference_text": "confirmed cleanup boundary",
            "description": None,
        }

    async def confirm(*_args, **_kwargs):
        app.state.db.execute(
            "UPDATE users SET account_status = 'suspended', "
            "auth_version = auth_version + 1 WHERE email = ?",
            ("voice-owner@example.com",),
        )

    async def delete(*_args, **_kwargs):
        raise PipelineUnavailable("compensation endpoint down")

    async def purge(*_args, **_kwargs):
        raise PipelineUnavailable("archive down")

    app.state.pipeline.register_voice = register_voice
    app.state.pipeline.confirm_voice_registration = confirm
    app.state.pipeline.delete_voice_registration = delete
    app.state.pipeline.purge_owner_voices = purge

    with TestClient(app) as client:
        user_id, token = _register_user(client)
        response = _post_voice(client, token)
        owner_ref = app.state.pipeline.archive_owner_ref(user_id)
        job = app.state.db.get_archive_voice_cleanup_job(
            owner_ref, "personal-voice-confirmed-outage",
        )

    assert response.status_code == 403
    assert job is not None
    assert not app.state.db.user_has_voice(user_id, "personal-voice-confirmed-outage")


def test_request_cancellation_compensates_after_account_becomes_inactive(tmp_path):
    app = _app(tmp_path)

    with TestClient(app) as client:
        user_id, _token = _register_user(client)
        user_row = app.state.db.get_user_by_id(user_id)
        assert user_row is not None
        current_user = CurrentUser(
            id=user_id,
            email=str(user_row["email"]),
            display_name=str(user_row["display_name"]),
            token_jti="voice-registration-cancellation",
            token_expires_at=2_000_000_000,
            auth_version=int(user_row["auth_version"]),
        )

        async def exercise_cancellation() -> list[str]:
            confirm_started = asyncio.Event()
            wait_forever = asyncio.Event()
            deleted: list[str] = []

            async def register_voice(*_args, **_kwargs):
                return {
                    "id": "personal-voice-cancelled",
                    "voice_name": "cancelled voice",
                    "audio_path": "private/sample.wav",
                    "reference_text": "cancellation boundary test",
                    "description": None,
                }

            async def confirm(*_args, **_kwargs):
                app.state.db.execute(
                    "UPDATE users SET account_status = 'suspended', "
                    "auth_version = auth_version + 1 WHERE id = ?",
                    (user_id,),
                )
                confirm_started.set()
                await wait_forever.wait()

            async def delete(voice_id: str, **_kwargs):
                # Force one suspension point so the test proves the shielded
                # compensation is awaited after the parent task is cancelled.
                await asyncio.sleep(0)
                deleted.append(voice_id)

            app.state.pipeline.register_voice = register_voice
            app.state.pipeline.confirm_voice_registration = confirm
            app.state.pipeline.delete_voice_registration = delete

            request = Request({"type": "http", "app": app})
            audio = UploadFile(
                BytesIO(b"RIFF-test-audio"),
                filename="sample.wav",
                headers=Headers({"content-type": "audio/wav"}),
            )
            task = asyncio.create_task(create_voice(
                request=request,
                audio=audio,
                voice_name="cancelled voice",
                reference_text="cancellation boundary test",
                description="",
                user=current_user,
            ))
            await asyncio.wait_for(confirm_started.wait(), timeout=1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            return deleted

        deleted = asyncio.run(exercise_cancellation())

    assert not app.state.db.user_has_voice(user_id, "personal-voice-cancelled")
    assert deleted == ["personal-voice-cancelled"]
    assert app.state.db.get_user_by_id(user_id)["account_status"] == "suspended"
