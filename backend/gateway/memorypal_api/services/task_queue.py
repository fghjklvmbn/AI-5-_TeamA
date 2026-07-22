"""Distributed task queue primitives for long-running MemoryPal analysis.

Redis is the cross-process source of truth when configured. The local backend
keeps the same ownership and retry contract for a single-process development
deployment, but is intentionally neither durable nor distributed. Task bodies
are JSON objects; Redis Stream events contain identifiers and allow-listed
operational metrics only, never the task body or conversation text.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import logging
import math
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol


logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[0-9A-Za-z_.:-]{1,128}$")
_DEFAULT_NAMESPACE = "memorypal"
_EVENT_STATES = {"queued", "running", "succeeded", "failed"}
_EVENT_ANALYTICS_KEYS = {
    "duration_ms",
    "error_code",
    "max_attempts",
    "message_count",
    "model",
    "progress_percent",
    "retry_delay_ms",
    "session_count",
    "stage",
    "vector_method",
    "will_retry",
}


class QueueError(RuntimeError):
    """Base error for task queue operations."""


class QueueUnavailable(QueueError):
    """Raised when a configured Redis queue cannot be reached."""


class InvalidTask(QueueError, ValueError):
    """Raised before malformed or non-JSON work is added to a queue."""


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    task_id: str
    created: bool


@dataclass(frozen=True, slots=True)
class QueueMessage:
    task_id: str
    queue: str
    payload: dict[str, Any]
    attempt: int
    max_attempts: int
    enqueued_at: float
    available_at: float
    worker_id: str
    receipt: str
    lease_expires_at: float
    request_id: str
    correlation_id: str


@dataclass(frozen=True, slots=True)
class RetryResult:
    accepted: bool
    requeued: bool
    exhausted: bool
    attempt: int


@dataclass(frozen=True, slots=True)
class TaskProgress:
    task_id: str
    status: str
    percent: float
    stage: str
    details: dict[str, Any]
    updated_at: float


@dataclass(frozen=True, slots=True)
class LockLease:
    name: str
    owner: str
    token: str
    expires_at: float


@dataclass(frozen=True, slots=True)
class TaskEvent:
    event_id: str
    task_id: str
    request_id: str
    correlation_id: str
    queue: str
    state: str
    attempt: int
    worker_id: str
    occurred_at: float
    analytics: dict[str, str | int | float | bool]


@dataclass(frozen=True, slots=True)
class EventDelivery:
    event: TaskEvent
    group: str
    consumer: str
    delivery_count: int


class TaskQueue(Protocol):
    """Shared interface implemented by Redis and process-local backends."""

    def enqueue(
        self,
        queue: str,
        payload: Mapping[str, Any],
        *,
        task_id: str | None = None,
        dedupe_key: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
        dedupe_ttl_seconds: int = 86_400,
        max_attempts: int = 3,
        delay_seconds: float = 0,
    ) -> EnqueueResult: ...

    def dequeue(
        self,
        queue: str,
        worker_id: str,
        *,
        lease_seconds: float = 120,
        timeout_seconds: float = 0,
    ) -> QueueMessage | None: ...

    def ack(self, message: QueueMessage) -> bool: ...

    def retry(
        self, message: QueueMessage, *, delay_seconds: float = 0, error: str = "",
    ) -> RetryResult: ...

    def heartbeat(
        self, message: QueueMessage, *, lease_seconds: float = 120,
    ) -> QueueMessage | None: ...

    def update_progress(
        self,
        message: QueueMessage,
        percent: float,
        stage: str,
        details: Mapping[str, Any] | None = None,
    ) -> bool: ...

    def get_progress(self, task_id: str) -> TaskProgress | None: ...

    def acquire_lock(
        self, name: str, owner: str, *, ttl_seconds: float = 120,
    ) -> LockLease | None: ...

    def renew_lock(
        self, lease: LockLease, *, ttl_seconds: float = 120,
    ) -> LockLease | None: ...

    def release_lock(self, lease: LockLease) -> bool: ...

    def publish_event(
        self,
        *,
        task_id: str,
        request_id: str,
        correlation_id: str,
        queue: str,
        state: str,
        attempt: int,
        worker_id: str = "",
        analytics: Mapping[str, Any] | None = None,
    ) -> TaskEvent: ...

    def read_events(
        self,
        group: str,
        consumer: str,
        *,
        count: int = 10,
        block_seconds: float = 0,
    ) -> list[EventDelivery]: ...

    def ack_event(self, group: str, event_id: str) -> bool: ...

    def retry_event(
        self,
        group: str,
        consumer: str,
        event_id: str,
        *,
        min_idle_seconds: float = 0,
    ) -> EventDelivery | None: ...


def _validated_name(value: str, label: str) -> str:
    clean = str(value or "").strip()
    if not _NAME_RE.fullmatch(clean):
        raise InvalidTask(
            f"{label} must be 1-128 characters using letters, digits, '.', '_', ':', or '-'."
        )
    return clean


def _validated_nonempty(value: str, label: str, max_length: int = 512) -> str:
    clean = str(value or "").strip()
    if not clean or len(clean) > max_length:
        raise InvalidTask(f"{label} must contain 1-{max_length} characters.")
    return clean


def _json_object(
    value: Mapping[str, Any] | None,
    *,
    label: str,
    max_bytes: int = 64 * 1024,
) -> tuple[dict[str, Any], str]:
    if value is None:
        normalized: dict[str, Any] = {}
    elif isinstance(value, Mapping):
        normalized = dict(value)
    else:
        raise InvalidTask(f"{label} must be a JSON object.")
    try:
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise InvalidTask(f"{label} must contain only finite JSON values.") from exc
    if len(encoded.encode("utf-8")) > max_bytes:
        raise InvalidTask(f"{label} exceeds the {max_bytes}-byte limit.")
    # Loading the canonical representation also prevents custom Mapping values
    # from escaping the simple JSON types promised by QueueMessage.
    return json.loads(encoded), encoded


def _event_analytics(
    value: Mapping[str, Any] | None,
) -> tuple[dict[str, str | int | float | bool], str]:
    """Allow only low-cardinality operational fields, never chat/task bodies."""

    result: dict[str, str | int | float | bool] = {}
    for raw_key, raw_value in dict(value or {}).items():
        key = str(raw_key)
        if key not in _EVENT_ANALYTICS_KEYS:
            raise InvalidTask(f"event analytics key is not allowed: {key}")
        if not isinstance(raw_value, (str, int, float, bool)) or raw_value is None:
            raise InvalidTask(f"event analytics value must be scalar: {key}")
        if isinstance(raw_value, float) and not math.isfinite(raw_value):
            raise InvalidTask(f"event analytics value must be finite: {key}")
        if isinstance(raw_value, str) and len(raw_value) > 128:
            raise InvalidTask(f"event analytics value is too long: {key}")
        result[key] = raw_value
    encoded = json.dumps(
        result,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )
    if len(encoded.encode("utf-8")) > 2048:
        raise InvalidTask("event analytics exceeds the 2048-byte limit.")
    return result, encoded


def _positive_seconds(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise InvalidTask(f"{label} must be a finite number greater than zero.")
    return number


def _nonnegative_seconds(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise InvalidTask(f"{label} must be a finite non-negative number.")
    return number


def _dedupe_digest(queue: str, dedupe_key: str) -> str:
    return hashlib.sha256(f"{queue}\0{dedupe_key}".encode()).hexdigest()


def _key_digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(slots=True)
class _LocalTask:
    task_id: str
    queue: str
    payload: dict[str, Any]
    status: str
    attempt: int
    max_attempts: int
    enqueued_at: float
    available_at: float
    updated_at: float
    request_id: str
    correlation_id: str
    dedupe_digest: str | None = None
    worker_id: str = ""
    receipt: str = ""
    lease_expires_at: float = 0
    last_error: str = ""
    result_expires_at: float = 0


@dataclass(slots=True)
class _LocalPendingEvent:
    consumer: str
    delivery_count: int
    delivered_at: float


@dataclass(slots=True)
class _LocalEventGroup:
    next_index: int = 0
    pending: dict[str, _LocalPendingEvent] = field(default_factory=dict)


@dataclass(slots=True)
class _LocalState:
    clock: Callable[[], float]
    condition: threading.Condition = field(
        default_factory=lambda: threading.Condition(threading.RLock())
    )
    tasks: dict[str, _LocalTask] = field(default_factory=dict)
    queues: dict[str, list[tuple[float, int, str]]] = field(default_factory=dict)
    progress: dict[str, TaskProgress] = field(default_factory=dict)
    dedupe: dict[str, tuple[str, float]] = field(default_factory=dict)
    locks: dict[str, LockLease] = field(default_factory=dict)
    events: list[TaskEvent] = field(default_factory=list)
    event_groups: dict[str, _LocalEventGroup] = field(default_factory=dict)
    sequence: int = 0
    event_sequence: int = 0


_LOCAL_STATES: dict[str, _LocalState] = {}
_LOCAL_STATES_LOCK = threading.Lock()


class LocalTaskQueue:
    """Thread-safe process-local fallback with Redis-equivalent lease fencing.

    The state is shared by namespace across LocalTaskQueue instances in one
    process. It is deliberately not durable or cross-process; deployments that
    need those guarantees must configure Redis rather than silently relying on
    this fallback.
    """

    def __init__(
        self,
        namespace: str = _DEFAULT_NAMESPACE,
        *,
        result_ttl_seconds: int = 86_400,
        clock: Callable[[], float] = time.time,
    ):
        self.namespace = _validated_name(namespace, "namespace")
        self.result_ttl_seconds = int(_positive_seconds(result_ttl_seconds, "result_ttl_seconds"))
        with _LOCAL_STATES_LOCK:
            self._state = _LOCAL_STATES.setdefault(self.namespace, _LocalState(clock=clock))

    def _append_event(
        self,
        *,
        task_id: str,
        request_id: str,
        correlation_id: str,
        queue: str,
        state: str,
        attempt: int,
        worker_id: str = "",
        analytics: Mapping[str, Any] | None = None,
    ) -> TaskEvent:
        if state not in _EVENT_STATES:
            raise InvalidTask(f"unsupported task event state: {state}")
        analytics_value, _encoded = _event_analytics(analytics)
        local = self._state
        occurred_at = local.clock()
        local.event_sequence += 1
        event = TaskEvent(
            event_id=f"{round(occurred_at * 1000)}-{local.event_sequence}",
            task_id=_validated_nonempty(task_id, "task_id"),
            request_id=_validated_nonempty(request_id, "request_id"),
            correlation_id=_validated_nonempty(correlation_id, "correlation_id"),
            queue=_validated_name(queue, "queue"),
            state=state,
            attempt=max(0, int(attempt)),
            worker_id=str(worker_id or "")[:512],
            occurred_at=occurred_at,
            analytics=analytics_value,
        )
        local.events.append(event)
        local.condition.notify_all()
        return event

    def _task_event(
        self,
        task: _LocalTask,
        state: str,
        analytics: Mapping[str, Any] | None = None,
        *,
        worker_id: str | None = None,
    ) -> TaskEvent:
        return self._append_event(
            task_id=task.task_id,
            request_id=task.request_id,
            correlation_id=task.correlation_id,
            queue=task.queue,
            state=state,
            attempt=task.attempt,
            worker_id=task.worker_id if worker_id is None else worker_id,
            analytics=analytics,
        )

    def _push(self, task: _LocalTask) -> None:
        self._state.sequence += 1
        heapq.heappush(
            self._state.queues.setdefault(task.queue, []),
            (task.available_at, self._state.sequence, task.task_id),
        )

    def _progress(
        self,
        task_id: str,
        status: str,
        percent: float,
        stage: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        normalized, _ = _json_object(details, label="progress details")
        self._state.progress[task_id] = TaskProgress(
            task_id=task_id,
            status=status,
            percent=max(0.0, min(100.0, float(percent))),
            stage=str(stage)[:200],
            details=normalized,
            updated_at=self._state.clock(),
        )

    def _cleanup(self, now: float) -> None:
        for digest, (_task_id, expires_at) in list(self._state.dedupe.items()):
            if expires_at <= now:
                self._state.dedupe.pop(digest, None)
        for name, lease in list(self._state.locks.items()):
            if lease.expires_at <= now:
                self._state.locks.pop(name, None)
        for task_id, task in list(self._state.tasks.items()):
            if task.result_expires_at and task.result_expires_at <= now:
                self._state.tasks.pop(task_id, None)
                self._state.progress.pop(task_id, None)

    def _requeue_expired(self, now: float) -> None:
        for task in list(self._state.tasks.values()):
            if task.status != "processing" or task.lease_expires_at > now:
                continue
            expired_worker = task.worker_id
            task.worker_id = ""
            task.receipt = ""
            task.lease_expires_at = 0
            task.updated_at = now
            task.last_error = "worker lease expired"
            if task.attempt >= task.max_attempts:
                task.status = "failed"
                task.result_expires_at = now + self.result_ttl_seconds
                self._progress(
                    task.task_id,
                    "failed",
                    self._state.progress.get(
                        task.task_id,
                        TaskProgress(task.task_id, "", 0, "", {}, now),
                    ).percent,
                    "failed",
                    {"error": task.last_error, "worker_id": expired_worker},
                )
                self._task_event(
                    task,
                    "failed",
                    {"error_code": "lease_expired", "max_attempts": task.max_attempts},
                    worker_id=expired_worker,
                )
            else:
                task.status = "queued"
                task.available_at = now
                self._push(task)
                self._progress(
                    task.task_id,
                    "queued",
                    self._state.progress.get(
                        task.task_id,
                        TaskProgress(task.task_id, "", 0, "", {}, now),
                    ).percent,
                    "retrying",
                    {"error": task.last_error, "attempt": task.attempt},
                )
                self._task_event(
                    task,
                    "queued",
                    {
                        "error_code": "lease_expired",
                        "max_attempts": task.max_attempts,
                        "will_retry": True,
                    },
                    worker_id=expired_worker,
                )

    def enqueue(
        self,
        queue: str,
        payload: Mapping[str, Any],
        *,
        task_id: str | None = None,
        dedupe_key: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
        dedupe_ttl_seconds: int = 86_400,
        max_attempts: int = 3,
        delay_seconds: float = 0,
    ) -> EnqueueResult:
        queue = _validated_name(queue, "queue")
        payload_value, _ = _json_object(payload, label="payload")
        task_id = _validated_nonempty(task_id or str(uuid.uuid4()), "task_id")
        request_id = _validated_nonempty(request_id or task_id, "request_id")
        correlation_id = _validated_nonempty(
            correlation_id or request_id, "correlation_id"
        )
        if not 1 <= int(max_attempts) <= 100:
            raise InvalidTask("max_attempts must be between 1 and 100.")
        delay_seconds = _nonnegative_seconds(delay_seconds, "delay_seconds")
        dedupe_ttl_seconds = int(_positive_seconds(dedupe_ttl_seconds, "dedupe_ttl_seconds"))
        digest = None
        if dedupe_key is not None:
            dedupe_key = _validated_nonempty(dedupe_key, "dedupe_key", 1000)
            digest = _dedupe_digest(queue, dedupe_key)

        state = self._state
        with state.condition:
            now = state.clock()
            self._cleanup(now)
            if digest is not None and digest in state.dedupe:
                existing_id, _expires_at = state.dedupe[digest]
                if existing_id in state.tasks:
                    return EnqueueResult(existing_id, False)
                state.dedupe.pop(digest, None)
            if task_id in state.tasks:
                return EnqueueResult(task_id, False)
            task = _LocalTask(
                task_id=task_id,
                queue=queue,
                payload=payload_value,
                status="queued",
                attempt=0,
                max_attempts=int(max_attempts),
                enqueued_at=now,
                available_at=now + delay_seconds,
                updated_at=now,
                request_id=request_id,
                correlation_id=correlation_id,
                dedupe_digest=digest,
            )
            state.tasks[task_id] = task
            if digest is not None:
                state.dedupe[digest] = (task_id, now + dedupe_ttl_seconds)
            self._push(task)
            self._progress(task_id, "queued", 0, "queued")
            self._task_event(task, "queued", {"max_attempts": task.max_attempts})
            state.condition.notify_all()
            return EnqueueResult(task_id, True)

    def _message(self, task: _LocalTask) -> QueueMessage:
        return QueueMessage(
            task_id=task.task_id,
            queue=task.queue,
            payload=dict(task.payload),
            attempt=task.attempt,
            max_attempts=task.max_attempts,
            enqueued_at=task.enqueued_at,
            available_at=task.available_at,
            worker_id=task.worker_id,
            receipt=task.receipt,
            lease_expires_at=task.lease_expires_at,
            request_id=task.request_id,
            correlation_id=task.correlation_id,
        )

    def dequeue(
        self,
        queue: str,
        worker_id: str,
        *,
        lease_seconds: float = 120,
        timeout_seconds: float = 0,
    ) -> QueueMessage | None:
        queue = _validated_name(queue, "queue")
        worker_id = _validated_nonempty(worker_id, "worker_id")
        lease_seconds = _positive_seconds(lease_seconds, "lease_seconds")
        timeout_seconds = _nonnegative_seconds(timeout_seconds, "timeout_seconds")
        state = self._state
        real_deadline = time.monotonic() + timeout_seconds

        with state.condition:
            while True:
                now = state.clock()
                self._cleanup(now)
                self._requeue_expired(now)
                heap = state.queues.setdefault(queue, [])
                while heap and heap[0][0] <= now:
                    _available_at, _sequence, task_id = heapq.heappop(heap)
                    task = state.tasks.get(task_id)
                    if task is None or task.status != "queued" or task.queue != queue:
                        continue
                    # A stale delayed-queue entry must not make a later retry run early.
                    if task.available_at > now:
                        self._push(task)
                        continue
                    task.status = "processing"
                    task.attempt += 1
                    task.worker_id = worker_id
                    task.receipt = str(uuid.uuid4())
                    task.lease_expires_at = now + lease_seconds
                    task.updated_at = now
                    self._progress(
                        task.task_id,
                        "processing",
                        self._state.progress[task.task_id].percent,
                        "processing",
                        {"attempt": task.attempt},
                    )
                    self._task_event(
                        task,
                        "running",
                        {"max_attempts": task.max_attempts},
                    )
                    return self._message(task)

                remaining = real_deadline - time.monotonic()
                if timeout_seconds == 0 or remaining <= 0:
                    return None
                wake_after = min(remaining, 0.25)
                if heap:
                    wake_after = min(wake_after, max(0.001, heap[0][0] - now))
                active_leases = [
                    task.lease_expires_at - now
                    for task in state.tasks.values()
                    if task.queue == queue and task.status == "processing"
                ]
                if active_leases:
                    wake_after = min(wake_after, max(0.001, min(active_leases)))
                state.condition.wait(wake_after)

    @staticmethod
    def _owns(task: _LocalTask, message: QueueMessage) -> bool:
        return (
            task.status == "processing"
            and task.worker_id == message.worker_id
            and task.receipt == message.receipt
        )

    def ack(self, message: QueueMessage) -> bool:
        state = self._state
        with state.condition:
            task = state.tasks.get(message.task_id)
            if task is None or not self._owns(task, message):
                return False
            now = state.clock()
            completed_worker = task.worker_id
            task.status = "complete"
            task.worker_id = ""
            task.receipt = ""
            task.lease_expires_at = 0
            task.updated_at = now
            task.result_expires_at = now + self.result_ttl_seconds
            # Do not retain possibly sensitive work payloads after completion.
            task.payload = {}
            self._progress(task.task_id, "complete", 100, "complete")
            self._task_event(task, "succeeded", worker_id=completed_worker)
            state.condition.notify_all()
            return True

    def retry(
        self, message: QueueMessage, *, delay_seconds: float = 0, error: str = "",
    ) -> RetryResult:
        delay_seconds = _nonnegative_seconds(delay_seconds, "delay_seconds")
        state = self._state
        with state.condition:
            task = state.tasks.get(message.task_id)
            if task is None or not self._owns(task, message):
                return RetryResult(False, False, False, message.attempt)
            now = state.clock()
            failed_worker = task.worker_id
            task.worker_id = ""
            task.receipt = ""
            task.lease_expires_at = 0
            task.updated_at = now
            task.last_error = str(error or "")[:1000]
            if task.attempt >= task.max_attempts:
                task.status = "failed"
                task.result_expires_at = now + self.result_ttl_seconds
                self._progress(
                    task.task_id,
                    "failed",
                    state.progress[task.task_id].percent,
                    "failed",
                    {"error": task.last_error, "attempt": task.attempt},
                )
                self._task_event(
                    task,
                    "failed",
                    {"error_code": "max_attempts", "max_attempts": task.max_attempts},
                    worker_id=failed_worker,
                )
                state.condition.notify_all()
                return RetryResult(True, False, True, task.attempt)
            task.status = "queued"
            task.available_at = now + delay_seconds
            self._push(task)
            self._progress(
                task.task_id,
                "queued",
                state.progress[task.task_id].percent,
                "retrying",
                {"error": task.last_error, "attempt": task.attempt},
            )
            self._task_event(
                task,
                "queued",
                {
                    "error_code": "retry_requested",
                    "max_attempts": task.max_attempts,
                    "retry_delay_ms": round(delay_seconds * 1000),
                    "will_retry": True,
                },
                worker_id=failed_worker,
            )
            state.condition.notify_all()
            return RetryResult(True, True, False, task.attempt)

    def heartbeat(
        self, message: QueueMessage, *, lease_seconds: float = 120,
    ) -> QueueMessage | None:
        lease_seconds = _positive_seconds(lease_seconds, "lease_seconds")
        state = self._state
        with state.condition:
            task = state.tasks.get(message.task_id)
            if task is None or not self._owns(task, message):
                return None
            task.lease_expires_at = state.clock() + lease_seconds
            task.updated_at = state.clock()
            state.condition.notify_all()
            return self._message(task)

    def update_progress(
        self,
        message: QueueMessage,
        percent: float,
        stage: str,
        details: Mapping[str, Any] | None = None,
    ) -> bool:
        if not math.isfinite(float(percent)) or not 0 <= float(percent) <= 100:
            raise InvalidTask("progress percent must be between 0 and 100.")
        stage = _validated_nonempty(stage, "stage", 200)
        # Validate before taking the lock so an invalid details object never
        # partially mutates progress.
        normalized, _ = _json_object(details, label="progress details")
        state = self._state
        with state.condition:
            task = state.tasks.get(message.task_id)
            if task is None or not self._owns(task, message):
                return False
            current = state.progress.get(message.task_id)
            # Progress is monotonic even when a client reports an older stage.
            next_percent = max(current.percent if current else 0, float(percent))
            self._progress(task.task_id, "processing", next_percent, stage, normalized)
            self._task_event(
                task,
                "running",
                {"progress_percent": next_percent, "stage": stage},
            )
            return True

    def get_progress(self, task_id: str) -> TaskProgress | None:
        task_id = _validated_nonempty(task_id, "task_id")
        state = self._state
        with state.condition:
            self._cleanup(state.clock())
            value = state.progress.get(task_id)
            if value is None:
                return None
            return TaskProgress(
                task_id=value.task_id,
                status=value.status,
                percent=value.percent,
                stage=value.stage,
                details=dict(value.details),
                updated_at=value.updated_at,
            )

    def acquire_lock(
        self, name: str, owner: str, *, ttl_seconds: float = 120,
    ) -> LockLease | None:
        name = _validated_nonempty(name, "lock name")
        owner = _validated_nonempty(owner, "lock owner")
        ttl_seconds = _positive_seconds(ttl_seconds, "ttl_seconds")
        state = self._state
        with state.condition:
            now = state.clock()
            self._cleanup(now)
            if name in state.locks:
                return None
            lease = LockLease(name, owner, str(uuid.uuid4()), now + ttl_seconds)
            state.locks[name] = lease
            return lease

    def renew_lock(
        self, lease: LockLease, *, ttl_seconds: float = 120,
    ) -> LockLease | None:
        ttl_seconds = _positive_seconds(ttl_seconds, "ttl_seconds")
        state = self._state
        with state.condition:
            now = state.clock()
            self._cleanup(now)
            current = state.locks.get(lease.name)
            if current is None or current.token != lease.token or current.owner != lease.owner:
                return None
            renewed = LockLease(lease.name, lease.owner, lease.token, now + ttl_seconds)
            state.locks[lease.name] = renewed
            return renewed

    def release_lock(self, lease: LockLease) -> bool:
        state = self._state
        with state.condition:
            self._cleanup(state.clock())
            current = state.locks.get(lease.name)
            if current is None or current.token != lease.token or current.owner != lease.owner:
                return False
            state.locks.pop(lease.name, None)
            state.condition.notify_all()
            return True

    def publish_event(
        self,
        *,
        task_id: str,
        request_id: str,
        correlation_id: str,
        queue: str,
        state: str,
        attempt: int,
        worker_id: str = "",
        analytics: Mapping[str, Any] | None = None,
    ) -> TaskEvent:
        local = self._state
        with local.condition:
            return self._append_event(
                task_id=task_id,
                request_id=request_id,
                correlation_id=correlation_id,
                queue=queue,
                state=state,
                attempt=attempt,
                worker_id=worker_id,
                analytics=analytics,
            )

    def read_events(
        self,
        group: str,
        consumer: str,
        *,
        count: int = 10,
        block_seconds: float = 0,
    ) -> list[EventDelivery]:
        group = _validated_name(group, "consumer group")
        consumer = _validated_name(consumer, "consumer")
        if not 1 <= int(count) <= 1000:
            raise InvalidTask("event count must be between 1 and 1000.")
        block_seconds = _nonnegative_seconds(block_seconds, "block_seconds")
        local = self._state
        deadline = time.monotonic() + block_seconds
        with local.condition:
            event_group = local.event_groups.setdefault(group, _LocalEventGroup())
            while event_group.next_index >= len(local.events):
                remaining = deadline - time.monotonic()
                if block_seconds == 0 or remaining <= 0:
                    return []
                local.condition.wait(remaining)
            events = local.events[
                event_group.next_index:event_group.next_index + int(count)
            ]
            event_group.next_index += len(events)
            delivered_at = local.clock()
            deliveries = []
            for event in events:
                pending = _LocalPendingEvent(consumer, 1, delivered_at)
                event_group.pending[event.event_id] = pending
                deliveries.append(EventDelivery(event, group, consumer, 1))
            return deliveries

    def ack_event(self, group: str, event_id: str) -> bool:
        group = _validated_name(group, "consumer group")
        event_id = _validated_nonempty(event_id, "event_id")
        local = self._state
        with local.condition:
            event_group = local.event_groups.get(group)
            return bool(event_group and event_group.pending.pop(event_id, None))

    def retry_event(
        self,
        group: str,
        consumer: str,
        event_id: str,
        *,
        min_idle_seconds: float = 0,
    ) -> EventDelivery | None:
        group = _validated_name(group, "consumer group")
        consumer = _validated_name(consumer, "consumer")
        event_id = _validated_nonempty(event_id, "event_id")
        min_idle_seconds = _nonnegative_seconds(min_idle_seconds, "min_idle_seconds")
        local = self._state
        with local.condition:
            event_group = local.event_groups.get(group)
            pending = event_group.pending.get(event_id) if event_group else None
            now = local.clock()
            if pending is None or now - pending.delivered_at < min_idle_seconds:
                return None
            event = next((item for item in local.events if item.event_id == event_id), None)
            if event is None:
                event_group.pending.pop(event_id, None)
                return None
            next_pending = _LocalPendingEvent(
                consumer=consumer,
                delivery_count=pending.delivery_count + 1,
                delivered_at=now,
            )
            event_group.pending[event_id] = next_pending
            return EventDelivery(
                event=event,
                group=group,
                consumer=consumer,
                delivery_count=next_pending.delivery_count,
            )


class _RedisClient(Protocol):
    def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any: ...

    def ping(self) -> Any: ...

    def xadd(self, name: str, fields: Mapping[str, Any], **kwargs: Any) -> Any: ...

    def xgroup_create(self, name: str, groupname: str, **kwargs: Any) -> Any: ...

    def xreadgroup(self, groupname: str, consumername: str, streams: Any, **kwargs: Any) -> Any: ...

    def xack(self, name: str, groupname: str, *ids: str) -> Any: ...

    def xclaim(
        self, name: str, groupname: str, consumername: str,
        min_idle_time: int, message_ids: list[str], **kwargs: Any,
    ) -> Any: ...


_ENQUEUE_SCRIPT = r"""
local existing = nil
if ARGV[9] == '1' then
  existing = redis.call('GET', KEYS[3])
  if existing then
    local existing_id = redis.call('HGET', existing, 'task_id')
    if existing_id then return {0, existing_id} end
    redis.call('DEL', KEYS[3])
  end
