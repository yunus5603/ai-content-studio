import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models import JobStatus
from app.schemas import AssetOut

Transition = Literal["cut", "fade"]


class ShotIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str = Field(default="", max_length=8000)
    motion: str | None = Field(default=None, max_length=8000)
    duration_seconds: int | None = Field(default=None, ge=1, le=60)
    reference_asset_ids: list[uuid.UUID] = Field(default_factory=list, max_length=8)
    end_on_next: bool = False


class ShotCreate(ShotIn):
    # Insert at this index (0 = first); default appends.
    position: int | None = Field(default=None, ge=0)


class ShotUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=8000)
    motion: str | None = Field(default=None, max_length=8000)
    duration_seconds: int | None = Field(default=None, ge=1, le=60)
    reference_asset_ids: list[uuid.UUID] | None = Field(default=None, max_length=8)
    end_on_next: bool | None = None


class StoryboardCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    logline: str | None = Field(default=None, max_length=4000)
    style: str | None = Field(default=None, max_length=4000)
    image_model: str | None = None
    image_params: dict[str, Any] | None = None
    video_model: str | None = None
    video_params: dict[str, Any] | None = None
    transition: Transition = "cut"
    # Lets a planner (e.g. the copilot) create a full storyboard in one call.
    shots: list[ShotIn] = Field(default_factory=list, max_length=60)


class StoryboardUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    logline: str | None = Field(default=None, max_length=4000)
    style: str | None = Field(default=None, max_length=4000)
    image_model: str | None = None
    image_params: dict[str, Any] | None = None
    video_model: str | None = None
    video_params: dict[str, Any] | None = None
    transition: Transition | None = None


class ShotOrder(BaseModel):
    shot_ids: list[uuid.UUID]


class KeyframePick(BaseModel):
    asset_id: uuid.UUID


class GenerateRequest(BaseModel):
    stage: Literal["keyframes", "clips"]
    # Only these shots (default: every shot).
    shot_ids: list[uuid.UUID] | None = None
    # Make new ones even where a result already exists.
    redo: bool = False


class JobBrief(BaseModel):
    id: uuid.UUID
    status: JobStatus
    progress: float
    error: str | None
    price_usd: float


class StepCost(BaseModel):
    """Price of making one keyframe or clip with the current settings."""

    price_usd: float | None
    # Why it can't be made right now (e.g. invalid settings, no keyframe yet).
    problem: str | None = None


class ShotOut(BaseModel):
    id: uuid.UUID
    position: int
    title: str | None
    description: str
    motion: str | None
    duration_seconds: int | None
    end_on_next: bool
    references: list[AssetOut]
    keyframe: AssetOut | None
    keyframe_job: JobBrief | None
    clip: AssetOut | None
    clip_job: JobBrief | None
    # The keyframe changed after this clip was made.
    clip_stale: bool
    keyframe_cost: StepCost
    clip_cost: StepCost


class StoryboardTotals(BaseModel):
    shots: int
    keyframes_done: int
    clips_done: int
    seconds: float
    # Price to make every missing keyframe / clip with the current settings.
    missing_keyframes_usd: float
    missing_clips_usd: float
    # Price to (re)make all of them.
    all_keyframes_usd: float
    all_clips_usd: float
    spent_usd: float


class StoryboardOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    created_by_id: uuid.UUID
    title: str
    logline: str | None
    style: str | None
    image_model: str
    image_params: dict[str, Any]
    video_model: str
    video_params: dict[str, Any]
    transition: Transition
    created_at: datetime
    updated_at: datetime
    shots: list[ShotOut]
    film: AssetOut | None
    film_job: JobBrief | None
    # Shots or clips changed since the film was assembled.
    film_stale: bool
    totals: StoryboardTotals


class StoryboardSummary(BaseModel):
    id: uuid.UUID
    title: str
    logline: str | None
    shot_count: int
    keyframes_done: int
    clips_done: int
    cover: AssetOut | None
    has_film: bool
    updated_at: datetime
