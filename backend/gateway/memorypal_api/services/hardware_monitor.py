from __future__ import annotations

import asyncio
import json
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from .llm_log_presenter import deduplicate_presented_logs, present_llm_log


class HardwareMonitorHub:
    def __init__(self, settings) -> None:
        self.token = settings.model_service_token
        self.interval_seconds = settings.hardware_monitor_interval_seconds
        self.log_path: Path = settings.hardware_monitor_log_path
        self.endpoints = {
            "stt": settings.monitor_stt_url,
            "llm": settings.monitor_llm_url,
            "tts": settings.monitor_tts_url,
            "gateway": settings.monitor_gateway_url,
            "archive": settings.monitor_archive_url,
        }
        self.current: dict[str, dict[str, Any]] = {}
        self.history: deque[dict[str, Any]] = deque(maxlen=2400)
        self._lock = asyncio.Lock()

    @staticmethod
    def _red(service: str, reason: str) -> dict[str, Any]:
        return {
            "service": service, "status": "red", "reason": reason,
            "sampled_at": datetime.now(UTC).isoformat(), "service_online": False,
            "response_latency_ms": None, "latency_baseline_ms": None,
            "cpu": {"process_percent": 0},
            "ram": {"total_bytes": 0, "available_bytes": 0, "used_percent": 0, "process_rss_bytes": 0, "process_percent": 0},
            "gpu": None,
        }

    async def _fetch(self, client: httpx.AsyncClient, service: str, base_url: str) -> dict[str, Any]:
        if not base_url:
            return self._red(service, "모니터 URL이 설정되지 않았습니다.")
        try:
            response = await client.get(
                f"{base_url.rstrip('/')}/v1/metrics/current",
                headers={"Authorization": f"Bearer {self.token}"},
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("service") != service or payload.get("status") not in {"green", "yellow", "red"}:
                raise ValueError("invalid monitor payload")
            return payload
        except (httpx.HTTPError, TypeError, ValueError):
            return self._red(service, "모니터 응답을 받을 수 없습니다.")

    async def collect_once(self) -> dict[str, dict[str, Any]]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            results = await asyncio.gather(*(
                self._fetch(client, service, url) for service, url in self.endpoints.items()
            ))
        snapshots = {item["service"]: item for item in results}
        async with self._lock:
            self.current = snapshots
            self.history.extend(results)
        await asyncio.to_thread(self._append_log, results)
        return snapshots

    def _append_log(self, snapshots: list[dict[str, Any]]) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            if self.log_path.exists() and self.log_path.stat().st_size > 25 * 1024**2:
                self.log_path.replace(self.log_path.with_suffix(self.log_path.suffix + ".1"))
            with self.log_path.open("a", encoding="utf-8") as handle:
                for snapshot in snapshots:
                    handle.write(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            pass

    async def run(self) -> None:
        while True:
            try:
                await self.collect_once()
            except Exception:
                # A transient collector or filesystem error must not stop the 15-second monitor loop.
                pass
            await asyncio.sleep(self.interval_seconds)

    async def snapshot(self, history_limit: int = 100) -> dict[str, Any]:
        async with self._lock:
            current = [self.current.get(name, self._red(name, "아직 수집되지 않았습니다.")) for name in self.endpoints]
            history = list(self.history)[-history_limit:]
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "interval_seconds": self.interval_seconds,
            "services": current,
            "history": history,
        }

    async def llm_logs(
        self, *, after_cursor: int = 0, limit: int = 200,
        source: str = "", level: str = "", model_key: str = "",
    ) -> dict[str, Any]:
        """Read privacy-filtered LM Studio events from the remote LLM monitor."""
        base_url = self.endpoints.get("llm", "")
        unavailable = {
            "enabled": False, "available": False, "items": [],
            "latest_cursor": max(0, after_cursor), "next_cursor": max(0, after_cursor),
        }
        if not base_url:
            return unavailable
        params: dict[str, str | int] = {
            "after_cursor": max(0, after_cursor), "limit": min(500, max(1, limit)),
        }
        if source:
            params["source"] = source
        if level:
            params["level"] = level
        if model_key:
            params["model_key"] = model_key
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{base_url.rstrip('/')}/v1/logs/recent",
                    headers={"Authorization": f"Bearer {self.token}"},
                    params=params,
                )
                response.raise_for_status()
                payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                raise ValueError("invalid LM Studio log payload")
            latest_cursor = int(payload.get("latest_cursor", after_cursor))
            next_cursor = int(payload.get("next_cursor", after_cursor))
            if latest_cursor < 0 or next_cursor < 0:
                raise ValueError("invalid LM Studio log cursor")
            presented = [present_llm_log(item) for item in payload["items"][:limit] if isinstance(item, dict)]
            return {
                "enabled": bool(payload.get("enabled", True)),
                "available": True,
                "items": deduplicate_presented_logs(presented),
                "latest_cursor": latest_cursor,
                "next_cursor": next_cursor,
            }
        except (httpx.HTTPError, TypeError, ValueError):
            return unavailable
