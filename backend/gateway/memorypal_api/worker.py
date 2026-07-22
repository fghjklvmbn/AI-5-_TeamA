from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import uuid
from contextlib import suppress

from .config import load_settings
from .database_factory import create_database
from .services.pipeline import ModelPipeline
from .services.portrait_engine import PortraitEngine
from .services.task_queue import QueueMessage, create_task_queue


logger = logging.getLogger(__name__)


def _transition(db, operation_id: str | None, status: str, **kwargs) -> None:
    if not operation_id:
        return
    try:
        db.transition_operation(operation_id, status, **kwargs)
    except (KeyError, RuntimeError, ValueError):
        logger.warning(
            "Worker operation transition rejected: operation_id=%s status=%s",
            operation_id,
            status,
            exc_info=True,
        )


async def _maintain_leases(
    queue,
    db,
    message: QueueMessage,
    lock_lease,
    operation_id: str | None,
    user_id: str,
    stop: asyncio.Event,
    lease_lost: asyncio.Event,
) -> None:
    current_lock = lock_lease
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=25)
            return
        except TimeoutError:
            pass
        try:
            renewed_message = await asyncio.to_thread(
                queue.heartbeat, message, lease_seconds=120,
            )
            current_lock = await asyncio.to_thread(
                queue.renew_lock, current_lock, ttl_seconds=120,
            )
            if renewed_message is None or current_lock is None:
                raise RuntimeError("queue or GPU fencing lease was lost")
            portrait = await asyncio.to_thread(db.get_portrait, user_id)
            if portrait is None:
                continue
            progress = int(portrait["progress_percent"] or 0)
            await asyncio.to_thread(
                queue.update_progress,
                message,
                progress,
                str(portrait["status"]),
                {
                    "session_count": int(portrait["analyzed_sessions"] or 0),
                    "message_count": int(portrait["analyzed_messages"] or 0),
                },
            )
            _transition(
                db, operation_id, "running", progress_percent=progress,
                reason="worker_heartbeat",
            )
        except Exception:
            logger.exception("Portrait worker lost its queue, DB, or GPU fencing lease")
            lease_lost.set()
            stop.set()
            return


async def _relay_outbox(queue, db, worker_id: str, *, limit: int = 50) -> None:
    """Deliver durable metadata envelopes to Redis Streams at least once."""
    rows = await asyncio.to_thread(
        db.claim_outbox_events,
        worker_id,
        limit=limit,
        lease_seconds=30,
    )
    for row in rows:
        event_id = str(row["event_id"])
        try:
            raw_payload = row["payload_json"]
            payload = raw_payload if isinstance(raw_payload, dict) else json.loads(raw_payload)
            state = str(payload.get("status") or "failed")
            if state not in {"succeeded", "failed"}:
                state = "failed"
            analytics = {"duration_ms": int(payload.get("latency_ms") or 0)}
            if state == "failed":
                analytics["error_code"] = f"http_{payload.get('http_status') or 500}"
            await asyncio.to_thread(
                queue.publish_event,
                # Stable DB event ID lets consumers deduplicate a publish that
                # succeeded immediately before the relay process crashed.
                task_id=event_id,
                request_id=str(payload.get("request_id") or row["aggregate_id"]),
                correlation_id=str(payload.get("correlation_id") or row["aggregate_id"]),
                queue="http",
                state=state,
                attempt=max(1, int(row["attempts"] or 1)),
                analytics=analytics,
            )
            await asyncio.to_thread(db.mark_outbox_published, event_id, worker_id)
        except Exception:
            attempts = max(1, int(row["attempts"] or 1))
            await asyncio.to_thread(
                db.mark_outbox_failed,
                event_id,
                worker_id,
                retry_seconds=min(300, 2 ** min(attempts, 8)),
            )
            logger.exception("Failed to relay transaction event: event_id=%s", event_id)


