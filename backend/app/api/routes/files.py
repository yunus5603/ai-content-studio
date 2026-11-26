"""Serves media from local storage using signed URLs. Unused with GCS."""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.services.media import EXTENSIONS
from app.services.storage import LocalStorage, get_storage

router = APIRouter(tags=["files"], include_in_schema=False)
_TYPES = {ext: ct for ct, ext in EXTENSIONS.items()}


@router.get("/files/{key:path}")
async def serve(key: str, expires: int, sig: str):
    storage = get_storage()
    if not isinstance(storage, LocalStorage) or not storage.verify(key, expires, sig):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or expired link")
    path = storage.file_path(key)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return FileResponse(path, media_type=_TYPES.get(path.suffix.lstrip(".")))
