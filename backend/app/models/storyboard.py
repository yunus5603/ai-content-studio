import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import IdMixin, TimestampMixin, utcnow


class Storyboard(IdMixin, TimestampMixin, Base):
    """A planned sequence of shots: keyframe image per shot, animated clip per shot,
    and the clips joined into one film."""

    __tablename__ = "storyboards"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    logline: Mapped[str | None] = mapped_column(Text)
    # Look and feel added to every keyframe prompt, e.g. "35mm film, warm dusk light".
    style: Mapped[str | None] = mapped_column(Text)
    # Catalog model ids and their params (validated per job against the catalog).
    image_model: Mapped[str] = mapped_column(String(128))
    image_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    video_model: Mapped[str] = mapped_column(String(128))
    video_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # How clips are joined: "cut" or "fade".
    transition: Mapped[str] = mapped_column(String(16), default="cut")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    film_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL")
    )
    film_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL")
    )
    # Shot ids + clip ids the current film was made from, to tell when it's out of date.
    film_source: Mapped[list[str] | None] = mapped_column(JSON)

    shots: Mapped[list["Shot"]] = relationship(
        back_populates="storyboard",
        order_by="Shot.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Shot(IdMixin, TimestampMixin, Base):
    __tablename__ = "storyboard_shots"

    storyboard_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("storyboards.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str | None] = mapped_column(String(200))
    # What the frame shows (keyframe prompt) and what happens in it (video prompt).
    description: Mapped[str] = mapped_column(Text, default="")
    motion: Mapped[str | None] = mapped_column(Text)
    # Clip length; None uses the storyboard's video params.
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    # Uploads or earlier outputs that guide the keyframe (characters, products, places).
    reference_asset_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    # End the clip on the next shot's keyframe, for a seamless move into it.
    end_on_next: Mapped[bool] = mapped_column(default=False)

    keyframe_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL")
    )
    keyframe_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL")
    )
    clip_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL")
    )
    clip_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL")
    )
    # Keyframe the current clip was animated from, to flag clips that are out of date.
    clip_keyframe_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL")
    )

    storyboard: Mapped[Storyboard] = relationship(back_populates="shots")
