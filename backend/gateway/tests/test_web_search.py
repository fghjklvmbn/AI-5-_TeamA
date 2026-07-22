import asyncio

from memorypal_api.services.web_search import WebSearchEngine


def test_web_search_builds_source_context_without_persistence():
    calls = []

    def search(query, max_results):
        calls.append((query, max_results))
        return [{
            "title": "MemoryPal 공식 소식",
            "href": "https://example.com/news",
            "body": "최신 발표 내용입니다.",
        }]

    engine = WebSearchEngine(max_results=3, search=search)
    context = asyncio.run(engine.retrieve_context("최신 소식", []))

    assert calls == [("최신 소식", 3)]
    assert "MemoryPal 공식 소식" in context
    assert "https://example.com/news" in context


def test_short_follow_up_includes_previous_user_topic():
    engine = WebSearchEngine(search=lambda *_args, **_kwargs: [])
    query = engine.contextual_query("언제야?", [{"user_text": "서울 벚꽃 개화 예상일 알려줘"}])
    assert query == "서울 벚꽃 개화 예상일 알려줘 언제야?"


def test_web_search_failure_does_not_raise_chat_error():
    def failing_search(*_args, **_kwargs):
        raise RuntimeError("network down")

    engine = WebSearchEngine(search=failing_search)
    context = asyncio.run(engine.retrieve_context("오늘 날씨", []))
    assert "웹 검색을 완료하지 못했습니다" in context
