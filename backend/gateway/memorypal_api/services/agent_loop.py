from __future__ import annotations

import logging
from dataclasses import dataclass

from .pipeline import ModelPipeline, PipelineUnavailable


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentContext:
    memories: list
    document_context: str
    web_context: str
    steps_used: int


class AgentLoop:
    """Bounded, read-only tool loop used before the final streamed answer."""

    def __init__(self, pipeline: ModelPipeline, max_steps: int = 2):
        self.pipeline = pipeline
        self.max_steps = max(1, min(3, max_steps))

    async def gather_context(
        self,
        *,
        user_id: str,
        session_id: str,
        user_text: str,
        history: list,
        persona: str,
        internet_enabled: bool,
        memory_engine,
        document_engine,
        web_search_engine,
    ) -> AgentContext:
        # Preserve the existing eager retrieval path. The loop may refine it,
        # but a planner outage must never remove memory, documents, or web context.
        memories = list(memory_engine.retrieve(user_id, user_text))
        document_context = document_engine.retrieve_context(user_id, session_id, user_text)
        web_context = (
            await web_search_engine.retrieve_context(user_text, history)
            if internet_enabled else ""
        )
        observations: list[str] = []
        attempted: set[tuple[str, str]] = set()
        allowed_tools = ["memory_search", "document_search"]

        if not memories and not document_context and not web_context:
            return AgentContext(
                memories=[], document_context="", web_context="", steps_used=0,
            )

        steps_used = 0
        for _ in range(self.max_steps):
            evidence = "\n\n".join(filter(None, (
                memory_engine.as_prompt(memories),
                document_context,
                web_context,
                "\n".join(observations),
            )))
            try:
                action, query = await self.pipeline.plan_agent_step(
                    user_text=user_text,
                    evidence=evidence,
                    history=history,
                    allowed_tools=allowed_tools,
                    attempted=[f"{tool}:{value}" for tool, value in sorted(attempted)],
                    persona=persona,
                )
            except PipelineUnavailable:
                logger.warning("Agent planner unavailable; continuing with eagerly retrieved context")
                break

            if action == "answer":
                break
            normalized_query = " ".join(query.split()).casefold()[:300]
            key = (action, normalized_query)
            if not normalized_query or action not in allowed_tools or key in attempted:
                break
            attempted.add(key)
            steps_used += 1

            try:
                if action == "memory_search":
                    additional = memory_engine.retrieve(user_id, query)
                    known_ids = {str(item["id"]) for item in memories}
                    for item in additional:
                        if str(item["id"]) not in known_ids:
                            memories.append(item)
                            known_ids.add(str(item["id"]))
                    observations.append(f"장기기억 추가 검색어: {query}")
                elif action == "document_search":
                    additional = document_engine.retrieve_context(user_id, session_id, query)
                    if additional and additional not in document_context:
                        document_context = "\n\n".join(filter(None, (
                            document_context,
                            f"[Agent 문서 추가 검색: {query}]\n{additional}",
                        )))
                    observations.append(f"문서 추가 검색어: {query}")
            except Exception as exc:
                # A read-only tool is optional evidence. Keep the contexts already
                # collected and let the final model state uncertainty naturally.
                logger.warning("Agent tool failed: action=%s error=%r", action, exc)
                observations.append(f"{action} 도구를 완료하지 못함")

        return AgentContext(
            memories=memories,
            document_context=document_context,
            web_context=web_context,
            steps_used=steps_used,
        )
