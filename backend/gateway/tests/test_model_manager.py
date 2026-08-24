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


def test_activate_regular_persona_loads_the_account_selection(monkeypatch):
    manager = ModelManager(settings())
    loaded = []

    async def selected_model(_user_id, _persona):
        return {"model_key": "account-model-2b", "display_name": "Account Model", "loaded": bool(loaded)}

    async def ensure_user_model(user_id, model_key):
        loaded.append((user_id, model_key))

    monkeypatch.setattr(manager, "selected_model", selected_model)
    monkeypatch.setattr(manager, "ensure_user_model", ensure_user_model)
    result = asyncio.run(manager.activate_persona("user-1", "none"))

    assert loaded == [("user-1", "account-model-2b")]
    assert result["loaded"] is True


def test_activate_companion_persona_loads_hidden_companion(monkeypatch):
    manager = ModelManager(settings())
    calls = []

    async def ensure_companion_model():
        calls.append("companion")
        return {}

    async def selected_model(_user_id, persona):
        return {"model_key": "memorypal_ai", "display_name": "MemoryPal", "loaded": persona == "emotional_companion"}

    monkeypatch.setattr(manager, "ensure_companion_model", ensure_companion_model)
    monkeypatch.setattr(manager, "selected_model", selected_model)
    result = asyncio.run(manager.activate_persona("user-1", "emotional_companion"))

    assert calls == ["companion"]
    assert result["loaded"] is True


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


def test_companion_activation_unloads_llms_but_keeps_embedding(monkeypatch):
    manager = ModelManager(settings())
    calls = []

    async def request(method, path, *, json_body=None):
        calls.append((method, path, json_body))
        if method == "GET":
            return {"models": [
                {
                    "key": "qwen3.5-4b", "type": "llm",
                    "loaded_instances": [{"id": "qwen-instance"}],
                },
                {
                    "key": "text-embedding-nomic", "type": "embedding",
                    "loaded_instances": [{"id": "embedding-instance"}],
                },
                {
                    "key": "memorypal_ai", "type": "llm", "loaded_instances": [],
                },
            ]}
        return {"ok": True}

    monkeypatch.setattr(manager, "_request", request)
    asyncio.run(manager.ensure_companion_model())

    assert calls == [
        ("GET", "/models", None),
        ("POST", "/models/unload", {"instance_id": "qwen-instance"}),
        ("POST", "/models/load", {
            "model": "memorypal_ai",
            "context_length": 40960,
            "flash_attention": True,
            "offload_kv_cache_to_gpu": True,
            "echo_load_config": True,
        }),
    ]


def test_companion_activation_is_noop_when_already_loaded(monkeypatch):
    manager = ModelManager(settings())
    calls = []

    async def request(method, path, *, json_body=None):
        calls.append((method, path, json_body))
        return {"models": [{
            "key": "memorypal_ai",
            "loaded_instances": [{"id": "companion-instance"}],
        }]}

    monkeypatch.setattr(manager, "_request", request)
    result = asyncio.run(manager.ensure_companion_model())

    assert result["already_loaded"] is True
    assert result["model_key"] == "memorypal_ai"
    assert calls == [("GET", "/models", None)]


def test_account_model_is_loaded_on_first_use(tmp_path, monkeypatch):
    manager = ModelManager(settings(database_path=tmp_path / "test.db"))
    manager._write_state({
        "user-1": [{
            "job_id": "job-one",
            "model": "publisher/Model-One-2B-Q4_K_M-GGUF",
            "status": "completed",
        }],
    })
    loaded = False
    calls = []

    async def models():
        return {"models": [{
            "key": "model-one-2b",
            "display_name": "Model One 2B",
            "loaded_instances": [{"id": "instance"}] if loaded else [],
        }]}

    async def request(method, path, *, json_body=None):
        nonlocal loaded
        calls.append((method, path, json_body))
        if method == "POST":
            loaded = True
            return {"instance_id": "instance"}
        return await models()

    monkeypatch.setattr(manager, "models", models)
    monkeypatch.setattr(manager, "_request", request)
    asyncio.run(manager.ensure_user_model("user-1", "model-one-2b"))
    assert calls[-1][0:2] == ("POST", "/models/load")
    assert calls[-1][2]["context_length"] == 40960


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


def test_user_models_matches_huggingface_repository_to_lmstudio_key(tmp_path, monkeypatch):
    manager = ModelManager(settings(database_path=tmp_path / "test.db"))
    manager._write_state({
        "user-1": [{
            "job_id": "job-hyperclova",
            "model": "rippertnt/HyperCLOVAX-SEED-Text-Instruct-1.5B-Q4_K_M-GGUF",
            "status": "completed",
        }],
    })

    async def models():
        return {"models": [
            {
                "key": "hyperclovax-seed-text-instruct-1.5b",
                "display_name": "Hyperclovax Seed Text Instruct 1.5B",
                "quantization": {"name": "Q4_K_M", "bits_per_weight": 4},
                "loaded_instances": [],
            },
            {"key": "other-user-model", "display_name": "Other User Model", "loaded_instances": []},
            {"key": "qwen3.5-4b", "display_name": "Qwen3.5 4B", "loaded_instances": []},
        ]}

    monkeypatch.setattr(manager, "models", models)
    result = asyncio.run(manager.user_models("user-1"))

    assert [model["key"] for model in result["models"]] == [
        "hyperclovax-seed-text-instruct-1.5b",
        "qwen3.5-4b",
    ]
    assert result["models"][0]["quantization"] == "Q4_K_M"


def test_selected_model_is_persisted_per_user(tmp_path, monkeypatch):
    manager = ModelManager(settings(database_path=tmp_path / "test.db"))
    manager._write_state({
        "user-1": [{
            "job_id": "job-one",
            "model": "publisher/Model-One-2B-Q4_K_M-GGUF",
            "status": "completed",
        }],
    })

    async def models():
        return {"models": [{
            "key": "model-one-2b",
            "display_name": "Model One 2B",
            "loaded_instances": [{"id": "model-one-instance"}],
        }]}

    monkeypatch.setattr(manager, "models", models)
    selected = asyncio.run(manager.select_model("user-1", "model-one-2b"))
    assert selected == {
        "model_key": "model-one-2b",
        "display_name": "Model One 2B",
        "loaded": True,
    }
    assert asyncio.run(manager.selected_model("user-1")) == selected
    assert asyncio.run(manager.selected_model("user-2"))["model_key"] == "qwen3.5-4b"

    cleared = asyncio.run(manager.select_model("user-1", None))
    assert cleared["model_key"] == "model-one-2b"
    assert asyncio.run(manager.selected_model("user-1"))["model_key"] == "model-one-2b"


def test_selected_model_reports_companion_from_lmstudio_state(tmp_path, monkeypatch):
    manager = ModelManager(settings(database_path=tmp_path / "test.db"))

    async def models():
        return {"models": [{
            "key": "memorypal_ai",
            "display_name": "MemoryPal Companion",
            "loaded_instances": [{"id": "companion-instance"}],
        }]}

    monkeypatch.setattr(manager, "models", models)
    assert asyncio.run(manager.selected_model("user-1", "emotional_companion")) == {
        "model_key": "memorypal_ai",
        "display_name": "MemoryPal Companion",
        "loaded": True,
    }
