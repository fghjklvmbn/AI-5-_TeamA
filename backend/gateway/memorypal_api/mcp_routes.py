from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from .dependencies import CurrentUser, get_current_user
from .services.tool_registry import ToolCallContext


router = APIRouter(prefix="/mcp", tags=["mcp"])


def rpc_result(request_id: Any, result: Any) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})


def rpc_error(request_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse({
        "jsonrpc": "2.0", "id": request_id,
        "error": {"code": code, "message": message},
    })


@router.post("")
async def mcp_rpc(
    payload: dict[str, Any], request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """Stateless MCP JSON-RPC endpoint backed by the gateway's shared tools."""
    request_id = payload.get("id")
    method = str(payload.get("method") or "")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}

    if method == "notifications/initialized":
        return Response(status_code=202)
    if method == "initialize":
        return rpc_result(request_id, {
            "protocolVersion": "2025-11-25",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "memorypal-tools", "version": "0.1.0"},
        })
    if method == "tools/list":
        return rpc_result(request_id, {
            "tools": request.app.state.tool_registry.definitions(),
        })
    if method != "tools/call":
        return rpc_error(request_id, -32601, "Method not found")

    name = str(params.get("name") or "")
    arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
    session_id = str(arguments.get("session_id") or "")
    try:
        result = await request.app.state.tool_registry.call(
            name,
            arguments,
            ToolCallContext(user_id=user.id, session_id=session_id, history=[]),
        )
    except (KeyError, ValueError) as exc:
        return rpc_result(request_id, {
            "content": [{"type": "text", "text": str(exc)}],
            "isError": True,
        })
    except Exception:
        return rpc_result(request_id, {
            "content": [{"type": "text", "text": "도구 실행에 실패했습니다."}],
            "isError": True,
        })

    sources = [
        {"title": source.title, "url": source.url, "snippet": source.snippet}
        for source in result.sources
    ]
    return rpc_result(request_id, {
        "content": [{"type": "text", "text": result.content}],
        "structuredContent": {"sources": sources},
        "isError": False,
    })
