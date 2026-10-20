"""Create append-only security and business audit storage."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_create_audit_log"
down_revision = "0002_auth_identity_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_role", sa.String(7), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["public.users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_audit_log_actor_user_id_users"),
        ),
        sa.CheckConstraint(
            "actor_role IN ('ADMIN', 'ANALYST', 'MANAGER', 'AUDITOR')",
            name=op.f("ck_audit_log_actor_role"),
        ),
        schema="public",
    )
    op.execute("""
        CREATE FUNCTION public.reject_audit_log_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only' USING ERRCODE = '55000';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER audit_log_append_only
        BEFORE UPDATE OR DELETE ON public.audit_log
        FOR EACH ROW EXECUTE FUNCTION public.reject_audit_log_mutation()
    """)


def downgrade() -> None:
    op.drop_table("audit_log", schema="public")
    op.execute("DROP FUNCTION public.reject_audit_log_mutation()")
