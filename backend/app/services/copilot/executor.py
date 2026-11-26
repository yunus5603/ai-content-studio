"""Run an approved copilot plan.

Steps become ordinary jobs (same validation and billing as manual generations). A
step starts once every step it takes input from has succeeded; the worker calls
`on_job_finished` after each job, which starts the next ready steps. If a step fails,
the steps that depend on it are skipped and the plan ends as failed.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.catalog import get_model, validate_params
from app.catalog.pricing import estimate_cost, with_fee
from app.core.config import Settings
from app.models import Asset, CopilotPlan, Job, JobStatus, PlanStatus, Workspace
from app.models.billing import to_micros, to_usd
from app.models.job import TERMINAL
from app.services import billing
from app.services.copilot.schema import PlanStep
from app.services.jobs import InputRef, JobError, submit_job

log = logging.getLogger(__name__)

DONE_STEP = {"succeeded", "failed", "canceled", "skipped"}


class PlanError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def steps_of(plan: CopilotPlan) -> list[PlanStep]:
    return [PlanStep.model_validate(s) for s in plan.steps]


def save_steps(plan: CopilotPlan, steps: list[PlanStep]) -> None:
    # Assign a new list so SQLAlchemy sees the JSON change.
    plan.steps = [s.model_dump(mode="json") for s in steps]


def plan_total(plan: CopilotPlan) -> float:
    return round(sum(s.get("estimated_price_usd", 0) for s in plan.steps), 6)


async def lock_plan(session: AsyncSession, plan_id: uuid.UUID) -> CopilotPlan | None:
    return await session.scalar(
        select(CopilotPlan)
        .where(CopilotPlan.id == plan_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _simulated(step: PlanStep) -> tuple[str, str, dict]:
    """Dev mode: run a step on the matching free debug model instead of a real provider."""
    if step.operation in ("text_to_video", "image_to_video"):
        seconds = step.params.get("duration_seconds", 4)
        return "debug/clip", step.operation, {"duration_seconds": 8 if seconds > 6 else 4}
    op = "text_to_image" if step.operation == "text_to_image" else "image_edit"
    return "debug/pixel", op, {"n": int(step.params.get("n", 1)), "placeholder": True}


def _simulated_price(step: PlanStep) -> float:
    model, operation, params = _simulated(step)
    spec = get_model(model, include_debug=True)
    return with_fee(estimate_cost(spec, validate_params(spec, operation, params)))


async def start(
    session: AsyncSession, plan: CopilotPlan, workspace: Workspace, settings: Settings
) -> None:
    """Approve and start a draft plan. The caller holds the plan lock and commits."""
    if plan.status != PlanStatus.draft:
        raise PlanError(409, "This plan has already run")
    total = plan_total(plan)
    if settings.copilot_simulate and settings.enable_debug_operations:
        total = sum(_simulated_price(PlanStep.model_validate(s)) for s in plan.steps)
    ws = await session.get(Workspace, workspace.id, populate_existing=True)
    if ws.balance_micros < to_micros(total):
        raise PlanError(
            402,
            f"This plan costs about ${total:.2f} and your balance is "
            f"${to_usd(ws.balance_micros):.2f}. Buy credits to run it.",
        )
    plan.status = PlanStatus.running
    plan.started_at = datetime.now(UTC)
    plan.error = None
    errors = await advance(session, plan, settings)
    if errors and not any(s.get("job_id") for s in plan.steps):
        # Nothing could start (no credit, over a limit...): leave the plan as a draft.
        raise PlanError(errors[0].status_code, str(errors[0]))


async def advance(session: AsyncSession, plan: CopilotPlan, settings: Settings) -> list[JobError]:
    """Sync step statuses from their jobs and submit every step that is ready."""
    errors: list[JobError] = []
    steps = steps_of(plan)
    jobs = {j.id: j for j in await session.scalars(select(Job).where(Job.plan_id == plan.id))}
    for step in steps:
        job = jobs.get(step.job_id) if step.job_id else None
        if job is not None:
            step.status = job.status.value
            step.error = job.error

    if plan.status == PlanStatus.running:
        by_id = {s.id: s for s in steps}
        workspace = await session.get(Workspace, plan.workspace_id)
        for step in steps:
            if step.status != "pending":
                continue
            deps = [by_id[i.from_step] for i in step.inputs if i.from_step in by_id]
            if any(d.status in ("failed", "canceled", "skipped") for d in deps):
                step.status = "skipped"
                step.error = "Skipped because an earlier step didn't finish"
                continue
            if not all(d.status == "succeeded" for d in deps):
                continue
            if error := await _submit(session, plan, workspace, step, by_id, jobs, settings):
                errors.append(error)

    if all(s.status in DONE_STEP for s in steps) and plan.status == PlanStatus.running:
        plan.finished_at = datetime.now(UTC)
        if all(s.status == "succeeded" for s in steps):
            plan.status = PlanStatus.succeeded
        else:
            plan.status = PlanStatus.failed
            failed = next((s for s in steps if s.status == "failed"), None)
            plan.error = (
                f"“{failed.title}” failed: {failed.error}" if failed else "Some steps didn't run"
            )
    save_steps(plan, steps)
    return errors


async def _submit(
    session: AsyncSession,
    plan: CopilotPlan,
    workspace: Workspace,
    step: PlanStep,
    by_id: dict[str, PlanStep],
    jobs: dict[uuid.UUID, Job],
    settings: Settings,
) -> JobError | None:
    inputs: list[InputRef] = []
    for item in step.inputs:
        if item.asset_id:
            inputs.append(InputRef(item.asset_id, item.role))
            continue
        src = jobs[by_id[item.from_step].job_id]
        outputs = (
            await session.scalars(
                select(Asset.id).where(Asset.job_id == src.id).order_by(Asset.created_at)
            )
        ).all()
        if not outputs:
            step.status, step.error = "failed", "The earlier step produced no output"
            return None
        inputs.append(InputRef(outputs[min(item.output_index, len(outputs) - 1)], item.role))

    model, operation, params = step.model, step.operation, step.params
    simulate = settings.copilot_simulate and settings.enable_debug_operations
    if simulate:
        model, operation, params = _simulated(step)
        if operation == "image_edit":
            inputs = [InputRef(i.asset_id, "image") for i in inputs if i.role == "image"][:4]
    try:
        async with session.begin_nested():
            job = await submit_job(
                session,
                workspace,
                plan.created_by_id,
                model=model,
                operation=operation,
                prompt=step.prompt,
                params=params,
                inputs=inputs,
                include_debug=settings.enable_debug_operations,
                plan_id=plan.id,
            )
    except JobError as exc:
        step.status, step.error = "failed", str(exc)
        return exc
    jobs[job.id] = job
    step.job_id, step.status, step.error = job.id, "queued", None
    return None


async def cancel(session: AsyncSession, plan: CopilotPlan, settings: Settings) -> None:
    """Stop a running plan: cancel its unfinished jobs and the steps not started."""
    if plan.status not in (PlanStatus.running, PlanStatus.draft):
        return
    now = datetime.now(UTC)
    for job in await session.scalars(select(Job).where(Job.plan_id == plan.id).with_for_update()):
        if job.status in TERMINAL:
            continue
        was_running = job.status == JobStatus.running
        job.status = JobStatus.canceled
        job.finished_at = now
        await billing.settle(session, job, job.hold_micros if was_running else 0)
    steps = steps_of(plan)
    for step in steps:
        if step.status == "pending":
            step.status = "canceled"
    save_steps(plan, steps)
    plan.status = PlanStatus.canceled
    plan.finished_at = now
    await advance(session, plan, settings)


async def on_job_finished(
    sessions: async_sessionmaker[AsyncSession], job_id: uuid.UUID, settings: Settings
) -> None:
    """Called by the worker after a job ends: move its plan forward."""
    async with sessions() as s:
        plan_id = await s.scalar(select(Job.plan_id).where(Job.id == job_id))
        if plan_id is None:
            return
        plan = await lock_plan(s, plan_id)
        if plan is None:
            return
        try:
            await advance(s, plan, settings)
            await s.commit()
        except Exception:
            log.exception("couldn't advance plan %s", plan_id)
            await s.rollback()
