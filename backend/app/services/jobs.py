"""Submitting a generation job: validation, input checks, billing hold.

Used by the jobs API and by the copilot when it runs a plan step.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import CatalogError, get_model, validate_params
from app.catalog.pricing import estimate_cost, with_fee
from app.models import Asset, Job, JobStatus, Workspace
from app.services import billing

MAX_ACTIVE_JOBS_PER_WORKSPACE = 20


class JobError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class InputRef:
    asset_id: uuid.UUID
    role: str


async def submit_job(
    session: AsyncSession,
    workspace: Workspace,
    user_id: uuid.UUID,
    *,
    model: str,
    operation: str,
    prompt: str,
    params: dict[str, Any],
    inputs: list[InputRef],
    include_debug: bool,
    plan_id: uuid.UUID | None = None,
    storyboard_id: uuid.UUID | None = None,
    include_internal: bool = False,
    check_active: bool = True,
) -> Job:
    """Create a queued job and hold its price. Flushes; the caller commits.

    Raises JobError (422 invalid, 429 busy, 402/403 billing). The caller should roll
    back (or use a savepoint) when it does.
    """
    try:
        # include_internal: studio-side steps such as storyboard assembly (never user-picked).
        spec = get_model(model, include_debug=include_debug, include_internal=include_internal)
        params = validate_params(spec, operation, params)
    except CatalogError as exc:
        raise JobError(422, str(exc)) from exc
    op_spec = spec.operation(operation)

    # Inputs: right roles, right counts, assets from this workspace, right media type.
    asset_ids = {i.asset_id for i in inputs}
    assets = (
        {
            a.id: a
            for a in await session.scalars(
                select(Asset).where(Asset.id.in_(asset_ids), Asset.workspace_id == workspace.id)
            )
        }
        if asset_ids
        else {}
    )
    if len(assets) != len(asset_ids):
        raise JobError(422, "One or more input files were not found in this workspace")
    allowed = {i.role: i for i in op_spec.inputs}
    for item in inputs:
        rule = allowed.get(item.role)
        if rule is None:
            raise JobError(422, f"{spec.name} doesn't take a {item.role} input for this mode")
        if assets[item.asset_id].media_type.value != rule.media_type:
            raise JobError(422, f"{rule.label} must be an {rule.media_type}")
    for role, rule in allowed.items():
        count = sum(1 for i in inputs if i.role == role)
        if not rule.min <= count <= rule.max:
            limit = f"exactly {rule.min}" if rule.min == rule.max else f"{rule.min} to {rule.max}"
            raise JobError(422, f"{rule.label}: provide {limit}")

    active = await session.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.workspace_id == workspace.id,
            Job.status.in_([JobStatus.queued, JobStatus.running]),
        )
    )
    # check_active=False: the caller already checked room for a whole batch.
    if check_active and active >= MAX_ACTIVE_JOBS_PER_WORKSPACE:
        raise JobError(429, "Too many generations in progress. Wait for some to finish.")

    job = Job(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        created_by_id=user_id,
        operation=operation,
        provider=spec.provider,
        model=spec.id,
        prompt=prompt,
        params=params,
        inputs=[{"asset_id": str(i.asset_id), "role": i.role} for i in inputs],
        estimated_cost_usd=estimate_cost(spec, params),
        plan_id=plan_id,
        storyboard_id=storyboard_id,
    )
    session.add(job)
    await session.flush()
    price = with_fee(job.estimated_cost_usd)
    if price > 0:  # free internal steps (e.g. joining clips) never touch the ledger
        try:
            await billing.reserve(session, workspace, user_id, job, price)
        except billing.BillingError as exc:
            raise JobError(exc.status_code, str(exc)) from exc
    return job
