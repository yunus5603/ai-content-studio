import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Action, Role, can
from app.models import Membership, User, Workspace


async def ensure_personal_workspace(session: AsyncSession, user: User) -> Workspace:
    existing = await session.scalar(
        select(Workspace).where(Workspace.owner_id == user.id, Workspace.is_personal.is_(True))
    )
    if existing:
        return existing
    from app.core.config import get_settings
    from app.services.billing import grant_signup_credit

    name = f"{user.display_name or user.email.split('@')[0]}'s studio"
    ws = await create_workspace(session, user, name, is_personal=True)
    # Only personal workspaces get the welcome credit, so creating extra team
    # workspaces can't be used to collect more free credit.
    await grant_signup_credit(session, ws, get_settings().signup_credit_usd)
    return ws


async def create_workspace(
    session: AsyncSession, owner: User, name: str, is_personal: bool = False
) -> Workspace:
    ws = Workspace(name=name, owner_id=owner.id, is_personal=is_personal)
    session.add(ws)
    await session.flush()
    session.add(Membership(workspace_id=ws.id, user_id=owner.id, role=Role.owner))
    await session.flush()
    return ws


class WorkspaceAccess:
    """The current user's membership in the workspace named in the URL."""

    def __init__(self, workspace: Workspace, role: Role, user: User):
        self.workspace = workspace
        self.role = role
        self.user = user

    def require(self, action: Action) -> None:
        if not can(self.role, action):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Your role ({self.role}) cannot {action.value}"
            )


async def load_access(
    session: AsyncSession, workspace_id: uuid.UUID, user: User
) -> WorkspaceAccess:
    row = (
        await session.execute(
            select(Workspace, Membership.role)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(Workspace.id == workspace_id, Membership.user_id == user.id)
        )
    ).first()
    if row is None:
        # Platform admins can read any workspace (support), with viewer rights.
        if user.is_platform_admin:
            ws = await session.get(Workspace, workspace_id)
            if ws:
                return WorkspaceAccess(ws, Role.viewer, user)
        # 404 rather than 403 so workspace ids can't be probed.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return WorkspaceAccess(row[0], row[1], user)
