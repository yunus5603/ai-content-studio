import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import Date, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import workspace_access
from app.catalog import CatalogError, get_model
from app.catalog.pricing import PLATFORM_FEE
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.permissions import Action, can
from app.models import CreditEntry, EntryKind, Job, Membership, User, Workspace
from app.models.billing import to_micros, to_usd
from app.schemas import (
    BillingSummary,
    CheckoutOut,
    CheckoutRequest,
    CreditEntryOut,
    LimitUpdate,
    MemberOut,
    Page,
    TopupRequest,
    UsageReport,
    UsageRow,
)
from app.services import billing
from app.services.workspaces import WorkspaceAccess

router = APIRouter(tags=["billing"])
log = logging.getLogger(__name__)


def _model_name(model_id: str) -> str:
    try:
        return get_model(model_id, include_debug=True, include_internal=True).name
    except CatalogError:
        return model_id


@router.get("/workspaces/{workspace_id}/billing", response_model=BillingSummary)
async def summary(
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    access.require(Action.view)
    ws = await session.get(Workspace, access.workspace.id, populate_existing=True)
    my_limit = await session.scalar(
        select(Membership.monthly_limit_micros).where(
            Membership.workspace_id == ws.id, Membership.user_id == access.user.id
        )
    )
    return BillingSummary(
        balance_usd=to_usd(ws.balance_micros),
        spent_this_month_usd=to_usd(await billing.spent_this_month(session, ws.id)),
        my_spent_this_month_usd=to_usd(
            await billing.spent_this_month(session, ws.id, access.user.id)
        ),
        monthly_limit_usd=to_usd(ws.monthly_limit_micros)
        if ws.monthly_limit_micros is not None
        else None,
        my_monthly_limit_usd=to_usd(my_limit) if my_limit is not None else None,
        credit_packs_usd=settings.credit_packs_usd,
        payments_enabled=bool(settings.stripe_secret_key),
        dev_topup_enabled=settings.enable_debug_operations and settings.env != "production",
        platform_fee=PLATFORM_FEE,
    )


@router.get("/workspaces/{workspace_id}/billing/entries", response_model=Page[CreditEntryOut])
async def entries(
    cursor: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
):
    access.require(Action.view)
    q = select(CreditEntry).where(CreditEntry.workspace_id == access.workspace.id)
    if not can(access.role, Action.manage_members):  # members see only their own activity
        q = q.where(CreditEntry.user_id == access.user.id)
    if cursor:
        q = q.where(CreditEntry.created_at < cursor)
    rows = (await session.scalars(q.order_by(CreditEntry.created_at.desc()).limit(limit + 1))).all()
    next_cursor = rows[limit - 1].created_at.isoformat() if len(rows) > limit else None
    return Page(items=rows[:limit], next_cursor=next_cursor)


@router.get("/workspaces/{workspace_id}/billing/usage", response_model=UsageReport)
async def usage(
    days: int = Query(default=30, ge=1, le=366),
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
):
    access.require(Action.view)
    since = datetime.now(UTC) - timedelta(days=days)
    base = [
        Job.workspace_id == access.workspace.id,
        Job.created_at >= since,
        Job.charged_micros.is_not(None),
    ]
    if not can(access.role, Action.manage_members):
        base.append(Job.created_by_id == access.user.id)
    spent = func.sum(Job.charged_micros)
    count = func.count(Job.id)

    day = cast(Job.created_at, Date)
    by_day = (
        await session.execute(select(day, count, spent).where(*base).group_by(day).order_by(day))
    ).all()
    by_model = (
        await session.execute(
            select(Job.model, count, spent).where(*base).group_by(Job.model).order_by(spent.desc())
        )
    ).all()
    by_member = (
        await session.execute(
            select(User.email, count, spent)
            .join(User, User.id == Job.created_by_id)
            .where(*base)
            .group_by(User.email)
            .order_by(spent.desc())
        )
    ).all()
    return UsageReport(
        days=days,
        total_usd=to_usd(sum(r[2] or 0 for r in by_model)),
        jobs=sum(r[1] for r in by_model),
        by_day=[
            UsageRow(key=str(d), label=str(d), jobs=n, spent_usd=to_usd(v or 0))
            for d, n, v in by_day
        ],
        by_model=[
            UsageRow(key=m, label=_model_name(m), jobs=n, spent_usd=to_usd(v or 0))
            for m, n, v in by_model
        ],
        by_member=[
            UsageRow(key=e, label=e, jobs=n, spent_usd=to_usd(v or 0)) for e, n, v in by_member
        ],
    )


@router.put("/workspaces/{workspace_id}/billing/limit", response_model=BillingSummary)
async def set_workspace_limit(
    body: LimitUpdate,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    access.require(Action.manage_billing)
    ws = await session.get(Workspace, access.workspace.id)
    ws.monthly_limit_micros = (
        to_micros(body.monthly_limit_usd) if body.monthly_limit_usd is not None else None
    )
    await session.commit()
    return await summary(access, session, settings)


@router.put("/workspaces/{workspace_id}/members/{user_id}/limit", response_model=MemberOut)
async def set_member_limit(
    user_id: uuid.UUID,
    body: LimitUpdate,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
):
    access.require(Action.manage_members)
    m = await session.scalar(
        select(Membership).where(
            Membership.workspace_id == access.workspace.id, Membership.user_id == user_id
        )
    )
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    m.monthly_limit_micros = (
        to_micros(body.monthly_limit_usd) if body.monthly_limit_usd is not None else None
    )
    await session.commit()
    return m


# ---- Buying credits ------------------------------------------------------


def _stripe(settings: Settings):
    import stripe

    if not settings.stripe_secret_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Payments aren't set up yet")
    return stripe.StripeClient(settings.stripe_secret_key)


@router.post("/workspaces/{workspace_id}/billing/checkout", response_model=CheckoutOut)
async def checkout(
    body: CheckoutRequest,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    access.require(Action.manage_billing)
    if body.amount_usd not in settings.credit_packs_usd:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose one of the credit packs")
    client = _stripe(settings)
    ws = await session.get(Workspace, access.workspace.id)
    if not ws.stripe_customer_id:
        customer = await client.v1.customers.create_async(
            params={
                "email": access.user.email,
                "name": ws.name,
                "metadata": {"workspace_id": str(ws.id)},
            }
        )
        ws.stripe_customer_id = customer.id
        await session.commit()
    back = f"{settings.public_web_url.rstrip('/')}/studio/billing"
    sess = await client.v1.checkout.sessions.create_async(
        params={
            "mode": "payment",
            "customer": ws.stripe_customer_id,
            "line_items": [
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": body.amount_usd * 100,
                        "product_data": {"name": f"${body.amount_usd} AI Content Studio credits"},
                    },
                }
            ],
            "metadata": {
                "workspace_id": str(ws.id),
                "user_id": str(access.user.id),
                "credit_micros": str(to_micros(body.amount_usd)),
            },
            "payment_intent_data": {"metadata": {"workspace_id": str(ws.id)}},
            "success_url": f"{back}?checkout=success",
            "cancel_url": f"{back}?checkout=canceled",
        }
    )
    return CheckoutOut(url=sess.url)


async def credit_purchase(session: AsyncSession, data: dict) -> bool:
    """Credit a paid Checkout Session once. Returns False if already credited."""
    meta = data.get("metadata") or {}
    workspace_id = uuid.UUID(meta["workspace_id"])
    amount = int(meta["credit_micros"])
    user_id = uuid.UUID(meta["user_id"]) if meta.get("user_id") else None
    try:
        await billing.post_entry(
            session,
            workspace_id,
            EntryKind.purchase,
            amount,
            user_id=user_id,
            external_ref=data["id"],
            description=f"Purchased ${to_usd(amount):.2f} credits",
        )
        await session.commit()
    except IntegrityError:  # already processed (Stripe retries webhooks)
        await session.rollback()
        return False
    return True


@router.post("/billing/stripe/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    import stripe

    if not settings.stripe_webhook_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Webhook not configured")
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret
        )
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature") from exc

    if event["type"] in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        data = event["data"]["object"].to_dict()
        if data.get("payment_status") == "paid":
            credited = await credit_purchase(session, data)
            log.info("checkout %s credited=%s", data.get("id"), credited)
    return {"received": True}


@router.post("/workspaces/{workspace_id}/billing/dev-topup", response_model=BillingSummary)
async def dev_topup(
    body: TopupRequest,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """Local development only: add credits without Stripe."""
    if not settings.enable_debug_operations or settings.env == "production":
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    access.require(Action.manage_billing)
    await billing.post_entry(
        session,
        access.workspace.id,
        EntryKind.adjustment,
        to_micros(body.amount_usd),
        user_id=access.user.id,
        description="Test credits (dev)",
    )
    await session.commit()
    return await summary(access, session, settings)
