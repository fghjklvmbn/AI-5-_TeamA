from dataclasses import replace

from fastapi.testclient import TestClient

from memorypal_api.app import create_app
from memorypal_api.config import load_settings


def register(client: TestClient) -> str:
    response = client.post("/v1/auth/register", json={
        "email": "mcp-tools@example.com",
        "password": "password123",
        "display_name": "MCP 테스트",
    })
    assert response.status_code == 201
    return response.json()["access_token"]


def test_authenticated_mcp_lists_and_calls_shared_web_tool(tmp_path):
    settings = replace(
        load_settings(), database_path=tmp_path / "memorypal.db", root_path="",
    )
    app = create_app(settings)
    app.state.web_search_engine._search = lambda query, max_results: [{
        "title": "공식 검색 결과",
        "href": "https://example.com/current",
        "body": f"{query} 최신 근거 {max_results}",
    }]

    with TestClient(app) as client:
        token = register(client)
        headers = {"Authorization": f"Bearer {token}"}
        initialized = client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {},
        })
        assert initialized.status_code == 200
        assert initialized.json()["result"]["serverInfo"]["name"] == "memorypal-tools"

        listed = client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
        })
        assert {tool["name"] for tool in listed.json()["result"]["tools"]} == {
            "web_search", "memory_search", "document_search",
        }

        called = client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "web_search", "arguments": {"query": "Motif 3"}},
        })
        result = called.json()["result"]
        assert result["isError"] is False
        assert "공식 검색 결과" in result["content"][0]["text"]
        assert result["structuredContent"]["sources"][0]["url"] == "https://example.com/current"


def test_mcp_requires_memorypal_authentication(tmp_path):
    settings = replace(
        load_settings(), database_path=tmp_path / "memorypal.db", root_path="",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {},
        })
        assert response.status_code == 401
