import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.db import get_session
from app.models import User
from app.services.workspaces import WorkspaceAccess, load_access


async def workspace_access(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceAccess:
    return await load_access(session, workspace_id, user)
