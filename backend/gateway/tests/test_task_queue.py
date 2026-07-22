from __future__ import annotations

import sys
import uuid

import pytest

from memorypal_api.services.task_queue import (
    InvalidTask,
    LocalTaskQueue,
    QueueUnavailable,
    RedisTaskQueue,
    create_task_queue,
)


class FakeClock:
    def __init__(self, value: float = 1_000.0):
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def local_queue(clock: FakeClock | None = None) -> LocalTaskQueue:
    return LocalTaskQueue(
        f"test-{uuid.uuid4().hex}",
        clock=clock or FakeClock(),
        result_ttl_seconds=3600,
    )


def test_local_queue_json_dedupe_progress_ack_and_state_events():
    clock = FakeClock()
    queue = local_queue(clock)
    payload = {"user_id": "사용자-1", "persona": "default", "counts": [1, 2]}

    first = queue.enqueue(
        "portrait",
        payload,
        dedupe_key="portrait:사용자-1",
        request_id="request-1",
        correlation_id="correlation-1",
    )
    duplicate = queue.enqueue(
        "portrait",
        {"ignored": True},
        dedupe_key="portrait:사용자-1",
        request_id="request-2",
    )

    assert first.created is True
    assert duplicate.created is False
    assert duplicate.task_id == first.task_id
    assert queue.get_progress(first.task_id).status == "queued"

    message = queue.dequeue("portrait", "worker-1", lease_seconds=60)
    assert message is not None
    assert message.payload == payload
    assert message.request_id == "request-1"
    assert message.correlation_id == "correlation-1"
    assert message.attempt == 1
    assert queue.update_progress(
        message, 35, "session_summary", {"session_count": 3, "message_count": 8}
    )
    # A stale progress update cannot move the public value backwards.
    assert queue.update_progress(message, 20, "session_summary")
    assert queue.get_progress(first.task_id).percent == 35
    assert queue.ack(message)
    assert not queue.ack(message)
    assert queue.get_progress(first.task_id).status == "complete"
    assert queue.get_progress(first.task_id).percent == 100

    deliveries = queue.read_events("admin-analytics", "consumer-1", count=20)
    assert [item.event.state for item in deliveries] == [
        "queued", "running", "running", "running", "succeeded",
    ]
    assert all(item.event.request_id == "request-1" for item in deliveries)
    # Events contain operational metadata, never the JSON task payload.
    assert "사용자-1" not in repr([item.event.analytics for item in deliveries])

    retried = queue.retry_event(
        "admin-analytics", "consumer-2", deliveries[0].event.event_id
    )
    assert retried is not None
    assert retried.delivery_count == 2
    assert retried.consumer == "consumer-2"
    assert queue.ack_event("admin-analytics", retried.event.event_id)
    assert not queue.ack_event("admin-analytics", retried.event.event_id)


def test_retry_is_fenced_and_exhausts_at_max_attempts():
    clock = FakeClock()
    queue = local_queue(clock)
    task = queue.enqueue("portrait", {"generation_id": "g1"}, max_attempts=2)

    first = queue.dequeue("portrait", "worker-1", lease_seconds=30)
    assert first is not None
    retry = queue.retry(first, delay_seconds=5, error="temporary upstream error")
    assert retry.accepted and retry.requeued and not retry.exhausted
    assert queue.dequeue("portrait", "worker-2") is None

    clock.advance(5)
    second = queue.dequeue("portrait", "worker-2", lease_seconds=30)
    assert second is not None
    assert second.task_id == task.task_id
    assert second.attempt == 2
    assert not queue.ack(first)
    assert not queue.update_progress(first, 80, "stale-worker")

    exhausted = queue.retry(second, error="still unavailable")
    assert exhausted.accepted and exhausted.exhausted and not exhausted.requeued
    assert queue.dequeue("portrait", "worker-3") is None
    progress = queue.get_progress(task.task_id)
    assert progress.status == "failed"
    assert progress.details["attempt"] == 2


def test_expired_worker_lease_requeues_and_rejects_stale_receipt():
    clock = FakeClock()
    queue = local_queue(clock)
    task = queue.enqueue("portrait", {"generation_id": "g1"}, max_attempts=3)
    first = queue.dequeue("portrait", "worker-1", lease_seconds=10)
    assert first is not None

    clock.advance(11)
    resumed = queue.dequeue("portrait", "worker-2", lease_seconds=10)
    assert resumed is not None
    assert resumed.task_id == task.task_id
    assert resumed.attempt == 2
    assert resumed.receipt != first.receipt
    assert not queue.ack(first)
    assert queue.heartbeat(first) is None
    assert queue.ack(resumed)


