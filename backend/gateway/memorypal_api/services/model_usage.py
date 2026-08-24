from __future__ import annotations

import asyncio
from collections import Counter
from contextlib import asynccontextmanager


class ModelInUseError(RuntimeError):
    pass


class ModelUsageTracker:
    """Coordinate inference leases with model unload transitions in one gateway."""

    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._active: Counter[str] = Counter()
        self._unloading: set[str] = set()

    @staticmethod
    def _key(model_key: str) -> str:
        return str(model_key or "").strip().casefold()

    def is_active(self, model_key: str) -> bool:
        return self._active[self._key(model_key)] > 0

    @asynccontextmanager
    async def using(self, model_key: str):
        key = self._key(model_key)
        if not key:
            yield
            return
        async with self._condition:
            await self._condition.wait_for(lambda: key not in self._unloading)
            self._active[key] += 1
        try:
            yield
        finally:
            async with self._condition:
                self._active[key] -= 1
                if self._active[key] <= 0:
                    self._active.pop(key, None)
                self._condition.notify_all()

    @asynccontextmanager
    async def unloading(self, model_key: str):
        key = self._key(model_key)
        if not key:
            yield
            return
        async with self._condition:
            if self._active[key] > 0:
                raise ModelInUseError("모델이 요청을 처리 중이어서 언로드할 수 없습니다.")
            self._unloading.add(key)
        try:
            yield
        finally:
            async with self._condition:
                self._unloading.discard(key)
                self._condition.notify_all()
