import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import workspace_access
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.permissions import Action
from app.models import Asset, AssetKind, MediaType
from app.schemas import AssetOut, Page
from app.services.media import EXTENSIONS, sniff
from app.services.storage import Storage, get_storage
from app.services.workspaces import WorkspaceAccess

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["assets"])


async def asset_out(asset: Asset, storage: Storage) -> AssetOut:
    out = AssetOut.model_validate(asset)
    out.url = await storage.url(asset.storage_key)
    return out


@router.post("/uploads", response_model=AssetOut, status_code=201)
async def upload(
    file: UploadFile,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    access.require(Action.upload)
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is too large")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")
    detected = sniff(data[:32])
    if detected is None or detected[0] not in settings.allowed_upload_types:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Unsupported file type. Upload PNG, JPEG, WebP, GIF, MP4, MOV or WebM.",
        )
    content_type, media_type = detected

    asset_id = uuid.uuid4()
    key = f"workspaces/{access.workspace.id}/uploads/{asset_id}.{EXTENSIONS[content_type]}"
    await storage.put(key, data, content_type)
    asset = Asset(
        id=asset_id,
        workspace_id=access.workspace.id,
        created_by_id=access.user.id,
        kind=AssetKind.upload,
        media_type=media_type,
        content_type=content_type,
        storage_key=key,
        filename=(file.filename or "")[:300] or None,
        size_bytes=len(data),
    )
    session.add(asset)
    await session.commit()
    return await asset_out(asset, storage)


@router.get("/assets", response_model=Page[AssetOut])
async def list_assets(
    kind: AssetKind | None = None,
    media_type: MediaType | None = None,
    cursor: datetime | None = Query(default=None, description="created_at of the last item"),
    limit: int = Query(default=40, ge=1, le=100),
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    access.require(Action.view)
    q = select(Asset).where(Asset.workspace_id == access.workspace.id)
    if kind:
        q = q.where(Asset.kind == kind)
    if media_type:
        q = q.where(Asset.media_type == media_type)
    if cursor:
        q = q.where(Asset.created_at < cursor)
    rows = (await session.scalars(q.order_by(Asset.created_at.desc()).limit(limit + 1))).all()
    items = [await asset_out(a, storage) for a in rows[:limit]]
    next_cursor = rows[limit - 1].created_at.isoformat() if len(rows) > limit else None
    return Page(items=items, next_cursor=next_cursor)


async def _get_asset(session: AsyncSession, access: WorkspaceAccess, asset_id: uuid.UUID):
    asset = await session.get(Asset, asset_id)
    if asset is None or asset.workspace_id != access.workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    return asset


@router.get("/assets/{asset_id}", response_model=AssetOut)
async def get_asset(
    asset_id: uuid.UUID,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    access.require(Action.view)
    return await asset_out(await _get_asset(session, access, asset_id), storage)


@router.delete("/assets/{asset_id}", status_code=204)
async def delete_asset(
    asset_id: uuid.UUID,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    asset = await _get_asset(session, access, asset_id)
    access.require(
        Action.delete_own_asset
        if asset.created_by_id == access.user.id
        else Action.delete_any_asset
    )
    await session.delete(asset)
    await session.commit()
    await storage.delete(asset.storage_key)
