import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import workspace_access
from app.api.routes.assets import asset_out
from app.catalog import CatalogError, get_model, validate_params
from app.catalog.pricing import estimate_cost, with_fee
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.permissions import Action
from app.models import Asset, Job, JobStatus
from app.models.job import TERMINAL
from app.schemas import JobCreate, JobOut, Page
from app.services.storage import Storage, get_storage
from app.services.workspaces import WorkspaceAccess

router = APIRouter(prefix="/workspaces/{workspace_id}/jobs", tags=["jobs"])

MAX_ACTIVE_JOBS_PER_WORKSPACE = 20


async def _job_out(session: AsyncSession, job: Job, storage: Storage) -> JobOut:
    out = JobOut.model_validate(job)
    out.estimated_price_usd = with_fee(job.estimated_cost_usd)
    out.price_usd = with_fee(job.cost_usd) if job.cost_usd is not None else None
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
        spec = get_model(body.model, include_debug=settings.enable_debug_operations)
        params = validate_params(spec, body.operation, body.params)
    except CatalogError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    op_spec = spec.operation(body.operation)

    # Inputs: right roles, right counts, assets from this workspace, right media type.
    asset_ids = {i.asset_id for i in body.inputs}
    assets = (
        {
            a.id: a
            for a in await session.scalars(
                select(Asset).where(
                    Asset.id.in_(asset_ids), Asset.workspace_id == access.workspace.id
                )
            )
        }
        if asset_ids
        else {}
    )
    if len(assets) != len(asset_ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "One or more input files were not found in this workspace",
        )
    allowed = {i.role: i for i in op_spec.inputs}
    for item in body.inputs:
        rule = allowed.get(item.role)
        if rule is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{spec.name} doesn't take a {item.role} input for this mode",
            )
        if assets[item.asset_id].media_type.value != rule.media_type:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"{rule.label} must be an {rule.media_type}"
            )
    for role, rule in allowed.items():
        count = sum(1 for i in body.inputs if i.role == role)
        if not rule.min <= count <= rule.max:
            limit = f"exactly {rule.min}" if rule.min == rule.max else f"{rule.min} to {rule.max}"
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"{rule.label}: provide {limit}"
            )

    active = await session.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.workspace_id == access.workspace.id,
            Job.status.in_([JobStatus.queued, JobStatus.running]),
        )
    )
    if active >= MAX_ACTIVE_JOBS_PER_WORKSPACE:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many generations in progress. Wait for some to finish.",
        )

    job = Job(
        workspace_id=access.workspace.id,
        created_by_id=access.user.id,
        operation=body.operation,
        provider=spec.provider,
        model=spec.id,
        prompt=body.prompt,
        params=params,
        inputs=[{"asset_id": str(i.asset_id), "role": i.role} for i in body.inputs],
        estimated_cost_usd=estimate_cost(spec, params),
    )
    session.add(job)
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
):
    job = await _get_job(session, access, job_id)
    if job.created_by_id != access.user.id:
        access.require(Action.manage_members)
    else:
        access.require(Action.generate)
    if job.status not in TERMINAL:
        job.status = JobStatus.canceled
        job.finished_at = datetime.now(UTC)
        await session.commit()
    return await _job_out(session, job, storage)
