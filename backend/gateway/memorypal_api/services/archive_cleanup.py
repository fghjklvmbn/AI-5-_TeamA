from __future__ import annotations

import asyncio
import logging
import uuid

logger = logging.getLogger(__name__)


async def process_archive_cleanup_job(app, job) -> None:
    """Perform remote I/O after the claim transaction has released every DB lock."""
    try:
        await app.state.pipeline.purge_owner_voices(
            str(job["owner_ref"]),
            voice_id=str(job["voice_id"]) if job["voice_id"] is not None else None,
        )
    except asyncio.CancelledError:
        # The running lease expires and becomes claimable after a crash/shutdown.
        raise
    except Exception as exc:
        attempt = max(1, int(job["attempt_count"]))
        delay = min(300.0, float(2 ** min(attempt, 8)))
        await asyncio.to_thread(
            app.state.db.retry_archive_voice_cleanup,
            str(job["id"]),
            str(job["lease_token"]),
            error=type(exc).__name__,
            delay_seconds=delay,
        )
        logger.warning(
            "Archive voice cleanup will retry (job=%s, attempt=%s)",
            job["id"],
            attempt,
        )
        return
    await asyncio.to_thread(
        app.state.db.complete_archive_voice_cleanup,
        str(job["id"]),
        str(job["lease_token"]),
    )


async def run_archive_cleanup_once(
    app,
    *,
    owner_ref: str | None = None,
    worker_id: str | None = None,
) -> bool:
    worker = worker_id or f"gateway-{uuid.uuid4()}"
    job = await asyncio.to_thread(
        app.state.db.claim_archive_voice_cleanup,
        worker,
        lease_seconds=45,
        owner_ref=owner_ref,
    )
    if job is None:
        return False
    await process_archive_cleanup_job(app, job)
    return True


async def archive_cleanup_loop(app, worker_id: str) -> None:
    while True:
        try:
            processed = await run_archive_cleanup_once(app, worker_id=worker_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Archive voice cleanup worker iteration failed")
            await asyncio.sleep(5)
            continue
        if not processed:
            await asyncio.sleep(5)


async def reconcile_legacy_voice_once(app) -> bool:
    mapping = await asyncio.to_thread(
        app.state.db.get_next_legacy_voice_mapping,
        app.state.settings.default_voice_id,
    )
    if mapping is None:
        return False
    user_id = str(mapping["user_id"])
    voice_id = str(mapping["voice_id"])
    owner_ref = app.state.pipeline.archive_owner_ref(user_id)
    await app.state.pipeline.adopt_legacy_voice(voice_id, owner_ref)
    await asyncio.to_thread(
        app.state.db.mark_legacy_voice_adopted,
        user_id,
        voice_id,
        owner_ref,
    )
    return True


async def legacy_voice_reconciliation_loop(app) -> None:
    while True:
        try:
            reconciled = await reconcile_legacy_voice_once(app)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Legacy private voice reconciliation failed")
            await asyncio.sleep(5)
            continue
        if not reconciled:
            await asyncio.sleep(15)


async def run_immediate_archive_cleanup(app, owner_ref: str) -> None:
    """Make a shieldable immediate attempt while retaining a strong task reference."""
    task = asyncio.create_task(run_archive_cleanup_once(app, owner_ref=owner_ref))
    app.state.archive_cleanup_tasks.add(task)

    def discard(done: asyncio.Task) -> None:
        app.state.archive_cleanup_tasks.discard(done)
        try:
            done.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Immediate Archive voice cleanup task failed")

    task.add_done_callback(discard)
    await asyncio.shield(task)
