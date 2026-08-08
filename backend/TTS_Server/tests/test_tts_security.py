import asyncio
import sys
import types
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

try:
    import torch  # noqa: F401
except ModuleNotFoundError:
    sys.modules["torch"] = types.ModuleType("torch")

try:
    import soundfile  # noqa: F401
except ModuleNotFoundError:
    soundfile_module = types.ModuleType("soundfile")
    soundfile_module.write = lambda *_args, **_kwargs: None
    sys.modules["soundfile"] = soundfile_module

from routers import tts_router
from services import tts_service as tts_service_module
from services.tts_service import TTSService


MODEL_SERVICE_TOKEN = "model-service-test-token-" + "x" * 40


def test_device_auto_selects_cpu_and_upstream_without_cuda(monkeypatch):
    monkeypatch.setattr(
        tts_service_module,
        "torch",
        types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False)),
    )
    monkeypatch.setenv("MEMORYPAL_TTS_DEVICE", "auto")
    monkeypatch.setenv("MEMORYPAL_TTS_ENGINE", "auto")

    service = TTSService()

    assert service.device == "cpu"
    assert service.accelerator == "cpu"
    assert service.engine == "upstream"


def test_explicit_cuda_falls_back_to_cpu_when_unavailable(monkeypatch):
    monkeypatch.setattr(
        tts_service_module,
        "torch",
        types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False)),
    )
    monkeypatch.setenv("MEMORYPAL_TTS_DEVICE", "cuda")
    monkeypatch.setenv("MEMORYPAL_TTS_ENGINE", "faster")

    with pytest.warns(RuntimeWarning):
        service = TTSService()

    assert service.device == "cpu"
    assert service.accelerator == "cpu"
    assert service.engine == "upstream"


def test_rocm_uses_pytorch_cuda_namespace_but_upstream_engine(monkeypatch):
    monkeypatch.setattr(
        tts_service_module,
        "torch",
        types.SimpleNamespace(
            cuda=types.SimpleNamespace(is_available=lambda: True),
            version=types.SimpleNamespace(hip="7.2.1"),
        ),
    )
    monkeypatch.setenv("MEMORYPAL_TTS_DEVICE", "auto")
    monkeypatch.setenv("MEMORYPAL_TTS_ENGINE", "auto")

    service = TTSService()

    assert service.accelerator == "rocm"
    assert service.device == "cuda"
    assert service.engine == "upstream"


def _test_app():
    app = FastAPI()
    tts_router.install_model_service_auth_middleware(app)
    app.include_router(tts_router.router)
    return app


def _synthesis_request(client, *, token=None, text="hello"):
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    return client.post(
        "/synthesize",
        headers=headers,
        json={
            "text": text,
            "ref_audio": "voice.wav",
            "ref_text": "reference",
            "language": "korean",
        },
    )


def test_synthesize_fails_closed_and_requires_matching_bearer(monkeypatch):
    app = _test_app()
    monkeypatch.delenv("MEMORYPAL_MODEL_SERVICE_TOKEN", raising=False)
    with TestClient(app) as client:
        assert _synthesis_request(client).status_code == 503

    monkeypatch.setenv("MEMORYPAL_MODEL_SERVICE_TOKEN", MODEL_SERVICE_TOKEN)
    monkeypatch.setattr(
        tts_router.tts_service,
        "synthesize",
        lambda **_kwargs: {"audio_path": "http://tts/outputs/result.wav"},
    )
    with TestClient(app) as client:
        rejected_before_parse = client.post(
            "/synthesize",
            content=b"{",
            headers={"Content-Type": "application/json"},
        )
        unauthorized = _synthesis_request(client, token="wrong-token")
        accepted = _synthesis_request(client, token=MODEL_SERVICE_TOKEN)

    assert rejected_before_parse.status_code == 401
    assert unauthorized.status_code == 401
    assert unauthorized.headers["www-authenticate"] == "Bearer"
    assert accepted.status_code == 200


