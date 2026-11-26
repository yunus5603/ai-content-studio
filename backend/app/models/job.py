import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import IdMixin, TimestampMixin


class JobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    canceled = "canceled"


TERMINAL = {JobStatus.succeeded, JobStatus.failed, JobStatus.canceled}


class Job(IdMixin, TimestampMixin, Base):
    """One generation request. The worker picks queued jobs from this table."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_created", "status", "created_at"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # operation="text_to_image", model="openai/gpt-image-2.6-sunburst" (catalog id)
    operation: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    prompt: Mapped[str | None] = mapped_column(Text)
    # Validated params with defaults filled in, exactly as sent to the provider.
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # [{"asset_id": "...", "role": "image" | "mask" | "first_frame" | "last_frame"}]
    inputs: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)

    # Provider cost in USD: estimate at submit time, actual when known.
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # What the customer pays (provider cost + platform fee), in micro-USD.
    hold_micros: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    charged_micros: Mapped[int | None] = mapped_column(BigInteger)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), default=JobStatus.queued
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Provider-side operation id, for long-running video jobs we poll.
    external_id: Mapped[str | None] = mapped_column(String(300))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when the job was started by a copilot plan step.
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("copilot_plans.id", ondelete="SET NULL"), index=True
    )
