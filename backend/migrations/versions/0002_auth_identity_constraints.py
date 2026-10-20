"""Normalize existing identities and enforce case-insensitive email uniqueness."""

import sqlalchemy as sa
from alembic import op

revision = "0002_auth_identity_constraints"
down_revision = "0001_create_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE public.users IN ACCESS EXCLUSIVE MODE"))
    rows = connection.execute(sa.text("SELECT id, email FROM public.users")).all()
    # Freeze the policy in this revision; do not import mutable application code.
    normalized = [(user_id, email.strip().lower()) for user_id, email in rows]
    identities = [email for _, email in normalized]
    if len(set(identities)) != len(identities):
        raise RuntimeError("Email normalization collision; resolve identities before migrating")
    for user_id, email in normalized:
        connection.execute(
            sa.text(
                "UPDATE public.users SET email = :email, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = :id AND email <> :email"
            ),
            {"id": user_id, "email": email},
        )
    op.drop_constraint("uq_users_email", "users", schema="public", type_="unique")
    op.create_index(
        "uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True, schema="public"
    )


def downgrade() -> None:
    op.drop_index("uq_users_email_lower", table_name="users", schema="public")
    op.create_unique_constraint("uq_users_email", "users", ["email"], schema="public")
