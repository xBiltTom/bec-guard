from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.email_limits import (
    MAX_AUTH_RESULTS_LENGTH,
    MAX_MESSAGE_ID_LENGTH,
    MAX_SENDER_NAME_LENGTH,
    MAX_SUBJECT_LENGTH,
    MAX_THREAD_ID_LENGTH,
)
from app.models.base import Base


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    message_id: Mapped[str] = mapped_column(String(MAX_MESSAGE_ID_LENGTH), nullable=False)
    thread_id: Mapped[str | None] = mapped_column(String(MAX_THREAD_ID_LENGTH))
    sender_name: Mapped[str | None] = mapped_column(String(MAX_SENDER_NAME_LENGTH))
    sender_email: Mapped[str] = mapped_column(String(320), nullable=False)
    reply_to: Mapped[str | None] = mapped_column(String(320))
    return_path: Mapped[str | None] = mapped_column(String(320))
    to_recipients: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    cc_recipients: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    subject: Mapped[str] = mapped_column(String(MAX_SUBJECT_LENGTH), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    authentication_results: Mapped[str | None] = mapped_column(String(MAX_AUTH_RESULTS_LENGTH))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("message_id"),
        Index("ix_emails_received_at_id", received_at.desc(), id),
    )
