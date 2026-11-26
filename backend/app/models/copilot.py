import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import IdMixin, TimestampMixin, utcnow


class PlanStatus(enum.StrEnum):
    draft = "draft"  # proposed, waiting for the user to approve
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    canceled = "canceled"


class CopilotPlan(IdMixin, TimestampMixin, Base):
    """A copilot proposal: the user's goal turned into ordered generation steps.

    Steps live in `steps` as JSON (see app.services.copilot.schema.PlanStep). A step can
    use an earlier step's output as its input, e.g. generate a key frame, then animate it.
    """

    __tablename__ = "copilot_plans"
    __table_args__ = (Index("ix_copilot_plans_ws_created", "workspace_id", "created_at"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    goal: Mapped[str] = mapped_column(Text)
    # quality | balanced | budget
    preference: Mapped[str] = mapped_column(String(16), default="balanced")
    budget_micros: Mapped[int | None] = mapped_column(BigInteger)
    # Uploaded or generated assets the user attached to the request.
    attachments: Mapped[list[str]] = mapped_column(JSON, default=list)
    title: Mapped[str] = mapped_column(String(200), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[list[str]] = mapped_column(JSON, default=list)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # Which planner produced it: "llm" or "rules".
    planner: Mapped[str] = mapped_column(String(16), default="rules")
    status: Mapped[PlanStatus] = mapped_column(
        Enum(PlanStatus, name="plan_status"), default=PlanStatus.draft
    )
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
