from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.dependencies import require_roles
from app.api.emails import Database, Reader
from app.models import AuditLog, BECAlert, Role, User
from app.schemas.product import AuditResponse, DashboardSummary
from app.services.operational_summary import operational_summary

router = APIRouter(prefix="/api", tags=["Product"])
AuditReader = Annotated[User, Depends(require_roles(Role.ADMIN, Role.AUDITOR))]


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(session: Database, _actor: Reader):
    today = datetime.now(UTC).date()
    dates = [today - timedelta(days=i) for i in reversed(range(7))]
    day = func.date(func.timezone("UTC", BECAlert.created_at))
    daily = dict(
        session.execute(
            select(day, func.count()).where(day >= dates[0], day <= today).group_by(day)
        ).all()
    )
    return {
        **operational_summary(session),
        "alerts_last_7_days": [{"date": d, "count": daily.get(d, 0)} for d in dates],
    }


@router.get("/audit", response_model=list[AuditResponse])
def list_audit(
    session: Database,
    _actor: AuditReader,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    action: Annotated[str | None, Query(max_length=64)] = None,
    resource_type: Annotated[str | None, Query(max_length=64)] = None,
):
    statement = select(*AuditLog.__table__.columns, User.name.label("actor_name")).outerjoin(
        User, AuditLog.actor_user_id == User.id
    )
    if action is not None:
        statement = statement.where(AuditLog.action == action)
    if resource_type is not None:
        statement = statement.where(AuditLog.resource_type == resource_type)
    return (
        session.execute(
            statement.order_by(AuditLog.created_at.desc(), AuditLog.id).limit(limit).offset(offset)
        )
        .mappings()
        .all()
    )
