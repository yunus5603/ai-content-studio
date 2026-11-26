import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import workspace_access
from app.core.auth import get_current_user
from app.core.db import get_session
from app.core.permissions import Action, Role, can_assign, permissions_for
from app.models import Invitation, Membership, User
from app.schemas import (
    InvitationCreate,
    InvitationOut,
    MemberOut,
    MemberUpdate,
    WorkspaceCreate,
    WorkspaceOut,
    WorkspaceUpdate,
    WorkspaceWithRole,
)
from app.services.workspaces import WorkspaceAccess, create_workspace

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _with_role(access: WorkspaceAccess) -> WorkspaceWithRole:
    return WorkspaceWithRole(
        **WorkspaceOut.model_validate(access.workspace).model_dump(),
        role=access.role,
        permissions=permissions_for(access.role),
    )


@router.post("", response_model=WorkspaceWithRole, status_code=201)
async def create(
    body: WorkspaceCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    ws = await create_workspace(session, user, body.name)
    await session.commit()
    return _with_role(WorkspaceAccess(ws, Role.owner, user))


@router.get("/{workspace_id}", response_model=WorkspaceWithRole)
async def get(access: WorkspaceAccess = Depends(workspace_access)):
    return _with_role(access)


@router.patch("/{workspace_id}", response_model=WorkspaceWithRole)
async def update(
    body: WorkspaceUpdate,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
):
    access.require(Action.manage_workspace)
    ws = await session.merge(access.workspace)
    ws.name = body.name
    await session.commit()
    access.workspace = ws
    return _with_role(access)


@router.delete("/{workspace_id}", status_code=204)
async def delete(
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
):
    access.require(Action.manage_workspace)
    if access.workspace.is_personal:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Personal workspaces can't be deleted")
    await session.delete(await session.merge(access.workspace))
    await session.commit()


# ---- Members -------------------------------------------------------------


@router.get("/{workspace_id}/members", response_model=list[MemberOut])
async def list_members(
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
):
    access.require(Action.view)
    return (
        await session.scalars(
            select(Membership)
            .where(Membership.workspace_id == access.workspace.id)
            .order_by(Membership.created_at)
        )
    ).all()


async def _membership(session: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID):
    m = await session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id, Membership.user_id == user_id
        )
    )
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return m


@router.patch("/{workspace_id}/members/{user_id}", response_model=MemberOut)
async def update_member(
    user_id: uuid.UUID,
    body: MemberUpdate,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
):
    access.require(Action.manage_members)
    m = await _membership(session, access.workspace.id, user_id)
    if not can_assign(access.role, m.role, body.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't assign that role")
    m.role = body.role
    await session.commit()
    return m


@router.delete("/{workspace_id}/members/{user_id}", status_code=204)
async def remove_member(
    user_id: uuid.UUID,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
):
    m = await _membership(session, access.workspace.id, user_id)
    if m.role == Role.owner:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The owner can't be removed")
    if user_id != access.user.id:  # anyone may leave; removing others needs admin
        access.require(Action.manage_members)
    await session.delete(m)
    await session.commit()


# ---- Invitations ---------------------------------------------------------


@router.get("/{workspace_id}/invitations", response_model=list[InvitationOut])
async def list_invitations(
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
):
    access.require(Action.manage_members)
    return (
        await session.scalars(
            select(Invitation)
            .where(Invitation.workspace_id == access.workspace.id, Invitation.accepted_at.is_(None))
            .order_by(Invitation.created_at.desc())
        )
    ).all()


@router.post("/{workspace_id}/invitations", response_model=InvitationOut, status_code=201)
async def invite(
    body: InvitationCreate,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
):
    access.require(Action.manage_members)
    if access.workspace.is_personal:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Create a team workspace to invite people")
    if not can_assign(access.role, None, body.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't invite with that role")
    email = body.email.lower()
    already = await session.scalar(
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .where(Membership.workspace_id == access.workspace.id, User.email == email)
    )
    if already:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already a member")
    invite = Invitation(
        workspace_id=access.workspace.id, email=email, role=body.role, invited_by_id=access.user.id
    )
    session.add(invite)
    try:
        await session.commit()
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already invited") from exc
    return invite


@router.delete("/{workspace_id}/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
):
    access.require(Action.manage_members)
    invite = await session.get(Invitation, invitation_id)
    if invite is None or invite.workspace_id != access.workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")
    await session.delete(invite)
    await session.commit()
