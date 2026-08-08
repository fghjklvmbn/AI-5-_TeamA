from __future__ import annotations

import hashlib
import os
import uuid
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app as archive_app
from database.models import Base, VoiceOwnerState, VoiceProfile
from repositories.voice_repository import VoiceRepository
from services.voice_service import VoiceService


SERVICE_TOKEN = "archive-unit-test-service-token-" + "s" * 48
OWNER_REF = "a" * 64
REGISTRATION_TOKEN = "registration-unit-test-" + "r" * 48


@pytest.fixture
def archive_client(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    private_dir = tmp_path / "private"
    private_dir.mkdir()
    legacy_dir = tmp_path / "voice_uploads"
    legacy_dir.mkdir()

    monkeypatch.setenv("MEMORYPAL_ARCHIVE_SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.delenv("MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE", raising=False)
    monkeypatch.setattr(archive_app, "SessionLocal", session_factory)
    monkeypatch.setattr(archive_app, "PRIVATE_UPLOAD_DIR", private_dir)
    monkeypatch.setattr(archive_app, "LEGACY_UPLOAD_DIR", legacy_dir)
    monkeypatch.setattr(archive_app, "PENDING_TTL_SECONDS", 60)
    monkeypatch.setattr(archive_app, "REAPER_INTERVAL_SECONDS", 3600)
    monkeypatch.setattr(archive_app, "ensure_voice_registration_schema", lambda: None)

    with TestClient(archive_app.app) as client:
        yield client, session_factory, private_dir
    engine.dispose()


def _headers(
    *,
    service_token: str = SERVICE_TOKEN,
    owner_ref: str = OWNER_REF,
    registration_token: str = REGISTRATION_TOKEN,
):
    return {
        "Authorization": f"Bearer {service_token}",
        "X-MemoryPal-Owner-Ref": owner_ref,
        "X-MemoryPal-Registration-Token": registration_token,
    }


def _register(client: TestClient, *, headers=None):
    return client.post(
        "/internal/voices",
        headers=headers or _headers(),
        data={
            "voice_name": "비공개 음성",
            "reference_text": "안녕하세요. 비공개 음성입니다.",
            "description": "내부 등록",
        },
        files={"file": ("sample.wav", b"RIFF-private-audio", "audio/wav")},
    )


def _owner_headers(owner_ref: str = OWNER_REF):
    return {
        "Authorization": f"Bearer {SERVICE_TOKEN}",
        "X-MemoryPal-Owner-Ref": owner_ref,
    }


def test_internal_ready_requires_the_current_archive_token(archive_client):
    client, _session_factory, _private_dir = archive_client
    assert client.get("/health").status_code == 200
    assert client.get("/internal/ready").status_code == 401
    assert client.get(
        "/internal/ready",
        headers={"Authorization": "Bearer stale-archive-token"},
    ).status_code == 401
    accepted = client.get(
        "/internal/ready",
        headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
    )
    assert accepted.status_code == 200
    assert accepted.json() == {"status": "ok", "database": "ok"}


def test_archive_token_file_is_supported_and_invalid_sources_fail_closed(
    archive_client,
    monkeypatch,
    tmp_path,
):
    client, _session_factory, _private_dir = archive_client
    token_file = tmp_path / "archive-service-token"
    token_file.write_text(SERVICE_TOKEN + "\n", encoding="utf-8")
    monkeypatch.delenv("MEMORYPAL_ARCHIVE_SERVICE_TOKEN")
    monkeypatch.setenv("MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE", str(token_file))

    assert client.get(
        "/internal/ready",
        headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
    ).status_code == 200

    monkeypatch.setenv("MEMORYPAL_ARCHIVE_SERVICE_TOKEN", SERVICE_TOKEN)
    assert client.get("/internal/ready", headers=_headers()).status_code == 503

    monkeypatch.delenv("MEMORYPAL_ARCHIVE_SERVICE_TOKEN")
    token_file.write_text("too-short\n", encoding="utf-8")
    assert client.get("/internal/ready", headers=_headers()).status_code == 503

    token_file.write_text("replace-with-a-random-archive-service-token\n", encoding="utf-8")
    assert client.get("/internal/ready", headers=_headers()).status_code == 503


def test_internal_voice_is_private_until_confirm_and_delete_is_owner_bound_idempotent(
    archive_client,
    monkeypatch,
):
    client, session_factory, private_dir = archive_client
    monkeypatch.delenv("MEMORYPAL_ARCHIVE_SERVICE_TOKEN")
    assert client.get("/internal/voices", headers=_headers()).status_code == 503
    monkeypatch.setenv("MEMORYPAL_ARCHIVE_SERVICE_TOKEN", SERVICE_TOKEN)
    assert _register(client, headers=_headers(service_token="wrong" * 10)).status_code == 401

    registered = _register(client)
    assert registered.status_code == 201
    payload = registered.json()
    voice_id = payload["id"]
    stored_path = payload["audio_path"]
    assert str(private_dir.resolve()) in stored_path
    assert "voice_uploads" not in stored_path
    assert list(private_dir.iterdir())

    with session_factory() as db:
        row = db.query(VoiceProfile).filter(VoiceProfile.id == voice_id).one()
        assert row.registration_state == "pending"
        assert row.owner_ref == OWNER_REF
        assert row.registration_token_hash == hashlib.sha256(
            REGISTRATION_TOKEN.encode(),
        ).hexdigest()
        assert REGISTRATION_TOKEN not in row.registration_token_hash

    assert client.get("/voice/list").json() == []
    assert client.get(f"/voice/{voice_id}").json() == {"error": "voice not found"}
    assert client.get("/internal/voices", headers=_headers()).json() == []

    confirmed = client.post(f"/internal/voices/{voice_id}/confirm", headers=_headers())
    assert confirmed.status_code == 200
    assert confirmed.json()["registration_state"] == "active"
    audio = client.get(f"/internal/voices/{voice_id}/audio", headers=_headers())
    assert audio.status_code == 200
    assert audio.content == b"RIFF-private-audio"
    assert client.get(f"/internal/voices/{voice_id}/audio").status_code == 401
    assert [item["id"] for item in client.get(
        "/internal/voices", headers=_headers(),
    ).json()] == [voice_id]
    assert client.get("/voice/list").json() == []

    wrong_owner = client.delete(
        f"/internal/voices/{voice_id}",
        headers=_headers(owner_ref="b" * 64),
    )
    assert wrong_owner.status_code == 204
    assert Path(stored_path).exists()

    deleted = client.delete(f"/internal/voices/{voice_id}", headers=_headers())
    assert deleted.status_code == 204
    assert not Path(stored_path).exists()
    assert client.delete(f"/internal/voices/{voice_id}", headers=_headers()).status_code == 204
    with session_factory() as db:
        assert db.query(VoiceProfile).filter(VoiceProfile.id == voice_id).first() is None


def test_expired_pending_voice_and_unreferenced_private_file_are_reaped(archive_client):
    client, session_factory, private_dir = archive_client
    registered = _register(client)
    assert registered.status_code == 201
    voice_id = registered.json()["id"]
    stored_path = Path(registered.json()["audio_path"])

    with session_factory() as db:
        row = db.query(VoiceProfile).filter(VoiceProfile.id == voice_id).one()
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    assert archive_app.run_archive_cleanup_once() == 1
    assert not stored_path.exists()
    with session_factory() as db:
        assert db.query(VoiceProfile).filter(VoiceProfile.id == voice_id).first() is None

    orphan = private_dir / f"{uuid.uuid4()}.wav"
    orphan.write_bytes(b"orphan")
    old = datetime.now(UTC).timestamp() - 120
    os.utime(orphan, (old, old))
    assert archive_app.run_archive_cleanup_once() == 1
    assert not orphan.exists()


def test_legacy_active_voice_remains_available_to_public_and_internal_reads(archive_client):
    client, session_factory, _private_dir = archive_client
    with session_factory() as db:
        db.add(VoiceProfile(
            id="00000000-0000-0000-0000-000000000001",
            voice_name="기본 음성",
            audio_path="legacy/default.wav",
            reference_text="안녕하세요",
            description=None,
            registration_state="active",
            created_at=datetime.now(UTC),
        ))
        db.commit()

    public = client.get("/voice/list")
    internal = client.get("/internal/voices", headers=_headers())
    assert public.status_code == 200
    assert internal.status_code == 200
    assert [item["id"] for item in public.json()] == [
        "00000000-0000-0000-0000-000000000001",
    ]
    assert [item["id"] for item in internal.json()] == [
        "00000000-0000-0000-0000-000000000001",
    ]


def test_create_pending_removes_private_file_when_database_create_fails(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "new-private.wav"
    path.write_bytes(b"private")

    class FakeDb:
        def rollback(self):
            return None

    monkeypatch.setattr(
        VoiceRepository,
        "get_by_registration_token",
        staticmethod(lambda _db, _token_hash: None),
    )
    monkeypatch.setattr(
        VoiceRepository,
        "lock_owner",
        staticmethod(lambda _db, _owner_ref, _now: SimpleNamespace(state="active")),
    )

    def fail_create(_db, _voice):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(VoiceRepository, "create", staticmethod(fail_create))
    with pytest.raises(RuntimeError):
        VoiceService.create_pending(
            FakeDb(),
            owner_ref=OWNER_REF,
            registration_token=REGISTRATION_TOKEN,
            voice_name="비공개 음성",
            audio_path=path,
            reference_text="안녕하세요",
            description=None,
            ttl_seconds=60,
        )
    assert not path.exists()


def test_create_pending_removes_private_file_when_initial_owner_guard_lookup_fails(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "lookup-failure.wav"
    path.write_bytes(b"private")

    class FakeDb:
        def rollback(self):
            return None

    def fail_lookup(_db, _owner_ref, _now):
        raise RuntimeError("lookup unavailable")

    monkeypatch.setattr(
        VoiceRepository,
        "lock_owner",
        staticmethod(fail_lookup),
    )
    with pytest.raises(RuntimeError):
        VoiceService.create_pending(
            FakeDb(),
            owner_ref=OWNER_REF,
            registration_token=REGISTRATION_TOKEN,
            voice_name="private voice",
            audio_path=path,
            reference_text="lookup cleanup",
            description=None,
            ttl_seconds=60,
        )
    assert not path.exists()


def test_owner_purge_is_isolated_per_owner_and_permanently_blocks_registration(
    archive_client,
):
    client, session_factory, _private_dir = archive_client
    other_owner = "b" * 64
    first = _register(client)
    second = _register(client, headers=_headers(
        owner_ref=other_owner,
        registration_token="other-registration-" + "o" * 48,
    ))
    assert first.status_code == second.status_code == 201
    first_id, second_id = first.json()["id"], second.json()["id"]
    assert client.post(
        f"/internal/voices/{first_id}/confirm", headers=_headers(),
    ).status_code == 200
    assert client.post(
        f"/internal/voices/{second_id}/confirm",
        headers=_headers(
            owner_ref=other_owner,
            registration_token="other-registration-" + "o" * 48,
        ),
    ).status_code == 200

    purged = client.delete("/internal/owner-voices", headers=_owner_headers())
    assert purged.status_code == 204
    assert client.delete(
        "/internal/owner-voices", headers=_owner_headers(),
    ).status_code == 204
    with session_factory() as db:
        assert db.query(VoiceProfile).filter(VoiceProfile.id == first_id).first() is None
        assert db.query(VoiceProfile).filter(VoiceProfile.id == second_id).one()
        state = db.query(VoiceOwnerState).filter(
            VoiceOwnerState.owner_ref == OWNER_REF,
        ).one()
        assert state.state == "purged"

    rejected = _register(
        client,
        headers=_headers(registration_token="post-purge-" + "p" * 48),
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "owner_has_been_purged"


def test_owner_bound_single_voice_purge_cannot_delete_another_owners_voice(
    archive_client,
):
    client, session_factory, _private_dir = archive_client
    registered = _register(client)
    assert registered.status_code == 201
    voice_id = registered.json()["id"]
    wrong_owner = client.delete(
        f"/internal/owner-voices/{voice_id}",
        headers=_owner_headers("c" * 64),
    )
    assert wrong_owner.status_code == 204
    with session_factory() as db:
        assert db.query(VoiceProfile).filter(VoiceProfile.id == voice_id).one()


def test_actual_legacy_voice_is_hidden_then_idempotently_adopted(archive_client):
    client, session_factory, private_dir = archive_client
    legacy_dir = archive_app.LEGACY_UPLOAD_DIR
    default_path = legacy_dir / "default.wav"
    personal_path = legacy_dir / "legacy-personal"
    default_path.write_bytes(b"default-audio")
    personal_payload = b"\x1a\x45\xdf\xa3" + b"webm-audio-payload"
    personal_path.write_bytes(personal_payload)
    legacy_voice_id = "11111111-1111-1111-1111-111111111111"
    with session_factory() as db:
        db.add_all([
            VoiceProfile(
                id=archive_app.DEFAULT_VOICE_ID,
                voice_name="default",
                audio_path=str(default_path.resolve()),
                reference_text="default reference",
                registration_state="active",
                created_at=datetime.now(UTC),
            ),
            VoiceProfile(
                id=legacy_voice_id,
                voice_name="legacy personalized",
                audio_path=str(personal_path.resolve()),
                reference_text="legacy reference",
                owner_ref=None,
                registration_state="active",
                created_at=datetime.now(UTC),
            ),
        ])
        db.commit()

    assert [item["id"] for item in client.get("/voice/list").json()] == [
        archive_app.DEFAULT_VOICE_ID,
    ]
    assert client.get(f"/voice/{legacy_voice_id}").json() == {
        "error": "voice not found",
    }
    assert client.get("/voice_uploads/legacy-personal").status_code == 404
    default_audio = client.get("/voice_uploads/default.wav")
    assert default_audio.status_code == 200
    assert default_audio.content == b"default-audio"

    adopted = client.post(
        f"/internal/legacy-voices/{legacy_voice_id}/adopt",
        headers=_owner_headers(),
    )
    assert adopted.status_code == 200
    adopted_path = Path(adopted.json()["audio_path"])
    assert adopted_path.is_relative_to(private_dir.resolve())
    assert adopted_path.suffix == ".webm"
    assert adopted_path.read_bytes() == personal_payload
    assert not personal_path.exists()
    repeated = client.post(
        f"/internal/legacy-voices/{legacy_voice_id}/adopt",
        headers=_owner_headers(),
    )
    assert repeated.status_code == 200
    assert repeated.json()["audio_path"] == str(adopted_path)
    with session_factory() as db:
        row = db.query(VoiceProfile).filter(VoiceProfile.id == legacy_voice_id).one()
        assert row.owner_ref == OWNER_REF
        assert row.legacy_source_path is None

    rejected_default = client.post(
        f"/internal/legacy-voices/{archive_app.DEFAULT_VOICE_ID}/adopt",
        headers=_owner_headers(),
    )
    assert rejected_default.status_code == 409
    assert default_path.exists()


def test_legacy_adoption_rejects_unknown_extensionless_format_without_mutation(
    archive_client,
):
    client, session_factory, private_dir = archive_client
    source = archive_app.LEGACY_UPLOAD_DIR / "unknown-legacy-audio"
    source.write_bytes(b"not-a-recognized-audio-container")
    voice_id = "33333333-3333-3333-3333-333333333333"
    with session_factory() as db:
        db.add(VoiceProfile(
            id=voice_id,
            voice_name="unknown legacy",
            audio_path=str(source.resolve()),
            reference_text="unknown",
            registration_state="active",
            created_at=datetime.now(UTC),
        ))
        db.commit()

    rejected = client.post(
        f"/internal/legacy-voices/{voice_id}/adopt",
        headers=_owner_headers(),
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "unsupported_legacy_voice_format"
    assert source.read_bytes() == b"not-a-recognized-audio-container"
    assert list(private_dir.iterdir()) == []
    with session_factory() as db:
        row = db.query(VoiceProfile).filter(VoiceProfile.id == voice_id).one()
        assert row.owner_ref is None
        assert Path(row.audio_path) == source.resolve()


def test_hard_delete_cleanup_can_remove_unadopted_legacy_voice_but_not_default(
    archive_client,
):
    client, session_factory, _private_dir = archive_client
    legacy_dir = archive_app.LEGACY_UPLOAD_DIR
    default_path = legacy_dir / "default-before-delete.wav"
    personal_path = legacy_dir / "legacy-before-delete.wav"
    default_path.write_bytes(b"default")
    personal_path.write_bytes(b"personal")
    legacy_voice_id = "22222222-2222-2222-2222-222222222222"
    with session_factory() as db:
        db.add_all([
            VoiceProfile(
                id=archive_app.DEFAULT_VOICE_ID,
                voice_name="default",
                audio_path=str(default_path.resolve()),
                reference_text="default",
                registration_state="active",
                created_at=datetime.now(UTC),
            ),
            VoiceProfile(
                id=legacy_voice_id,
                voice_name="legacy",
                audio_path=str(personal_path.resolve()),
                reference_text="legacy",
                registration_state="active",
                created_at=datetime.now(UTC),
            ),
        ])
        db.commit()

    removed = client.delete(
        f"/internal/owner-voices/{legacy_voice_id}",
        headers=_owner_headers(),
    )
    assert removed.status_code == 204
    assert not personal_path.exists()
    protected = client.delete(
        f"/internal/owner-voices/{archive_app.DEFAULT_VOICE_ID}",
        headers=_owner_headers(),
    )
    assert protected.status_code == 409
    assert default_path.exists()
    with session_factory() as db:
        assert db.query(VoiceProfile).filter(
            VoiceProfile.id == legacy_voice_id,
        ).first() is None
        assert db.query(VoiceProfile).filter(
            VoiceProfile.id == archive_app.DEFAULT_VOICE_ID,
        ).one()


def test_legacy_write_and_session_routes_require_service_auth_and_upload_limits(
    archive_client,
):
    client, _session_factory, _private_dir = archive_client
    assert client.get("/session/list").status_code == 401
    assert client.post("/voice", json={
        "voice_name": "blocked",
        "audio_path": "blocked.wav",
        "reference_text": "blocked",
    }).status_code == 401
    assert client.post(
        "/upload/audio",
        files={"file": ("sample.wav", b"audio", "audio/wav")},
    ).status_code == 401
    invalid_type = client.post(
        "/upload/audio",
        headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
        files={"file": ("sample.html", b"<script>x</script>", "text/html")},
    )
    assert invalid_type.status_code == 415
    too_large = client.post(
        "/upload/audio",
        headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
        files={"file": ("sample.wav", b"0" * (20 * 1024 * 1024 + 1), "audio/wav")},
    )
    assert too_large.status_code == 413
