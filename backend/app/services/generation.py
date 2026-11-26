"""Helpers for features that start generations (storyboards): catalog lookups,
prices, batch capacity, and job submission through app.services.jobs so every
path gets the same validation, limits and billing.
"""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import CatalogError, get_model, validate_params
from app.catalog.pricing import estimate_cost, with_fee
from app.catalog.schema import ModelSpec
from app.core.config import Settings
from app.models import Job, JobStatus
from app.services import jobs
from app.services.jobs import MAX_ACTIVE_JOBS_PER_WORKSPACE
from app.services.workspaces import WorkspaceAccess


class GenerationError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def resolve(
    settings: Settings,
    model: str,
    operation: str,
    params: dict[str, Any],
    *,
    internal: bool = False,
) -> tuple[ModelSpec, dict[str, Any]]:
    """Look up the model and validate params (defaults filled in)."""
    try:
        spec = get_model(
            model, include_debug=settings.enable_debug_operations, include_internal=internal
        )
        return spec, validate_params(spec, operation, params)
    except CatalogError as exc:
        raise GenerationError(str(exc)) from exc


def price_of(spec: ModelSpec, params: dict[str, Any]) -> float:
    """What the customer pays for a job, in USD (provider cost + platform fee)."""
    return with_fee(estimate_cost(spec, params))


async def submit_job(
    session: AsyncSession,
    access: WorkspaceAccess,
    settings: Settings,
    *,
    model: str,
    operation: str,
    prompt: str,
    params: dict[str, Any],
    inputs: list[dict[str, str]],
    internal: bool = False,
    check_active: bool = True,
    storyboard_id: uuid.UUID | None = None,
) -> Job:
    """Create a queued job and hold its price (app.services.jobs). The caller commits."""
    try:
        return await jobs.submit_job(
            session,
            access.workspace,
            access.user.id,
            model=model,
            operation=operation,
            prompt=prompt,
            params=params,
            inputs=[jobs.InputRef(uuid.UUID(str(i["asset_id"])), i["role"]) for i in inputs],
            include_debug=settings.enable_debug_operations,
            include_internal=internal,
            check_active=check_active,
            storyboard_id=storyboard_id,
        )
    except jobs.JobError as exc:
        raise GenerationError(str(exc), exc.status_code) from exc


async def ensure_capacity(session: AsyncSession, access: WorkspaceAccess, new_jobs: int) -> None:
    active = await session.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.workspace_id == access.workspace.id,
            Job.status.in_([JobStatus.queued, JobStatus.running]),
        )
    )
    if active + new_jobs > MAX_ACTIVE_JOBS_PER_WORKSPACE:
        raise GenerationError(
            "Too many generations in progress. Wait for some to finish.", status_code=429
        )
