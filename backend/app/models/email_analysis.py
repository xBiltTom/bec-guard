from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EmailAnalysis(Base):
    __tablename__ = "email_analysis"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email_id: Mapped[UUID] = mapped_column(
        ForeignKey("emails.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    deterministic_score: Mapped[int] = mapped_column(Integer, nullable=False)
    semantic_score: Mapped[int | None] = mapped_column(Integer)
    risk_score: Mapped[int | None] = mapped_column(Integer)
    risk_level: Mapped[str | None] = mapped_column(String(16))
    bec_type: Mapped[str | None] = mapped_column(String(32))
    signals: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    summary: Mapped[str | None] = mapped_column(String(600))
    recommended_action: Mapped[str | None] = mapped_column(String(400))
    provider: Mapped[str | None] = mapped_column(String(16))
    model: Mapped[str | None] = mapped_column(String(200))
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(32))
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("email_id"),
        CheckConstraint("status IN ('COMPLETED', 'ERROR')", name="status"),
        CheckConstraint("deterministic_score BETWEEN 0 AND 100", name="deterministic_score"),
        CheckConstraint("semantic_score BETWEEN 0 AND 100", name="semantic_score"),
        CheckConstraint("risk_score BETWEEN 0 AND 100", name="risk_score"),
        CheckConstraint("risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="risk_level"),
        CheckConstraint(
            "bec_type IN ('EXECUTIVE_IMPERSONATION', 'VENDOR_FRAUD', "
            "'BANK_ACCOUNT_CHANGE', 'SENSITIVE_DATA_REQUEST', 'OTHER')",
            name="bec_type",
        ),
        CheckConstraint("provider IN ('openai', 'google', 'gemini', 'groq')", name="provider"),
        CheckConstraint(
            "error_code IN ('LLM_NOT_CONFIGURED', 'LLM_TIMEOUT', "
            "'LLM_PROVIDER_ERROR', 'LLM_INVALID_OUTPUT')",
            name="error_code",
        ),
        CheckConstraint("jsonb_typeof(signals) = 'array'", name="signals_array"),
        CheckConstraint(
            "(status = 'COMPLETED' AND semantic_score IS NOT NULL AND risk_score IS NOT NULL "
            "AND risk_level IS NOT NULL AND summary IS NOT NULL AND recommended_action IS NOT NULL "
            "AND provider IS NOT NULL AND model IS NOT NULL AND error_code IS NULL) OR "
            "(status = 'ERROR' AND semantic_score IS NULL AND risk_score IS NULL "
            "AND risk_level IS NULL AND bec_type IS NULL AND summary IS NULL "
            "AND recommended_action IS NULL AND error_code IS NOT NULL)",
            name="result_status",
        ),
        CheckConstraint(
            "risk_score IS NULL OR "
            "(risk_score < 40 AND risk_level = 'LOW' AND bec_type IS NULL) OR "
            "(risk_score BETWEEN 40 AND 69 AND risk_level = 'MEDIUM') OR "
            "(risk_score BETWEEN 70 AND 84 AND risk_level = 'HIGH') OR "
            "(risk_score >= 85 AND risk_level = 'CRITICAL')",
            name="risk_thresholds",
        ),
    )
