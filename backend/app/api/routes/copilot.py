import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import workspace_access
from app.api.routes.jobs import _job_out
from app.catalog import CatalogError, get_model, validate_params
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.permissions import Action
from app.models import Asset, CopilotPlan, Job, PlanStatus
from app.models.billing import to_micros, to_usd
from app.services.copilot import executor
from app.services.copilot.planner import (
    PlanningError,
    finalize,
    make_plan,
    safe_params,
    step_price,
)
from app.services.copilot.schema import (
    Draft,
    PlanOut,
    PlanRequest,
    ReviseRequest,
    StepUpdate,
)
from app.services.storage import Storage, get_storage
from app.services.workspaces import WorkspaceAccess

router = APIRouter(prefix="/workspaces/{workspace_id}/copilot", tags=["copilot"])


async def _attachments(
    session: AsyncSession, access: WorkspaceAccess, ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(Asset.id, Asset.media_type).where(
                Asset.id.in_(ids), Asset.workspace_id == access.workspace.id
            )
        )
    ).all()
    if len(rows) != len(set(ids)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "An attached file wasn't found in this workspace"
        )
    found = {r[0]: r[1].value for r in rows}
    return {i: found[i] for i in ids}


async def _plan_out(
    session: AsyncSession, plan: CopilotPlan, storage: Storage, settings: Settings
) -> PlanOut:
    jobs = (
        await session.scalars(select(Job).where(Job.plan_id == plan.id).order_by(Job.created_at))
    ).all()
    total = executor.plan_total(plan)
    return PlanOut(
        id=plan.id,
        workspace_id=plan.workspace_id,
        created_by_id=plan.created_by_id,
        goal=plan.goal,
        preference=plan.preference,
        budget_usd=to_usd(plan.budget_micros) if plan.budget_micros else None,
        attachments=[uuid.UUID(a) for a in plan.attachments],
        title=plan.title,
        summary=plan.summary,
        notes=plan.notes,
        steps=executor.steps_of(plan),
        planner=plan.planner,
        status=plan.status.value,
        error=plan.error,
        estimated_price_usd=total,
        charged_usd=to_usd(sum(j.charged_micros or 0 for j in jobs)),
        can_autorun=total <= settings.copilot_autorun_max_usd,
        created_at=plan.created_at,
        started_at=plan.started_at,
        finished_at=plan.finished_at,
        jobs=[await _job_out(session, j, storage) for j in jobs],
    )


async def _get_plan(
    session: AsyncSession, access: WorkspaceAccess, plan_id: uuid.UUID, lock: bool = False
) -> CopilotPlan:
    plan = (
        await executor.lock_plan(session, plan_id)
        if lock
        else await session.get(CopilotPlan, plan_id)
    )
    if plan is None or plan.workspace_id != access.workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    if plan.created_by_id != access.user.id and lock:
        access.require(Action.manage_members)
    return plan


def _apply(plan: CopilotPlan, draft: Draft) -> None:
    plan.title = draft.title or plan.goal[:60]
    plan.summary = draft.summary
    plan.notes = draft.notes
    plan.planner = draft.planner
    executor.save_steps(plan, draft.steps)


def _draft_of(plan: CopilotPlan) -> Draft:
    return Draft(
        title=plan.title,
        summary=plan.summary,
        notes=[],
        steps=executor.steps_of(plan),
        planner=plan.planner,
    )


