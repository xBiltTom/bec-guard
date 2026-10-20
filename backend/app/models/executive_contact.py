from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Index, String, Uuid, func, true
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.identity import validate_identity_email
from app.models.base import Base


class ExecutiveContact(Base):
    __tablename__ = "executive_contacts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("uq_executive_contacts_email_lower", func.lower(email), unique=True),)

    @validates("email")
    def normalize_email(self, _key: str, value: str) -> str:
        return validate_identity_email(value)
