import asyncio
from dataclasses import replace

import httpx
import pytest

from memorypal_api.config import load_settings
from memorypal_api.schemas import ChatRequest, RegenerateRequest
from memorypal_api.services.pipeline import ModelPipeline, PipelineUnavailable


ARCHIVE_SERVICE_TOKEN = "archive-pipeline-test-token-" + "x" * 48
MODEL_SERVICE_TOKEN = "model-pipeline-test-token-" + "m" * 48


def test_public_audio_url_replaces_internal_tts_origin():
    pipeline = ModelPipeline(replace(load_settings(), tts_public_url="https://example.com/tts"))
    assert pipeline.public_audio_url("http://127.0.0.1:8003/outputs/a.wav") == "https://example.com/tts/outputs/a.wav"


def test_generate_retries_once_when_llm_returns_blank():
    pipeline = ModelPipeline(load_settings()); responses = iter(["", "다시 생성한 답변입니다."])
    async def completion(_messages, temperature, model=None, **_kwargs):
        return next(responses)
    pipeline._completion = completion
    assert asyncio.run(pipeline.generate("안녕", "", [])) == "다시 생성한 답변입니다."


def test_completion_disables_reasoning_without_mutating_stored_messages(monkeypatch):
    pipeline = ModelPipeline(load_settings())
    original = [{"role": "user", "content": "오늘 지쳤어"}]
    captured = {}

    class Response:
        def raise_for_status(self): return None
        def json(self):
            return {"choices": [{"message": {"content": "푹 쉬어도 괜찮아요."}, "finish_reason": "stop"}]}

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def post(self, _url, headers, json):
            captured["messages"] = json["messages"]
            captured["reasoning_effort"] = json["reasoning_effort"]
            captured["max_tokens"] = json["max_tokens"]
            return Response()

    monkeypatch.setattr("memorypal_api.services.pipeline.httpx.AsyncClient", lambda **_kwargs: Client())
    assert asyncio.run(pipeline._completion(original, 0.7, "memorypal_ai")) == "푹 쉬어도 괜찮아요."
    assert captured["messages"][-1]["content"].endswith("/nothink")
    assert captured["messages"][-1]["content"].count("/nothink") == 1
    assert captured["reasoning_effort"] == "none"
    assert captured["max_tokens"] == 768
    assert original[-1]["content"] == "오늘 지쳤어"


def test_completion_streams_visible_content_deltas(monkeypatch):
    pipeline = ModelPipeline(load_settings())
    captured = {}

    class Response:
        def raise_for_status(self): return None
        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"role":"assistant"}}]}'
            yield 'data: {"choices":[{"delta":{"content":"안녕"}}]}'
            yield 'data: {"choices":[{"delta":{"content":"하세요"}}]}'
            yield 'data: [DONE]'

    class StreamContext:
        async def __aenter__(self): return Response()
        async def __aexit__(self, *_args): return None

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        def stream(self, method, _url, headers, json):
            captured.update({"method": method, "payload": json})
            return StreamContext()

    deltas = []

    async def run():
        async def on_delta(delta):
            deltas.append(delta)
        return await pipeline._completion(
            [{"role": "user", "content": "인사해 줘"}], 0.7, on_delta=on_delta,
        )

    monkeypatch.setattr("memorypal_api.services.pipeline.httpx.AsyncClient", lambda **_kwargs: Client())
    assert asyncio.run(run()) == "안녕하세요"
    assert deltas == ["안녕", "하세요"]
    assert captured["method"] == "POST"
    assert captured["payload"]["stream"] is True


@pytest.mark.parametrize("reasoning_effort", ["low", "medium", "high"])
def test_completion_thinking_mode_reserves_reasoning_budget(monkeypatch, reasoning_effort):
    pipeline = ModelPipeline(load_settings())
    original = [{"role": "user", "content": "19 곱하기 23은?"}]
    captured = {}

    class Response:
        def raise_for_status(self): return None
        def json(self):
            return {"choices": [{
                "message": {"content": "437입니다.", "reasoning_content": "계산 과정"},
                "finish_reason": "stop",
            }]}

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def post(self, _url, headers, json):
            captured.update(json)
            return Response()

    monkeypatch.setattr("memorypal_api.services.pipeline.httpx.AsyncClient", lambda **_kwargs: Client())
    answer = asyncio.run(pipeline._completion(
        original, 0.4, "qwen/qwen3.5-9b", thinking_mode=True,
        reasoning_effort=reasoning_effort,
    ))
    assert answer == "437입니다."
    assert not captured["messages"][-1]["content"].endswith("/nothink")
    assert captured["reasoning_effort"] == reasoning_effort
    assert captured["max_tokens"] == 4096
    assert original[-1]["content"] == "19 곱하기 23은?"


