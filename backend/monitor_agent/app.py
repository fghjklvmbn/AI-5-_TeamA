from __future__ import annotations

import asyncio
import hmac
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from collections import deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlsplit

import psutil
from fastapi import Depends, FastAPI, Header, HTTPException, Query

from lmstudio_logs import LMStudioLogCollector, LogEventStore


INTERVAL_SECONDS = max(5, int(os.getenv("MEMORYPAL_MONITOR_INTERVAL_SECONDS", "15")))
SERVICE_NAME = os.getenv("MEMORYPAL_MONITOR_SERVICE", "service").strip().lower()
TARGET_PID = int(os.getenv("MEMORYPAL_MONITOR_TARGET_PID", "0") or 0)
PROCESS_NAMES = tuple(
    value.strip().casefold() for value in os.getenv("MEMORYPAL_MONITOR_PROCESS_NAMES", "").split(",") if value.strip()
)
HEALTH_URL = os.getenv("MEMORYPAL_MONITOR_HEALTH_URL", "").strip()
GPU_ENABLED = os.getenv("MEMORYPAL_MONITOR_GPU", "false").strip().casefold() in {"1", "true", "yes", "on"}
LOG_PATH = Path(os.getenv("MEMORYPAL_MONITOR_LOG_PATH", f"logs/{SERVICE_NAME}.hardware.jsonl")).resolve()
LMSTUDIO_LOG_ENABLED = (
    SERVICE_NAME == "llm"
    and os.getenv("MEMORYPAL_LMSTUDIO_LOG_ENABLED", "true").strip().casefold() in {"1", "true", "yes", "on"}
)
LMSTUDIO_LOG_PATH = Path(
    os.getenv("MEMORYPAL_LMSTUDIO_LOG_PATH", "logs/llm.lmstudio.jsonl")
).resolve()
LMSTUDIO_LOG_LIMIT = max(100, int(os.getenv("MEMORYPAL_LMSTUDIO_LOG_LIMIT", "2000")))
LMSTUDIO_LMS_CLI = os.getenv("MEMORYPAL_LMS_CLI", "lms").strip() or "lms"
LMSTUDIO_LOG_SOURCES = tuple(
    value.strip().casefold()
    for value in os.getenv("MEMORYPAL_LMSTUDIO_LOG_SOURCES", "server,runtime,model").split(",")
    if value.strip().casefold() in {"server", "runtime", "model"}
)
TOKEN = os.getenv("MEMORYPAL_MODEL_SERVICE_TOKEN", "").strip()
if not TOKEN:
    token_file = os.getenv("MEMORYPAL_MODEL_SERVICE_TOKEN_FILE", "").strip()
    if token_file:
        TOKEN = Path(token_file).read_text(encoding="utf-8").strip()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def classify_status(
    *,
    service_online: bool,
    process_cpu_percent: float,
    system_ram_percent: float,
    gpu: dict[str, Any] | None,
    gpu_expected: bool,
    latency_delayed: bool,
) -> tuple[str, str]:
    if not service_online:
        return "red", "서비스가 중단되었거나 상태 확인에 실패했습니다."
    overloaded = process_cpu_percent > 50 or system_ram_percent > 70 or latency_delayed
    if gpu_expected:
        overloaded = overloaded or gpu is None or bool(
            gpu and (gpu["vram_used_percent"] >= 80 or gpu["cuda_utilization_percent"] >= 70)
        )
    if overloaded:
        return "yellow", "리소스 부하 또는 응답 지연이 감지되었습니다."
    return "green", "정상"


