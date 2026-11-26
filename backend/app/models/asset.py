import enum
import uuid

from sqlalchemy import BigInteger, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import IdMixin, TimestampMixin


class AssetKind(enum.StrEnum):
    upload = "upload"  # media a user uploaded as input
    output = "output"  # media a generation job produced


class MediaType(enum.StrEnum):
    image = "image"
    video = "video"


class Asset(IdMixin, TimestampMixin, Base):
    __tablename__ = "assets"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[AssetKind] = mapped_column(Enum(AssetKind, name="asset_kind"))
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType, name="media_type"))
    content_type: Mapped[str] = mapped_column(String(100))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    filename: Mapped[str | None] = mapped_column(String(300))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
