"""Create organizational context without changing users, audit or n8n."""

import sqlalchemy as sa
from alembic import op

revision = "0004_organizational_context"
down_revision = "0003_create_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "executive_contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("position", sa.String(200), nullable=False),
        sa.Column("department", sa.String(200), nullable=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_executive_contacts")),
        schema="public",
    )
    op.create_index(
        "uq_executive_contacts_email_lower",
        "executive_contacts",
        [sa.text("lower(email)")],
        unique=True,
        schema="public",
    )
    op.create_table(
        "vendors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("domain", sa.String(253), nullable=False),
        sa.Column("contact_email", sa.String(320), nullable=True),
        sa.Column("bank_account_reference", sa.String(256), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vendors")),
        schema="public",
    )
    op.create_index(
        "uq_vendors_domain_lower",
        "vendors",
        [sa.text("lower(domain)")],
        unique=True,
        schema="public",
    )


def downgrade() -> None:
    op.drop_index("uq_vendors_domain_lower", table_name="vendors", schema="public")
    op.drop_table("vendors", schema="public")
    op.drop_index(
        "uq_executive_contacts_email_lower", table_name="executive_contacts", schema="public"
    )
    op.drop_table("executive_contacts", schema="public")
