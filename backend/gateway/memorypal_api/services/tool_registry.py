from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .web_search import WebSource


@dataclass(frozen=True, slots=True)
class ToolCallContext:
    user_id: str
    session_id: str
    history: list = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ToolResult:
    content: str
    sources: list[WebSource] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class GatewayToolRegistry:
    """Shared tool registry used by MemoryPal orchestration and the MCP endpoint."""

    def __init__(self, memory_engine, document_engine, web_search_engine):
        self.memory_engine = memory_engine
        self.document_engine = document_engine
        self.web_search_engine = web_search_engine

    @staticmethod
    def definitions() -> list[dict[str, Any]]:
        query_schema = {
            "type": "object",
            "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 300}},
            "required": ["query"],
            "additionalProperties": False,
        }
        document_schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 300},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 100},
            },
            "required": ["query", "session_id"],
            "additionalProperties": False,
        }
        return [
            {
                "name": "web_search",
                "description": "Search the public web and return current sources. Results are ephemeral.",
                "inputSchema": query_schema,
            },
            {
                "name": "memory_search",
                "description": "Search the authenticated user's long-term MemoryPal memories.",
                "inputSchema": query_schema,
            },
            {
                "name": "document_search",
                "description": "Search attachments in the current MemoryPal chat session.",
                "inputSchema": document_schema,
            },
        ]

    async def call(
        self, name: str, arguments: dict[str, Any], context: ToolCallContext,
    ) -> ToolResult:
        query = " ".join(str(arguments.get("query") or "").split())[:300]
        if not query:
            raise ValueError("query is required")
        if name == "web_search":
            result = await self.web_search_engine.search(query, context.history)
            return ToolResult(
                content=result.context,
                sources=result.sources,
                metadata={"query": result.query, "error": result.error},
            )
        if name == "memory_search":
            memories = list(self.memory_engine.retrieve(context.user_id, query))
            return ToolResult(
                content=self.memory_engine.as_prompt(memories),
                metadata={"items": memories},
            )
        if name == "document_search":
            if not context.session_id:
                raise ValueError("session_id is required")
            content = self.document_engine.retrieve_context(
                context.user_id, context.session_id, query,
            )
            return ToolResult(content=content)
        raise KeyError(f"Unknown tool: {name}")