def test_internal_ready_verifies_current_token_while_health_stays_public(monkeypatch):
    monkeypatch.setenv("MEMORYPAL_MODEL_SERVICE_TOKEN", MODEL_SERVICE_TOKEN)
    with TestClient(_test_app()) as client:
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


def test_synthesize_enforces_bounded_text(monkeypatch):
    monkeypatch.setenv("MEMORYPAL_MODEL_SERVICE_TOKEN", MODEL_SERVICE_TOKEN)
    with TestClient(_test_app()) as client:
        response = _synthesis_request(
            client, token=MODEL_SERVICE_TOKEN, text="a" * 601,
        )
    assert response.status_code == 422


def test_synthesize_upload_authenticates_and_removes_temporary_audio(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORYPAL_MODEL_SERVICE_TOKEN", MODEL_SERVICE_TOKEN)
    monkeypatch.setenv("MEMORYPAL_TTS_REFERENCE_UPLOAD_DIR", str(tmp_path))
    observed = {}

    def synthesize(**kwargs):
        observed["path"] = kwargs["ref_audio"]
        assert Path(kwargs["ref_audio"]).is_file()
        return {"audio_path": "http://tts/outputs/upload.wav"}

    monkeypatch.setattr(tts_router.tts_service, "synthesize", synthesize)
    with TestClient(_test_app()) as client:
        unauthorized = client.post(
            "/synthesize-upload",
            data={"text": "hello", "ref_text": "reference", "language": "korean"},
            files={"ref_audio": ("ref.wav", b"RIFF-data", "audio/wav")},
        )
        accepted = client.post(
            "/synthesize-upload",
            headers={"Authorization": f"Bearer {MODEL_SERVICE_TOKEN}"},
            data={"text": "hello", "ref_text": "reference", "language": "korean"},
            files={"ref_audio": ("ref.wav", b"RIFF-data", "audio/wav")},
        )

    assert unauthorized.status_code == 401
    assert accepted.status_code == 200
    assert not Path(observed["path"]).exists()


def test_synthesize_fails_fast_when_gpu_slot_is_busy(monkeypatch):
    monkeypatch.setenv("MEMORYPAL_MODEL_SERVICE_TOKEN", MODEL_SERVICE_TOKEN)
    app = _test_app()

    async def request_while_busy():
        slot = asyncio.Semaphore(1)
        monkeypatch.setattr(tts_router, "_inference_slot", slot)
        await slot.acquire()
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver",
            ) as client:
                return await client.post(
                    "/synthesize",
                    headers={"Authorization": f"Bearer {MODEL_SERVICE_TOKEN}"},
                    json={
                        "text": "hello",
                        "ref_audio": "voice.wav",
                        "ref_text": "reference",
                        "language": "korean",
                    },
                )
        finally:
            slot.release()

    response = asyncio.run(request_while_busy())
    assert response.status_code == 429
    assert response.headers["retry-after"] == "1"


@pytest.mark.parametrize(
    "remote_path",
    [
        "http://169.254.169.254/latest/meta-data",
        "https://example.com/reference.wav",
        "file:///etc/passwd",
        "//internal-server/share/reference.wav",
    ],
)
def test_reference_audio_never_fetches_remote_or_network_paths(remote_path):
    with pytest.raises(ValueError):
        TTSService()._localize_ref_audio(remote_path)


def test_reference_audio_is_confined_to_configured_local_root(tmp_path, monkeypatch):
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    allowed = allowed_root / "voice.wav"
    allowed.write_bytes(b"wave")
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"wave")
    monkeypatch.setenv("MEMORYPAL_TTS_REFERENCE_AUDIO_ROOTS", str(allowed_root))

    service = TTSService()
    assert service._localize_ref_audio(str(allowed)) == str(allowed.resolve())
    with pytest.raises(ValueError, match="outside the allowed"):
        service._localize_ref_audio(str(outside))
