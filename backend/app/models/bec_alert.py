from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BECAlert(Base):
    __tablename__ = "bec_alerts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    analysis_id: Mapped[UUID] = mapped_column(
        ForeignKey("email_analysis.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="OPEN")
    verdict: Mapped[str | None] = mapped_column(String(16))
    assigned_to: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    resolution: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("analysis_id"),
        CheckConstraint("status IN ('OPEN', 'UNDER_REVIEW', 'CLOSED')", name="status"),
        CheckConstraint("verdict IN ('CONFIRMED_BEC', 'FALSE_POSITIVE')", name="verdict"),
        CheckConstraint("status <> 'OPEN' OR closed_at IS NULL", name="open_not_closed"),
        Index("ix_bec_alerts_created_at_id", created_at.desc(), id),
    )
