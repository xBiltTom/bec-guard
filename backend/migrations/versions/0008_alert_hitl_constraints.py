"""Enforce human review state consistency without changing historical revisions."""

from alembic import op

revision = "0008_alert_hitl_constraints"
down_revision = "0007_bec_alerts"
branch_labels = None
depends_on = None

CONSISTENCY = (
    "(status = 'OPEN' AND assigned_to IS NULL AND verdict IS NULL "
    "AND resolution IS NULL AND closed_at IS NULL) OR "
    "(status = 'UNDER_REVIEW' AND assigned_to IS NOT NULL AND verdict IS NULL "
    "AND resolution IS NULL AND closed_at IS NULL) OR "
    "(status = 'CLOSED' AND assigned_to IS NOT NULL AND verdict IS NOT NULL "
    "AND resolution IS NOT NULL AND closed_at IS NOT NULL)"
)


def upgrade():
    op.drop_constraint(op.f("ck_bec_alerts_open_not_closed"), "bec_alerts", schema="public")
    op.create_check_constraint(
        op.f("ck_bec_alerts_review_consistency"), "bec_alerts", CONSISTENCY, schema="public"
    )


def downgrade():
    op.drop_constraint(op.f("ck_bec_alerts_review_consistency"), "bec_alerts", schema="public")
    op.create_check_constraint(
        op.f("ck_bec_alerts_open_not_closed"),
        "bec_alerts",
        "status <> 'OPEN' OR closed_at IS NULL",
        schema="public",
    )
