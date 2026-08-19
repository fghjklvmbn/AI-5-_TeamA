import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import httpx
from fastapi.testclient import TestClient


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))


class _FakeTranscriptionService:
    calls = []

    @staticmethod
    def transcribe(path):
        _FakeTranscriptionService.calls.append(path)
        return "recognized"


fake_transcription_module = types.ModuleType("services.transcription_service")
fake_transcription_module.TranscriptionService = _FakeTranscriptionService
sys.modules["services.transcription_service"] = fake_transcription_module

app_spec = importlib.util.spec_from_file_location(
    "memorypal_stt_app_under_test", SERVICE_ROOT / "app.py",
)
stt_app = importlib.util.module_from_spec(app_spec)
assert app_spec.loader is not None
app_spec.loader.exec_module(stt_app)


MODEL_SERVICE_TOKEN = "model-service-test-token-" + "x" * 40


def _audio_request(client, *, token=None, content=b"audio", content_type="audio/wav"):
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    return client.post(
        "/transcribe",
        headers=headers,
        files={"audio": ("sample.wav", content, content_type)},
    )


def test_transcribe_fails_closed_without_server_token(monkeypatch):
    monkeypatch.delenv("MEMORYPAL_MODEL_SERVICE_TOKEN", raising=False)
    with TestClient(stt_app.app) as client:
        assert _audio_request(client).status_code == 503


def test_internal_ready_verifies_current_token_while_health_stays_public(monkeypatch):
    monkeypatch.setenv("MEMORYPAL_MODEL_SERVICE_TOKEN", MODEL_SERVICE_TOKEN)
    with TestClient(stt_app.app) as client:
        assert client.get("/health").status_code == 200
        rejected = client.get(
            "/internal/ready", headers={"Authorization": "Bearer stale-token"},
        )
        accepted = client.get(
            "/internal/ready",
            headers={"Authorization": f"Bearer {MODEL_SERVICE_TOKEN}"},
        )

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json() == {"status": "ready"}


def test_transcribe_requires_matching_bearer_and_accepts_valid_audio(monkeypatch):
    monkeypatch.setenv("MEMORYPAL_MODEL_SERVICE_TOKEN", MODEL_SERVICE_TOKEN)
    _FakeTranscriptionService.calls.clear()
    with TestClient(stt_app.app) as client:
        rejected_before_parse = client.post(
            "/transcribe",
            content=b"not multipart",
            headers={"Content-Type": "multipart/form-data"},
        )
        unauthorized = _audio_request(client, token="wrong-token")
        accepted = _audio_request(client, token=MODEL_SERVICE_TOKEN)

    assert rejected_before_parse.status_code == 401
    assert unauthorized.status_code == 401
    assert unauthorized.headers["www-authenticate"] == "Bearer"
    assert accepted.status_code == 200
    assert accepted.json() == {"text": "recognized"}
    assert len(_FakeTranscriptionService.calls) == 1
    assert not Path(_FakeTranscriptionService.calls[0]).exists()


def test_transcribe_rejects_oversized_and_disguised_uploads(monkeypatch):
    monkeypatch.setenv("MEMORYPAL_MODEL_SERVICE_TOKEN", MODEL_SERVICE_TOKEN)
    monkeypatch.setattr(stt_app, "MAX_AUDIO_BYTES", 4)
    with TestClient(stt_app.app) as client:
        oversized = _audio_request(client, token=MODEL_SERVICE_TOKEN, content=b"12345")
        disguised = _audio_request(
            client,
            token=MODEL_SERVICE_TOKEN,
            content=b"not audio",
            content_type="application/octet-stream",
        )

    assert oversized.status_code == 413
    assert disguised.status_code == 415


def test_transcribe_fails_fast_when_gpu_slot_is_busy(monkeypatch):
    monkeypatch.setenv("MEMORYPAL_MODEL_SERVICE_TOKEN", MODEL_SERVICE_TOKEN)

    async def request_while_busy():
        slot = asyncio.Semaphore(1)
        monkeypatch.setattr(stt_app, "_inference_slot", slot)
        await slot.acquire()
        try:
            transport = httpx.ASGITransport(app=stt_app.app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver",
            ) as client:
                return await client.post(
                    "/transcribe",
                    headers={"Authorization": f"Bearer {MODEL_SERVICE_TOKEN}"},
                    files={"audio": ("sample.wav", b"audio", "audio/wav")},
                )
        finally:
            slot.release()

    response = asyncio.run(request_while_busy())
    assert response.status_code == 429
    assert response.headers["retry-after"] == "1"