def test_request_schemas_default_thinking_mode_off():
    assert ChatRequest(text="질문").thinking_mode is False
    assert RegenerateRequest().thinking_mode is False
    assert ChatRequest(text="질문").reasoning_effort == "medium"
    assert RegenerateRequest().reasoning_effort == "medium"
    assert ChatRequest(text="질문", persona="none").persona == "none"
    assert RegenerateRequest(persona="none").persona == "none"


def test_request_schemas_reject_unknown_reasoning_effort():
    with pytest.raises(ValueError):
        ChatRequest(text="질문", reasoning_effort="extreme")


def test_agent_planner_accepts_only_an_allowed_read_only_action():
    pipeline = ModelPipeline(load_settings())
    captured = {}

    async def completion(messages, temperature, model=None, **_kwargs):
        captured.update({"messages": messages, "temperature": temperature, "model": model})
        return '{"action":"document_search","query":"배포 일정"}'

    pipeline._completion = completion
    action, query = asyncio.run(pipeline.plan_agent_step(
        user_text="배포 일정이 언제야?",
        evidence="현재 근거",
        history=[],
        allowed_tools=["memory_search", "document_search"],
        attempted=[],
        persona="none",
    ))

    assert (action, query) == ("document_search", "배포 일정")
    assert captured["temperature"] == 0.0
    assert "읽기 전용" in captured["messages"][0]["content"]


def test_agent_planner_rejects_unavailable_or_mutating_action():
    pipeline = ModelPipeline(load_settings())

    async def completion(*_args, **_kwargs):
        return '{"action":"delete_memory","query":"all"}'

    pipeline._completion = completion
    assert asyncio.run(pipeline.plan_agent_step(
        user_text="기억을 확인해 줘",
        evidence="근거",
        history=[],
        allowed_tools=["memory_search"],
        attempted=[],
    )) == ("answer", "")


def test_generate_forwards_selected_reasoning_effort():
    pipeline = ModelPipeline(load_settings())
    captured = {}

    async def completion(
        _messages, temperature, model=None, thinking_mode=False,
        reasoning_effort="medium", **_kwargs,
    ):
        captured.update({
            "thinking_mode": thinking_mode,
            "reasoning_effort": reasoning_effort,
        })
        return "신중한 답변"

    pipeline._completion = completion
    asyncio.run(pipeline.generate(
        "질문", "", [], thinking_mode=True, reasoning_effort="high",
    ))

    assert captured == {"thinking_mode": True, "reasoning_effort": "high"}


def test_thinking_mode_blank_answer_falls_back_without_reasoning():
    pipeline = ModelPipeline(load_settings()); calls = []
    responses = iter(["", "최종 답변"])
    async def completion(_messages, temperature, model=None, thinking_mode=False, **_kwargs):
        calls.append(thinking_mode)
        return next(responses)
    pipeline._completion = completion
    answer = asyncio.run(pipeline.generate("질문", "", [], thinking_mode=True))
    assert answer == "최종 답변"
    assert calls == [True, False]


def test_completion_does_not_retry_invalid_400_request(monkeypatch):
    pipeline = ModelPipeline(load_settings()); state = {"count": 0}

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def post(self, url, headers, json):
            state["count"] += 1
            return httpx.Response(400, request=httpx.Request("POST", url), text="context overflow")

    monkeypatch.setattr("memorypal_api.services.pipeline.httpx.AsyncClient", lambda **_kwargs: Client())
    with pytest.raises(PipelineUnavailable):
        asyncio.run(pipeline._completion([{"role": "user", "content": "질문"}], 0.7))
    assert state["count"] == 1


