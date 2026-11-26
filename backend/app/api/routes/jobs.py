import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import workspace_access
from app.api.routes.assets import asset_out
from app.catalog.pricing import with_fee
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.permissions import Action
from app.models import Asset, Job, JobStatus
from app.models.billing import to_usd
from app.models.job import TERMINAL
from app.schemas import JobCreate, JobOut, Page
from app.services import billing
from app.services.copilot import executor as copilot
from app.services.jobs import InputRef, JobError, submit_job
from app.services.storage import Storage, get_storage
from app.services.workspaces import WorkspaceAccess

router = APIRouter(prefix="/workspaces/{workspace_id}/jobs", tags=["jobs"])


async def _job_out(session: AsyncSession, job: Job, storage: Storage) -> JobOut:
    out = JobOut.model_validate(job)
    out.estimated_price_usd = (
        to_usd(job.hold_micros) if job.hold_micros else with_fee(job.estimated_cost_usd)
    )
    out.price_usd = to_usd(job.charged_micros) if job.charged_micros is not None else None
    outputs = await session.scalars(
        select(Asset).where(Asset.job_id == job.id).order_by(Asset.created_at)
    )
    out.outputs = [await asset_out(a, storage) for a in outputs]
    return out


@router.post("", response_model=JobOut, status_code=201)
async def create_job(
    body: JobCreate,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    access.require(Action.generate)
    try:
        job = await submit_job(
            session,
            access.workspace,
            access.user.id,
            model=body.model,
            operation=body.operation,
            prompt=body.prompt,
            params=body.params,
            inputs=[InputRef(i.asset_id, i.role) for i in body.inputs],
            include_debug=settings.enable_debug_operations,
        )
    except JobError as exc:
        await session.rollback()
        raise HTTPException(exc.status_code, str(exc)) from exc
    await session.commit()
    return await _job_out(session, job, storage)


@router.get("", response_model=Page[JobOut])
async def list_jobs(
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    cursor: datetime | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    access.require(Action.view)
    q = select(Job).where(Job.workspace_id == access.workspace.id)
    if status_filter:
        q = q.where(Job.status == status_filter)
    if cursor:
        q = q.where(Job.created_at < cursor)
    rows = (await session.scalars(q.order_by(Job.created_at.desc()).limit(limit + 1))).all()
    items = [await _job_out(session, j, storage) for j in rows[:limit]]
    next_cursor = rows[limit - 1].created_at.isoformat() if len(rows) > limit else None
    return Page(items=items, next_cursor=next_cursor)


async def _get_job(session: AsyncSession, access: WorkspaceAccess, job_id: uuid.UUID) -> Job:
    job = await session.get(Job, job_id)
    if job is None or job.workspace_id != access.workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: uuid.UUID,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    access.require(Action.view)
    return await _job_out(session, await _get_job(session, access, job_id), storage)


@router.post("/{job_id}/cancel", response_model=JobOut)
async def cancel_job(
    job_id: uuid.UUID,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    job = await _get_job(session, access, job_id)
    if job.created_by_id != access.user.id:
        access.require(Action.manage_members)
    else:
        access.require(Action.generate)
    job = await billing.lock_job(session, job.id)
    if job.status not in TERMINAL:
        was_running = job.status == JobStatus.running
        job.status = JobStatus.canceled
        job.finished_at = datetime.now(UTC)
        # Queued jobs are refunded. Once a provider has started, it charges us anyway,
        # so a running job is charged its estimate.
        await billing.settle(session, job, job.hold_micros if was_running else 0)
        await session.commit()
        if job.plan_id and (plan := await copilot.lock_plan(session, job.plan_id)):
            await copilot.advance(session, plan, settings)
            await session.commit()
    return await _job_out(session, job, storage)
