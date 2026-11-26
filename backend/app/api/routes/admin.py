"""Platform staff dashboard. Only users with is_platform_admin."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.billing import _model_name
from app.core.auth import get_current_user
from app.core.db import get_session
from app.models import CreditEntry, EntryKind, Job, JobStatus, User, Workspace
from app.models.billing import to_micros, to_usd
from app.schemas import AdjustmentRequest, AdminOverview, AdminWorkspaceRow, UsageRow
from app.services import billing

router = APIRouter(prefix="/admin", tags=["admin"])


async def platform_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_platform_admin:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return user


def _sum_entries(kind: EntryKind, since: datetime | None = None):
    q = select(func.coalesce(func.sum(CreditEntry.amount_micros), 0)).where(
        CreditEntry.kind == kind
    )
    return q.where(CreditEntry.created_at >= since) if since else q


@router.get("/overview", response_model=AdminOverview)
async def overview(
    days: int = Query(default=30, ge=1, le=366),
    _: User = Depends(platform_admin),
    session: AsyncSession = Depends(get_session),
):
    since = datetime.now(UTC) - timedelta(days=days)
    revenue = await session.scalar(_sum_entries(EntryKind.purchase, since))
    granted = await session.scalar(_sum_entries(EntryKind.signup_grant, since))
    done = [Job.created_at >= since, Job.charged_micros.is_not(None)]
    spend = await session.scalar(
        select(func.coalesce(func.sum(Job.charged_micros), 0)).where(*done)
    )
    cost = float(
        await session.scalar(
            select(func.coalesce(func.sum(Job.cost_usd), 0.0)).where(
                *done, Job.status == JobStatus.succeeded
            )
        )
    )
    jobs = await session.scalar(select(func.count(Job.id)).where(Job.created_at >= since))
    failed = await session.scalar(
        select(func.count(Job.id)).where(Job.created_at >= since, Job.status == JobStatus.failed)
    )
    outstanding = await session.scalar(select(func.coalesce(func.sum(Workspace.balance_micros), 0)))
    users = await session.scalar(select(func.count(User.id)))
    new_users = await session.scalar(select(func.count(User.id)).where(User.created_at >= since))
    workspaces = await session.scalar(select(func.count(Workspace.id)))

    spent = func.sum(Job.charged_micros)
    by_model = (
        await session.execute(
            select(Job.model, func.count(Job.id), spent)
            .where(*done)
            .group_by(Job.model)
            .order_by(spent.desc())
        )
    ).all()
    day = cast(Job.created_at, Date)
    by_day = (
        await session.execute(
            select(day, func.count(Job.id), spent).where(*done).group_by(day).order_by(day)
        )
    ).all()

    return AdminOverview(
        days=days,
        revenue_usd=to_usd(revenue),
        customer_spend_usd=to_usd(spend),
        provider_cost_usd=round(cost, 4),
        margin_usd=round(to_usd(spend) - cost, 4),
        outstanding_credit_usd=to_usd(outstanding),
        free_credit_granted_usd=to_usd(granted),
        jobs=jobs,
        failed_jobs=failed,
        users=users,
        new_users=new_users,
        workspaces=workspaces,
        by_model=[
            UsageRow(key=m, label=_model_name(m), jobs=n, spent_usd=to_usd(v or 0))
            for m, n, v in by_model
        ],
        by_day=[
            UsageRow(key=str(d), label=str(d), jobs=n, spent_usd=to_usd(v or 0))
            for d, n, v in by_day
        ],
    )


@router.get("/workspaces", response_model=list[AdminWorkspaceRow])
async def workspaces(
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(platform_admin),
    session: AsyncSession = Depends(get_session),
):
    purchased = (
        select(func.coalesce(func.sum(CreditEntry.amount_micros), 0))
        .where(CreditEntry.workspace_id == Workspace.id, CreditEntry.kind == EntryKind.purchase)
        .scalar_subquery()
    )
    spent = (
        select(func.coalesce(func.sum(Job.charged_micros), 0))
        .where(Job.workspace_id == Workspace.id)
        .scalar_subquery()
    )
    jobs = select(func.count(Job.id)).where(Job.workspace_id == Workspace.id).scalar_subquery()
    query = (
        select(Workspace, User.email, purchased, spent, jobs)
        .join(User, User.id == Workspace.owner_id)
        .order_by(spent.desc(), Workspace.created_at.desc())
        .limit(limit)
    )
    if q:
        like = f"%{q.lower()}%"
        query = query.where(func.lower(Workspace.name).like(like) | User.email.like(like))
    rows = (await session.execute(query)).all()
    return [
        AdminWorkspaceRow(
            id=ws.id,
            name=ws.name,
            owner_email=email,
            balance_usd=to_usd(ws.balance_micros),
            purchased_usd=to_usd(p),
            spent_usd=to_usd(s),
            jobs=n,
            created_at=ws.created_at,
        )
        for ws, email, p, s, n in rows
    ]


@router.post("/workspaces/{workspace_id}/credits", response_model=AdminWorkspaceRow)
async def adjust_credits(
    workspace_id: uuid.UUID,
    body: AdjustmentRequest,
    admin: User = Depends(platform_admin),
    session: AsyncSession = Depends(get_session),
):
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    await billing.post_entry(
        session,
        ws.id,
        EntryKind.adjustment,
        to_micros(body.amount_usd),
        user_id=admin.id,
        description=f"{body.reason} (by {admin.email})",
    )
    await session.commit()
    rows = await workspaces(q=None, limit=200, _=admin, session=session)
    return next(r for r in rows if r.id == ws.id)
