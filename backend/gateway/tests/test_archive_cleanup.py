from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from memorypal_api.app import create_app
from memorypal_api.config import load_settings
from memorypal_api.security import hash_password
from memorypal_api.services.archive_cleanup import run_archive_cleanup_once
from memorypal_api.services.archive_cleanup import reconcile_legacy_voice_once
from memorypal_api.services.pipeline import PipelineUnavailable


SERVICE_TOKEN = "cleanup-test-service-token-" + "s" * 48


def _settings(
    tmp_path,
    *,
    service_token: str = SERVICE_TOKEN,
    admin_emails: tuple[str, ...] = (),
):
    return replace(
        load_settings(),
        database_path=tmp_path / "archive-cleanup.db",
        database_url="",
        root_path="",
        archive_service_token=service_token,
        admin_emails=admin_emails,
    )


def _register(client: TestClient, email: str = "cleanup@example.com") -> dict:
    response = client.post("/v1/auth/register", json={
        "email": email,
        "password": "password123",
        "display_name": "cleanup user",
    })
    assert response.status_code == 201
    return response.json()


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def test_archive_outage_does_not_rollback_hard_delete_and_jobs_eventually_drain(
    tmp_path,
):
    app = create_app(_settings(tmp_path))
    attempted: list[tuple[str, str | None]] = []

    async def unavailable(owner_ref: str, *, voice_id: str | None = None):
        attempted.append((owner_ref, voice_id))
        raise PipelineUnavailable("archive unavailable")

    app.state.pipeline.purge_owner_voices = unavailable

    async def adoption_unavailable(*_args, **_kwargs):
        raise PipelineUnavailable("adoption unavailable")

    app.state.pipeline.adopt_legacy_voice = adoption_unavailable
    with TestClient(app) as client:
        auth = _register(client)
        user_id = auth["user"]["id"]
        current_owner = app.state.pipeline.archive_owner_ref(user_id)
        old_owner = "a" * 64
        app.state.db.add_user_voice(
            user_id, "old-token-voice", owner_ref=old_owner,
        )
        app.state.db.add_user_voice(user_id, "unadopted-legacy-voice")

        deleted = client.request(
            "DELETE",
            "/v1/auth/account",
            json={"current_password": "password123", "confirmation": "DELETE"},
            headers=_headers(auth),
        )
        assert deleted.status_code == 204
        assert app.state.db.get_user_by_id(user_id) is None
        assert app.state.db.get_archive_voice_cleanup_job(current_owner) is not None
        assert app.state.db.get_archive_voice_cleanup_job(old_owner) is not None
        assert app.state.db.get_archive_voice_cleanup_job(
            current_owner, "unadopted-legacy-voice",
        ) is not None

        async def available(owner_ref: str, *, voice_id: str | None = None):
            attempted.append((owner_ref, voice_id))

        app.state.pipeline.purge_owner_voices = available
        app.state.db.execute(
            "UPDATE archive_voice_cleanup_jobs SET status = 'pending', "
            "available_at = ?, lease_owner = NULL, lease_token = NULL, "
            "lease_expires_at = NULL",
            ("2000-01-01T00:00:00+00:00",),
        )
        for _ in range(4):
            asyncio.run(run_archive_cleanup_once(app, worker_id="eventual-test"))
        assert app.state.db.fetch_all("SELECT * FROM archive_voice_cleanup_jobs") == []
        assert {owner for owner, voice_id in attempted if voice_id is None} >= {
            current_owner, old_owner,
        }
        assert (current_owner, "unadopted-legacy-voice") in attempted


def test_missing_archive_credential_fails_before_local_hard_delete(tmp_path):
    app = create_app(_settings(tmp_path, service_token=""))
    with TestClient(app) as client:
        auth = _register(client, "missing-token@example.com")
        response = client.request(
            "DELETE",
            "/v1/auth/account",
            json={"current_password": "password123", "confirmation": "DELETE"},
            headers=_headers(auth),
        )
        assert response.status_code == 503
        assert app.state.db.get_user_by_id(auth["user"]["id"]) is not None
        assert app.state.db.fetch_all("SELECT * FROM archive_voice_cleanup_jobs") == []


def test_cancelled_cleanup_keeps_lease_recoverable(tmp_path):
    app = create_app(_settings(tmp_path))
    app.state.db.initialize()
    owner_ref = "b" * 64
    app.state.db.enqueue_archive_voice_cleanup(owner_ref=owner_ref)

    async def exercise() -> None:
        started = asyncio.Event()
        never = asyncio.Event()

        async def blocked(_owner_ref: str, *, voice_id: str | None = None):
            started.set()
            await never.wait()

        app.state.pipeline.purge_owner_voices = blocked
        task = asyncio.create_task(run_archive_cleanup_once(
            app, worker_id="cancelled-worker",
        ))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        job = app.state.db.get_archive_voice_cleanup_job(owner_ref)
        assert job is not None and job["status"] == "running"

        async def available(_owner_ref: str, *, voice_id: str | None = None):
            return None

        app.state.pipeline.purge_owner_voices = available
        app.state.db.execute(
            "UPDATE archive_voice_cleanup_jobs SET lease_expires_at = ? WHERE job_key = ?",
            ("2000-01-01T00:00:00+00:00", f"{owner_ref}:*"),
        )
        assert await run_archive_cleanup_once(app, worker_id="recovery-worker")

    asyncio.run(exercise())
    assert app.state.db.get_archive_voice_cleanup_job(owner_ref) is None


