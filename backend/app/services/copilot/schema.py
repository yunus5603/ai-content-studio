import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas import JobOut

Preference = Literal["quality", "balanced", "budget"]
StepStatus = Literal["pending", "queued", "running", "succeeded", "failed", "canceled", "skipped"]


class StepInput(BaseModel):
    """Where a step's input comes from: an attached asset, or an earlier step's output."""

    role: Literal["image", "mask", "first_frame", "last_frame"]
    asset_id: uuid.UUID | None = None
    from_step: str | None = None
    output_index: int = Field(default=0, ge=0)


class PlanStep(BaseModel):
    id: str  # "s1", "s2", ...
    title: str
    model: str
    operation: str
    prompt: str
    params: dict[str, Any] = Field(default_factory=dict)
    inputs: list[StepInput] = Field(default_factory=list)
    why: str = ""
    estimated_price_usd: float = 0.0
    status: StepStatus = "pending"
    job_id: uuid.UUID | None = None
    error: str | None = None


class PlanRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=4000)
    preference: Preference = "balanced"
    budget_usd: float | None = Field(default=None, gt=0, le=10_000)
    attachments: list[uuid.UUID] = Field(default_factory=list, max_length=8)
    # Run straight away if the plan costs no more than COPILOT_AUTORUN_MAX_USD.
    autorun: bool = False


class ReviseRequest(BaseModel):
    instruction: str | None = Field(default=None, max_length=2000)
    preference: Preference | None = None
    budget_usd: float | None = Field(default=None, gt=0, le=10_000)


class StepUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    model: str | None = None
    prompt: str | None = Field(default=None, min_length=1, max_length=32000)
    params: dict[str, Any] | None = None


class PlanOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    created_by_id: uuid.UUID
    goal: str
    preference: Preference
    budget_usd: float | None
    attachments: list[uuid.UUID]
    title: str
    summary: str
    notes: list[str]
    steps: list[PlanStep]
    planner: str
    status: str
    error: str | None
    estimated_price_usd: float
    charged_usd: float
    can_autorun: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    jobs: list[JobOut] = Field(default_factory=list)


class Draft(BaseModel):
    """What a planner returns before validation."""

    title: str = ""
    summary: str = ""
    steps: list[PlanStep]
    notes: list[str] = Field(default_factory=list)
    planner: str = "rules"
