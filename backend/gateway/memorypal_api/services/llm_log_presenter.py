from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any


TIMING_NUMBER = r"([0-9]+(?:\.[0-9]+)?)"


def _iso_timestamp(value: Any, fallback: str) -> str:
    candidate = value if value not in (None, "") else fallback
    try:
        if isinstance(candidate, (int, float)) or str(candidate).isdigit():
            numeric = float(candidate)
            if numeric > 10_000_000_000:
                numeric /= 1000
            return datetime.fromtimestamp(numeric, tz=UTC).isoformat()
    except (OSError, OverflowError, ValueError):
        pass
    return str(candidate or "")[:100]


def deduplicate_presented_logs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge the duplicate server/runtime copy emitted for one LM Studio event."""
    merged: list[dict[str, Any]] = []
    positions: dict[tuple[str, str], int] = {}
    for item in items:
        key = (str(item.get("event_type") or ""), str(item.get("occurred_at") or ""))
        position = positions.get(key)
        if position is None:
            positions[key] = len(merged)
            merged.append(item)
            continue
        previous = merged[position]
        previous_quality = (
            bool(previous.get("model_key")), previous.get("source") == "runtime",
            len(str(previous.get("detail") or "")),
        )
        item_quality = (
            bool(item.get("model_key")), item.get("source") == "runtime",
            len(str(item.get("detail") or "")),
        )
        if item_quality > previous_quality:
            merged[position] = item
    return merged


def _nested_payload(event: dict[str, Any]) -> tuple[dict[str, Any], str]:
    raw = str(event.get("message") or "")
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return {}, raw
    if not isinstance(decoded, dict):
        return {}, raw
    nested = decoded.get("data")
    payload = nested if isinstance(nested, dict) else decoded
    detail = str(payload.get("message") or payload.get("content") or raw)
    return payload, detail


def _timing_stats(detail: str) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    prompt = re.search(
        rf"prompt eval time\s*=\s*{TIMING_NUMBER}\s*ms\s*/\s*(\d+) tokens.*?{TIMING_NUMBER}\s*tokens per second",
        detail, re.I | re.S,
    )
    generation = re.search(
        rf"(?<!prompt )eval time\s*=\s*{TIMING_NUMBER}\s*ms\s*/\s*(\d+) tokens.*?{TIMING_NUMBER}\s*tokens per second",
        detail, re.I | re.S,
    )
    total = re.search(rf"total time\s*=\s*{TIMING_NUMBER}\s*ms\s*/\s*(\d+) tokens", detail, re.I)
    progress = re.search(rf"n_decoded\s*=\s*(\d+).*?tg\s*=\s*{TIMING_NUMBER}\s*t/s", detail, re.I | re.S)
    if prompt:
        stats.update(prompt_tokens=int(prompt.group(2)), prompt_tokens_per_second=float(prompt.group(3)))
    if generation:
        stats.update(
            completion_tokens=int(generation.group(2)),
            tokens_per_second=float(generation.group(3)),
        )
    if total:
        stats.update(duration_ms=float(total.group(1)), total_tokens=int(total.group(2)))
    if progress and "completion_tokens" not in stats:
        stats.update(completion_tokens=int(progress.group(1)), tokens_per_second=float(progress.group(2)))
    context = re.search(r"n_ctx_slot\s*=\s*(\d+)", detail, re.I)
    slots = re.search(r"n_slots\s*=\s*(\d+)", detail, re.I)
    if context:
        stats["context_length"] = int(context.group(1))
    if slots:
        stats["parallel_slots"] = int(slots.group(1))
    return stats


def present_llm_log(event: dict[str, Any]) -> dict[str, Any]:
    """Convert LM Studio/llama.cpp internals into an operator-facing event."""
    result = dict(event)
    payload, detail = _nested_payload(event)
    normalized = detail.casefold()
    source = str(event.get("source") or "server")
    model_key = str(
        payload.get("modelIdentifier") or payload.get("model_identifier")
        or payload.get("model") or event.get("model_key") or ""
    )[:300]
    level = str(payload.get("level") or event.get("level") or "info").casefold()
    level = "warn" if level == "warning" else level
    if level not in {"trace", "debug", "info", "warn", "error", "fatal"}:
        level = "info"
    stats = {**(event.get("stats") if isinstance(event.get("stats"), dict) else {}), **_timing_stats(detail)}
    event_type = str(event.get("event_type") or "server_event")
    title = "LM Studio 상태"
    summary = "LM Studio 내부 상태가 갱신되었습니다."
    importance = "debug"

    if "streaming logs from lm studio" in normalized:
        event_type, title = "log_stream_connected", "로그 수집 연결"
        summary, importance = f"{source} 로그 스트림 연결이 시작되었습니다.", "routine"
    elif "received request:" in normalized:
        match = re.search(r"received request:\s*([A-Z]+)\s+to\s+([^\s]+)", detail, re.I)
        method, path = (match.group(1).upper(), match.group(2)) if match else ("API", "요청")
        event_type, title = "api_request_received", "API 요청 수신"
        summary, importance = f"{method} {path} 요청을 받았습니다.", "routine"
    elif match := re.search(r"returning\s+(\d+)\s+models", normalized):
        event_type, title = "model_catalog_returned", "모델 목록 응답"
        summary, importance = f"사용 가능한 모델 {match.group(1)}개를 반환했습니다.", "routine"
        stats["model_count"] = int(match.group(1))
    elif "loading model" in normalized or "loading model from path" in normalized:
        event_type, title = "model_load_progress", "모델 로드 중"
        summary, importance = f"{model_key or '모델'} 파일을 메모리에 불러오고 있습니다.", "important"
    elif "loading model into embedding engine" in normalized:
        event_type, title = "embedding_load_progress", "임베딩 모델 로드 중"
        summary, importance = f"{model_key or '임베딩 모델'}을 검색 엔진에 불러오고 있습니다.", "important"
    elif "model load complete" in normalized or "model loaded" in normalized:
        event_type, title = "model_loaded", "모델 로드 완료"
        summary, importance = f"{model_key or '모델'}을 사용할 준비가 완료됐습니다.", "important"
    elif "initializing" in normalized and ("n_ctx" in normalized or "n_slots" in normalized):
        event_type, title = "model_runtime_initialized", "추론 환경 초기화"
        context = stats.get("context_length")
        summary = f"{model_key or '모델'}의 추론 환경을 초기화했습니다."
        if context:
            summary += f" 컨텍스트 {int(context):,} 토큰"
        importance = "important"
    elif "prompt eval time" in normalized and "total time" in normalized:
        event_type, title = "inference_completed", "응답 생성 완료"
        speed = stats.get("tokens_per_second")
        summary = f"{model_key or '모델'}의 응답 생성이 완료됐습니다."
        if speed is not None:
            summary += f" 생성 속도 {float(speed):.1f} tok/s"
        importance = "important"
    elif "n_decoded" in normalized and "t/s" in normalized:
        event_type, title = "inference_progress", "응답 생성 중"
        tokens, speed = stats.get("completion_tokens"), stats.get("tokens_per_second")
        summary = f"{model_key or '모델'}이 응답을 생성하고 있습니다."
        if tokens is not None and speed is not None:
            summary += f" {int(tokens):,}토큰 · {float(speed):.1f} tok/s"
        importance = "debug"
    elif "processing task" in normalized:
        event_type, title = "inference_started", "응답 생성 시작"
        summary, importance = f"{model_key or '모델'}이 요청 처리를 시작했습니다.", "important"
    elif event_type == "inference_completed" or (source == "model" and "output" in normalized):
        event_type, title = "inference_completed", "응답 생성 완료"
        summary, importance = f"{model_key or '모델'}의 응답 생성이 완료됐습니다.", "important"
    elif event_type == "model_load_failed" or "failed to load model" in normalized:
        event_type, title = "model_load_failed", "모델 로드 실패"
        summary, importance, level = f"{model_key or '모델'}을 불러오지 못했습니다.", "critical", "error"
    elif level in {"error", "fatal"} or any(word in normalized for word in ("error", "failed", "aborted", "exception")):
        event_type, title = "runtime_error", "LLM 런타임 오류"
        summary, importance, level = f"{model_key or 'LM Studio'} 처리 중 오류가 발생했습니다.", "critical", "error"
    elif level == "warn" or re.search(r"(?:^|\s)W\s", detail):
        event_type, title = "runtime_warning", "LLM 런타임 경고"
        summary, importance, level = f"{model_key or 'LM Studio'}에서 확인이 필요한 경고가 발생했습니다.", "important", "warn"
    elif event_type == "model_loaded":
        title, summary, importance = "모델 로드 완료", f"{model_key or '모델'}을 사용할 준비가 완료됐습니다.", "important"

    result.update({
        "source": source,
        "level": level,
        "event_type": event_type,
        "model_key": model_key or None,
        "title": title,
        "message": summary,
        "detail": detail.replace("\r", " ").replace("\n", " ")[:4000] or None,
        "importance": importance,
        "stats": stats,
        "occurred_at": _iso_timestamp(payload.get("timestamp"), str(event.get("occurred_at") or "")),
    })
    return result
