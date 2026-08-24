import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx

from memorypal_api.services.hardware_monitor import HardwareMonitorHub


def settings(tmp_path: Path):
    return SimpleNamespace(
        model_service_token="monitor-test-" + "m" * 48,
        hardware_monitor_interval_seconds=15,
        hardware_monitor_log_path=tmp_path / "hardware.jsonl",
        monitor_stt_url="http://stt:8100",
        monitor_llm_url="http://llm:8101",
        monitor_tts_url="http://tts:8102",
        monitor_gateway_url="http://gateway:8103",
        monitor_archive_url="http://archive:8104",
    )


def test_collects_all_services_and_persists_snapshots(tmp_path, monkeypatch):
    hub = HardwareMonitorHub(settings(tmp_path))

    class Response:
        def __init__(self, service): self.service = service
        def raise_for_status(self): return None
        def json(self):
            return {
                "service": self.service, "status": "green", "reason": "정상",
                "sampled_at": "2026-08-19T00:00:00+00:00", "service_online": True,
                "response_latency_ms": 1, "latency_baseline_ms": 1,
                "cpu": {"process_percent": 1},
                "ram": {"total_bytes": 1, "available_bytes": 1, "used_percent": 1, "process_rss_bytes": 1, "process_percent": 1},
                "gpu": None,
            }

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def get(self, url, headers):
            assert headers["Authorization"].startswith("Bearer ")
            return Response(url.split("//", 1)[1].split(":", 1)[0])

    monkeypatch.setattr("memorypal_api.services.hardware_monitor.httpx.AsyncClient", lambda **_kwargs: Client())
    result = asyncio.run(hub.collect_once())
    assert set(result) == {"stt", "llm", "tts", "gateway", "archive"}
    assert len((tmp_path / "hardware.jsonl").read_text(encoding="utf-8").splitlines()) == 5


def test_reads_incremental_llm_logs_with_service_token(tmp_path, monkeypatch):
    hub = HardwareMonitorHub(settings(tmp_path))

    class Response:
        def raise_for_status(self): return None
        def json(self):
            return {
                "enabled": True, "latest_cursor": 13, "next_cursor": 13,
                "items": [{
                    "cursor": 13, "source": "runtime", "level": "error",
                    "event_type": "model_load_failed", "model_key": "qwen3.5-4b",
                    "message": "Engine startup aborted", "stats": {},
                    "occurred_at": "2026-08-24T00:00:00+00:00",
                }],
            }

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def get(self, url, headers, params):
            assert url == "http://llm:8101/v1/logs/recent"
            assert headers == {"Authorization": f"Bearer {hub.token}"}
            assert params == {
                "after_cursor": 12, "limit": 50, "source": "runtime",
                "level": "error", "model_key": "qwen3.5",
            }
            return Response()

    monkeypatch.setattr("memorypal_api.services.hardware_monitor.httpx.AsyncClient", lambda **_kwargs: Client())
    result = asyncio.run(hub.llm_logs(
        after_cursor=12, limit=50, source="runtime", level="error", model_key="qwen3.5",
    ))
    assert result["available"] is True
    assert result["items"][0]["event_type"] == "model_load_failed"
    assert result["next_cursor"] == 13


def test_llm_logs_fail_closed_when_monitor_is_unavailable(tmp_path, monkeypatch):
    hub = HardwareMonitorHub(settings(tmp_path))

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def get(self, *_args, **_kwargs):
            raise httpx.ConnectError(
                "network detail must not escape", request=httpx.Request("GET", "http://llm:8101"),
            )

    monkeypatch.setattr("memorypal_api.services.hardware_monitor.httpx.AsyncClient", lambda **_kwargs: Client())
    result = asyncio.run(hub.llm_logs(after_cursor=7))
    assert result == {
        "enabled": False, "available": False, "items": [],
        "latest_cursor": 7, "next_cursor": 7,
    }
