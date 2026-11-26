import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.permissions import Role
from app.models.base import IdMixin, TimestampMixin
from app.models.user import User

role_enum = Enum(Role, name="workspace_role", values_callable=lambda e: [r.value for r in e])


class Workspace(IdMixin, TimestampMixin, Base):
    """A team (or a single person) that owns media, jobs and, later, credits."""

    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(120))
    is_personal: Mapped[bool] = mapped_column(default=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class Membership(IdMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[Role] = mapped_column(role_enum)

    workspace: Mapped[Workspace] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(lazy="joined")


class Invitation(IdMixin, TimestampMixin, Base):
    """An invite by email. The invitee sees it after signing in with that email."""

    __tablename__ = "invitations"
    __table_args__ = (UniqueConstraint("workspace_id", "email"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[Role] = mapped_column(role_enum)
    invited_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    workspace: Mapped[Workspace] = relationship(lazy="joined")
