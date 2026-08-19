from __future__ import annotations

import asyncio
import uuid

from memorypal_api.database import Database
from memorypal_api.services.task_queue import LocalTaskQueue, QueueMessage
from memorypal_api.worker import _process_message, _reconcile_failed_tasks


class FakeClock:
    def __init__(self, value: float = 1000.0):
        self.value = value

    def __call__(self) -> float:
        return self.value


def test_worker_cancels_generation_immediately_when_fencing_lease_is_lost(monkeypatch):
    class DB:
        def __init__(self):
            self.transitions = []

        def transition_operation(self, operation_id, status, **kwargs):
            self.transitions.append((operation_id, status, kwargs))

    class Queue:
        ack_called = False

        def ack(self, _message):
            self.ack_called = True
            return True

    class Engine:
        cancelled = False

        async def generate(self, *_args, **_kwargs):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    async def lose_lease(
        _queue, _db, _message, _lock, _operation_id, _user_id, stop, lease_lost,
    ):
        lease_lost.set()
        stop.set()

    monkeypatch.setattr("memorypal_api.worker._maintain_leases", lose_lease)
    db = DB()
    queue = Queue()
    engine = Engine()
    message = QueueMessage(
        task_id="generation-1",
        queue="portrait",
        payload={
            "user_id": "user-1",
            "generation_id": "generation-1",
            "persona": "default",
            "operation_id": "operation-1",
        },
        attempt=1,
        max_attempts=3,
        enqueued_at=1,
        available_at=1,
        worker_id="worker-1",
        receipt="receipt-1",
        lease_expires_at=120,
        request_id="request-1",
        correlation_id="correlation-1",
    )

    asyncio.run(_process_message(queue, db, engine, object(), message, object()))

    assert engine.cancelled is True
    assert queue.ack_called is False
    assert [status for _operation, status, _kwargs in db.transitions] == [
        "running", "retrying",
    ]


def test_worker_reconciles_terminal_queue_failure_into_database(tmp_path):
    db = Database(tmp_path / "reconcile.db")
    db.initialize()
    user = db.create_user("reconcile@example.com", "reconcile", "hash", "salt")
    portrait, _started = db.begin_portrait_generation(user["id"], "default")
    generation_id = str(portrait["generation_id"])
    operation = db.begin_operation(
        "portrait_generation",
        f"portrait-{generation_id}",
        str(uuid.uuid4()),
        user_id=user["id"],
        resource_id=generation_id,
        status="queued",
    )

    clock = FakeClock()
    queue = LocalTaskQueue(
        f"worker-reconcile-{uuid.uuid4().hex}",
        clock=clock,
        result_ttl_seconds=3600,
    )
    queue.enqueue(
        "portrait",
        {"generation_id": generation_id},
        task_id=generation_id,
        max_attempts=1,
    )
    message = queue.dequeue("portrait", "dead-worker", lease_seconds=1)
    assert message is not None
    clock.value += 2
    assert queue.dequeue("portrait", "reconciler") is None
    assert queue.get_progress(generation_id).status == "failed"

    asyncio.run(_reconcile_failed_tasks(queue, db))

    assert db.get_portrait(user["id"])["status"] == "failed"
    assert db.get_operation(operation["id"])["status"] == "failed"
