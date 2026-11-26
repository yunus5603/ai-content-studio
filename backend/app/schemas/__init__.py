import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.permissions import Role
from app.models import AssetKind, JobStatus, MediaType


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORM):
    id: uuid.UUID
    email: str
    display_name: str | None
    photo_url: str | None
    is_platform_admin: bool


class WorkspaceOut(ORM):
    id: uuid.UUID
    name: str
    is_personal: bool
    owner_id: uuid.UUID
    created_at: datetime


class WorkspaceWithRole(WorkspaceOut):
    role: Role
    permissions: list[str]


class MeOut(BaseModel):
    user: UserOut
    workspaces: list[WorkspaceWithRole]
    pending_invitations: int


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WorkspaceUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class MemberOut(ORM):
    user: UserOut
    role: Role
    created_at: datetime


class MemberUpdate(BaseModel):
    role: Role


class InvitationCreate(BaseModel):
    email: EmailStr
    role: Role = Role.member


class InvitationOut(ORM):
    id: uuid.UUID
    workspace_id: uuid.UUID
    email: str
    role: Role
    created_at: datetime


class MyInvitationOut(InvitationOut):
    workspace_name: str


class AssetOut(ORM):
    id: uuid.UUID
    workspace_id: uuid.UUID
    created_by_id: uuid.UUID
    job_id: uuid.UUID | None
    kind: AssetKind
    media_type: MediaType
    content_type: str
    filename: str | None
    size_bytes: int
    width: int | None
    height: int | None
    duration_seconds: float | None
    created_at: datetime
    url: str | None = None


class JobCreate(BaseModel):
    operation: str = Field(examples=["text_to_image"])
    provider: str = Field(examples=["openai"])
    model: str = Field(examples=["gpt-image-1"])
    prompt: str | None = Field(default=None, max_length=32000)
    params: dict[str, Any] = Field(default_factory=dict)
    input_asset_ids: list[uuid.UUID] = Field(default_factory=list, max_length=16)


class JobOut(ORM):
    id: uuid.UUID
    workspace_id: uuid.UUID
    created_by_id: uuid.UUID
    operation: str
    provider: str
    model: str
    prompt: str | None
    params: dict[str, Any]
    input_asset_ids: list[str]
    status: JobStatus
    progress: float
    error: str | None
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    outputs: list[AssetOut] = []


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None
