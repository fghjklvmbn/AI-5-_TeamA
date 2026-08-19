import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from memorypal_api.services.model_manager import ModelManager, ModelManagerConflict


def settings(**overrides):
    values = {
        "llm_url": "https://developark.duckdns.org/api_memoripal/llm/v1",
        "llm_resource_url": "",
        "monitor_llm_url": "http://192.168.2.41:8101",
        "llm_api_key": "test-key",
        "model_service_token": "resource-token-" + "r" * 48,
        "request_timeout_seconds": 30.0,
        "huggingface_token": "",
        "lmstudio_model_root": None,
        "lmstudio_cli": "lms",
        "database_path": Path("data/test.db"),
        "llm_default_model": "qwen3.5-4b",
        "llm_companion_model": "memorypal_ai",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_native_api_url_preserves_external_proxy_prefix():
    manager = ModelManager(settings())
    assert manager.native_base == "https://developark.duckdns.org/api_memoripal/llm/api/v1"


def test_gpu_memory_status_comes_from_authenticated_llm_server(monkeypatch):
    manager = ModelManager(settings())
    captured = {}

    class Response:
        def raise_for_status(self): return None
        def json(self):
            return {
                "service": "llm",
                "status": "green",
                "gpu": {
                    "names": ["GPU One", "GPU Two"],
                    "count": 2,
                    "vram_total_bytes": 12288 * 1024**2,
                    "vram_used_bytes": 7168 * 1024**2,
                    "vram_free_bytes": 5120 * 1024**2,
                },
            }

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def get(self, url, headers):
            captured.update(url=url, headers=headers)
            return Response()

    monkeypatch.setattr("memorypal_api.services.model_manager.httpx.AsyncClient", lambda **_kwargs: Client())

    result = asyncio.run(manager._gpu_memory_status())

    assert result["gpu_metrics_available"] is True
    assert result["gpu_name"] == "GPU One · GPU Two"
    assert result["gpu_count"] == 2
    assert result["vram_total_bytes"] == 12288 * 1024**2
    assert result["vram_used_bytes"] == 7168 * 1024**2
    assert result["vram_free_bytes"] == 5120 * 1024**2
    assert result["gpu_metrics_source"] == "llm-server"
    assert captured == {
        "url": "http://192.168.2.41:8101/v1/metrics/current",
        "headers": {"Authorization": f"Bearer {manager.settings.model_service_token}"},
    }


def test_gpu_memory_status_does_not_fall_back_to_gateway_gpu():
    manager = ModelManager(settings(monitor_llm_url="", llm_resource_url=""))
    assert asyncio.run(manager._gpu_memory_status()) == {"gpu_metrics_available": False}


def test_load_uses_40k_context_and_safe_lmstudio_options(monkeypatch):
    manager = ModelManager(settings())
    captured = {}

    async def request(method, path, *, json_body=None):
        captured.update(method=method, path=path, body=json_body)
        return {"instance_id": "loaded-1"}

    monkeypatch.setattr(manager, "_request", request)
    asyncio.run(manager.load("publisher/model-q4_k_m.gguf", 40960))
    assert captured == {
        "method": "POST",
        "path": "/models/load",
        "body": {
            "model": "publisher/model-q4_k_m.gguf",
            "context_length": 40960,
            "flash_attention": True,
            "offload_kv_cache_to_gpu": True,
            "echo_load_config": True,
        },
    }


def test_load_blocks_a_fourth_loaded_model(monkeypatch):
    manager = ModelManager(settings())
    calls = []

    async def request(method, path, *, json_body=None):
        calls.append((method, path, json_body))
        if method == "GET":
            return {"models": [
                {"key": "publisher/loaded-1", "loaded_instances": [{"id": "one"}]},
                {"key": "publisher/loaded-2", "loaded_instances": [{"id": "two"}]},
                {"key": "publisher/loaded-3", "loaded_instances": [{"id": "three"}]},
                {"key": "publisher/new-model", "loaded_instances": []},
            ]}
        return {"instance_id": "should-not-load"}

    monkeypatch.setattr(manager, "_request", request)
    with pytest.raises(ModelManagerConflict, match="리소스가 부족하여 로드가 제한됩니다"):
        asyncio.run(manager.load("publisher/new-model", 40960))
    assert calls == [("GET", "/models", None)]


def test_selecting_an_already_loaded_model_does_not_hit_limit(monkeypatch):
    manager = ModelManager(settings())

    async def models():
        return {"models": [
            {"key": "publisher/selected", "loaded_instances": [{"id": "selected-instance"}]},
            {"key": "publisher/loaded-2", "loaded_instances": [{"id": "two"}]},
            {"key": "publisher/loaded-3", "loaded_instances": [{"id": "three"}]},
        ]}

    monkeypatch.setattr(manager, "models", models)
    result = asyncio.run(manager.load("publisher/selected", 40960))
    assert result["already_loaded"] is True
    assert result["model_key"] == "publisher/selected"


def test_selected_chat_model_must_be_loaded(monkeypatch):
    manager = ModelManager(settings())

    async def models():
        return {"models": [{"key": "publisher/model", "loaded_instances": []}]}

    monkeypatch.setattr(manager, "models", models)
    with pytest.raises(ModelManagerConflict, match="언로드"):
        asyncio.run(manager.ensure_loaded("publisher/model"))


def test_failed_download_can_be_dismissed_persistently(tmp_path):
    manager = ModelManager(settings(database_path=tmp_path / "test.db"))
    manager._write_state({
        "user-1": [
            {"job_id": "failed-1", "model": "publisher/model-2b", "status": "failed"},
            {"job_id": "active-1", "model": "publisher/other-2b", "status": "downloading"},
        ],
    })

    result = asyncio.run(manager.dismiss_download("user-1", "failed-1"))

    assert result == {"dismissed": True, "job_id": "failed-1"}
    assert [job["job_id"] for job in manager._read_state()["user-1"]] == ["active-1"]


def test_active_download_cannot_be_dismissed(tmp_path):
    manager = ModelManager(settings(database_path=tmp_path / "test.db"))
    manager._write_state({
        "user-1": [{"job_id": "active-1", "model": "publisher/model-2b", "status": "downloading"}],
    })

    with pytest.raises(ModelManagerConflict, match="실패하거나 취소된"):
        asyncio.run(manager.dismiss_download("user-1", "active-1"))
