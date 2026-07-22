import asyncio
import json
import time
from dataclasses import replace

from fastapi.testclient import TestClient

from memorypal_api.app import create_app
from memorypal_api.config import load_settings
from memorypal_api.database import Database
from memorypal_api.services.pipeline import ModelPipeline, PipelineUnavailable
from memorypal_api.services.portrait_engine import PortraitEngine


def register(client: TestClient, email: str) -> tuple[str, str]:
    response = client.post("/v1/auth/register", json={
        "email": email,
        "password": "password123",
        "display_name": "테스트",
    })
    assert response.status_code == 201
    body = response.json()
    return body["user"]["id"], body["access_token"]


def wait_for_portrait(client: TestClient, headers: dict[str, str]) -> dict:
    for _ in range(100):
        body = client.get("/v1/portrait", headers=headers).json()
        if body["status"] in {"complete", "failed"}:
            return body
        time.sleep(0.01)
    raise AssertionError("portrait job did not finish")


def test_relevance_weight_excludes_knowledge_and_keeps_personal_evidence():
    assert PortraitEngine.relevance_weight("파이썬 리스트가 뭐야?") == 0
    assert PortraitEngine.relevance_weight("대한민국의 수도를 알려줘") == 0
    assert PortraitEngine.relevance_weight("오늘 회사에서 너무 지치고 속상했어") >= 0.9
    assert PortraitEngine.relevance_weight("나는 조용히 산책하는 걸 좋아해") >= 0.75


def test_portrait_api_runs_once_persists_weighted_features_and_isolates_users(tmp_path):
    settings = replace(load_settings(), database_path=tmp_path / "memorypal.db", root_path="")
    app = create_app(settings)
    summarize_calls: list[str] = []
    compose_personas: list[str] = []

    async def summarize_portrait_session(_title: str, transcript: str) -> str:
        summarize_calls.append(transcript)
        return "사용자는 일상의 감정을 솔직하게 말하며 관계에서 온기를 중요하게 여깁니다."

    async def compose_portrait(_evidence: str, persona: str) -> str:
        compose_personas.append(persona)
        # Keep the job active long enough for the duplicate HTTP request even
        # when transaction-observability middleware persists its first event.
        await asyncio.sleep(0.2)
        return json.dumps({
            "title": "온기",
            "summary": "일상에서 느낀 감정을 솔직히 나누고 가까운 관계의 온기를 소중히 여기는 모습이 보여요.",
        }, ensure_ascii=False)

    async def embed_texts(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    app.state.pipeline.summarize_portrait_session = summarize_portrait_session
    app.state.pipeline.compose_portrait = compose_portrait
    app.state.pipeline.embed_texts = embed_texts

    with TestClient(app) as client:
        owner_id, owner_token = register(client, "portrait-owner@example.com")
        _other_id, other_token = register(client, "portrait-other@example.com")
        mixed = app.state.db.create_session(owner_id, "오늘 이야기")
        app.state.db.save_conversation(
            owner_id, mixed["id"], "오늘 회사에서 너무 지쳤고 친구가 위로해 줘서 고마웠어", "많이 힘드셨겠어요.",
        )
        app.state.db.save_conversation(
            owner_id, mixed["id"], "파이썬 리스트가 뭐야?", "순서가 있는 자료구조예요.",
        )
        knowledge = app.state.db.create_session(owner_id, "지식 질문")
        app.state.db.save_conversation(
            owner_id, knowledge["id"], "대한민국의 수도가 뭐야?", "서울입니다.",
        )

        owner_headers = {"Authorization": f"Bearer {owner_token}"}
        first = client.post(
            "/v1/portrait/generate",
            json={"persona": "emotional_companion"},
            headers=owner_headers,
        )
        duplicate = client.post(
            "/v1/portrait/generate",
            json={"persona": "default"},
            headers=owner_headers,
        )
        assert first.status_code == 202
        assert first.json()["status"] == "queued"
        assert duplicate.status_code == 202
        assert duplicate.json()["persona"] == "emotional_companion"

        complete = wait_for_portrait(client, owner_headers)
        assert complete["status"] == "complete"
        assert complete["title"] == "온기"
        assert len(complete["title"]) == 2
        assert len(complete["summary"]) <= 500
        assert complete["persona"] == "emotional_companion"
        assert complete["analyzed_sessions"] == 2
        assert complete["analyzed_messages"] == 3
        assert complete["progress_percent"] == 100
        assert 1 <= complete["accuracy_percent"] < 95
        assert complete["vector_method"].startswith("lm_studio:")
        assert complete["error"] is None
        assert compose_personas == ["emotional_companion"]
        assert len(summarize_calls) == 1
        assert "회사에서 너무 지쳤고" in summarize_calls[0]
        assert "파이썬 리스트" not in summarize_calls[0]

        features = app.state.db.list_portrait_session_features(
            owner_id, app.state.db.get_portrait(owner_id)["generation_id"],
        )
        assert len(features) == 2
        assert sorted(round(row["weight"], 2) for row in features) == [0.0, 0.5]
        assert all(row["vector_method"].startswith("lm_studio:") for row in features)
        assert all(len(json.loads(row["vector_json"])) == 3 for row in features)

        other = client.get(
            "/v1/portrait", headers={"Authorization": f"Bearer {other_token}"},
        )
        assert other.status_code == 200
        assert other.json()["status"] == "empty"
        assert other.json()["summary"] is None


def test_local_hash_embedding_fallback_is_deterministic(tmp_path):
    engine = PortraitEngine(None)  # type: ignore[arg-type]

    class OfflinePipeline:
        settings = replace(load_settings(), llm_embedding_model="offline-model")

        async def embed_texts(self, _texts):
            raise PipelineUnavailable("offline")

    first_vectors, first_method = asyncio.run(engine._vectors(
        OfflinePipeline(), ["따뜻한 대화", "차분한 산책"],
    ))
    second_vectors, second_method = asyncio.run(engine._vectors(
        OfflinePipeline(), ["따뜻한 대화", "차분한 산책"],
    ))
    assert first_method == second_method == "local_hash_char_ngram_v1"
    assert first_vectors == second_vectors
    assert len(first_vectors[0]) == PortraitEngine.LOCAL_VECTOR_DIMENSIONS
    assert any(value for value in first_vectors[0])


def test_lm_studio_embeddings_use_configured_model_and_clustering_prefix(monkeypatch):
    pipeline = ModelPipeline(load_settings())
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ],
            }

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, headers, json):
            captured.update({"url": url, "headers": headers, "payload": json})
            return Response()

    monkeypatch.setattr(
        "memorypal_api.services.pipeline.httpx.AsyncClient", lambda **_kwargs: Client(),
    )
    vectors = asyncio.run(pipeline.embed_texts(["첫 특징", "최종 자화상"]))
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert captured["url"].endswith("/embeddings")
    assert captured["payload"]["model"] == "text-embedding-nomic-embed-text-v1.5"
    assert captured["payload"]["input"] == [
        "clustering: 첫 특징", "clustering: 최종 자화상",
    ]