end
if redis.call('EXISTS', KEYS[1]) == 1 then
  return {0, redis.call('HGET', KEYS[1], 'task_id')}
end
redis.call('HSET', KEYS[1],
  'task_id', ARGV[1], 'queue', ARGV[2], 'payload', ARGV[3],
  'status', 'queued', 'attempt', '0', 'max_attempts', ARGV[4],
  'enqueued_at', ARGV[5], 'available_at', ARGV[6], 'updated_at', ARGV[5],
  'worker_id', '', 'receipt', '', 'lease_expires_at', '', 'last_error', '',
  'request_id', ARGV[10], 'correlation_id', ARGV[11])
redis.call('ZADD', KEYS[2], ARGV[6], KEYS[1])
redis.call('HSET', KEYS[4], 'task_id', ARGV[1], 'status', 'queued',
  'percent', '0', 'stage', 'queued', 'details', '{}', 'updated_at', ARGV[5])
if ARGV[9] == '1' then
  redis.call('SET', KEYS[3], KEYS[1], 'EX', ARGV[7])
end
redis.call('EXPIRE', KEYS[4], ARGV[8])
return {1, ARGV[1]}
"""


_DEQUEUE_SCRIPT = r"""
local expired = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', ARGV[1], 'LIMIT', 0, 100)
for _, task_key in ipairs(expired) do
  redis.call('ZREM', KEYS[2], task_key)
  if redis.call('HGET', task_key, 'status') == 'processing' then
    local attempt = tonumber(redis.call('HGET', task_key, 'attempt') or '0')
    local maximum = tonumber(redis.call('HGET', task_key, 'max_attempts') or '1')
    local suffix = string.sub(task_key, string.len(ARGV[7]) + 1)
    local progress_key = ARGV[8] .. suffix
    if attempt >= maximum then
      redis.call('HSET', task_key, 'status', 'failed', 'worker_id', '', 'receipt', '',
        'lease_expires_at', '', 'last_error', 'worker lease expired', 'updated_at', ARGV[1])
      redis.call('ZADD', KEYS[3], ARGV[1], task_key)
      redis.call('HSET', progress_key, 'status', 'failed', 'stage', 'failed',
        'details', '{"error":"worker lease expired"}', 'updated_at', ARGV[1])
      redis.call('EXPIRE', task_key, ARGV[6])
      redis.call('EXPIRE', progress_key, ARGV[6])
    else
      redis.call('HSET', task_key, 'status', 'queued', 'worker_id', '', 'receipt', '',
        'lease_expires_at', '', 'available_at', ARGV[1],
        'last_error', 'worker lease expired', 'updated_at', ARGV[1])
      redis.call('ZADD', KEYS[1], ARGV[1], task_key)
      redis.call('HSET', progress_key, 'status', 'queued', 'stage', 'retrying',
        'details', '{"error":"worker lease expired"}', 'updated_at', ARGV[1])
    end
  end