async def _reconcile_failed_tasks(queue, db) -> None:
    """Resolve DB jobs whose Redis retry budget ended after a worker crash."""
    rows = await asyncio.to_thread(db.list_active_portraits)
    for row in rows:
        generation_id = str(row["generation_id"])
        progress = await asyncio.to_thread(queue.get_progress, generation_id)
        if progress is None or progress.status != "failed":
            continue
        failed = await asyncio.to_thread(
            db.fail_expired_portrait,
            str(row["user_id"]),
            generation_id,
            "자화상 worker 재시도 횟수를 모두 사용했습니다.",
        )
        if not failed:
            continue
        operation = await asyncio.to_thread(
            db.get_operation_for_resource, "portrait_generation", generation_id,
        )
        _transition(
            db,
            str(operation["id"]) if operation is not None else None,
            "failed",
            error_code="worker_retry_exhausted",
            reason="redis_state_reconciled",
        )


async def _process_message(queue, db, engine, pipeline, message: QueueMessage, lock_lease) -> None:
    payload = message.payload
    user_id = str(payload.get("user_id") or "")
    generation_id = str(payload.get("generation_id") or "")
    persona = str(payload.get("persona") or "")
    operation_id = str(payload.get("operation_id") or "") or None
    _transition(
        db, operation_id, "running", progress_percent=1, reason="redis_worker_claimed",
    )
    if not user_id or not generation_id or persona not in {"default", "emotional_companion"}:
        logger.error("Discarding malformed portrait task: task_id=%s", message.task_id)
        retry = await asyncio.to_thread(queue.retry, message, error="invalid_task_payload")
        if retry.requeued:
            _transition(
                db, operation_id, "retrying", error_code="invalid_task_payload",
                reason="invalid_task_payload",
            )
            _transition(db, operation_id, "queued", reason="invalid_task_retry")
        elif retry.exhausted:
            _transition(
                db, operation_id, "failed", error_code="invalid_task_payload",
                reason="invalid_task_payload",
            )
        return

    heartbeat_stop = asyncio.Event()
    lease_lost = asyncio.Event()
    heartbeat = asyncio.create_task(_maintain_leases(
        queue, db, message, lock_lease, operation_id, user_id, heartbeat_stop, lease_lost,
    ))
    generation_task: asyncio.Task | None = None
    lease_waiter: asyncio.Task | None = None
    try:
        generation_task = asyncio.create_task(engine.generate(
            user_id, generation_id, persona, pipeline,
            operation_id=operation_id, manage_operation=False,
        ))
        lease_waiter = asyncio.create_task(lease_lost.wait())
        await asyncio.wait(
            {generation_task, lease_waiter},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if lease_lost.is_set():
            generation_task.cancel()
            with suppress(asyncio.CancelledError):
                await generation_task
            _transition(
                db, operation_id, "retrying", error_code="worker_lease_lost",
                reason="worker_lease_lost",
            )
            return
        lease_waiter.cancel()
        with suppress(asyncio.CancelledError):
            await lease_waiter
        await generation_task
        portrait = await asyncio.to_thread(db.get_portrait, user_id)
        if (
            portrait is not None
            and str(portrait["generation_id"]) == generation_id
            and portrait["status"] == "complete"
        ):
            acknowledged = await asyncio.to_thread(queue.ack, message)
            if not acknowledged:
                _transition(
                    db, operation_id, "retrying", error_code="queue_ack_rejected",
                    reason="queue_ack_rejected",
                )
                return
            _transition(
                db, operation_id, "succeeded", progress_percent=100,
                reason="redis_worker_completed",
            )
            return

        error_code = "portrait_generation_failed"
        retry = await asyncio.to_thread(
            queue.retry, message, delay_seconds=30, error=error_code,
        )
        if retry.requeued:
            _transition(
                db, operation_id, "retrying", error_code=error_code,
                reason="redis_worker_retry",
            )
            await asyncio.to_thread(
                db.requeue_failed_portrait, user_id, generation_id,
            )
            _transition(
                db, operation_id, "queued", reason="retry_scheduled",
            )
            return
        if retry.exhausted:
            _transition(
                db, operation_id, "failed", error_code=error_code,
                reason="retry_exhausted",
            )
    except asyncio.CancelledError:
        if generation_task is not None and not generation_task.done():
            generation_task.cancel()
            with suppress(asyncio.CancelledError):
                await generation_task
        retry = await asyncio.to_thread(
            queue.retry, message, delay_seconds=5, error="worker_shutdown",
        )
        if retry.requeued:
            _transition(
                db, operation_id, "retrying", error_code="worker_shutdown",
                reason="worker_shutdown",
            )
            _transition(db, operation_id, "queued", reason="worker_shutdown_requeued")
        elif retry.exhausted:
            _transition(
                db, operation_id, "failed", error_code="worker_shutdown",
                reason="worker_shutdown_retry_exhausted",
            )
        else:
            _transition(
                db, operation_id, "retrying", error_code="worker_shutdown",
                reason="worker_shutdown_lease_lost",
            )
        raise
    except Exception:
        logger.exception("Unhandled portrait worker failure: task_id=%s", message.task_id)
        retry = await asyncio.to_thread(
            queue.retry, message, delay_seconds=30, error="worker_internal_error",
        )
        if retry.requeued:
            _transition(
                db, operation_id, "retrying", error_code="worker_internal_error",
                reason="worker_internal_error",
            )
            await asyncio.to_thread(db.requeue_failed_portrait, user_id, generation_id)
            _transition(db, operation_id, "queued", reason="worker_retry_scheduled")
        elif retry.exhausted:
            _transition(
                db, operation_id, "failed", error_code="worker_internal_error",
                reason="worker_retry_exhausted",
            )
    finally:
        for task in (generation_task, lease_waiter):
            if task is not None and not task.done():
                task.cancel()
        for task in (generation_task, lease_waiter):
            if task is not None:
                with suppress(asyncio.CancelledError, Exception):
                    await task
        heartbeat_stop.set()
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat


async def run_worker() -> None:
    settings = load_settings()
    if settings.task_queue_mode != "redis" or not settings.redis_url:
        raise RuntimeError(
            "The distributed worker requires MEMORYPAL_TASK_QUEUE_MODE=redis "
            "and MEMORYPAL_REDIS_URL."
        )
    db = create_database(settings)
    db.initialize()
    queue = create_task_queue(settings.redis_url, namespace=settings.redis_prefix)
    pipeline = ModelPipeline(settings)
    engine = PortraitEngine(db)
    worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    gpu_lock_name = os.getenv("MEMORYPAL_GPU_LOCK_NAME", "portrait:gpu:default")
    logger.info("MemoryPal portrait worker started: %s", worker_id)
    retry_delay = 1.0
    try:
        while True:
            try:
                await _relay_outbox(queue, db, worker_id)
                await _reconcile_failed_tasks(queue, db)
                lock_lease = await asyncio.to_thread(
                    queue.acquire_lock, gpu_lock_name, worker_id, ttl_seconds=120,
                )
                if lock_lease is None:
                    await asyncio.sleep(1)
                    continue
                try:
                    message = await asyncio.to_thread(
                        queue.dequeue,
                        "portrait",
                        worker_id,
                        lease_seconds=120,
                        timeout_seconds=2,
                    )
                    # dequeue performs expired-lease recovery; immediately make
                    # its terminal result consistent with PostgreSQL.
                    await _reconcile_failed_tasks(queue, db)
                    if message is not None:
                        await _process_message(
                            queue, db, engine, pipeline, message, lock_lease,
                        )
                finally:
                    await asyncio.to_thread(queue.release_lock, lock_lease)
                retry_delay = 1.0
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Transient portrait worker loop failure; retrying in %.1fs",
                    retry_delay,
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(30.0, retry_delay * 2)
    finally:
        client = getattr(queue, "client", None)
        if client is not None:
            await asyncio.to_thread(client.close)
        db.close()


def main() -> None:
    logging.basicConfig(
        level=os.getenv("MEMORYPAL_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