class HardwareSampler:
    def __init__(self) -> None:
        self.lock = Lock()
        self.history: deque[dict[str, Any]] = deque(maxlen=240)
        self.latencies: deque[float] = deque(maxlen=20)
        self.current: dict[str, Any] = self._red("모니터 초기화 중")
        self._cpu_times: dict[int, tuple[float, float]] = {}

    def _candidate_processes(self) -> list[psutil.Process]:
        processes: dict[int, psutil.Process] = {}
        # A Windows Python launcher or a service-only restart can make the PID
        # captured at monitor startup stale while the service is still healthy.
        # For a loopback health URL, the listening socket is the authoritative
        # process identity and lets the monitor rebind without a false RED.
        parsed = urlsplit(HEALTH_URL) if HEALTH_URL else None
        if parsed and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            try:
                listeners = psutil.net_connections(kind="inet")
            except (psutil.Error, OSError):
                listeners = []
            for connection in listeners:
                if (
                    connection.status != psutil.CONN_LISTEN
                    or not connection.pid
                    or not connection.laddr
                    or connection.laddr.port != port
                ):
                    continue
                try:
                    root = psutil.Process(connection.pid)
                    processes[root.pid] = root
                    for child in root.children(recursive=True):
                        processes[child.pid] = child
                except (psutil.Error, OSError):
                    continue
            if processes:
                return list(processes.values())
        if TARGET_PID:
            try:
                root = psutil.Process(TARGET_PID)
                processes[root.pid] = root
                for child in root.children(recursive=True):
                    processes[child.pid] = child
            except (psutil.Error, OSError):
                return []
        elif PROCESS_NAMES:
            for process in psutil.process_iter(["pid", "name"]):
                try:
                    if str(process.info.get("name") or "").casefold() in PROCESS_NAMES:
                        processes[process.pid] = process
                        for child in process.children(recursive=True):
                            processes[child.pid] = child
                except (psutil.Error, OSError):
                    continue
        return list(processes.values())

    def _process_usage(self, processes: list[psutil.Process]) -> tuple[float, int, int]:
        now = time.monotonic()
        cpu_percent = 0.0
        rss = 0
        alive = 0
        active_pids: set[int] = set()
        for process in processes:
            try:
                times = process.cpu_times()
                total_cpu = float(times.user + times.system)
                previous = self._cpu_times.get(process.pid)
                if previous and now > previous[1]:
                    cpu_percent += max(0.0, (total_cpu - previous[0]) / (now - previous[1]) * 100)
                self._cpu_times[process.pid] = (total_cpu, now)
                active_pids.add(process.pid)
                rss += process.memory_info().rss
                alive += 1
            except (psutil.Error, OSError):
                continue
        self._cpu_times = {pid: value for pid, value in self._cpu_times.items() if pid in active_pids}
        return cpu_percent, rss, alive

    @staticmethod
    def _health() -> tuple[bool, float | None]:
        if not HEALTH_URL:
            return True, None
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=5) as response:
                online = int(response.status) < 500
        except urllib.error.HTTPError as exc:
            online = int(exc.code) < 500
        except (OSError, ValueError):
            return False, None
        return online, round((time.perf_counter() - started) * 1000, 2)

    @staticmethod
    def _gpu() -> dict[str, Any] | None:
        if not GPU_ENABLED:
            return None
        executable = shutil.which("nvidia-smi")
        if not executable:
            return None
        try:
            completed = subprocess.run(
                [executable, "--query-gpu=name,utilization.gpu,utilization.memory,memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"],
                check=True, capture_output=True, text=True, timeout=5, shell=False,
            )
            rows = []
            for line in completed.stdout.splitlines():
                parts = [part.strip() for part in line.split(",")]
                if len(parts) == 6:
                    rows.append((parts[0], *[float(value) for value in parts[1:]]))
            if not rows:
                return None
            mib = 1024**2
            total = sum(row[3] for row in rows)
            used = sum(row[4] for row in rows)
            free = sum(row[5] for row in rows)
            return {
                "names": [row[0] for row in rows],
                "count": len(rows),
                "cuda_utilization_percent": round(sum(row[1] for row in rows) / len(rows), 2),
                "memory_controller_utilization_percent": round(sum(row[2] for row in rows) / len(rows), 2),
                "vram_total_bytes": int(total * mib),
                "vram_used_bytes": int(used * mib),
                "vram_free_bytes": int(free * mib),
                "vram_used_percent": round(used / total * 100, 2) if total else 0,
            }
        except (OSError, subprocess.SubprocessError, ValueError):
            return None

    def _red(self, reason: str) -> dict[str, Any]:
        memory = psutil.virtual_memory()
        return {
            "service": SERVICE_NAME, "status": "red", "reason": reason,
            "sampled_at": utc_now(), "interval_seconds": INTERVAL_SECONDS,
            "service_online": False, "response_latency_ms": None, "latency_baseline_ms": None,
            "cpu": {"process_percent": 0.0},
            "ram": {"total_bytes": memory.total, "available_bytes": memory.available, "used_percent": memory.percent, "process_rss_bytes": 0, "process_percent": 0.0},
            "gpu": None,
        }

    def sample(self) -> dict[str, Any]:
        processes = self._candidate_processes()
        online, latency = self._health()
        if not processes:
            snapshot = self._red("서비스 프로세스를 찾을 수 없습니다.")
        elif not online:
            snapshot = self._red("서비스 상태 확인에 실패했습니다.")
        else:
            cpu, rss, alive = self._process_usage(processes)
            if not alive:
                snapshot = self._red("서비스 프로세스가 종료되었습니다.")
            else:
                memory = psutil.virtual_memory()
                gpu = self._gpu()
                baseline = sum(self.latencies) / len(self.latencies) if self.latencies else None
                latency_delayed = bool(latency is not None and baseline and latency >= baseline * 1.5)
                status, reason = classify_status(
                    service_online=True,
                    process_cpu_percent=cpu,
                    system_ram_percent=memory.percent,
                    gpu=gpu,
                    gpu_expected=GPU_ENABLED,
                    latency_delayed=latency_delayed,
                )
                snapshot = {
                    "service": SERVICE_NAME,
                    "status": status,
                    "reason": reason,
                    "sampled_at": utc_now(), "interval_seconds": INTERVAL_SECONDS,
                    "service_online": True, "process_count": alive,
                    "response_latency_ms": latency,
                    "latency_baseline_ms": round(baseline, 2) if baseline is not None else None,
                    "cpu": {"process_percent": round(cpu, 2)},
                    "ram": {
                        "total_bytes": memory.total, "available_bytes": memory.available,
                        "used_percent": memory.percent, "process_rss_bytes": rss,
                        "process_percent": round(rss / memory.total * 100, 2) if memory.total else 0,
                    },
                    "gpu": gpu,
                }
        if latency is not None and online:
            self.latencies.append(latency)
        with self.lock:
            self.current = snapshot
            self.history.append(snapshot)
        self._append_log(snapshot)
        return snapshot

    @staticmethod
    def _append_log(snapshot: dict[str, Any]) -> None:
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            if LOG_PATH.exists() and LOG_PATH.stat().st_size > 10 * 1024**2:
                LOG_PATH.replace(LOG_PATH.with_suffix(LOG_PATH.suffix + ".1"))
            with LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            pass

    def read_current(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.current)

    def read_history(self, limit: int) -> list[dict[str, Any]]:
        with self.lock:
            return list(self.history)[-limit:]


