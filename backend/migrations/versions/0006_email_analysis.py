"""Persist the current hybrid assessment for each email, without raw LLM data.

Revision ID: 0006_email_analysis
Revises: 0005_email_ingestion
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_email_analysis"
down_revision = "0005_email_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_analysis",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("deterministic_score", sa.Integer(), nullable=False),
        sa.Column("semantic_score", sa.Integer(), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.Column("risk_level", sa.String(length=16), nullable=True),
        sa.Column("bec_type", sa.String(length=32), nullable=True),
        sa.Column("signals", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary", sa.String(length=600), nullable=True),
        sa.Column("recommended_action", sa.String(length=400), nullable=True),
        sa.Column("provider", sa.String(length=16), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("policy_version", sa.String(length=80), nullable=False),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(status = 'COMPLETED' AND semantic_score IS NOT NULL AND risk_score IS NOT NULL "
            "AND risk_level IS NOT NULL AND summary IS NOT NULL AND recommended_action IS NOT NULL "
            "AND provider IS NOT NULL AND model IS NOT NULL AND error_code IS NULL) OR "
            "(status = 'ERROR' AND semantic_score IS NULL AND risk_score IS NULL "
            "AND risk_level IS NULL AND bec_type IS NULL AND summary IS NULL "
            "AND recommended_action IS NULL AND error_code IS NOT NULL)",
            name=op.f("ck_email_analysis_result_status"),
        ),
        sa.CheckConstraint(
            "bec_type IN ('EXECUTIVE_IMPERSONATION', 'VENDOR_FRAUD', "
            "'BANK_ACCOUNT_CHANGE', 'SENSITIVE_DATA_REQUEST', 'OTHER')",
            name=op.f("ck_email_analysis_bec_type"),
        ),
        sa.CheckConstraint(
            "error_code IN ('LLM_NOT_CONFIGURED', 'LLM_TIMEOUT', "
            "'LLM_PROVIDER_ERROR', 'LLM_INVALID_OUTPUT')",
            name=op.f("ck_email_analysis_error_code"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(signals) = 'array'", name=op.f("ck_email_analysis_signals_array")
        ),
        sa.CheckConstraint(
            "provider IN ('openai', 'google', 'gemini', 'groq')",
            name=op.f("ck_email_analysis_provider"),
        ),
        sa.CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name=op.f("ck_email_analysis_risk_level"),
        ),
        sa.CheckConstraint(
            "risk_score IS NULL OR "
            "(risk_score < 40 AND risk_level = 'LOW' AND bec_type IS NULL) OR "
            "(risk_score BETWEEN 40 AND 69 AND risk_level = 'MEDIUM') OR "
            "(risk_score BETWEEN 70 AND 84 AND risk_level = 'HIGH') OR "
            "(risk_score >= 85 AND risk_level = 'CRITICAL')",
            name=op.f("ck_email_analysis_risk_thresholds"),
        ),
        sa.CheckConstraint(
            "status IN ('COMPLETED', 'ERROR')", name=op.f("ck_email_analysis_status")
        ),
        sa.CheckConstraint(
            "deterministic_score BETWEEN 0 AND 100",
            name=op.f("ck_email_analysis_deterministic_score"),
        ),
        sa.CheckConstraint(
            "risk_score BETWEEN 0 AND 100", name=op.f("ck_email_analysis_risk_score")
        ),
        sa.CheckConstraint(
            "semantic_score BETWEEN 0 AND 100", name=op.f("ck_email_analysis_semantic_score")
        ),
        sa.ForeignKeyConstraint(
            ["email_id"],
            ["public.emails.id"],
            name=op.f("fk_email_analysis_email_id_emails"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_analysis")),
        sa.UniqueConstraint("email_id", name=op.f("uq_email_analysis_email_id")),
        schema="public",
    )


def downgrade() -> None:
    op.drop_table("email_analysis", schema="public")
