import asyncio
from dataclasses import replace

import httpx

from memorypal_api.config import load_settings
from memorypal_api.services.pipeline import ModelPipeline


def test_public_audio_url_replaces_internal_tts_origin():
    pipeline = ModelPipeline(replace(load_settings(), tts_public_url="https://example.com/tts"))
    assert pipeline.public_audio_url("http://127.0.0.1:8003/outputs/a.wav") == "https://example.com/tts/outputs/a.wav"


def test_generate_retries_once_when_llm_returns_blank():
    pipeline = ModelPipeline(load_settings()); responses = iter(["", "다시 생성한 답변입니다."])
    async def completion(_messages, temperature, model=None):
        return next(responses)
    pipeline._completion = completion
    assert asyncio.run(pipeline.generate("안녕", "", [])) == "다시 생성한 답변입니다."


def test_generate_uses_casual_korean_prompt_when_enabled():
    pipeline = ModelPipeline(load_settings()); captured = {}
    async def completion(messages, temperature, model=None):
        captured["system"] = messages[0]["content"]; return "알겠어"
    pipeline._completion = completion
    asyncio.run(pipeline.generate("안녕", "", [], casual_mode=True))
    assert "반말(해체)" in captured["system"]


def test_generate_routes_personas_to_separate_models():
    pipeline = ModelPipeline(load_settings()); models = []
    async def completion(_messages, temperature, model=None):
        models.append(model); return "답변"
    pipeline._completion = completion
    asyncio.run(pipeline.generate("질문", "", [], persona="default"))
    asyncio.run(pipeline.generate("질문", "", [], persona="emotional_companion"))
    assert models == ["qwen3.5-4b", "memorypal_ai"]


def test_default_persona_limits_answer_to_200_characters():
    pipeline = ModelPipeline(load_settings())
    async def completion(_messages, temperature, model=None): return "가" * 250
    pipeline._completion = completion
    assert len(asyncio.run(pipeline.generate("질문", "", []))) == 200


def test_generate_includes_document_context_and_omits_empty_memory():
    pipeline = ModelPipeline(load_settings()); captured = {}
    async def completion(messages, temperature, model=None):
        captured["system"] = messages[0]["content"]; return "답변"
    pipeline._completion = completion
    asyncio.run(pipeline.generate("일정", "", [], document_context="[첨부파일: plan.md]\n8월 20일"))
    assert "plan.md" in captured["system"]
    assert "관련 장기 기억" not in captured["system"]


def test_generate_marks_session_context_as_temporary_and_resolves_short_replies():
    pipeline = ModelPipeline(load_settings()); captured = {}
    async def completion(messages, temperature, model=None):
        captured["system"] = messages[0]["content"]; return "응, 이어서 말할게"
    pipeline._completion = completion
    asyncio.run(pipeline.generate(
        "어", "", [], session_context="MemoryPal: 조리법을 알려줄까?",
    ))
    assert "현재 세션의 임시 작업 기억" in captured["system"]
    assert "장기 기억과 완전히 별개" in captured["system"]
    assert "'어', '응', '그래'" in captured["system"]


def test_explicit_session_memory_extraction_uses_prior_context():
    pipeline = ModelPipeline(load_settings()); captured = {}
    async def completion(messages, temperature, model=None):
        captured["prompt"] = messages[-1]["content"]
        return '[{"type":"fact","content":"두부조림에는 간장 두 숟갈을 넣는다","confidence":0.95,"importance":0.85}]'
    pipeline._completion = completion
    result = asyncio.run(pipeline.extract_session_memories(
        "MemoryPal: 두부조림에는 간장 두 숟갈을 넣어", "어 저장해줘",
    ))
    assert result[0].content == "두부조림에는 간장 두 숟갈을 넣는다"
    assert "최근 세션 대화" in captured["prompt"]
    assert "저장 약속 자체는 저장하지 마" in captured["prompt"]


def test_synthesize_retries_once_after_temporary_failure(monkeypatch):
    pipeline = ModelPipeline(load_settings())
    class Response:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): return None
        def json(self): return self.payload
    class Client:
        count = 0
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def get(self, _url): return Response({"audio_path": "ref.wav", "reference_text": "안녕"})
        async def post(self, _url, json):
            self.count += 1
            if self.count == 1: raise httpx.ConnectError("temporary")
            return Response({"audio_path": "http://127.0.0.1:8003/outputs/retry.wav"})
    client = Client()
    monkeypatch.setattr("memorypal_api.services.pipeline.httpx.AsyncClient", lambda **_kwargs: client)
    assert asyncio.run(pipeline.synthesize("답변", None))
