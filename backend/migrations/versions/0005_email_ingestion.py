"""Persist normalized email evidence; no analysis or evaluation metadata."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_email_ingestion"
down_revision = "0004_organizational_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emails",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.String(998), nullable=False),
        sa.Column("thread_id", sa.String(255), nullable=True),
        sa.Column("sender_name", sa.String(200), nullable=True),
        sa.Column("sender_email", sa.String(320), nullable=False),
        sa.Column("reply_to", sa.String(320), nullable=True),
        sa.Column("return_path", sa.String(320), nullable=True),
        sa.Column("to_recipients", postgresql.JSONB(), nullable=False),
        sa.Column("cc_recipients", postgresql.JSONB(), nullable=False),
        sa.Column("subject", sa.String(998), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("authentication_results", sa.String(4096), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_emails")),
        sa.UniqueConstraint("message_id", name=op.f("uq_emails_message_id")),
        schema="public",
    )
    op.create_index(
        "ix_emails_received_at_id", "emails", [sa.text("received_at DESC"), "id"], schema="public"
    )


def downgrade() -> None:
    op.drop_index("ix_emails_received_at_id", table_name="emails", schema="public")
    op.drop_table("emails", schema="public")