def test_expired_provisional_mapping_is_removed_after_owner_bound_cleanup(tmp_path):
    app = create_app(_settings(tmp_path))
    app.state.db.initialize()
    password_hash, password_salt = hash_password("password123")
    user = app.state.db.create_user(
        "provisional@example.com", "provisional", password_hash, password_salt,
    )
    owner_ref = app.state.pipeline.archive_owner_ref(str(user["id"]))
    app.state.db.add_user_voice(
        str(user["id"]),
        "provisional-voice",
        expected_auth_version=int(user["auth_version"]),
        owner_ref=owner_ref,
        provisional_cleanup_delay_seconds=0,
    )

    async def available(_owner_ref: str, *, voice_id: str | None = None):
        assert voice_id == "provisional-voice"

    app.state.pipeline.purge_owner_voices = available
    assert asyncio.run(run_archive_cleanup_once(app, worker_id="stale-mapping-test"))
    assert app.state.db.fetch_one(
        "SELECT 1 FROM user_voice_profiles WHERE user_id = ?",
        (user["id"],),
    ) is None
    assert app.state.db.get_archive_voice_cleanup_job(
        owner_ref, "provisional-voice",
    ) is None


def test_legacy_adoption_retries_after_remote_success_before_local_update(tmp_path):
    app = create_app(_settings(tmp_path))
    app.state.db.initialize()
    password_hash, password_salt = hash_password("password123")
    user = app.state.db.create_user(
        "legacy-retry@example.com", "legacy retry", password_hash, password_salt,
    )
    user_id = str(user["id"])
    voice_id = "legacy-retry-voice"
    app.state.db.add_user_voice(user_id, voice_id)
    adopted: list[tuple[str, str]] = []

    async def adopt(remote_voice_id: str, owner_ref: str):
        adopted.append((remote_voice_id, owner_ref))

    app.state.pipeline.adopt_legacy_voice = adopt
    original_mark = app.state.db.mark_legacy_voice_adopted

    def crash_after_remote(*_args, **_kwargs):
        raise RuntimeError("gateway crashed before local CAS")

    app.state.db.mark_legacy_voice_adopted = crash_after_remote
    with pytest.raises(RuntimeError):
        asyncio.run(reconcile_legacy_voice_once(app))
    assert app.state.db.get_next_legacy_voice_mapping(
        app.state.settings.default_voice_id,
    ) is not None

    app.state.db.mark_legacy_voice_adopted = original_mark
    assert asyncio.run(reconcile_legacy_voice_once(app))
    row = app.state.db.fetch_one(
        "SELECT owner_ref FROM user_voice_profiles WHERE user_id = ? AND voice_id = ?",
        (user_id, voice_id),
    )
    assert row["owner_ref"] == app.state.pipeline.archive_owner_ref(user_id)
    assert len(adopted) == 2


def test_admin_suspension_and_soft_deactivation_retain_voice_without_purge_job(tmp_path):
    app = create_app(_settings(
        tmp_path, admin_emails=("cleanup-admin@example.com",),
    ))
    with TestClient(app) as client:
        admin = _register(client, "cleanup-admin@example.com")
        target = _register(client, "soft-state-target@example.com")
        target_id = target["user"]["id"]
        target_row = app.state.db.get_user_by_id(target_id)
        target_ref = str(target_row["admin_ref"])
        owner_ref = app.state.pipeline.archive_owner_ref(target_id)
        app.state.db.add_user_voice(
            target_id, "retained-voice", owner_ref=owner_ref,
        )

        suspended = client.post(
            f"/v1/admin/users/{target_ref}/suspend",
            json={"expected_version": 1},
            headers=_headers(admin),
        )
        assert suspended.status_code == 200
        assert app.state.db.user_has_voice(target_id, "retained-voice")
        assert app.state.db.fetch_all("SELECT * FROM archive_voice_cleanup_jobs") == []

        resumed = client.post(
            f"/v1/admin/users/{target_ref}/unsuspend",
            json={"expected_version": 2},
            headers=_headers(admin),
        )
        assert resumed.status_code == 200
        deactivated = client.request(
            "DELETE",
            f"/v1/admin/users/{target_ref}",
            json={"confirmation": "DEACTIVATE", "expected_version": 3},
            headers=_headers(admin),
        )
        assert deactivated.status_code == 200
        assert app.state.db.get_user_by_id(target_id)["account_status"] == "deactivated"
        assert app.state.db.user_has_voice(target_id, "retained-voice")
        assert app.state.db.fetch_all("SELECT * FROM archive_voice_cleanup_jobs") == []