sampler = HardwareSampler()
lmstudio_log_store = LogEventStore(LMSTUDIO_LOG_PATH, LMSTUDIO_LOG_LIMIT)
lmstudio_log_collector = (
    LMStudioLogCollector(LMSTUDIO_LMS_CLI, lmstudio_log_store, LMSTUDIO_LOG_SOURCES)
    if LMSTUDIO_LOG_ENABLED else None
)


def public_log_health() -> dict[str, Any]:
    if lmstudio_log_collector is None:
        return {"enabled": False, "running": False}
    status = lmstudio_log_collector.status()
    states = [item.get("state") for item in status.get("sources", {}).values()]
    return {"enabled": True, "running": bool(states) and any(state == "running" for state in states)}


def require_token(authorization: str = Header(default="")) -> None:
    if len(TOKEN) < 32 or not hmac.compare_digest(authorization, f"Bearer {TOKEN}"):
        raise HTTPException(status_code=401, detail="Unauthorized")


async def sampling_loop() -> None:
    while True:
        await asyncio.to_thread(sampler.sample)
        await asyncio.sleep(INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if lmstudio_log_collector is not None:
        lmstudio_log_collector.start()
    task = asyncio.create_task(sampling_loop())
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if lmstudio_log_collector is not None:
            await asyncio.to_thread(lmstudio_log_collector.stop)


app = FastAPI(title="MemoryPal Hardware Monitor", version="1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok", "service": SERVICE_NAME,
        "lmstudio_logs": public_log_health(),
    }


@app.get("/v1/metrics/current", dependencies=[Depends(require_token)])
def current_metrics():
    return sampler.read_current()


@app.get("/v1/metrics/history", dependencies=[Depends(require_token)])
def metric_history(limit: int = Query(default=60, ge=1, le=240)):
    return {"items": sampler.read_history(limit)}


@app.get("/v1/logs/status", dependencies=[Depends(require_token)])
def lmstudio_log_status():
    if lmstudio_log_collector is None:
        return {"enabled": False, "sources": {}, "latest_cursor": 0}
    return lmstudio_log_collector.status()


@app.get("/v1/logs/recent", dependencies=[Depends(require_token)])
def lmstudio_recent_logs(
    after_cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    source: str = Query(default="", pattern="^(|server|runtime|model)$"),
    level: str = Query(default="", pattern="^(|trace|debug|info|warn|error|fatal)$"),
    model_key: str = Query(default="", max_length=300),
):
    if lmstudio_log_collector is None:
        return {"items": [], "latest_cursor": 0, "next_cursor": after_cursor, "enabled": False}
    result = lmstudio_log_store.read(
        after_cursor=after_cursor, limit=limit, source=source, level=level, model_key=model_key,
    )
    result["enabled"] = True
    return result
