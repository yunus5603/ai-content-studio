import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import workspace_access
from app.catalog import CatalogError, get_model
from app.core.config import Settings, get_settings
from app.core.permissions import Action
from app.schemas import EnhanceOut, EnhanceRequest
from app.services import prompts
from app.services.workspaces import WorkspaceAccess

router = APIRouter(prefix="/workspaces/{workspace_id}/prompts", tags=["prompts"])
log = logging.getLogger(__name__)


@router.post("/enhance", response_model=EnhanceOut)
async def enhance(
    body: EnhanceRequest,
    access: WorkspaceAccess = Depends(workspace_access),
    settings: Settings = Depends(get_settings),
):
    access.require(Action.generate)
    spec = None
    if body.model:
        try:
            spec = get_model(body.model, include_debug=settings.enable_debug_operations)
        except CatalogError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    try:
        return EnhanceOut(prompt=await prompts.enhance_prompt(body.prompt, spec))
    except Exception as exc:
        log.exception("prompt enhancement failed")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Prompt enhancement is unavailable right now"
        ) from exc