def test_completion_retries_transient_503_once(monkeypatch):
    pipeline = ModelPipeline(load_settings()); state = {"count": 0}

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def post(self, url, headers, json):
            state["count"] += 1
            request = httpx.Request("POST", url)
            if state["count"] == 1:
                return httpx.Response(503, request=request, text="model loading")
            return httpx.Response(
                200, request=request,
                json={"choices": [{"message": {"content": "정상 답변"}, "finish_reason": "stop"}]},
            )

    async def no_sleep(_seconds): return None
    monkeypatch.setattr("memorypal_api.services.pipeline.httpx.AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr("memorypal_api.services.pipeline.asyncio.sleep", no_sleep)
    assert asyncio.run(pipeline._completion([{"role": "user", "content": "질문"}], 0.7)) == "정상 답변"
    assert state["count"] == 2


def test_companion_retries_with_compact_context_without_model_swap():
    pipeline = ModelPipeline(load_settings()); calls = []
    responses = iter(["", "같은 모델의 따뜻한 답변입니다."])
    async def completion(messages, temperature, model=None, **_kwargs):
        calls.append((messages, model)); return next(responses)
    pipeline._completion = completion
    answer = asyncio.run(pipeline.generate("오늘 힘들어", "", [], persona="emotional_companion"))
    assert answer == "같은 모델의 따뜻한 답변입니다."
    assert [model for _, model in calls] == ["memorypal_ai", "memorypal_ai"]
    assert "따뜻한 동반자" in calls[1][0][0]["content"]


def test_generate_uses_casual_korean_prompt_when_enabled():
    pipeline = ModelPipeline(load_settings()); captured = {}
    async def completion(messages, temperature, model=None, **_kwargs):
        captured["system"] = messages[0]["content"]; return "알겠어"
    pipeline._completion = completion
    asyncio.run(pipeline.generate("안녕", "", [], casual_mode=True))
    assert "반말(해체)" in captured["system"]


def test_generate_routes_each_persona_to_its_own_model():
    pipeline = ModelPipeline(load_settings()); models = []
    async def completion(_messages, temperature, model=None, **_kwargs):
        models.append(model); return "답변"
    pipeline._completion = completion
    asyncio.run(pipeline.generate("질문", "", [], persona="default"))
    asyncio.run(pipeline.generate("질문", "", [], persona="emotional_companion"))
    asyncio.run(pipeline.generate("질문", "", [], persona="none"))
    assert models == ["qwen/qwen3.5-9b", "memorypal_ai", "qwen/qwen3.5-9b"]


@pytest.mark.parametrize(
    ("casual_mode", "expected_style"),
    [(False, "존댓말(해요체)"), (True, "반말(해체)")],
)
def test_none_persona_is_neutral_but_keeps_memory_web_and_document_context(
    casual_mode, expected_style,
):
    pipeline = ModelPipeline(load_settings())
    captured = {}

    async def completion(messages, temperature, model=None, **_kwargs):
        captured["system"] = messages[0]["content"]
        captured["model"] = model
        return "확인된 범위에서 답변"

    pipeline._completion = completion
    asyncio.run(pipeline.generate(
        "질문", "사용자는 커피를 좋아함", [],
        casual_mode=casual_mode,
        persona="none",
        document_context="[첨부파일: note.md] 문서 근거",
        web_context="[1] 검색 근거\nURL: https://example.com",
    ))

    system = captured["system"]
    assert "특정 이름·성격·동반자 역할이 설정되지 않은" in system
    assert "MemoryPal이라는" not in system
    assert "관련 장기 기억" in system
    assert "note.md" in system
    assert "이번 답변용 웹 검색 결과" in system
    assert expected_style in system
    assert captured["model"] == "qwen/qwen3.5-9b"


def test_companion_uses_its_model_for_memory_judgment():
    pipeline = ModelPipeline(load_settings()); models = []
    async def completion(_messages, temperature, model=None, **_kwargs):
        models.append(model); return "[]"
    pipeline._completion = completion
    asyncio.run(pipeline.extract_memories(
        "나는 따뜻한 라떼를 좋아해", persona="emotional_companion",
    ))
    asyncio.run(pipeline.extract_session_memories(
        "사용자: 라떼를 좋아해", "기억해줘", persona="emotional_companion",
    ))
    asyncio.run(pipeline.summarize_user_note(
        "라떼 레시피", persona="emotional_companion",
    ))
    assert models == ["memorypal_ai", "memorypal_ai", "memorypal_ai"]


def test_none_persona_keeps_memory_extraction_on_the_default_model():
    pipeline = ModelPipeline(load_settings())
    models = []

    async def completion(_messages, temperature, model=None, **_kwargs):
        models.append(model)
        return "[]"

    pipeline._completion = completion
    asyncio.run(pipeline.extract_memories("커피를 좋아해", persona="none"))
    asyncio.run(pipeline.extract_session_memories(
        "사용자: 커피를 좋아해", "기억해줘", persona="none",
    ))
    asyncio.run(pipeline.summarize_user_note("커피 취향", persona="none"))

    assert models == ["qwen/qwen3.5-9b"] * 3


def test_default_persona_limits_answer_to_200_characters():
    pipeline = ModelPipeline(load_settings())
    async def completion(_messages, temperature, model=None, **_kwargs): return "가" * 250
    pipeline._completion = completion
    assert len(asyncio.run(pipeline.generate("질문", "", []))) == 200
    assert len(asyncio.run(pipeline.generate("질문", "", [], thinking_mode=True))) == 200


def test_companion_persona_also_limits_answer_to_200_characters():
    pipeline = ModelPipeline(load_settings())
    async def completion(_messages, temperature, model=None, **_kwargs): return "가" * 250
    pipeline._completion = completion
    answer = asyncio.run(pipeline.generate(
        "질문", "", [], persona="emotional_companion", thinking_mode=True,
    ))
    assert len(answer) == 200


@pytest.mark.parametrize(
    ("persona", "thinking_mode"),
    [
        ("default", False),
        ("default", True),
        ("emotional_companion", False),
        ("emotional_companion", True),
        ("none", False),
        ("none", True),
    ],
)
def test_text_only_mode_removes_200_character_rule_and_keeps_full_answer(
    persona, thinking_mode,
):
    pipeline = ModelPipeline(load_settings())
    captured = {}

    async def completion(messages, temperature, model=None, **_kwargs):
        captured["messages"] = messages
        return "가" * 250

    pipeline._completion = completion
    answer = asyncio.run(pipeline.generate(
        "자세히 설명해줘", "", [], persona=persona,
        thinking_mode=thinking_mode, max_answer_chars=None,
    ))

    assert len(answer) == 250
    assert all("200자" not in message["content"] for message in captured["messages"])


def test_text_only_fallback_answer_is_not_truncated():
    pipeline = ModelPipeline(load_settings())
    responses = iter(["", "나" * 250])

    async def completion(_messages, temperature, model=None, **_kwargs):
        return next(responses)

    pipeline._completion = completion
    answer = asyncio.run(pipeline.generate(
        "자세히 설명해줘", "", [], max_answer_chars=None,
    ))

    assert len(answer) == 250


def test_generate_includes_document_context_and_omits_empty_memory():
    pipeline = ModelPipeline(load_settings()); captured = {}
    async def completion(messages, temperature, model=None, **_kwargs):
        captured["system"] = messages[0]["content"]; return "답변"
    pipeline._completion = completion
    asyncio.run(pipeline.generate("일정", "", [], document_context="[첨부파일: plan.md]\n8월 20일"))
    assert "plan.md" in captured["system"]
    assert "관련 장기 기억" not in captured["system"]


def test_generate_keeps_web_context_ephemeral_and_requests_a_source():
    pipeline = ModelPipeline(load_settings()); captured = {}
    async def completion(messages, temperature, model=None, **_kwargs):
        captured["system"] = messages[0]["content"]; return "검색 답변"
    pipeline._completion = completion
    asyncio.run(pipeline.generate(
        "오늘 소식", "", [], web_context="[1] 공식 발표\nURL: https://example.com/news",
    ))
    assert "이번 답변용 웹 검색 결과" in captured["system"]
    assert "장기 기억이 아니다" in captured["system"]
    assert "사이트명과 URL" in captured["system"]


def test_generate_marks_session_context_as_temporary_and_resolves_short_replies():
    pipeline = ModelPipeline(load_settings()); captured = {}
    async def completion(messages, temperature, model=None, **_kwargs):
        captured["system"] = messages[0]["content"]; return "응, 이어서 말할게"
    pipeline._completion = completion
    asyncio.run(pipeline.generate(
        "어", "", [], session_context="MemoryPal: 조리법을 알려줄까?",
    ))
    assert "현재 세션의 임시 작업 기억" in captured["system"]
    assert "현재 세션에서만" in captured["system"]
    assert "'응', '그래'" in captured["system"]


def test_generate_does_not_duplicate_history_as_session_context():
    pipeline = ModelPipeline(load_settings()); captured = {}
    history = [{"user_text": "앞 질문", "assistant_text": "앞 답변"}]
    async def completion(messages, temperature, model=None, **_kwargs):
        captured["messages"] = messages; return "이어진 답변"
    pipeline._completion = completion
    asyncio.run(pipeline.generate(
        "그거 해줘", "", history,
        session_context="사용자: 앞 질문\nMemoryPal: 앞 답변",
    ))
    assert "현재 세션의 임시 작업 기억" not in captured["messages"][0]["content"]
    assert [item["content"] for item in captured["messages"][1:3]] == ["앞 질문", "앞 답변"]


def test_generate_applies_global_context_budget_and_keeps_newest_turn():
    pipeline = ModelPipeline(load_settings()); captured = {}
    history = [
        {"user_text": f"질문-{index}-" + "가" * 3500,
         "assistant_text": f"답변-{index}-" + "나" * 3500}
        for index in range(10)
    ]
    async def completion(messages, temperature, model=None, **_kwargs):
        captured["messages"] = messages; return "답변"
    pipeline._completion = completion
    asyncio.run(pipeline.generate(
        "다" * 8000,
        "기억" * 3000,
        history,
        document_context="문서" * 3000,
        web_context="검색" * 3000,
        session_context="중복 세션" * 3000,
    ))
    contents = [item["content"] for item in captured["messages"]]
    assert len(contents[-1]) <= pipeline._MAX_USER_CHARS
    assert sum(len(content) for content in contents) <= 8500
    assert any("질문-9-" in content for content in contents)
    assert all("질문-0-" not in content for content in contents)
    assert "중복 세션" not in contents[0]


def test_primary_failure_retries_compact_prompt_with_same_model():
    pipeline = ModelPipeline(load_settings()); calls = []
    async def completion(messages, temperature, model=None, **_kwargs):
        calls.append((messages, model))
        if len(calls) == 1:
            raise PipelineUnavailable("context overflow")
        return "압축 재시도 성공"
    pipeline._completion = completion
    answer = asyncio.run(pipeline.generate(
        "질문", "장기 기억" * 1000,
        [{"user_text": "이전 질문", "assistant_text": "이전 답변"}],
        persona="default", document_context="문서" * 1000,
    ))
    assert answer == "압축 재시도 성공"
    assert [model for _, model in calls] == ["qwen/qwen3.5-9b", "qwen/qwen3.5-9b"]
    assert len(calls[1][0]) < len(calls[0][0]) + 2


def test_explicit_session_memory_extraction_uses_prior_context():
    pipeline = ModelPipeline(load_settings()); captured = {}
    async def completion(messages, temperature, model=None, **_kwargs):
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
    pipeline = ModelPipeline(replace(
        load_settings(), archive_service_token=ARCHIVE_SERVICE_TOKEN,
        model_service_token=MODEL_SERVICE_TOKEN,
    ))
    class Response:
        def __init__(self, payload=None, *, content=b"", headers=None):
            self.payload = payload
            self.content = content
            self.headers = headers or {}
        def raise_for_status(self): return None
        def json(self): return self.payload
    class Client:
        count = 0
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def get(self, _url, headers):
            assert headers["Authorization"] == f"Bearer {ARCHIVE_SERVICE_TOKEN}"
            if _url.endswith("/audio"):
                return Response(
                    content=b"RIFF-reference",
                    headers={
                        "content-type": "audio/wav",
                        "content-disposition": 'attachment; filename="ref.wav"',
                    },
                )
            return Response({"audio_path": "ref.wav", "reference_text": "안녕"})
        async def post(self, _url, headers, data, files):
            assert headers == {"Authorization": f"Bearer {MODEL_SERVICE_TOKEN}"}
            assert _url.endswith("/synthesize-upload")
            assert data["ref_text"] == "안녕"
            assert files["ref_audio"][0] == "ref.wav"
            assert files["ref_audio"][1] == b"RIFF-reference"
            self.count += 1
            if self.count == 1: raise httpx.ConnectError("temporary")
            return Response({"audio_path": "http://127.0.0.1:8003/outputs/retry.wav"})
    client = Client()
    monkeypatch.setattr("memorypal_api.services.pipeline.httpx.AsyncClient", lambda **_kwargs: client)
    assert asyncio.run(pipeline.synthesize("답변", None))


def test_transcribe_uses_model_service_bearer(monkeypatch):
    pipeline = ModelPipeline(replace(
        load_settings(), model_service_token=MODEL_SERVICE_TOKEN,
    ))
    captured = {}

    class Response:
        def raise_for_status(self): return None
        def json(self): return {"text": "인식 결과"}

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def post(self, url, headers, files):
            captured.update({"url": url, "headers": headers, "files": files})
            return Response()

    monkeypatch.setattr(
        "memorypal_api.services.pipeline.httpx.AsyncClient",
        lambda **_kwargs: Client(),
    )
    result = asyncio.run(pipeline.transcribe(b"audio", "sample.wav", "audio/wav"))

    assert result == "인식 결과"
    assert captured["headers"] == {
        "Authorization": f"Bearer {MODEL_SERVICE_TOKEN}",
    }
    assert captured["files"]["audio"] == ("sample.wav", b"audio", "audio/wav")


def test_model_calls_fail_closed_without_service_token():
    pipeline = ModelPipeline(replace(load_settings(), model_service_token="short"))
    with pytest.raises(PipelineUnavailable):
        asyncio.run(pipeline.transcribe(b"audio", "sample.wav", "audio/wav"))
    with pytest.raises(PipelineUnavailable):
        pipeline._model_service_headers()


def test_archive_registration_uses_internal_auth_owner_and_token(monkeypatch):
    pipeline = ModelPipeline(replace(
        load_settings(), archive_service_token=ARCHIVE_SERVICE_TOKEN,
    ))
    captured = []

    class Response:
        def __init__(self, payload=None):
            self.payload = payload or {}
        def raise_for_status(self): return None
        def json(self): return self.payload

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def post(self, url, **kwargs):
            captured.append(("POST", url, kwargs))
            if url.endswith("/internal/voices"):
                return Response({
                    "id": "voice-1", "voice_name": "내 음성",
                    "audio_path": "private.wav", "reference_text": "안녕하세요",
                    "description": None,
                })
            return Response()
        async def delete(self, url, **kwargs):
            captured.append(("DELETE", url, kwargs))
            return Response()

    monkeypatch.setattr(
        "memorypal_api.services.pipeline.httpx.AsyncClient",
        lambda **_kwargs: Client(),
    )
    owner_ref = pipeline.archive_owner_ref("user-1")
    registration_token = "registration-" + "r" * 48
    voice = asyncio.run(pipeline.register_voice(
        b"audio", "sample.wav", "audio/wav", "내 음성", "안녕하세요", None,
        owner_ref=owner_ref, registration_token=registration_token,
    ))
    asyncio.run(pipeline.confirm_voice_registration(
        voice["id"], owner_ref=owner_ref, registration_token=registration_token,
    ))
    asyncio.run(pipeline.delete_voice_registration(
        voice["id"], owner_ref=owner_ref, registration_token=registration_token,
    ))

    expected_headers = {
        "Authorization": f"Bearer {ARCHIVE_SERVICE_TOKEN}",
        "X-MemoryPal-Owner-Ref": owner_ref,
        "X-MemoryPal-Registration-Token": registration_token,
    }
    assert [method for method, _url, _kwargs in captured] == ["POST", "POST", "DELETE"]
    assert all(kwargs["headers"] == expected_headers for _method, _url, kwargs in captured)
    assert captured[0][1].endswith("/internal/voices")
    assert captured[1][1].endswith("/internal/voices/voice-1/confirm")
    assert captured[2][1].endswith("/internal/voices/voice-1")


def test_archive_internal_calls_fail_closed_without_service_token():
    pipeline = ModelPipeline(replace(load_settings(), archive_service_token=""))
    with pytest.raises(PipelineUnavailable):
        pipeline.archive_owner_ref("user-1")
    with pytest.raises(PipelineUnavailable):
        asyncio.run(pipeline.register_voice(
            b"audio", "sample.wav", "audio/wav", "내 음성", "안녕하세요", None,
            owner_ref="0" * 64, registration_token="r" * 64,
        ))
