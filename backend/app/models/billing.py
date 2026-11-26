import enum
import uuid

from sqlalchemy import BigInteger, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import IdMixin, TimestampMixin

MICROS = 1_000_000  # amounts are stored in millionths of a US dollar


def to_micros(usd: float) -> int:
    return round(usd * MICROS)


def to_usd(micros: int) -> float:
    return int(micros or 0) / MICROS


class EntryKind(enum.StrEnum):
    signup_grant = "signup_grant"  # free credits for a new account
    purchase = "purchase"  # Stripe payment
    job_hold = "job_hold"  # reserved when a job starts (negative)
    job_settle = "job_settle"  # difference between hold and final price (+/-)
    adjustment = "adjustment"  # manual change by platform staff


class CreditEntry(IdMixin, TimestampMixin, Base):
    """Append-only credit ledger. A workspace's balance is the sum of its entries."""

    __tablename__ = "credit_entries"
    __table_args__ = (Index("ix_credit_entries_ws_created", "workspace_id", "created_at"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    kind: Mapped[EntryKind] = mapped_column(Enum(EntryKind, name="credit_entry_kind"))
    amount_micros: Mapped[int] = mapped_column(BigInteger)
    balance_after_micros: Mapped[int] = mapped_column(BigInteger)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # Stripe Checkout Session id for purchases; unique so webhooks are idempotent.
    external_ref: Mapped[str | None] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(String(500))
