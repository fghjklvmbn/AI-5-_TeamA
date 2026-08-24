import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from memorypal_api.services.model_manager import ModelManager, ModelManagerConflict
from memorypal_api.services.model_usage import ModelInUseError, ModelUsageTracker
from memorypal_api.services.pipeline import ModelPipeline


def settings():
    return SimpleNamespace(
        llm_url="http://llm.test/v1",
        llm_api_key="test-key",
        llm_default_model="default-model",
        llm_companion_model="memorypal_ai",
        request_timeout_seconds=30.0,
        database_path=Path("data/test.db"),
        huggingface_token="",
    )


def test_usage_tracker_rejects_unload_until_inference_finishes():
    async def scenario():
        tracker = ModelUsageTracker()
        async with tracker.using("model-a"):
            assert tracker.is_active("MODEL-A")
            with pytest.raises(ModelInUseError):
                async with tracker.unloading("model-a"):
                    pass
        async with tracker.unloading("model-a"):
            assert not tracker.is_active("model-a")

    asyncio.run(scenario())


def test_pipeline_holds_model_usage_for_the_entire_completion(monkeypatch):
    async def scenario():
        tracker = ModelUsageTracker()
        pipeline = ModelPipeline(settings(), tracker)

        async def completion(*_args, **_kwargs):
            assert tracker.is_active("selected-model")
            return "완료된 답변"

        monkeypatch.setattr(pipeline, "_completion_untracked", completion)
        answer = await pipeline._completion(
            [{"role": "user", "content": "질문"}], 0.7, model="selected-model",
        )
        assert answer == "완료된 답변"
        assert not tracker.is_active("selected-model")

    asyncio.run(scenario())


def test_model_manager_blocks_busy_instance_before_lmstudio_unload(monkeypatch):
    async def scenario():
        tracker = ModelUsageTracker()
        manager = ModelManager(settings(), tracker)
        requests = []

        async def models():
            return {"models": [{
                "key": "model-a", "loaded_instances": [{"id": "instance-a"}],
            }]}

        async def request(*args, **kwargs):
            requests.append((args, kwargs))
            return {"ok": True}

        monkeypatch.setattr(manager, "models", models)
        monkeypatch.setattr(manager, "_request", request)
        async with tracker.using("model-a"):
            with pytest.raises(ModelManagerConflict, match="처리 중"):
                await manager.unload("instance-a")
        assert requests == []
        assert await manager.unload("instance-a") == {"ok": True}
        assert len(requests) == 1

    asyncio.run(scenario())