@router.post("/plans", response_model=PlanOut, status_code=201)
async def create_plan(
    body: PlanRequest,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    """Turn a goal into a costed plan. Nothing is charged until the plan runs."""
    access.require(Action.generate)
    attachments = await _attachments(session, access, body.attachments)
    try:
        draft = await make_plan(body.goal, body.preference, body.budget_usd, attachments, settings)
    except PlanningError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    plan = CopilotPlan(
        id=uuid.uuid4(),
        workspace_id=access.workspace.id,
        created_by_id=access.user.id,
        goal=body.goal,
        preference=body.preference,
        budget_micros=to_micros(body.budget_usd) if body.budget_usd else None,
        attachments=[str(a) for a in body.attachments],
    )
    _apply(plan, draft)
    session.add(plan)
    await session.flush()
    total = executor.plan_total(plan)
    fits = not body.budget_usd or total <= body.budget_usd
    if body.autorun and total <= settings.copilot_autorun_max_usd and fits:
        try:
            await executor.start(session, plan, access.workspace, settings)
        except executor.PlanError as exc:
            plan.notes = [*plan.notes, f"Didn't start automatically: {exc}"]
    await session.commit()
    return await _plan_out(session, plan, storage, settings)


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(
    limit: int = Query(default=20, ge=1, le=50),
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    plans = await session.scalars(
        select(CopilotPlan)
        .where(
            CopilotPlan.workspace_id == access.workspace.id,
            CopilotPlan.created_by_id == access.user.id,
        )
        .order_by(CopilotPlan.created_at.desc())
        .limit(limit)
    )
    return [await _plan_out(session, p, storage, settings) for p in plans]


@router.get("/plans/{plan_id}", response_model=PlanOut)
async def get_plan(
    plan_id: uuid.UUID,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    plan = await _get_plan(session, access, plan_id)
    return await _plan_out(session, plan, storage, settings)


async def _editable(
    session: AsyncSession, access: WorkspaceAccess, plan_id: uuid.UUID
) -> CopilotPlan:
    access.require(Action.generate)
    plan = await _get_plan(session, access, plan_id, lock=True)
    if plan.status != PlanStatus.draft:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a plan that hasn't run can be changed")
    return plan


@router.patch("/plans/{plan_id}/steps/{step_id}", response_model=PlanOut)
async def update_step(
    plan_id: uuid.UUID,
    step_id: str,
    body: StepUpdate,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    plan = await _editable(session, access, plan_id)
    steps = executor.steps_of(plan)
    step = next((s for s in steps if s.id == step_id), None)
    if step is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Step not found")
    if body.title is not None:
        step.title = body.title
    if body.prompt is not None:
        step.prompt = body.prompt
    try:
        if body.model is not None and body.model != step.model:
            spec = get_model(body.model, include_debug=settings.enable_debug_operations)
            if spec.operation(step.operation) is None:
                raise CatalogError(
                    f"{spec.name} can't do {step.operation.replace('_', ' ')} for this step"
                )
            step.model = spec.id
            # Carry over the settings the new model understands.
            step.params = safe_params(spec, step.operation, step.params)
        spec = get_model(step.model, include_debug=settings.enable_debug_operations)
        if body.params is not None:
            step.params = validate_params(spec, step.operation, {**step.params, **body.params})
    except CatalogError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    step.estimated_price_usd = step_price(spec, step.params)
    executor.save_steps(plan, steps)
    await session.commit()
    return await _plan_out(session, plan, storage, settings)


@router.delete("/plans/{plan_id}/steps/{step_id}", response_model=PlanOut)
async def delete_step(
    plan_id: uuid.UUID,
    step_id: str,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    plan = await _editable(session, access, plan_id)
    steps = [s for s in executor.steps_of(plan) if s.id != step_id]
    if len(steps) == len(plan.steps):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Step not found")
    if not steps:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A plan needs at least one step")
    attachments = await _attachments(session, access, [uuid.UUID(a) for a in plan.attachments])
    draft = _draft_of(plan).model_copy(update={"steps": steps})
    try:
        draft = finalize(
            draft,
            plan.preference,
            to_usd(plan.budget_micros) if plan.budget_micros else None,
            attachments,
            include_debug=settings.enable_debug_operations,
        )
    except PlanningError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    _apply(plan, draft.model_copy(update={"notes": plan.notes}))
    await session.commit()
    return await _plan_out(session, plan, storage, settings)


@router.post("/plans/{plan_id}/revise", response_model=PlanOut)
async def revise_plan(
    plan_id: uuid.UUID,
    body: ReviseRequest,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    """Re-plan with a change ("make it vertical", "cheaper", "add a second scene")."""
    plan = await _editable(session, access, plan_id)
    if body.preference:
        plan.preference = body.preference
    if body.budget_usd:
        plan.budget_micros = to_micros(body.budget_usd)
    attachments = await _attachments(session, access, [uuid.UUID(a) for a in plan.attachments])
    try:
        draft = await make_plan(
            plan.goal,
            plan.preference,
            to_usd(plan.budget_micros) if plan.budget_micros else None,
            attachments,
            settings,
            previous=_draft_of(plan),
            instruction=body.instruction,
        )
    except PlanningError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if body.instruction:
        plan.goal = f"{plan.goal}\n\nChange: {body.instruction}"[:4000]
    _apply(plan, draft)
    await session.commit()
    return await _plan_out(session, plan, storage, settings)


@router.post("/plans/{plan_id}/run", response_model=PlanOut)
async def run_plan(
    plan_id: uuid.UUID,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    """Approve the plan and start its first steps."""
    access.require(Action.generate)
    plan = await _get_plan(session, access, plan_id, lock=True)
    try:
        await executor.start(session, plan, access.workspace, settings)
    except executor.PlanError as exc:
        await session.rollback()
        raise HTTPException(exc.status_code, str(exc)) from exc
    await session.commit()
    return await _plan_out(session, plan, storage, settings)


@router.post("/plans/{plan_id}/cancel", response_model=PlanOut)
async def cancel_plan(
    plan_id: uuid.UUID,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    access.require(Action.generate)
    plan = await _get_plan(session, access, plan_id, lock=True)
    await executor.cancel(session, plan, settings)
    await session.commit()
    return await _plan_out(session, plan, storage, settings)
