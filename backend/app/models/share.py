import secrets
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.asset import Asset
from app.models.base import IdMixin, TimestampMixin


def new_token() -> str:
    return secrets.token_urlsafe(16)


class ShareLink(IdMixin, TimestampMixin, Base):
    """A public, unguessable link to one asset. Revoking deletes the row."""

    __tablename__ = "share_links"

    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=new_token)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    include_prompt: Mapped[bool] = mapped_column(Boolean, default=False)

    asset: Mapped[Asset] = relationship(lazy="joined")
