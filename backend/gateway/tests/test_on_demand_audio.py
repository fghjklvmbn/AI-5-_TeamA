import json
import asyncio
import time
from dataclasses import replace

from fastapi.testclient import TestClient

from memorypal_api.app import create_app
from memorypal_api.config import load_settings
from memorypal_api.services.agent_loop import AgentContext
from memorypal_api.services.memory_engine import MemoryCandidate
from memorypal_api.services.pipeline import PipelineUnavailable


def register(client: TestClient, email: str) -> tuple[str, str]:
    response = client.post("/v1/auth/register", json={
        "email": email,
        "password": "password123",
        "display_name": "테스트",
    })
    assert response.status_code == 201
    body = response.json()
    return body["user"]["id"], body["access_token"]


def wait_for_memory_postprocessing(app) -> None:
    for _ in range(100):
        if not app.state.chat_postprocess_tasks:
            return
        time.sleep(0.01)
    raise AssertionError("chat memory postprocessing did not finish")


def test_chat_keeps_first_evidence_in_session_memory_and_promotes_after_cross_session_repeat(tmp_path):
    settings = replace(
        load_settings(), database_path=tmp_path / "memorypal.db", root_path="",
    )
    app = create_app(settings)

    async def generate(*_args, **_kwargs) -> str:
        return "재즈 취향에 맞춰 이야기할게요."

    async def extract_memories(*_args, **_kwargs) -> list[MemoryCandidate]:
        return [MemoryCandidate(
            "preference", "사용자는 재즈를 선호해", 0.94, 0.84,
        )]

    app.state.pipeline.generate = generate
    app.state.pipeline.extract_memories = extract_memories
    with TestClient(app) as client:
        user_id, token = register(client, "memory-boundary@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        first = client.post(
            "/v1/chat/messages",
            json={"text": "나는 재즈를 선호하는 편이야", "speak": False},
            headers=headers,
        )
        assert first.status_code == 200
        wait_for_memory_postprocessing(app)
        first_session_id = first.json()["session"]["id"]
        assert "재즈를 선호하는 편이야" in app.state.db.get_session_working_memory(
            user_id, first_session_id,
        )
        assert app.state.db.list_memories(user_id) == []

        second = client.post(
            "/v1/chat/messages",
            json={"text": "나는 재즈를 선호하는 편이야", "speak": False},
            headers=headers,
        )
        assert second.status_code == 200
        assert second.json()["session"]["id"] != first_session_id
        wait_for_memory_postprocessing(app)

        long_term = app.state.db.list_memories(user_id)
        assert len(long_term) == 1
        assert long_term[0]["memory_type"] == "preference"
        assert "재즈" in long_term[0]["content"]


def test_on_demand_audio_is_generated_once_and_scoped_to_owner(tmp_path):
    settings = replace(
        load_settings(), database_path=tmp_path / "memorypal.db", root_path="",
    )
    app = create_app(settings)
    calls: list[tuple[str, str | None, str]] = []

    async def synthesize(text: str, voice_id: str | None, voice_style: str) -> str:
        calls.append((text, voice_id, voice_style))
        return "https://example.com/tts/outputs/message.wav"

    app.state.pipeline.synthesize = synthesize
    with TestClient(app) as client:
        owner_id, owner_token = register(client, "owner-audio@example.com")
        _other_id, other_token = register(client, "other-audio@example.com")
        session = app.state.db.create_session(owner_id)
        message = app.state.db.save_conversation(
            owner_id, session["id"], "질문", "음성으로 만들 답변",
        )
        path = f"/v1/chat/messages/{message['id']}/audio"
        owner_headers = {"Authorization": f"Bearer {owner_token}"}
        response = client.post(path, json={}, headers=owner_headers)
        assert response.status_code == 200
        assert response.json()["audio_url"].endswith("message.wav")
        assert calls == [("음성으로 만들 답변", None, "calm")]

        cached = client.post(path, json={}, headers=owner_headers)
        assert cached.status_code == 200
        assert calls == [("음성으로 만들 답변", None, "calm")]

        forbidden = client.post(
            path, json={}, headers={"Authorization": f"Bearer {other_token}"},
        )
        assert forbidden.status_code == 404


