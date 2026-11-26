import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import workspace_access
from app.catalog import CatalogError, get_model
from app.core.db import get_session
from app.core.permissions import Action
from app.models import Asset, Job, ShareLink
from app.schemas import PublicShareOut, ShareCreate, ShareOut
from app.services.storage import Storage, get_storage
from app.services.workspaces import WorkspaceAccess

router = APIRouter(tags=["shares"])


@router.post(
    "/workspaces/{workspace_id}/assets/{asset_id}/shares", response_model=ShareOut, status_code=201
)
async def create_share(
    asset_id: uuid.UUID,
    body: ShareCreate,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
):
    access.require(Action.generate)
    asset = await session.get(Asset, asset_id)
    if asset is None or asset.workspace_id != access.workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    expires = (
        datetime.now(UTC) + timedelta(days=body.expires_in_days) if body.expires_in_days else None
    )
    link = ShareLink(
        asset_id=asset.id,
        workspace_id=access.workspace.id,
        created_by_id=access.user.id,
        expires_at=expires,
        include_prompt=body.include_prompt,
    )
    session.add(link)
    await session.commit()
    return link


@router.get("/workspaces/{workspace_id}/assets/{asset_id}/shares", response_model=list[ShareOut])
async def list_shares(
    asset_id: uuid.UUID,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
):
    access.require(Action.view)
    return (
        await session.scalars(
            select(ShareLink)
            .where(ShareLink.asset_id == asset_id, ShareLink.workspace_id == access.workspace.id)
            .order_by(ShareLink.created_at.desc())
        )
    ).all()


@router.delete("/workspaces/{workspace_id}/shares/{share_id}", status_code=204)
async def revoke_share(
    share_id: uuid.UUID,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
):
    link = await session.get(ShareLink, share_id)
    if link is None or link.workspace_id != access.workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    if link.created_by_id != access.user.id:
        access.require(Action.manage_members)
    await session.delete(link)
    await session.commit()


@router.get("/share/{token}", response_model=PublicShareOut)
async def public_share(
    token: str,
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    """Public: anyone with the link can view the shared file."""
    link = await session.scalar(select(ShareLink).where(ShareLink.token == token))
    if link is None or (link.expires_at and link.expires_at < datetime.now(UTC)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link doesn't exist or has expired")
    asset = link.asset
    prompt = model_name = None
    if link.include_prompt and asset.job_id:
        job = await session.get(Job, asset.job_id)
        if job:
            prompt = job.prompt
            try:
                model_name = get_model(job.model, include_debug=True, include_internal=True).name
            except CatalogError:
                model_name = None
    return PublicShareOut(
        media_type=asset.media_type.value,
        content_type=asset.content_type,
        url=await storage.url(asset.storage_key),
        width=asset.width,
        height=asset.height,
        created_at=asset.created_at,
        prompt=prompt,
        model_name=model_name,
    )
