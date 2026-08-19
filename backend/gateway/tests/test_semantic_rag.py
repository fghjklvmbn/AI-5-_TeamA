import asyncio
import math
from types import SimpleNamespace

from memorypal_api.database import Database
from memorypal_api.services.document_engine import DocumentEngine
from memorypal_api.services.semantic_rag import SemanticRagEngine


def normalized(*values):
    magnitude = math.sqrt(sum(value * value for value in values))
    return [value / magnitude for value in values]


class FakePipeline:
    def __init__(self):
        self.settings = SimpleNamespace(llm_embedding_model="semantic-test")
        self.calls = []

    async def embed_texts(self, texts):
        self.calls.append(list(texts))
        vectors = []
        for text in texts:
            if any(word in text for word in ("고양이", "반려묘", "동물")):
                vectors.append(normalized(1.0, 0.0, 0.0))
            elif any(word in text for word in ("배포", "출시")):
                vectors.append(normalized(0.0, 1.0, 0.0))
            else:
                vectors.append(normalized(0.0, 0.0, 1.0))
        return vectors


def test_sqlite_semantic_rag_indexes_and_reuses_memory_and_document_vectors(tmp_path):
    db = Database(tmp_path / "semantic.db")
    db.initialize()
    user = db.create_user("semantic@example.com", "Semantic", "hash", "salt")
    session = db.create_session(user["id"])
    memory = db.upsert_memory(
        user_id=user["id"], session_id=session["id"], memory_type="preference",
        content="나는 고양이를 좋아한다", normalized_content="나는 고양이를 좋아한다",
        keywords="고양이 좋아한다", confidence=0.9, importance=0.8,
    )
    db.create_attachment(
        user["id"], session["id"], "plan.txt", "text/plain", 30,
        "서비스 출시 일정은 금요일이다.",
    )
    pipeline = FakePipeline()
    engine = SemanticRagEngine(db, pipeline, DocumentEngine(db))

    first = asyncio.run(engine.retrieve(
        user_id=user["id"], session_id=session["id"], query="반려묘 취향",
    ))
    assert [row["id"] for row in first.memories] == [memory["id"]]
    assert "plan.txt" not in first.document_context
    assert len(pipeline.calls) == 3  # memory index, document index, query

    second = asyncio.run(engine.retrieve(
        user_id=user["id"], session_id=session["id"], query="동물 취향",
    ))
    assert [row["id"] for row in second.memories] == [memory["id"]]
    assert len(pipeline.calls) == 4  # only the new query was embedded

    document = asyncio.run(engine.retrieve(
        user_id=user["id"], session_id=session["id"], query="배포 출시 일정",
    ))
    assert "plan.txt" in document.document_context
    assert "금요일" in document.document_context


def test_sqlite_vector_search_orders_by_cosine_similarity(tmp_path):
    db = Database(tmp_path / "vectors.db")
    db.initialize()
    user = db.create_user("vectors@example.com", "Vectors", "hash", "salt")
    db.upsert_rag_embedding(
        user_id=user["id"], namespace="n", source_id="near", content="near",
        vector=[1.0, 0.0], embedding_model="m",
    )
    db.upsert_rag_embedding(
        user_id=user["id"], namespace="n", source_id="far", content="far",
        vector=[0.0, 1.0], embedding_model="m",
    )
    results = db.search_rag_embeddings(
        user_id=user["id"], namespace="n", vector=[0.9, 0.1],
        embedding_model="m", limit=2,
    )
    assert [row["source_id"] for row in results] == ["near", "far"]