def test_on_demand_audio_rejects_unfinished_answer(tmp_path):
    settings = replace(
        load_settings(), database_path=tmp_path / "memorypal.db", root_path="",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        owner_id, token = register(client, "pending-audio@example.com")
        session = app.state.db.create_session(owner_id)
        message = app.state.db.save_conversation(owner_id, session["id"], "질문", "")
        response = client.post(
            f"/v1/chat/messages/{message['id']}/audio",
            json={}, headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 409


def test_on_demand_audio_excludes_display_only_web_sources(tmp_path):
    settings = replace(
        load_settings(), database_path=tmp_path / "memorypal.db", root_path="",
    )
    app = create_app(settings)
    calls: list[str] = []

    async def synthesize(text: str, _voice_id: str | None, _voice_style: str) -> str:
        calls.append(text)
        return "https://example.com/tts/outputs/answer-only.wav"

    app.state.pipeline.synthesize = synthesize
    with TestClient(app) as client:
        owner_id, token = register(client, "source-audio@example.com")
        session = app.state.db.create_session(owner_id)
        full_answer = (
            "검색 결과를 바탕으로 정리한 답변입니다.\n\n"
            "### 검색 출처\n"
            "- [첫 번째 출처](https://example.com/one)\n"
            "- [두 번째 출처](https://example.com/two)"
        )
        message = app.state.db.save_conversation(
            owner_id, session["id"], "질문", full_answer,
        )
        response = client.post(
            f"/v1/chat/messages/{message['id']}/audio",
            json={}, headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert calls == ["검색 결과를 바탕으로 정리한 답변입니다."]
        assert response.json()["assistant_text"] == full_answer


def test_chat_stream_emits_deltas_then_persists_completed_message(tmp_path):
    settings = replace(
        load_settings(), database_path=tmp_path / "memorypal.db", root_path="",
    )
    app = create_app(settings)

    async def generate(*_args, **kwargs) -> str:
        await kwargs["on_delta"]("안녕")
        await kwargs["on_delta"]("하세요")
        return "안녕하세요"

    async def extract_memories(*_args, **_kwargs) -> list:
        return []

    app.state.pipeline.generate = generate
    app.state.pipeline.extract_memories = extract_memories
    with TestClient(app) as client:
        user_id, token = register(client, "stream-chat@example.com")
        response = client.post(
            "/v1/chat/messages/stream",
            json={"text": "인사해 줘", "speak": False},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        events = [json.loads(line) for line in response.text.splitlines()]
        assert events[:2] == [
            {"type": "delta", "delta": "안녕"},
            {"type": "delta", "delta": "하세요"},
        ]
        assert events[-1]["type"] == "complete"
        completed = events[-1]["response"]
        assert completed["message"]["assistant_text"] == "안녕하세요"
        assert completed["message"]["character_cue"]["voice_style"] == "calm"
        stored = app.state.db.get_conversation(user_id, completed["message"]["id"])
        assert json.loads(stored["character_cue_json"])["voice_style"] == "calm"
        history = client.get(
            f'/v1/sessions/{completed["session"]["id"]}/messages',
            headers={"Authorization": f"Bearer {token}"},
        )
        assert history.json()[-1]["assistant_text"] == "안녕하세요"
        assert history.json()[-1]["character_cue"] == completed["message"]["character_cue"]


def test_chat_stream_does_not_wait_for_memory_extraction(tmp_path):
    settings = replace(
        load_settings(), database_path=tmp_path / "memorypal.db", root_path="",
    )
    app = create_app(settings)

    async def generate(*_args, **kwargs) -> str:
        await kwargs["on_delta"]("완료")
        return "완료"

    extraction_release = asyncio.Event()

    async def extract_memories(*_args, **_kwargs) -> list:
        await extraction_release.wait()
        return []

    app.state.pipeline.generate = generate
    app.state.pipeline.extract_memories = extract_memories
    with TestClient(app) as client:
        _user_id, token = register(client, "nonblocking-memory@example.com")
        response = client.post(
            "/v1/chat/messages/stream",
            json={"text": "답해 줘", "speak": False},
            headers={"Authorization": f"Bearer {token}"},
        )

        events = [json.loads(line) for line in response.text.splitlines()]
        assert response.status_code == 200
        assert events[-1]["type"] == "complete"
        assert events[-1]["response"]["message"]["assistant_text"] == "완료"
        assert app.state.chat_postprocess_tasks


def test_chat_consumes_only_the_attachments_used_by_a_successful_request(tmp_path):
    settings = replace(
        load_settings(), database_path=tmp_path / "memorypal.db", root_path="",
    )
    app = create_app(settings)

    async def gather_context(**kwargs) -> AgentContext:
        rows = app.state.db.list_attachments(kwargs["user_id"], kwargs["session_id"])
        assert [row["filename"] for row in rows] == ["one-time.txt"]
        return AgentContext(
            memories=[], document_context="일회용 문서 근거", web_context="",
            web_sources=[], steps_used=0,
        )

    async def generate(*_args, **_kwargs) -> str:
        return "문서를 반영한 답변"

    async def extract_memories(*_args, **_kwargs) -> list:
        return []

    app.state.agent_loop.gather_context = gather_context
    app.state.pipeline.generate = generate
    app.state.pipeline.extract_memories = extract_memories
    with TestClient(app) as client:
        user_id, token = register(client, "one-time-attachment@example.com")
        session = app.state.db.create_session(user_id)
        attachment = app.state.db.create_attachment(
            user_id, session["id"], "one-time.txt", "text/plain", 12, "문서 내용",
            file_content="문서 내용".encode("utf-8"),
        )

        response = client.post(
            "/v1/chat/messages",
            json={"text": "이 내용을 요약해줘", "session_id": session["id"], "speak": False},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["message"]["attachments"] == [{
            "id": attachment["id"], "session_id": session["id"],
            "filename": "one-time.txt", "content_type": "text/plain",
            "size_bytes": 12, "created_at": attachment["created_at"],
        }]
        history = client.get(
            f"/v1/sessions/{session['id']}/messages",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert history.json()[0]["attachments"][0]["filename"] == "one-time.txt"
        content = client.get(
            f"/v1/attachments/{attachment['id']}/content",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert content.status_code == 200
        assert content.content == "문서 내용".encode("utf-8")
        assert app.state.db.get_attachment(user_id, attachment["id"])["consumed_at"] is not None
        assert app.state.db.list_attachments(user_id, session["id"]) == []
        assert len(app.state.db.list_all_attachments(user_id, session["id"])) == 1


def test_failed_chat_keeps_one_time_attachment_for_retry(tmp_path):
    settings = replace(
        load_settings(), database_path=tmp_path / "memorypal.db", root_path="",
    )
    app = create_app(settings)

    async def gather_context(**_kwargs) -> AgentContext:
        return AgentContext(
            memories=[], document_context="재시도할 문서", web_context="",
            web_sources=[], steps_used=0,
        )

    async def generate(*_args, **_kwargs) -> str:
        raise PipelineUnavailable("temporary failure")

    app.state.agent_loop.gather_context = gather_context
    app.state.pipeline.generate = generate
    with TestClient(app) as client:
        user_id, token = register(client, "retry-attachment@example.com")
        session = app.state.db.create_session(user_id)
        attachment = app.state.db.create_attachment(
            user_id, session["id"], "retry.txt", "text/plain", 12, "문서 내용",
        )

        response = client.post(
            "/v1/chat/messages",
            json={"text": "다시 시도할 질문", "session_id": session["id"], "speak": False},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 503
        assert app.state.db.get_attachment(user_id, attachment["id"]) is not None


def test_chat_voice_switch_controls_output_length_policy(tmp_path):
    settings = replace(
        load_settings(), database_path=tmp_path / "memorypal.db", root_path="",
    )
    app = create_app(settings)
    max_answer_chars_values: list[int | None] = []
    reasoning_effort_values: list[str] = []
    synthesis_calls: list[tuple[str, str]] = []

    async def generate(*_args, **kwargs) -> str:
        max_answer_chars_values.append(kwargs["max_answer_chars"])
        reasoning_effort_values.append(kwargs["reasoning_effort"])
        return "충분히 자세한 답변"

    async def synthesize(text: str, _voice_id: str | None, voice_style: str) -> str:
        synthesis_calls.append((text, voice_style))
        return "https://example.com/tts/outputs/automatic.wav"

    async def generate_character_cue(*_args, **_kwargs) -> dict:
        return {
            "emotion": "happy", "intensity": 0.8,
            "gesture": "nod", "voice_style": "bright",
        }

    async def extract_memories(*_args, **_kwargs) -> list:
        return []

    app.state.pipeline.generate = generate
    app.state.pipeline.synthesize = synthesize
    app.state.pipeline.generate_character_cue = generate_character_cue
    app.state.pipeline.extract_memories = extract_memories
    with TestClient(app) as client:
        _user_id, token = register(client, "chat-output-mode@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        text_only = client.post(
            "/v1/chat/messages",
            json={
                "text": "자세히 알려줘", "speak": False,
                "thinking_mode": True, "reasoning_effort": "high",
            },
            headers=headers,
        )
        automatic_voice = client.post(
            "/v1/chat/messages",
            json={
                "text": "짧게 알려줘", "speak": True,
                "thinking_mode": True, "reasoning_effort": "low",
            },
            headers=headers,
        )
        message_id = text_only.json()["message"]["id"]
        regenerated_text_only = client.post(
            f"/v1/chat/messages/{message_id}/regenerate",
            json={"speak": False, "thinking_mode": True, "reasoning_effort": "medium"},
            headers=headers,
        )
        regenerated_with_voice = client.post(
            f"/v1/chat/messages/{message_id}/regenerate",
            json={"speak": True, "thinking_mode": True, "reasoning_effort": "high"},
            headers=headers,
        )

        assert text_only.status_code == 200
        assert text_only.json()["message"]["audio_url"] is None
        assert automatic_voice.status_code == 200
        assert regenerated_text_only.status_code == 200
        assert regenerated_text_only.json()["message"]["audio_url"] is None
        assert regenerated_with_voice.status_code == 200
        assert max_answer_chars_values == [None, 200, None, 200]
        assert reasoning_effort_values == ["high", "low", "medium", "high"]
        assert synthesis_calls == [
            ("충분히 자세한 답변", "bright"),
            ("충분히 자세한 답변", "bright"),
        ]
