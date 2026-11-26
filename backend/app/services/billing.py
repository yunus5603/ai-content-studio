"""Credits: holds when a job is submitted, settlement when it ends, purchases, limits.

Every balance change is a row in credit_entries written in the same transaction
as the cached Workspace.balance_micros update, under a row lock on the workspace,
so concurrent jobs can't overspend.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CreditEntry, EntryKind, Job, Membership, Workspace
from app.models.billing import to_micros, to_usd


class BillingError(Exception):
    status_code = 402


class InsufficientCredits(BillingError):
    status_code = 402


class LimitReached(BillingError):
    status_code = 403


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def post_entry(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    kind: EntryKind,
    amount_micros: int,
    *,
    job_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    external_ref: str | None = None,
    description: str | None = None,
) -> CreditEntry:
    """Add a ledger entry and update the cached balance. The caller commits."""
    ws = await session.scalar(
        select(Workspace).where(Workspace.id == workspace_id).with_for_update()
    )
    ws.balance_micros += amount_micros
    entry = CreditEntry(
        workspace_id=workspace_id,
        kind=kind,
        amount_micros=amount_micros,
        balance_after_micros=ws.balance_micros,
        job_id=job_id,
        user_id=user_id,
        external_ref=external_ref,
        description=description,
    )
    session.add(entry)
    await session.flush()
    return entry


async def grant_signup_credit(session: AsyncSession, workspace: Workspace, usd: float) -> None:
    if usd > 0:
        await post_entry(
            session,
            workspace.id,
            EntryKind.signup_grant,
            to_micros(usd),
            description="Welcome credit",
        )


async def spent_this_month(
    session: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> int:
    """Micro-USD spent on jobs since the start of the month (holds net of settlements)."""
    q = select(func.coalesce(func.sum(CreditEntry.amount_micros), 0)).where(
        CreditEntry.workspace_id == workspace_id,
        CreditEntry.kind.in_([EntryKind.job_hold, EntryKind.job_settle]),
        CreditEntry.created_at >= month_start(),
    )
    if user_id is not None:
        q = q.where(CreditEntry.user_id == user_id)
    return -int(await session.scalar(q))


async def reserve(
    session: AsyncSession, workspace: Workspace, user_id: uuid.UUID, job: Job, price_usd: float
) -> None:
    """Check balance and limits, then hold the job's estimated price. The caller commits."""
    hold = max(to_micros(price_usd), 1)
    # Lock first so two simultaneous submissions see each other's holds.
    ws = await session.scalar(
        select(Workspace).where(Workspace.id == workspace.id).with_for_update()
    )
    if ws.balance_micros < hold:
        raise InsufficientCredits(
            f"Not enough credits: this costs about ${to_usd(hold):.2f} and your balance is "
            f"${to_usd(ws.balance_micros):.2f}. Buy credits to continue."
        )
    if ws.monthly_limit_micros is not None:
        spent = await spent_this_month(session, ws.id)
        if spent + hold > ws.monthly_limit_micros:
            raise LimitReached("This workspace has reached its monthly spending limit.")
    member_limit = await session.scalar(
        select(Membership.monthly_limit_micros).where(
            Membership.workspace_id == ws.id, Membership.user_id == user_id
        )
    )
    if member_limit is not None:
        spent = await spent_this_month(session, ws.id, user_id)
        if spent + hold > member_limit:
            raise LimitReached("You've reached your monthly spending limit in this workspace.")

    job.hold_micros = hold
    await post_entry(
        session,
        ws.id,
        EntryKind.job_hold,
        -hold,
        job_id=job.id,
        user_id=user_id,
        description="Generation",
    )


async def settle(session: AsyncSession, job: Job, final_micros: int) -> None:
    """Replace the job's hold with its final price (0 refunds it). Idempotent."""
    if job.settled_at is not None:
        return
    final = max(final_micros, 0)
    difference = job.hold_micros - final
    if difference:
        await post_entry(
            session,
            job.workspace_id,
            EntryKind.job_settle,
            difference,
            job_id=job.id,
            user_id=job.created_by_id,
            description="Refund" if final == 0 else "Final price adjustment",
        )
    job.charged_micros = final
    job.settled_at = datetime.now(UTC)


async def lock_job(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    return await session.scalar(select(Job).where(Job.id == job_id).with_for_update())
