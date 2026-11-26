"""Postgres-backed job queue.

Jobs live in the `jobs` table. Workers claim one with SELECT ... FOR UPDATE
SKIP LOCKED, so any number of worker instances can run without a separate
queue service. A running job writes a heartbeat; if a worker dies, the job is
re-queued once its heartbeat goes stale (up to JOB_MAX_ATTEMPTS).
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import Asset, AssetKind, Job, JobStatus
from app.services.media import EXTENSIONS
from app.services.storage import Storage
from app.worker.registry import UnknownOperation, resolve

log = logging.getLogger("studio.worker")
HEARTBEAT_SECONDS = 15


def _now() -> datetime:
    return datetime.now(UTC)


class JobContext:
    def __init__(self, job: Job, sessions: async_sessionmaker[AsyncSession], storage: Storage):
        self.job = job
        self._sessions = sessions
        self.storage = storage

    async def report_progress(self, progress: float) -> None:
        async with self._sessions() as s:
            await s.execute(
                update(Job)
                .where(Job.id == self.job.id)
                .values(progress=max(0.0, min(progress, 1.0)), heartbeat_at=_now())
            )
            await s.commit()

    async def set_external_id(self, external_id: str) -> None:
        async with self._sessions() as s:
            await s.execute(
                update(Job).where(Job.id == self.job.id).values(external_id=external_id)
            )
            await s.commit()

    async def load_inputs(self) -> list[tuple[Asset, bytes]]:
        ids = [uuid.UUID(i) for i in self.job.input_asset_ids]
        if not ids:
            return []
        async with self._sessions() as s:
            assets = {a.id: a for a in await s.scalars(select(Asset).where(Asset.id.in_(ids)))}
        return [(assets[i], await self.storage.get(assets[i].storage_key)) for i in ids]


async def claim_next(sessions: async_sessionmaker[AsyncSession]) -> Job | None:
    async with sessions() as s:
        next_id = (
            select(Job.id)
            .where(Job.status == JobStatus.queued)
            .order_by(Job.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
            .scalar_subquery()
        )
        job = await s.scalar(
            update(Job)
            .where(Job.id == next_id)
            .values(
                status=JobStatus.running,
                started_at=_now(),
                heartbeat_at=_now(),
                attempts=Job.attempts + 1,
            )
            .returning(Job)
        )
        await s.commit()
        return job


async def requeue_stale(sessions: async_sessionmaker[AsyncSession], settings: Settings) -> int:
    """Return jobs whose worker vanished to the queue, or fail them after max attempts."""
    cutoff = _now() - timedelta(seconds=HEARTBEAT_SECONDS * 8)
    async with sessions() as s:
        failed = await s.execute(
            update(Job)
            .where(
                Job.status == JobStatus.running,
                Job.heartbeat_at < cutoff,
                Job.attempts >= settings.job_max_attempts,
            )
            .values(
                status=JobStatus.failed,
                finished_at=_now(),
                error="The job stopped responding and ran out of retries",
            )
        )
        requeued = await s.execute(
            update(Job)
            .where(Job.status == JobStatus.running, Job.heartbeat_at < cutoff)
            .values(status=JobStatus.queued)
        )
        await s.commit()
        return failed.rowcount + requeued.rowcount


async def run_job(
    job: Job, sessions: async_sessionmaker[AsyncSession], storage: Storage, settings: Settings
) -> None:
    ctx = JobContext(job, sessions, storage)

    async def heartbeat():
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            async with sessions() as s:
                await s.execute(update(Job).where(Job.id == job.id).values(heartbeat_at=_now()))
                await s.commit()

    beat = asyncio.create_task(heartbeat())
    try:
        op = resolve(job.provider, job.model, job.operation, settings.enable_debug_operations)
        outputs = await asyncio.wait_for(op.handler(ctx), timeout=settings.job_timeout_seconds)
    except (UnknownOperation, TimeoutError, Exception) as exc:  # noqa: B014
        message = ("Timed out" if isinstance(exc, TimeoutError) else str(exc)) or type(exc).__name__
        log.warning("job %s failed: %s", job.id, message)
        async with sessions() as s:
            await s.execute(
                update(Job)
                .where(Job.id == job.id, Job.status == JobStatus.running)
                .values(status=JobStatus.failed, error=message[:2000], finished_at=_now())
            )
            await s.commit()
        return
    finally:
        beat.cancel()

    async with sessions() as s:
        current = await s.get(Job, job.id)
        if current is None or current.status != JobStatus.running:  # canceled meanwhile
            return
        for media in outputs:
            asset_id = uuid.uuid4()
            key = (
                f"workspaces/{job.workspace_id}/outputs/{job.id}/"
                f"{asset_id}.{EXTENSIONS.get(media.content_type, 'bin')}"
            )
            await storage.put(key, media.data, media.content_type)
            s.add(
                Asset(
                    id=asset_id,
                    workspace_id=job.workspace_id,
                    created_by_id=job.created_by_id,
                    job_id=job.id,
                    kind=AssetKind.output,
                    media_type=media.media_type,
                    content_type=media.content_type,
                    storage_key=key,
                    size_bytes=len(media.data),
                    width=media.width,
                    height=media.height,
                    duration_seconds=media.duration_seconds,
                )
            )
        current.status = JobStatus.succeeded
        current.progress = 1.0
        current.finished_at = _now()
        await s.commit()
    log.info("job %s succeeded with %d output(s)", job.id, len(outputs))


async def work_forever(
    sessions: async_sessionmaker[AsyncSession],
    storage: Storage,
    settings: Settings,
    stop: asyncio.Event,
) -> None:
    slots = asyncio.Semaphore(settings.worker_concurrency)
    running: set[asyncio.Task] = set()
    last_sweep = 0.0
    loop = asyncio.get_running_loop()
    while not stop.is_set():
        if loop.time() - last_sweep > HEARTBEAT_SECONDS:
            await requeue_stale(sessions, settings)
            last_sweep = loop.time()
        await slots.acquire()
        job = await claim_next(sessions)
        if job is None:
            slots.release()
            try:
                await asyncio.wait_for(stop.wait(), settings.worker_poll_interval_seconds)
            except TimeoutError:
                pass
            continue
        task = asyncio.create_task(run_job(job, sessions, storage, settings))
        running.add(task)
        task.add_done_callback(lambda t: (running.discard(t), slots.release()))
    if running:
        await asyncio.gather(*running, return_exceptions=True)