end
for _ = 1, 20 do
  local due = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, 1)
  if #due == 0 then return {} end
  local task_key = due[1]
  redis.call('ZREM', KEYS[1], task_key)
  if redis.call('HGET', task_key, 'status') == 'queued' then
    local attempt = redis.call('HINCRBY', task_key, 'attempt', 1)
    local lease_until = tonumber(ARGV[1]) + tonumber(ARGV[4])
    redis.call('HSET', task_key, 'status', 'processing', 'worker_id', ARGV[2],
      'receipt', ARGV[3], 'lease_expires_at', lease_until, 'updated_at', ARGV[1])
    redis.call('ZADD', KEYS[2], lease_until, task_key)
    local suffix = string.sub(task_key, string.len(ARGV[7]) + 1)
    local progress_key = ARGV[8] .. suffix
    redis.call('HSET', progress_key, 'status', 'processing', 'stage', 'processing',
      'details', '{"attempt":' .. attempt .. '}', 'updated_at', ARGV[1])
    redis.call('EXPIRE', progress_key, ARGV[6])
    return redis.call('HGETALL', task_key)
  end
end
return {}
"""


_ACK_SCRIPT = r"""
if redis.call('HGET', KEYS[1], 'status') ~= 'processing' or
   redis.call('HGET', KEYS[1], 'worker_id') ~= ARGV[1] or
   redis.call('HGET', KEYS[1], 'receipt') ~= ARGV[2] then return 0 end