def test_portrait_database_lease_prevents_cross_worker_duplicate(tmp_path):
    db = Database(tmp_path / "lease.db")
    db.initialize()
    user = db.create_user("lease@example.com", "lease", "hash", "salt")
    portrait, started = db.begin_portrait_generation(user["id"], "default")
    assert started is True
    assert db.claim_portrait_generation(
        user["id"], portrait["generation_id"], "worker-one", lease_seconds=120,
    )
    assert not db.claim_portrait_generation(
        user["id"], portrait["generation_id"], "worker-two", lease_seconds=120,
    )
    db.execute(
        "UPDATE portraits SET lease_expires_at = '2000-01-01T00:00:00+00:00' WHERE user_id = ?",
        (user["id"],),
    )
    assert db.claim_portrait_generation(
        user["id"], portrait["generation_id"], "worker-two", lease_seconds=120,
    )


def test_portrait_feature_writes_are_fenced_by_current_worker_lease(tmp_path):
    db = Database(tmp_path / "feature-fence.db")
    db.initialize()
    user = db.create_user("fence@example.com", "fence", "hash", "salt")
    portrait, _started = db.begin_portrait_generation(user["id"], "default")
    generation_id = portrait["generation_id"]
    assert db.claim_portrait_generation(
        user["id"], generation_id, "worker-one", lease_seconds=120,
    )
    db.execute(
        "UPDATE portraits SET lease_expires_at = '2000-01-01T00:00:00+00:00' "
        "WHERE user_id = ?",
        (user["id"],),
    )
    assert db.claim_portrait_generation(
        user["id"], generation_id, "worker-two", lease_seconds=120,
    )

    assert not db.save_portrait_session_feature(
        user["id"], generation_id, "session-one", 2, 1, 0.5,
        "오래된 worker 요약", "worker-one",
    )
    assert db.save_portrait_session_feature(
        user["id"], generation_id, "session-one", 2, 1, 0.5,
        "현재 worker 요약", "worker-two",
    )
    assert not db.update_portrait_session_vector(
        user["id"], generation_id, "session-one", "[1.0,0.0]", "test",
        "worker-one",
    )
    assert db.update_portrait_session_vector(
        user["id"], generation_id, "session-one", "[1.0,0.0]", "test",
        "worker-two",
    )
    feature = db.list_portrait_session_features(user["id"], generation_id)[0]
    assert feature["summary"] == "현재 worker 요약"


def test_portrait_lease_can_be_requeued_for_clean_restart(tmp_path):
    db = Database(tmp_path / "restart.db")
    db.initialize()
    user = db.create_user("restart@example.com", "restart", "hash", "salt")
    portrait, _started = db.begin_portrait_generation(user["id"], "default")
    assert db.claim_portrait_generation(
        user["id"], portrait["generation_id"], "worker-one", lease_seconds=120,
    )

    assert db.release_portrait_lease(
        user["id"], portrait["generation_id"], "worker-one",
    )
    queued = db.get_portrait(user["id"])
    assert queued is not None
    assert queued["status"] == "queued"
    assert queued["worker_id"] is None
    assert queued["lease_expires_at"] is None
    assert db.claim_portrait_generation(
        user["id"], portrait["generation_id"], "worker-two", lease_seconds=120,
    )


def test_empty_history_completes_with_low_confidence_portrait(tmp_path):
    settings = replace(load_settings(), database_path=tmp_path / "empty.db", root_path="")
    app = create_app(settings)

    async def embed_texts(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    app.state.pipeline.embed_texts = embed_texts
    with TestClient(app) as client:
        _user_id, token = register(client, "empty-portrait@example.com")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post("/v1/portrait/generate", json={}, headers=headers)
        assert response.status_code == 202
        complete = wait_for_portrait(client, headers)
        assert complete["status"] == "complete"
        assert complete["title"] == "여백"
        assert complete["accuracy_percent"] == 0
        assert complete["analyzed_sessions"] == 0
        assert complete["analyzed_messages"] == 0
