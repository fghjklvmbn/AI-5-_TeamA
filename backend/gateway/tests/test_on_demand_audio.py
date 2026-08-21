import json
import asyncio
from dataclasses import replace

from fastapi.testclient import TestClient

from memorypal_api.app import create_app
from memorypal_api.config import load_settings


def register(client: TestClient, email: str) -> tuple[str, str]:
    response = client.post("/v1/auth/register", json={
        "email": email,
        "password": "password123",
        "display_name": "테스트",
    })
    assert response.status_code == 201
    body = response.json()
    return body["user"]["id"], body["access_token"]


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
