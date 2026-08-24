from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SemanticContext:
    memories: list
    document_context: str


class SemanticRagEngine:
    """Lazy, persistent semantic index shared by SQLite and PostgreSQL."""

    MEMORY_NAMESPACE = "chat-memory-v1"
    DOCUMENT_NAMESPACE_PREFIX = "chat-document-v1:"
    MIN_SIMILARITY = 0.30

    def __init__(self, db, pipeline, document_engine):
        self.db = db
        self.pipeline = pipeline
        self.document_engine = document_engine

    @staticmethod
    def _metadata(row: Any) -> dict[str, Any]:
        try:
            value = json.loads(row["metadata_json"] or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    async def _ensure_index(
        self,
        *,
        user_id: str,
        namespace: str,
        sources: list[tuple[str, str, dict[str, Any]]],
    ) -> None:
        model = self.pipeline.settings.llm_embedding_model
        existing = {
            str(row["source_id"]): str(row["content"])
            for row in self.db.list_rag_embeddings(
                user_id=user_id, namespace=namespace, embedding_model=model,
            )
        }
        pending = [source for source in sources if existing.get(source[0]) != source[1]]
        if not pending:
            return
        for start in range(0, len(pending), 32):
            batch = pending[start:start + 32]
            vectors = await self.pipeline.embed_texts([content for _, content, _ in batch])
            for (source_id, content, metadata), vector in zip(batch, vectors):
                self.db.upsert_rag_embedding(
                    user_id=user_id,
                    namespace=namespace,
                    source_id=source_id,
                    content=content,
                    vector=vector,
                    embedding_model=model,
                    metadata=metadata,
                )

    async def retrieve(
        self, *, user_id: str, session_id: str, query: str,
    ) -> SemanticContext:
        if not query.strip():
            return SemanticContext([], "")
        memory_rows = list(self.db.list_memories(user_id, limit=500))
        memory_by_id = {str(row["id"]): row for row in memory_rows}
        memory_sources = [
            (
                str(row["id"]),
                str(row["content"]),
                {"memory_type": str(row["memory_type"])},
            )
            for row in memory_rows
        ]
        document_namespace = f"{self.DOCUMENT_NAMESPACE_PREFIX}{session_id}"
        document_sources: list[tuple[str, str, dict[str, Any]]] = []
        for attachment in self.document_engine.attachments_for_query(
            user_id, session_id, query,
        ):
            for index, chunk in enumerate(self.document_engine._chunks(attachment["text_content"])):
                document_sources.append((
                    f"{attachment['id']}:{index}",
                    chunk,
                    {"filename": str(attachment["filename"]), "attachment_id": str(attachment["id"])},
                ))
        try:
            await self._ensure_index(
                user_id=user_id, namespace=self.MEMORY_NAMESPACE, sources=memory_sources,
            )
            await self._ensure_index(
                user_id=user_id, namespace=document_namespace, sources=document_sources,
            )
            query_vector = (await self.pipeline.embed_texts([query]))[0]
        except Exception as exc:
            logger.warning("Semantic RAG unavailable; keeping lexical retrieval: %r", exc)
            return SemanticContext([], "")

        model = self.pipeline.settings.llm_embedding_model
        memory_matches = self.db.search_rag_embeddings(
            user_id=user_id,
            namespace=self.MEMORY_NAMESPACE,
            vector=query_vector,
            embedding_model=model,
            limit=6,
        )
        memories = [
            memory_by_id[str(match["source_id"])]
            for match in memory_matches
            if float(match["similarity"]) >= self.MIN_SIMILARITY
            and str(match["source_id"]) in memory_by_id
        ][:3]

        document_matches = self.db.search_rag_embeddings(
            user_id=user_id,
            namespace=document_namespace,
            vector=query_vector,
            embedding_model=model,
            limit=8,
        )
        current_document_ids = {source_id for source_id, _, _ in document_sources}
        blocks = []
        for match in document_matches:
            if float(match["similarity"]) < self.MIN_SIMILARITY:
                continue
            if str(match["source_id"]) not in current_document_ids:
                continue
            filename = self._metadata(match).get("filename") or "첨부 문서"
            blocks.append(f"[첨부파일: {filename}]\n{match['content']}")
            if len(blocks) == 4:
                break
        return SemanticContext(memories, "\n\n".join(blocks)[:4_000])