redis.call('ZREM', KEYS[2], KEYS[1])
redis.call('HSET', KEYS[1], 'status', 'complete', 'worker_id', '', 'receipt', '',
  'lease_expires_at', '', 'updated_at', ARGV[3])
redis.call('HDEL', KEYS[1], 'payload')
redis.call('EXPIRE', KEYS[1], ARGV[4])
redis.call('HSET', KEYS[3], 'status', 'complete', 'percent', '100',
  'stage', 'complete', 'details', '{}', 'updated_at', ARGV[3])
redis.call('EXPIRE', KEYS[3], ARGV[4])
return 1
"""


_RETRY_SCRIPT = r"""
if redis.call('HGET', KEYS[1], 'status') ~= 'processing' or
   redis.call('HGET', KEYS[1], 'worker_id') ~= ARGV[1] or
   redis.call('HGET', KEYS[1], 'receipt') ~= ARGV[2] then return {0, 0, 0, 0} end
redis.call('ZREM', KEYS[3], KEYS[1])
local attempt = tonumber(redis.call('HGET', KEYS[1], 'attempt') or '0')
local maximum = tonumber(redis.call('HGET', KEYS[1], 'max_attempts') or '1')
if attempt >= maximum then
  redis.call('HSET', KEYS[1], 'status', 'failed', 'worker_id', '', 'receipt', '',
    'lease_expires_at', '', 'last_error', ARGV[5], 'updated_at', ARGV[3])
  redis.call('ZADD', KEYS[4], ARGV[3], KEYS[1])
  redis.call('EXPIRE', KEYS[1], ARGV[6])
  redis.call('HSET', KEYS[5], 'status', 'failed', 'stage', 'failed',
    'details', ARGV[7], 'updated_at', ARGV[3])
  redis.call('EXPIRE', KEYS[5], ARGV[6])
  return {1, 0, 1, attempt}
