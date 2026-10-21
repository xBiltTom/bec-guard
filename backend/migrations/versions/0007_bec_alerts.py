"""Create automatic alerts without implementing human review transitions."""

import sqlalchemy as sa
from alembic import op

revision = "0007_bec_alerts"
down_revision = "0006_email_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bec_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), server_default="OPEN", nullable=False),
        sa.Column("verdict", sa.String(16), nullable=True),
        sa.Column("assigned_to", sa.Uuid(), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bec_alerts")),
        sa.UniqueConstraint("analysis_id", name=op.f("uq_bec_alerts_analysis_id")),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["public.email_analysis.id"],
            name=op.f("fk_bec_alerts_analysis_id_email_analysis"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to"],
            ["public.users.id"],
            name=op.f("fk_bec_alerts_assigned_to_users"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'UNDER_REVIEW', 'CLOSED')", name=op.f("ck_bec_alerts_status")
        ),
        sa.CheckConstraint(
            "verdict IN ('CONFIRMED_BEC', 'FALSE_POSITIVE')", name=op.f("ck_bec_alerts_verdict")
        ),
        sa.CheckConstraint(
            "status <> 'OPEN' OR closed_at IS NULL", name=op.f("ck_bec_alerts_open_not_closed")
        ),
        schema="public",
    )
    op.create_index(
        "ix_bec_alerts_created_at_id",
        "bec_alerts",
        [sa.text("created_at DESC"), "id"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index("ix_bec_alerts_created_at_id", table_name="bec_alerts", schema="public")
    op.drop_table("bec_alerts", schema="public")