def test_local_lock_is_shared_by_namespace_and_token_fenced():
    clock = FakeClock()
    namespace = f"test-{uuid.uuid4().hex}"
    first_queue = LocalTaskQueue(namespace, clock=clock)
    second_queue = LocalTaskQueue(namespace, clock=clock)

    first = first_queue.acquire_lock("portrait:gpu", "worker-1", ttl_seconds=10)
    assert first is not None
    assert second_queue.acquire_lock("portrait:gpu", "worker-2", ttl_seconds=10) is None
    renewed = first_queue.renew_lock(first, ttl_seconds=20)
    assert renewed is not None
    assert renewed.token == first.token
    assert second_queue.release_lock(
        type(first)(first.name, "worker-2", "wrong-token", first.expires_at)
    ) is False
    assert first_queue.release_lock(renewed)
    assert second_queue.acquire_lock("portrait:gpu", "worker-2", ttl_seconds=10)


def test_invalid_json_and_sensitive_event_fields_are_rejected():
    queue = local_queue()
    with pytest.raises(InvalidTask):
        queue.enqueue("portrait", {"bad": float("nan")})
    with pytest.raises(InvalidTask):
        queue.enqueue("portrait", {"bad": object()})
    with pytest.raises(InvalidTask):
        queue.publish_event(
            task_id="task",
            request_id="request",
            correlation_id="correlation",
            queue="portrait",
            state="running",
            attempt=1,
            analytics={"conversation_text": "민감한 본문"},
        )


def test_factory_uses_local_without_redis_and_fails_closed_when_configured(monkeypatch):
    monkeypatch.delenv("MEMORYPAL_REDIS_URL", raising=False)
    assert isinstance(
        create_task_queue(namespace=f"test-{uuid.uuid4().hex}"), LocalTaskQueue
    )

    # The repository intentionally keeps redis-py optional until the integration
    # point adds the deployment dependency.
    monkeypatch.setitem(sys.modules, "redis", None)
    with pytest.raises(QueueUnavailable):
        create_task_queue("redis://127.0.0.1:6379/0")
    assert isinstance(
        create_task_queue(
            "redis://127.0.0.1:6379/0",
            namespace=f"test-{uuid.uuid4().hex}",
            fallback_on_redis_error=True,
        ),
        LocalTaskQueue,
    )


class FakeStreamRedis:
    """Small stream-only double; queue transition scripts are tested locally."""

    def __init__(self):
        self.events: list[tuple[str, dict[str, object]]] = []
        self.groups: dict[str, int] = {}
        self.pending: dict[tuple[str, str], dict[str, object]] = {}

    def eval(self, _script, _numkeys, *_args):
        raise AssertionError("this test only exercises Redis Stream methods")

    def ping(self):
        return True

    def xadd(self, _name, fields, **_kwargs):
        event_id = f"{len(self.events) + 1}-0"
        self.events.append((event_id, dict(fields)))
        return event_id

    def xgroup_create(self, _name, groupname, **_kwargs):
        if groupname in self.groups:
            raise RuntimeError("BUSYGROUP Consumer Group name already exists")
        self.groups[groupname] = 0

    def xreadgroup(self, groupname, consumername, _streams, **kwargs):
        start = self.groups[groupname]
        selected = self.events[start:start + kwargs.get("count", 10)]
        self.groups[groupname] += len(selected)
        for event_id, _fields in selected:
            self.pending[(groupname, event_id)] = {
                "consumer": consumername,
                "times_delivered": 1,
            }
        return [("events", selected)] if selected else []

    def xack(self, _name, groupname, *ids):
        removed = 0
        for event_id in ids:
            removed += bool(self.pending.pop((groupname, event_id), None))
        return removed

    def xclaim(self, _name, groupname, consumername, _min_idle, message_ids, **_kwargs):
        result = []
        for event_id in message_ids:
            pending = self.pending.get((groupname, event_id))
            if pending is None:
                continue
            pending["consumer"] = consumername
            pending["times_delivered"] = int(pending["times_delivered"]) + 1
            result.extend(item for item in self.events if item[0] == event_id)
        return result

    def xpending_range(self, _name, groupname, min, max, count):
        pending = self.pending.get((groupname, min))
        return [pending] if pending and min == max and count else []


def test_redis_stream_event_group_ack_and_retry_contract():
    clock = FakeClock()
    client = FakeStreamRedis()
    queue = RedisTaskQueue(client, "test-stream", clock=clock)
    published = queue.publish_event(
        task_id="task-1",
        request_id="request-1",
        correlation_id="correlation-1",
        queue="portrait",
        state="running",
        attempt=1,
        worker_id="worker-1",
        analytics={"stage": "summarizing", "session_count": 4},
    )
    assert published.event_id == "1-0"

    deliveries = queue.read_events("admin", "consumer-1")
    assert len(deliveries) == 1
    assert deliveries[0].event.analytics == {"session_count": 4, "stage": "summarizing"}
    claimed = queue.retry_event("admin", "consumer-2", "1-0")
    assert claimed is not None
    assert claimed.consumer == "consumer-2"
    assert claimed.delivery_count == 2
    assert queue.ack_event("admin", "1-0")
    assert not queue.ack_event("admin", "1-0")
