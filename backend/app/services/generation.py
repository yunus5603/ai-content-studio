"""Submitting a generation job: validate against the catalog, check inputs, hold credits.

Shared by the jobs API, storyboards and anything else that starts generations, so
every path gets the same validation, limits and billing.
"""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import CatalogError, get_model, validate_params
from app.catalog.pricing import estimate_cost, with_fee
from app.catalog.schema import ModelSpec
from app.core.config import Settings
from app.models import Asset, Job, JobStatus
from app.services import billing
from app.services.workspaces import WorkspaceAccess

MAX_ACTIVE_JOBS_PER_WORKSPACE = 20


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
) -> Job:
    """Create a queued job and hold its price. The caller commits (or rolls back)."""
    spec, params = resolve(settings, model, operation, params, internal=internal)
    op_spec = spec.operation(operation)

    # Inputs: right roles, right counts, assets from this workspace, right media type.
    asset_ids = {uuid.UUID(str(i["asset_id"])) for i in inputs}
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
        raise GenerationError("One or more input files were not found in this workspace")
    allowed = {i.role: i for i in op_spec.inputs}
    for item in inputs:
        rule = allowed.get(item["role"])
        if rule is None:
            raise GenerationError(f"{spec.name} doesn't take a {item['role']} input for this mode")
        if assets[uuid.UUID(str(item["asset_id"]))].media_type.value != rule.media_type:
            raise GenerationError(f"{rule.label} must be an {rule.media_type}")
    for role, rule in allowed.items():
        count = sum(1 for i in inputs if i["role"] == role)
        if not rule.min <= count <= rule.max:
            limit = f"exactly {rule.min}" if rule.min == rule.max else f"{rule.min} to {rule.max}"
            raise GenerationError(f"{rule.label}: provide {limit}")

    if check_active:
        await ensure_capacity(session, access, 1)

    job = Job(
        id=uuid.uuid4(),
        workspace_id=access.workspace.id,
        created_by_id=access.user.id,
        operation=operation,
        provider=spec.provider,
        model=spec.id,
        prompt=prompt,
        params=params,
        inputs=[{"asset_id": str(i["asset_id"]), "role": i["role"]} for i in inputs],
        estimated_cost_usd=estimate_cost(spec, params),
    )
    session.add(job)
    await session.flush()
    price = with_fee(job.estimated_cost_usd)
    if price > 0:  # free internal steps (e.g. stitching clips) never touch the ledger
        try:
            await billing.reserve(session, access.workspace, access.user.id, job, price)
        except billing.BillingError as exc:
            raise GenerationError(str(exc), exc.status_code) from exc
    return job


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
