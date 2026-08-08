import asyncio

from memorypal_api.services.agent_loop import AgentLoop
from memorypal_api.services.pipeline import PipelineUnavailable


class MemoryEngine:
    def __init__(self):
        self.queries = []

    def retrieve(self, _user_id, query):
        self.queries.append(query)
        if query == "프로젝트 일정":
            return [{"id": "m1", "memory_type": "fact", "content": "프로젝트 이름은 MemoryPal"}]
        return [{"id": "m2", "memory_type": "schedule", "content": "배포일은 금요일"}]

    @staticmethod
    def as_prompt(memories):
        return "\n".join(item["content"] for item in memories)


class DocumentEngine:
    def __init__(self):
        self.queries = []

    def retrieve_context(self, _user_id, _session_id, query):
        self.queries.append(query)
        return "문서의 기본 근거" if query == "프로젝트 일정" else ""


class WebEngine:
    def __init__(self):
        self.queries = []

    async def retrieve_context(self, query, _history):
        self.queries.append(query)
        return "공개 웹 근거"


def test_agent_loop_refines_memory_with_bounded_read_only_steps():
    class Pipeline:
        def __init__(self):
            self.calls = []

        async def plan_agent_step(self, **kwargs):
            self.calls.append(kwargs)
            return ("memory_search", "배포 일정") if len(self.calls) == 1 else ("answer", "")

    pipeline = Pipeline()
    memory, document, web = MemoryEngine(), DocumentEngine(), WebEngine()
    result = asyncio.run(AgentLoop(pipeline, max_steps=2).gather_context(
        user_id="u1",
        session_id="s1",
        user_text="프로젝트 일정",
        history=[],
        persona="none",
        internet_enabled=False,
        memory_engine=memory,
        document_engine=document,
        web_search_engine=web,
    ))

    assert [item["id"] for item in result.memories] == ["m1", "m2"]
    assert result.steps_used == 1
    assert memory.queries == ["프로젝트 일정", "배포 일정"]
    assert len(pipeline.calls) == 2
    assert pipeline.calls[0]["allowed_tools"] == ["memory_search", "document_search"]
    assert web.queries == []


def test_agent_loop_preserves_eager_context_when_planner_is_unavailable():
    class Pipeline:
        async def plan_agent_step(self, **_kwargs):
            raise PipelineUnavailable("offline")

    result = asyncio.run(AgentLoop(Pipeline()).gather_context(
        user_id="u1",
        session_id="s1",
        user_text="프로젝트 일정",
        history=[],
        persona="default",
        internet_enabled=True,
        memory_engine=MemoryEngine(),
        document_engine=DocumentEngine(),
        web_search_engine=WebEngine(),
    ))

    assert result.memories[0]["id"] == "m1"
    assert result.document_context == "문서의 기본 근거"
    assert result.web_context == "공개 웹 근거"
    assert result.steps_used == 0


def test_agent_loop_skips_planner_without_any_retrieved_evidence():
    class EmptyMemory(MemoryEngine):
        def retrieve(self, _user_id, query):
            self.queries.append(query)
            return []

    class EmptyDocument(DocumentEngine):
        def retrieve_context(self, _user_id, _session_id, query):
            self.queries.append(query)
            return ""

    class Pipeline:
        async def plan_agent_step(self, **_kwargs):
            raise AssertionError("planner should not be called")

    result = asyncio.run(AgentLoop(Pipeline()).gather_context(
        user_id="u1",
        session_id="s1",
        user_text="안녕",
        history=[],
        persona="default",
        internet_enabled=False,
        memory_engine=EmptyMemory(),
        document_engine=EmptyDocument(),
        web_search_engine=WebEngine(),
    ))
    assert result.steps_used == 0
    assert result.memories == []