end
local available = tonumber(ARGV[3]) + tonumber(ARGV[4])
redis.call('HSET', KEYS[1], 'status', 'queued', 'worker_id', '', 'receipt', '',
  'lease_expires_at', '', 'available_at', available,
  'last_error', ARGV[5], 'updated_at', ARGV[3])
redis.call('ZADD', KEYS[2], available, KEYS[1])
redis.call('HSET', KEYS[5], 'status', 'queued', 'stage', 'retrying',
  'details', ARGV[7], 'updated_at', ARGV[3])
return {1, 1, 0, attempt}
"""


_HEARTBEAT_SCRIPT = r"""
if redis.call('HGET', KEYS[1], 'status') ~= 'processing' or
   redis.call('HGET', KEYS[1], 'worker_id') ~= ARGV[1] or
   redis.call('HGET', KEYS[1], 'receipt') ~= ARGV[2] then return 0 end
local lease_until = tonumber(ARGV[3]) + tonumber(ARGV[4])
redis.call('HSET', KEYS[1], 'lease_expires_at', lease_until, 'updated_at', ARGV[3])
redis.call('ZADD', KEYS[2], lease_until, KEYS[1])
return lease_until
"""


_PROGRESS_SCRIPT = r"""
if redis.call('HGET', KEYS[1], 'status') ~= 'processing' or
   redis.call('HGET', KEYS[1], 'worker_id') ~= ARGV[1] or
   redis.call('HGET', KEYS[1], 'receipt') ~= ARGV[2] then return 0 end
