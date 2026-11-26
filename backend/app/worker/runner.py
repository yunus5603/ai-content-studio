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

from app.catalog import get_model
from app.catalog.pricing import cost_from_usage, with_fee
from app.catalog.schema import ModelSpec
from app.core.config import Settings
from app.models import Asset, AssetKind, Job, JobStatus
from app.models.billing import to_micros
from app.providers import ProviderError, get_adapter
from app.services import billing
from app.services.copilot import executor as copilot
from app.services.media import EXTENSIONS
from app.services.storage import Storage

log = logging.getLogger("studio.worker")
HEARTBEAT_SECONDS = 15


def _now() -> datetime:
    return datetime.now(UTC)


class JobContext:
    """What an adapter needs: the job, its catalog entry, inputs, and ways to report back."""

    def __init__(
        self,
        job: Job,
        spec: ModelSpec,
        sessions: async_sessionmaker[AsyncSession],
        storage: Storage,
    ):
        self.job = job
        self.spec = spec
        self.params = job.params or {}
        self._sessions = sessions
        self.storage = storage
        self.usage: dict[str, int] | None = None
        self._inputs: dict[str, list[tuple[Asset, bytes]]] = {}

    async def load_inputs(self) -> None:
        ids = [uuid.UUID(i["asset_id"]) for i in self.job.inputs or []]
        if not ids:
            return
        async with self._sessions() as s:
            assets = {a.id: a for a in await s.scalars(select(Asset).where(Asset.id.in_(ids)))}
        for item in self.job.inputs:
            asset = assets[uuid.UUID(item["asset_id"])]
            data = await self.storage.get(asset.storage_key)
            self._inputs.setdefault(item["role"], []).append((asset, data))

    def inputs(self, role: str) -> list[tuple[Asset, bytes]]:
        return self._inputs.get(role, [])

    async def report_progress(self, progress: float) -> None:
        async with self._sessions() as s:
            await s.execute(
                update(Job)
                .where(Job.id == self.job.id)
                .values(progress=max(0.0, min(progress, 1.0)), heartbeat_at=_now())
            )
            await s.commit()

    async def set_external_id(self, external_id: str) -> None:
        self.job.external_id = external_id
        async with self._sessions() as s:
            await s.execute(
                update(Job).where(Job.id == self.job.id).values(external_id=external_id)
            )
            await s.commit()

    async def is_canceled(self) -> bool:
        async with self._sessions() as s:
            return (
                await s.scalar(select(Job.status).where(Job.id == self.job.id))
                == JobStatus.canceled
            )


def _final_cost(ctx: JobContext, job: Job, produced: int) -> float:
    """Provider cost: from token usage when the provider reports it, else the estimate
    scaled to what was actually produced (e.g. 2 of 3 images)."""
    actual = cost_from_usage(ctx.spec, ctx.usage)
    if actual is not None:
        return actual
    pricing = ctx.spec.pricing
    requested = int(job.params.get(pricing.quantity_param, 1)) if pricing.quantity_param else 1
    if requested and produced < requested:
        return round(job.estimated_cost_usd * produced / requested, 6)
    return job.estimated_cost_usd


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
        dead = (
            await s.scalars(
                select(Job)
                .where(
                    Job.status == JobStatus.running,
                    Job.heartbeat_at < cutoff,
                    Job.attempts >= settings.job_max_attempts,
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
        for job in dead:
            job.status = JobStatus.failed
            job.finished_at = _now()
            job.error = "The job stopped responding and ran out of retries"
            await billing.settle(s, job, 0)
        requeued = await s.execute(
            update(Job)
            .where(Job.status == JobStatus.running, Job.heartbeat_at < cutoff)
            .values(status=JobStatus.queued)
        )
        await s.commit()
    for job in dead:
        await copilot.on_job_finished(sessions, job.id, settings)
    return len(dead) + requeued.rowcount


async def run_job(
    job: Job, sessions: async_sessionmaker[AsyncSession], storage: Storage, settings: Settings
) -> None:
    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            async with sessions() as s:
                await s.execute(update(Job).where(Job.id == job.id).values(heartbeat_at=_now()))
                await s.commit()

    beat = asyncio.create_task(heartbeat())
    ctx: JobContext | None = None
    try:
        spec = get_model(job.model, include_debug=settings.enable_debug_operations)
        ctx = JobContext(job, spec, sessions, storage)
        await ctx.load_inputs()
        adapter = get_adapter(spec.adapter)
        outputs = await asyncio.wait_for(adapter(ctx), timeout=settings.job_timeout_seconds)
    except Exception as exc:
        if isinstance(exc, ProviderError):
            message = str(exc)
        elif isinstance(exc, TimeoutError):
            message = "The generation timed out"
        else:
            # Unexpected errors: log details, show a generic message.
            log.exception("job %s crashed", job.id)
            message = "Something went wrong while generating. Please try again."
        log.warning("job %s failed: %s", job.id, message)
        async with sessions() as s:
            current = await billing.lock_job(s, job.id)
            if current is not None and current.status == JobStatus.running:
                current.status = JobStatus.failed
                current.error = message[:2000]
                current.finished_at = _now()
                await billing.settle(s, current, 0)  # failed jobs are free
            await s.commit()
        await copilot.on_job_finished(sessions, job.id, settings)
        return
    finally:
        beat.cancel()

    async with sessions() as s:
        current = await billing.lock_job(s, job.id)
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
        current.usage = ctx.usage
        current.cost_usd = _final_cost(ctx, current, len(outputs))
        await billing.settle(s, current, to_micros(with_fee(current.cost_usd)))
        current.finished_at = _now()
        await s.commit()
    await copilot.on_job_finished(sessions, job.id, settings)
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
