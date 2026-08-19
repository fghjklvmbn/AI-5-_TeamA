from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable


logger = logging.getLogger(__name__)


class WebSearchEngine:
    """Builds ephemeral web context without writing results to MemoryPal storage."""

    def __init__(
        self,
        max_results: int = 4,
        search: Callable[..., list[dict[str, Any]]] | None = None,
    ):
        self.max_results = max(1, min(6, max_results))
        self._search = search

    @staticmethod
    def contextual_query(user_text: str, history: list) -> str:
        query = " ".join(user_text.split())
        # Short follow-ups such as "그건 언제야?" need the immediately preceding topic.
        if len(query) < 24 and history:
            previous = " ".join(str(history[-1]["user_text"]).split())
            if previous and previous != query:
                query = f"{previous} {query}"
        return query[:300]

    def _run_search(self, query: str) -> list[dict[str, Any]]:
        if self._search is not None:
            return list(self._search(query, max_results=self.max_results))
        from ddgs import DDGS

        return list(DDGS(timeout=10).text(query, max_results=self.max_results))

    async def retrieve_context(self, user_text: str, history: list) -> str:
        query = self.contextual_query(user_text, history)
        if not query:
            return ""
        try:
            results = await asyncio.wait_for(asyncio.to_thread(self._run_search, query), timeout=15)
        except Exception as exc:
            # Internet mode is optional. A search outage must not turn chat into HTTP 503.
            logger.warning("Web search failed for query=%r: %r", query, exc)
            return "웹 검색을 완료하지 못했습니다. 최신 정보가 확인됐다고 주장하지 마세요."

        blocks: list[str] = []
        for index, item in enumerate(results[: self.max_results], 1):
            title = " ".join(str(item.get("title") or "제목 없음").split())[:200]
            url = str(item.get("href") or item.get("url") or "").strip()
            snippet = " ".join(str(item.get("body") or item.get("snippet") or "").split())[:700]
            if not url.startswith(("https://", "http://")):
                continue
            blocks.append(f"[{index}] {title}\nURL: {url}\n요약: {snippet or '검색 결과 요약 없음'}")
        if not blocks:
            return "관련 웹 검색 결과를 찾지 못했습니다. 최신 정보가 확인됐다고 주장하지 마세요."
        searched_at = datetime.now().astimezone().isoformat(timespec="minutes")
        return f"검색 시각: {searched_at}\n검색어: {query}\n\n" + "\n\n".join(blocks)
