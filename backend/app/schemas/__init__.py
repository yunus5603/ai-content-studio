import uuid
from datetime import datetime
from typing import Any, Literal

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
    monthly_limit_micros: int | None = None


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


class JobInput(BaseModel):
    asset_id: uuid.UUID
    role: Literal["image", "mask", "first_frame", "last_frame"]


class JobCreate(BaseModel):
    model: str = Field(examples=["openai/gpt-image-2.6-sunburst"])
    operation: str = Field(examples=["text_to_image"])
    prompt: str = Field(min_length=1, max_length=32000)
    params: dict[str, Any] = Field(default_factory=dict)
    inputs: list[JobInput] = Field(default_factory=list, max_length=20)


class JobOut(ORM):
    id: uuid.UUID
    workspace_id: uuid.UUID
    created_by_id: uuid.UUID
    operation: str
    provider: str
    model: str
    prompt: str | None
    params: dict[str, Any]
    inputs: list[dict[str, str]]
    status: JobStatus
    progress: float
    error: str | None
    attempts: int
    estimated_cost_usd: float
    cost_usd: float | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    outputs: list[AssetOut] = []
    estimated_price_usd: float = 0.0
    price_usd: float | None = None
    hold_micros: int = 0
    charged_micros: int | None = None


class EstimateRequest(BaseModel):
    model: str
    operation: str
    params: dict[str, Any] = Field(default_factory=dict)


class EstimateOut(BaseModel):
    params: dict[str, Any]
    provider_cost_usd: float
    price_usd: float


class EnhanceRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    model: str | None = None
    operation: str | None = None


class EnhanceOut(BaseModel):
    prompt: str


class ShareCreate(BaseModel):
    include_prompt: bool = False
    expires_in_days: int | None = Field(default=None, ge=1, le=365)


class ShareOut(ORM):
    id: uuid.UUID
    token: str
    asset_id: uuid.UUID
    created_at: datetime
    expires_at: datetime | None
    include_prompt: bool = False


class PublicShareOut(BaseModel):
    media_type: str
    content_type: str
    url: str
    width: int | None
    height: int | None
    created_at: datetime
    prompt: str | None = None
    model_name: str | None = None


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None


class BillingSummary(BaseModel):
    balance_usd: float
    spent_this_month_usd: float
    my_spent_this_month_usd: float
    monthly_limit_usd: float | None
    my_monthly_limit_usd: float | None
    credit_packs_usd: list[int]
    payments_enabled: bool
    dev_topup_enabled: bool
    platform_fee: float


class CreditEntryOut(ORM):
    id: uuid.UUID
    kind: str
    amount_micros: int
    balance_after_micros: int
    job_id: uuid.UUID | None
    user_id: uuid.UUID | None
    description: str | None
    created_at: datetime


class UsageRow(BaseModel):
    key: str
    label: str
    jobs: int
    spent_usd: float


class UsageReport(BaseModel):
    days: int
    total_usd: float
    jobs: int
    by_day: list[UsageRow]
    by_model: list[UsageRow]
    by_member: list[UsageRow]


class LimitUpdate(BaseModel):
    monthly_limit_usd: float | None = Field(default=None, ge=0, le=1_000_000)


class CheckoutRequest(BaseModel):
    amount_usd: int


class CheckoutOut(BaseModel):
    url: str


class TopupRequest(BaseModel):
    amount_usd: float = Field(gt=0, le=10_000)


class AdjustmentRequest(BaseModel):
    amount_usd: float = Field(ge=-100_000, le=100_000)
    reason: str = Field(min_length=3, max_length=300)


class AdminWorkspaceRow(BaseModel):
    id: uuid.UUID
    name: str
    owner_email: str
    balance_usd: float
    purchased_usd: float
    spent_usd: float
    jobs: int
    created_at: datetime


class AdminOverview(BaseModel):
    days: int
    revenue_usd: float  # Stripe purchases
    customer_spend_usd: float  # credits consumed by jobs
    provider_cost_usd: float
    margin_usd: float
    outstanding_credit_usd: float
    free_credit_granted_usd: float
    jobs: int
    failed_jobs: int
    users: int
    new_users: int
    workspaces: int
    by_model: list[UsageRow]
    by_day: list[UsageRow]
