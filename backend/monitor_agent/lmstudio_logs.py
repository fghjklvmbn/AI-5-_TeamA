from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any


SENSITIVE_KEYS = {
    "authorization", "api_key", "apikey", "token", "access_token",
    "input", "output", "prompt", "prompts", "messages", "content", "text",
}
STAT_KEYS = {
    "tokens_per_second", "tokensPerSecond", "predicted_tokens_per_second",
    "prompt_tokens", "completion_tokens", "total_tokens", "tokens",
    "time_to_first_token", "time_to_first_token_seconds", "ttft",
    "stop_reason", "finish_reason", "duration_ms", "load_time_ms",
}
MODEL_KEYS = (
    "modelIdentifier", "model_identifier", "model", "modelKey", "model_key",
    "identifier", "modelPath", "model_path",
)
LEVEL_RE = re.compile(r"\b(trace|debug|info|warn(?:ing)?|error|fatal)\b", re.I)
SECRET_TEXT_RE = re.compile(
    r"(?i)(authorization\s*[:=]\s*bearer\s+|bearer\s+|(?:api[_-]?key|access[_-]?token|token)\s*[:=]\s*)"
    r"[^\s,;\"']+"
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def normalize_timestamp(value: Any) -> str:
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            numeric = float(value)
            if numeric > 10_000_000_000:
                numeric /= 1000
            return datetime.fromtimestamp(numeric, tz=UTC).isoformat()
    except (OSError, OverflowError, ValueError):
        pass
    return str(value or utc_now())[:100]


def _safe_scalar(value: Any, *, maximum: int = 500) -> Any:
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return redact_text(str(value), maximum=maximum)


def redact_text(value: str, *, maximum: int = 2000) -> str:
    normalized = value.replace("\r", " ").replace("\n", " ")
    return SECRET_TEXT_RE.sub(lambda match: f"{match.group(1)}[REDACTED]", normalized)[:maximum]


def sanitize_payload(value: Any) -> Any:
    """Remove model IO and credentials before an event can reach disk or an API."""
    if isinstance(value, dict):
        return {
            str(key): sanitize_payload(item)
            for key, item in value.items()
            if str(key).casefold() not in SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value[:50]]
    return _safe_scalar(value)


def classify_event(source: str, text: str, payload: dict[str, Any]) -> str:
    combined = f"{payload.get('type', '')} {payload.get('event', '')} {text}".casefold()
    if "unload" in combined:
        if any(word in combined for word in ("fail", "error", "abort", "block")):
            return "model_unload_failed"
        if any(word in combined for word in ("complete", "success", "unloaded")):
            return "model_unloaded"
        return "model_unload_requested"
    if "load" in combined or "engine" in combined or source == "runtime":
        if any(word in combined for word in ("fail", "error", "abort", "exception", "fatal")):
            return "model_load_failed"
        if any(word in combined for word in ("complete", "success", "loaded", "ready")):
            return "model_loaded"
        return "runtime_event" if source == "runtime" else "model_load_progress"
    if source == "model" or any(word in combined for word in ("prediction", "inference", "completion")):
        if any(word in combined for word in ("fail", "error", "abort", "exception")):
            return "inference_failed"
        if any(word in combined for word in ("output", "complete", "finish")):
            return "inference_completed"
        return "inference_progress"
    if any(word in combined for word in ("fail", "error", "abort", "exception", "fatal")):
        return "server_error"
    return "server_event"


class LogEventStore:
    def __init__(self, path: Path, maximum: int = 2000) -> None:
        self.path = path
        self.events: deque[dict[str, Any]] = deque(maxlen=max(100, maximum))
        self.lock = Lock()
        self.cursor = 0

    def append(self, source: str, raw_line: str) -> dict[str, Any] | None:
        line = raw_line.strip()
        if not line:
            return None
        try:
            decoded = json.loads(line)
            payload = decoded if isinstance(decoded, dict) else {"value": decoded}
        except (TypeError, ValueError):
            payload = {}

        nested = payload.get("data")
        event_payload = nested if isinstance(nested, dict) else payload
        sanitized = sanitize_payload(event_payload)
        searchable = json.dumps(sanitized, ensure_ascii=False) if payload else line
        level_match = LEVEL_RE.search(searchable)
        level = str(event_payload.get("level") or (level_match.group(1) if level_match else "info"))
        level = level.casefold().replace("warning", "warn")
        model_key = next(
            (str(event_payload.get(key) or "")[:300] for key in MODEL_KEYS if event_payload.get(key)), ""
        )
        stats: dict[str, Any] = {}
        raw_stats = event_payload.get("stats")
        if isinstance(raw_stats, dict):
            stats.update(sanitize_payload(raw_stats))
        for key in STAT_KEYS:
            if key in event_payload:
                stats[key] = _safe_scalar(event_payload[key])

        # Never retain unstructured model lines: they can be raw prompts or answers.
        if source == "model":
            message = redact_text(
                str(event_payload.get("type") or event_payload.get("event") or "LM Studio model event"), maximum=500,
            )
        else:
            message = redact_text(str(
                event_payload.get("message") or event_payload.get("content") or event_payload.get("msg")
                or event_payload.get("type") or event_payload.get("event") or line
            ))
        occurred_at = normalize_timestamp(
            payload.get("timestamp") or event_payload.get("timestamp") or event_payload.get("occurred_at")
        )

        with self.lock:
            self.cursor += 1
            event = {
                "cursor": self.cursor,
                "source": source,
                "level": level,
                "event_type": classify_event(source, f"{searchable} {message}", event_payload),
                "model_key": model_key or None,
                "message": message,
                "stats": stats,
                "occurred_at": occurred_at,
            }
            self.events.append(event)
            self._append_file(event)
            return dict(event)

    def _append_file(self, event: dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size > 50 * 1024**2:
                rotated = self.path.with_suffix(self.path.suffix + ".1")
                rotated.unlink(missing_ok=True)
                self.path.replace(rotated)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            pass

    def read(
        self, *, after_cursor: int = 0, limit: int = 200,
        source: str = "", level: str = "", model_key: str = "",
    ) -> dict[str, Any]:
        with self.lock:
            snapshot = list(self.events)
            latest_cursor = self.cursor
        normalized_model = model_key.casefold()
        items = [
            event for event in snapshot
            if event["cursor"] > after_cursor
            and (not source or event["source"] == source)
            and (not level or event["level"] == level)
            and (not normalized_model or normalized_model in str(event.get("model_key") or "").casefold())
        ][:limit]
        return {
            "items": items,
            "latest_cursor": latest_cursor,
            "next_cursor": items[-1]["cursor"] if items else after_cursor,
        }


class LMStudioLogCollector:
    """Supervise local `lms log stream` processes and retain sanitized events."""

    def __init__(self, cli: str, store: LogEventStore, sources: tuple[str, ...]) -> None:
        self.cli = cli
        self.store = store
        self.sources = tuple(dict.fromkeys(source for source in sources if source))
        self.stop_event = Event()
        self.threads: list[Thread] = []
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.statuses: dict[str, dict[str, Any]] = {
            source: {"state": "stopped", "pid": None, "error": None} for source in self.sources
        }
        self.lock = Lock()

    def start(self) -> None:
        if self.threads:
            return
        self.stop_event.clear()
        for source in self.sources:
            thread = Thread(target=self._supervise, args=(source,), daemon=True, name=f"lmstudio-log-{source}")
            self.threads.append(thread)
            thread.start()

    def _command(self, source: str) -> list[str]:
        command = [self.cli, "log", "stream", "--source", source, "--json"]
        if source == "model":
            command.extend(["--filter", "output", "--stats"])
        return command

    def _set_status(self, source: str, state: str, *, pid: int | None = None, error: str | None = None) -> None:
        with self.lock:
            self.statuses[source] = {"state": state, "pid": pid, "error": error, "updated_at": utc_now()}

    def _supervise(self, source: str) -> None:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        while not self.stop_event.is_set():
            process: subprocess.Popen[str] | None = None
            try:
                process = subprocess.Popen(
                    self._command(source), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    shell=False, creationflags=creation_flags,
                )
                with self.lock:
                    self.processes[source] = process
                self._set_status(source, "running", pid=process.pid)
                if process.stdout is not None:
                    for line in process.stdout:
                        if self.stop_event.is_set():
                            break
                        self.store.append(source, line)
                return_code = process.wait(timeout=3)
                if not self.stop_event.is_set():
                    self._set_status(source, "reconnecting", error=f"lms exited with code {return_code}")
            except (OSError, subprocess.SubprocessError) as exc:
                self._set_status(source, "reconnecting", error=str(exc)[:500])
            finally:
                with self.lock:
                    self.processes.pop(source, None)
                if process is not None and process.poll() is None:
                    process.terminate()
            self.stop_event.wait(2.0)
        self._set_status(source, "stopped")

    def stop(self) -> None:
        self.stop_event.set()
        with self.lock:
            processes = list(self.processes.values())
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for thread in self.threads:
            thread.join(timeout=5)
        self.threads.clear()

    def status(self) -> dict[str, Any]:
        with self.lock:
            sources = {key: dict(value) for key, value in self.statuses.items()}
        return {
            "enabled": True,
            "cli": self.cli,
            "sources": sources,
            "latest_cursor": self.store.cursor,
        }
