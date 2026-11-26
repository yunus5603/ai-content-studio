import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.db import get_session
from app.core.permissions import permissions_for
from app.models import Invitation, Membership, User, Workspace
from app.schemas import MeOut, MyInvitationOut, UserOut, WorkspaceOut, WorkspaceWithRole

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeOut)
async def me(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(Workspace, Membership.role)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(Membership.user_id == user.id)
            .order_by(Workspace.is_personal.desc(), Workspace.created_at)
        )
    ).all()
    pending = await session.scalar(
        select(func.count())
        .select_from(Invitation)
        .where(Invitation.email == user.email, Invitation.accepted_at.is_(None))
    )
    return MeOut(
        user=UserOut.model_validate(user),
        workspaces=[
            WorkspaceWithRole(
                **WorkspaceOut.model_validate(ws).model_dump(),
                role=role,
                permissions=permissions_for(role),
            )
            for ws, role in rows
        ],
        pending_invitations=pending or 0,
    )


@router.get("/me/invitations", response_model=list[MyInvitationOut])
async def my_invitations(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    invites = (
        await session.scalars(
            select(Invitation)
            .where(Invitation.email == user.email, Invitation.accepted_at.is_(None))
            .order_by(Invitation.created_at.desc())
        )
    ).all()
    return [
        MyInvitationOut(
            **{c: getattr(i, c) for c in MyInvitationOut.model_fields if c != "workspace_name"},
            workspace_name=i.workspace.name,
        )
        for i in invites
    ]


async def _my_invite(session: AsyncSession, invitation_id: uuid.UUID, user: User) -> Invitation:
    invite = await session.get(Invitation, invitation_id)
    if invite is None or invite.email != user.email or invite.accepted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")
    return invite


@router.post("/me/invitations/{invitation_id}/accept", status_code=204)
async def accept_invitation(
    invitation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    invite = await _my_invite(session, invitation_id, user)
    existing = await session.scalar(
        select(Membership).where(
            Membership.workspace_id == invite.workspace_id, Membership.user_id == user.id
        )
    )
    if existing is None:
        session.add(Membership(workspace_id=invite.workspace_id, user_id=user.id, role=invite.role))
    invite.accepted_at = datetime.now(UTC)
    await session.commit()


@router.post("/me/invitations/{invitation_id}/decline", status_code=204)
async def decline_invitation(
    invitation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    invite = await _my_invite(session, invitation_id, user)
    await session.delete(invite)
    await session.commit()