local previous = tonumber(redis.call('HGET', KEYS[2], 'percent') or '0')
local requested = tonumber(ARGV[3])
if requested < previous then requested = previous end
redis.call('HSET', KEYS[2], 'task_id', ARGV[7], 'status', 'processing',
  'percent', requested, 'stage', ARGV[4], 'details', ARGV[5], 'updated_at', ARGV[6])
redis.call('EXPIRE', KEYS[2], ARGV[8])
return 1
"""


_RENEW_LOCK_SCRIPT = r"""
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('PEXPIRE', KEYS[1], ARGV[2])
return 1
"""


_RELEASE_LOCK_SCRIPT = r"""
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
return redis.call('DEL', KEYS[1])
"""


class RedisTaskQueue:
    """Redis-backed queue using Lua scripts for atomic ownership transitions."""

    def __init__(
        self,
        client: _RedisClient,
        namespace: str = _DEFAULT_NAMESPACE,
        *,
        result_ttl_seconds: int = 86_400,
        poll_interval_seconds: float = 0.1,
        event_stream_maxlen: int = 100_000,
        clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.client = client
        self.namespace = _validated_name(namespace, "namespace")
        self.result_ttl_seconds = int(_positive_seconds(result_ttl_seconds, "result_ttl_seconds"))
        self.poll_interval_seconds = _positive_seconds(
            poll_interval_seconds, "poll_interval_seconds"
        )
        if not 100 <= int(event_stream_maxlen) <= 10_000_000:
            raise InvalidTask("event_stream_maxlen must be between 100 and 10000000.")
        self.event_stream_maxlen = int(event_stream_maxlen)
        self.clock = clock
        self.sleeper = sleeper
        self._prefix = f"{self.namespace}:taskq:"
        self._task_prefix = f"{self._prefix}task:"
        self._progress_prefix = f"{self._prefix}progress:"
        self._event_stream_key = f"{self._prefix}events"

    def _queue_key(self, queue: str) -> str:
        return f"{self._prefix}queue:{queue}"

    def _processing_key(self, queue: str) -> str:
        return f"{self._prefix}processing:{queue}"

    def _dead_key(self, queue: str) -> str:
        return f"{self._prefix}dead:{queue}"

    def _task_key(self, task_id: str) -> str:
        return f"{self._task_prefix}{_key_digest(task_id)}"

    def _progress_key(self, task_id: str) -> str:
        return f"{self._progress_prefix}{_key_digest(task_id)}"

    def _publish_transition_event(self, **values: Any) -> None:
        """Do not roll back completed work if the observability stream is full/down.

        Queue state remains the source of truth and an administrator can
        reconcile it after a Redis Stream write failure. Explicit
        ``publish_event`` calls still raise so analytics producers can choose
        their own retry policy.
        """

        try:
            self.publish_event(**values)
        except Exception:
            logger.exception("Could not publish Redis task transition event")

    @staticmethod
    def _decode(value: Any) -> str:
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)

    @classmethod
    def _hash_result(cls, value: Any) -> dict[str, str]:
        if isinstance(value, Mapping):
            return {cls._decode(key): cls._decode(item) for key, item in value.items()}
        items = list(value or [])
        return {
            cls._decode(items[index]): cls._decode(items[index + 1])
            for index in range(0, len(items) - 1, 2)
        }

    def enqueue(
        self,
        queue: str,
        payload: Mapping[str, Any],
        *,
        task_id: str | None = None,
        dedupe_key: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
        dedupe_ttl_seconds: int = 86_400,
        max_attempts: int = 3,
        delay_seconds: float = 0,
    ) -> EnqueueResult:
        queue = _validated_name(queue, "queue")
        _payload, payload_json = _json_object(payload, label="payload")
        task_id = _validated_nonempty(task_id or str(uuid.uuid4()), "task_id")
        request_id = _validated_nonempty(request_id or task_id, "request_id")
        correlation_id = _validated_nonempty(
            correlation_id or request_id, "correlation_id"
        )
        if not 1 <= int(max_attempts) <= 100:
            raise InvalidTask("max_attempts must be between 1 and 100.")
        delay_seconds = _nonnegative_seconds(delay_seconds, "delay_seconds")
        dedupe_ttl_seconds = int(_positive_seconds(dedupe_ttl_seconds, "dedupe_ttl_seconds"))
        digest = _dedupe_digest(
            queue, _validated_nonempty(dedupe_key, "dedupe_key", 1000)
        ) if dedupe_key is not None else _key_digest(task_id)
        now = self.clock()
        result = self.client.eval(
            _ENQUEUE_SCRIPT,
            4,
            self._task_key(task_id),
            self._queue_key(queue),
            f"{self._prefix}dedupe:{digest}",
            self._progress_key(task_id),
            task_id,
            queue,
            payload_json,
            int(max_attempts),
            now,
            now + delay_seconds,
            dedupe_ttl_seconds,
            self.result_ttl_seconds,
            1 if dedupe_key is not None else 0,
            request_id,
            correlation_id,
        )
        values = list(result or [])
        if len(values) < 2:
            raise QueueUnavailable("Redis returned an invalid enqueue response.")
        enqueue_result = EnqueueResult(self._decode(values[1]), bool(int(values[0])))
        if enqueue_result.created:
            self._publish_transition_event(
                task_id=task_id,
                request_id=request_id,
                correlation_id=correlation_id,
                queue=queue,
                state="queued",
                attempt=0,
                analytics={"max_attempts": int(max_attempts)},
            )
        return enqueue_result

    def _message_from_hash(self, values: Any) -> QueueMessage | None:
        row = self._hash_result(values)
        if not row:
            return None
        try:
            payload = json.loads(row.get("payload") or "{}")
            if not isinstance(payload, dict):
                raise TypeError("payload is not an object")
            return QueueMessage(
                task_id=row["task_id"],
                queue=row["queue"],
                payload=payload,
                attempt=int(row["attempt"]),
                max_attempts=int(row["max_attempts"]),
                enqueued_at=float(row["enqueued_at"]),
                available_at=float(row["available_at"]),
                worker_id=row["worker_id"],
                receipt=row["receipt"],
                lease_expires_at=float(row["lease_expires_at"]),
                request_id=row.get("request_id") or row["task_id"],
                correlation_id=row.get("correlation_id") or row.get("request_id") or row["task_id"],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise QueueUnavailable("Redis returned a malformed task record.") from exc

    def dequeue(
        self,
        queue: str,
        worker_id: str,
        *,
        lease_seconds: float = 120,
        timeout_seconds: float = 0,
    ) -> QueueMessage | None:
        queue = _validated_name(queue, "queue")
        worker_id = _validated_nonempty(worker_id, "worker_id")
        lease_seconds = _positive_seconds(lease_seconds, "lease_seconds")
        timeout_seconds = _nonnegative_seconds(timeout_seconds, "timeout_seconds")
        deadline = time.monotonic() + timeout_seconds
        while True:
            now = self.clock()
            receipt = str(uuid.uuid4())
            result = self.client.eval(
                _DEQUEUE_SCRIPT,
                3,
                self._queue_key(queue),
                self._processing_key(queue),
                self._dead_key(queue),
                now,
                worker_id,
                receipt,
                lease_seconds,
                queue,
                self.result_ttl_seconds,
                self._task_prefix,
                self._progress_prefix,
            )
            message = self._message_from_hash(result)
            if message is not None:
                self._publish_transition_event(
                    task_id=message.task_id,
                    request_id=message.request_id,
                    correlation_id=message.correlation_id,
                    queue=message.queue,
                    state="running",
                    attempt=message.attempt,
                    worker_id=message.worker_id,
                    analytics={"max_attempts": message.max_attempts},
                )
                return message
            remaining = deadline - time.monotonic()
            if timeout_seconds == 0 or remaining <= 0:
                return None
            self.sleeper(min(self.poll_interval_seconds, remaining))

    def ack(self, message: QueueMessage) -> bool:
        acknowledged = bool(self.client.eval(
            _ACK_SCRIPT,
            3,
            self._task_key(message.task_id),
            self._processing_key(message.queue),
            self._progress_key(message.task_id),
            message.worker_id,
            message.receipt,
            self.clock(),
            self.result_ttl_seconds,
        ))
        if acknowledged:
            self._publish_transition_event(
                task_id=message.task_id,
                request_id=message.request_id,
                correlation_id=message.correlation_id,
                queue=message.queue,
                state="succeeded",
                attempt=message.attempt,
                worker_id=message.worker_id,
            )
        return acknowledged

    def retry(
        self, message: QueueMessage, *, delay_seconds: float = 0, error: str = "",
    ) -> RetryResult:
        delay_seconds = _nonnegative_seconds(delay_seconds, "delay_seconds")
        detail = json.dumps(
            {"error": str(error or "")[:1000], "attempt": message.attempt},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        result = list(self.client.eval(
            _RETRY_SCRIPT,
            5,
            self._task_key(message.task_id),
            self._queue_key(message.queue),
            self._processing_key(message.queue),
            self._dead_key(message.queue),
            self._progress_key(message.task_id),
            message.worker_id,
            message.receipt,
            self.clock(),
            delay_seconds,
            str(error or "")[:1000],
            self.result_ttl_seconds,
            detail,
        ) or [])
        if len(result) < 4:
            raise QueueUnavailable("Redis returned an invalid retry response.")
        retry_result = RetryResult(
            *(bool(int(value)) for value in result[:3]), int(result[3])
        )
        if retry_result.accepted:
            self._publish_transition_event(
                task_id=message.task_id,
                request_id=message.request_id,
                correlation_id=message.correlation_id,
                queue=message.queue,
                state="queued" if retry_result.requeued else "failed",
                attempt=retry_result.attempt,
                worker_id=message.worker_id,
                analytics={
                    "error_code": "retry_requested" if retry_result.requeued else "max_attempts",
                    "max_attempts": message.max_attempts,
                    "retry_delay_ms": round(delay_seconds * 1000),
                    "will_retry": retry_result.requeued,
                },
            )
        return retry_result

    def heartbeat(
        self, message: QueueMessage, *, lease_seconds: float = 120,
    ) -> QueueMessage | None:
        lease_seconds = _positive_seconds(lease_seconds, "lease_seconds")
        lease_until = self.client.eval(
            _HEARTBEAT_SCRIPT,
            2,
            self._task_key(message.task_id),
            self._processing_key(message.queue),
            message.worker_id,
            message.receipt,
            self.clock(),
            lease_seconds,
        )
        if not lease_until:
            return None
        return QueueMessage(
            task_id=message.task_id,
            queue=message.queue,
            payload=dict(message.payload),
            attempt=message.attempt,
            max_attempts=message.max_attempts,
            enqueued_at=message.enqueued_at,
            available_at=message.available_at,
            worker_id=message.worker_id,
            receipt=message.receipt,
            lease_expires_at=float(lease_until),
            request_id=message.request_id,
            correlation_id=message.correlation_id,
        )

    def update_progress(
        self,
        message: QueueMessage,
        percent: float,
        stage: str,
        details: Mapping[str, Any] | None = None,
    ) -> bool:
        if not math.isfinite(float(percent)) or not 0 <= float(percent) <= 100:
            raise InvalidTask("progress percent must be between 0 and 100.")
        stage = _validated_nonempty(stage, "stage", 200)
        _details, details_json = _json_object(details, label="progress details")
        updated = bool(self.client.eval(
            _PROGRESS_SCRIPT,
            2,
            self._task_key(message.task_id),
            self._progress_key(message.task_id),
            message.worker_id,
            message.receipt,
            float(percent),
            stage,
            details_json,
            self.clock(),
            message.task_id,
            self.result_ttl_seconds,
        ))
        if updated:
            self._publish_transition_event(
                task_id=message.task_id,
                request_id=message.request_id,
                correlation_id=message.correlation_id,
                queue=message.queue,
                state="running",
                attempt=message.attempt,
                worker_id=message.worker_id,
                analytics={"progress_percent": float(percent), "stage": stage},
            )
        return updated

    def get_progress(self, task_id: str) -> TaskProgress | None:
        task_id = _validated_nonempty(task_id, "task_id")
        # A tiny Lua read keeps this module compatible with clients that only
        # expose eval through a narrow adapter.
        result = self.client.eval(
            "return redis.call('HGETALL', KEYS[1])", 1, self._progress_key(task_id)
        )
        row = self._hash_result(result)
        if not row:
            return None
        try:
            details = json.loads(row.get("details") or "{}")
            return TaskProgress(
                task_id=row.get("task_id") or task_id,
                status=row["status"],
                percent=float(row["percent"]),
                stage=row["stage"],
                details=details if isinstance(details, dict) else {},
                updated_at=float(row["updated_at"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise QueueUnavailable("Redis returned malformed progress state.") from exc

    def acquire_lock(
        self, name: str, owner: str, *, ttl_seconds: float = 120,
    ) -> LockLease | None:
        name = _validated_nonempty(name, "lock name")
        owner = _validated_nonempty(owner, "lock owner")
        ttl_seconds = _positive_seconds(ttl_seconds, "ttl_seconds")
        token = str(uuid.uuid4())
        value = f"{owner}\0{token}"
        key = f"{self._prefix}lock:{_key_digest(name)}"
        result = self.client.eval(
            "if redis.call('SET', KEYS[1], ARGV[1], 'NX', 'PX', ARGV[2]) "
            "then return 1 else return 0 end",
            1,
            key,
            value,
            round(ttl_seconds * 1000),
        )
        if not result:
            return None
        return LockLease(name, owner, token, self.clock() + ttl_seconds)

    def renew_lock(
        self, lease: LockLease, *, ttl_seconds: float = 120,
    ) -> LockLease | None:
        ttl_seconds = _positive_seconds(ttl_seconds, "ttl_seconds")
        key = f"{self._prefix}lock:{_key_digest(lease.name)}"
        value = f"{lease.owner}\0{lease.token}"
        renewed = self.client.eval(
            _RENEW_LOCK_SCRIPT, 1, key, value, round(ttl_seconds * 1000)
        )
        if not renewed:
            return None
        return LockLease(lease.name, lease.owner, lease.token, self.clock() + ttl_seconds)

    def release_lock(self, lease: LockLease) -> bool:
        key = f"{self._prefix}lock:{_key_digest(lease.name)}"
        value = f"{lease.owner}\0{lease.token}"
        return bool(self.client.eval(_RELEASE_LOCK_SCRIPT, 1, key, value))

    def publish_event(
        self,
        *,
        task_id: str,
        request_id: str,
        correlation_id: str,
        queue: str,
        state: str,
        attempt: int,
        worker_id: str = "",
        analytics: Mapping[str, Any] | None = None,
    ) -> TaskEvent:
        task_id = _validated_nonempty(task_id, "task_id")
        request_id = _validated_nonempty(request_id, "request_id")
        correlation_id = _validated_nonempty(correlation_id, "correlation_id")
        queue = _validated_name(queue, "queue")
        if state not in _EVENT_STATES:
            raise InvalidTask(f"unsupported task event state: {state}")
        analytics_value, analytics_json = _event_analytics(analytics)
        occurred_at = self.clock()
        event_id = self.client.xadd(
            self._event_stream_key,
            {
                "task_id": task_id,
                "request_id": request_id,
                "correlation_id": correlation_id,
                "queue": queue,
                "state": state,
                "attempt": max(0, int(attempt)),
                "worker_id": str(worker_id or "")[:512],
                "occurred_at": occurred_at,
                "analytics": analytics_json,
            },
            maxlen=self.event_stream_maxlen,
            approximate=True,
        )
        return TaskEvent(
            event_id=self._decode(event_id),
            task_id=task_id,
            request_id=request_id,
            correlation_id=correlation_id,
            queue=queue,
            state=state,
            attempt=max(0, int(attempt)),
            worker_id=str(worker_id or "")[:512],
            occurred_at=occurred_at,
            analytics=analytics_value,
        )

    def _stream_event(self, event_id: Any, fields: Any) -> TaskEvent:
        row = self._hash_result(fields)
        try:
            analytics = json.loads(row.get("analytics") or "{}")
            return TaskEvent(
                event_id=self._decode(event_id),
                task_id=row["task_id"],
                request_id=row["request_id"],
                correlation_id=row["correlation_id"],
                queue=row["queue"],
                state=row["state"],
                attempt=int(row["attempt"]),
                worker_id=row.get("worker_id", ""),
                occurred_at=float(row["occurred_at"]),
                analytics=analytics if isinstance(analytics, dict) else {},
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise QueueUnavailable("Redis returned a malformed task event.") from exc

    def _ensure_event_group(self, group: str) -> None:
        try:
            self.client.xgroup_create(
                self._event_stream_key,
                group,
                id="0",
                mkstream=True,
            )
        except Exception as exc:
            # Redis reports an existing consumer group as BUSYGROUP. Any other
            # failure is operational and must not be disguised as an empty stream.
            if "BUSYGROUP" not in str(exc).upper():
                raise QueueUnavailable("Redis event consumer group is unavailable.") from exc

    def read_events(
        self,
        group: str,
        consumer: str,
        *,
        count: int = 10,
        block_seconds: float = 0,
    ) -> list[EventDelivery]:
        group = _validated_name(group, "consumer group")
        consumer = _validated_name(consumer, "consumer")
        if not 1 <= int(count) <= 1000:
            raise InvalidTask("event count must be between 1 and 1000.")
        block_seconds = _nonnegative_seconds(block_seconds, "block_seconds")
        self._ensure_event_group(group)
        kwargs: dict[str, Any] = {"count": int(count)}
        if block_seconds > 0:
            kwargs["block"] = max(1, round(block_seconds * 1000))
        response = self.client.xreadgroup(
            group,
            consumer,
            {self._event_stream_key: ">"},
            **kwargs,
        )
        deliveries: list[EventDelivery] = []
        for _stream, entries in response or []:
            for event_id, fields in entries:
                deliveries.append(
                    EventDelivery(
                        event=self._stream_event(event_id, fields),
                        group=group,
                        consumer=consumer,
                        delivery_count=1,
                    )
                )
        return deliveries

    def ack_event(self, group: str, event_id: str) -> bool:
        group = _validated_name(group, "consumer group")
        event_id = _validated_nonempty(event_id, "event_id")
        self._ensure_event_group(group)
        return bool(self.client.xack(self._event_stream_key, group, event_id))

    def retry_event(
        self,
        group: str,
        consumer: str,
        event_id: str,
        *,
        min_idle_seconds: float = 0,
    ) -> EventDelivery | None:
        group = _validated_name(group, "consumer group")
        consumer = _validated_name(consumer, "consumer")
        event_id = _validated_nonempty(event_id, "event_id")
        min_idle_seconds = _nonnegative_seconds(min_idle_seconds, "min_idle_seconds")
        self._ensure_event_group(group)
        claimed = self.client.xclaim(
            self._event_stream_key,
            group,
            consumer,
            round(min_idle_seconds * 1000),
            [event_id],
        )
        if not claimed:
            return None
        claimed_id, fields = claimed[0]
        delivery_count = 2
        pending_reader = getattr(self.client, "xpending_range", None)
        if pending_reader is not None:
            try:
                pending = pending_reader(
                    self._event_stream_key,
                    group,
                    min=event_id,
                    max=event_id,
                    count=1,
                )
                if pending:
                    item = pending[0]
                    if isinstance(item, Mapping):
                        delivery_count = int(
                            item.get("times_delivered")
                            or item.get(b"times_delivered")
                            or delivery_count
                        )
            except Exception:
                logger.debug("Could not read Redis event delivery count", exc_info=True)
        return EventDelivery(
            event=self._stream_event(claimed_id, fields),
            group=group,
            consumer=consumer,
            delivery_count=delivery_count,
        )


def create_task_queue(
    redis_url: str | None = None,
    *,
    namespace: str = _DEFAULT_NAMESPACE,
    fallback_on_redis_error: bool = False,
    result_ttl_seconds: int = 86_400,
) -> TaskQueue:
    """Create the configured queue without weakening distributed guarantees.

    With no URL, this intentionally returns the process-local backend. If a
    Redis URL is configured, connection/import failures are fatal by default;
    silently splitting workers across independent local queues would permit
    duplicate GPU work. A development environment may opt into that behavior
    with ``fallback_on_redis_error=True``.
    """

    resolved_url = redis_url if redis_url is not None else os.getenv("MEMORYPAL_REDIS_URL", "")
    if not str(resolved_url or "").strip():
        logger.info("MEMORYPAL_REDIS_URL is unset; using the process-local task queue")
        return LocalTaskQueue(namespace, result_ttl_seconds=result_ttl_seconds)
    try:
        import redis  # type: ignore[import-not-found]

        client = redis.Redis.from_url(
            str(resolved_url),
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=5,
            health_check_interval=30,
        )
        client.ping()
        return RedisTaskQueue(
            client,
            namespace,
            result_ttl_seconds=result_ttl_seconds,
        )
    except Exception as exc:
        if not fallback_on_redis_error:
            raise QueueUnavailable("Configured Redis task queue is unavailable.") from exc
        logger.warning(
            "Redis task queue is unavailable; using non-distributed local fallback",
            exc_info=exc,
        )
        return LocalTaskQueue(namespace, result_ttl_seconds=result_ttl_seconds)


__all__ = [
    "EnqueueResult",
    "EventDelivery",
    "InvalidTask",
    "LocalTaskQueue",
    "LockLease",
    "QueueError",
    "QueueMessage",
    "QueueUnavailable",
    "RedisTaskQueue",
    "RetryResult",
    "TaskProgress",
    "TaskEvent",
    "TaskQueue",
    "create_task_queue",
]
