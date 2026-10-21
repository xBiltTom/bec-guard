from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from app.api.emails import Database, Reader, Writer
from app.models import BECAlert, Email, EmailAnalysis, User
from app.models.enums import AlertStatus, BECType, RiskLevel
from app.schemas.alerts import AlertDetailResponse, AlertResolveRequest, AlertSummaryResponse
from app.services.alerts import review_alert

router = APIRouter(prefix="/api/alerts", tags=["BEC alerts"])


@router.get("", response_model=list[AlertSummaryResponse])
def list_alerts(
    session: Database,
    _actor: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: AlertStatus | None = None,
    risk_level: RiskLevel | None = None,
    bec_type: BECType | None = None,
    assigned_to: UUID | None = None,
    analysis_id: UUID | None = None,
):
    # Select queue fields explicitly: never load the email body or provider output.
    statement = (
        select(
            BECAlert.id,
            BECAlert.analysis_id,
            BECAlert.status,
            BECAlert.verdict,
            BECAlert.assigned_to,
            User.name.label("assigned_to_name"),
            BECAlert.created_at,
            BECAlert.updated_at,
            Email.id.label("email_id"),
            EmailAnalysis.risk_score,
            EmailAnalysis.risk_level,
            EmailAnalysis.bec_type,
            Email.sender_name,
            Email.sender_email,
            Email.subject,
            Email.received_at,
        )
        .join(EmailAnalysis, BECAlert.analysis_id == EmailAnalysis.id)
        .join(Email, EmailAnalysis.email_id == Email.id)
        .outerjoin(User, BECAlert.assigned_to == User.id)
        .order_by(BECAlert.created_at.desc(), BECAlert.id)
        .limit(limit)
        .offset(offset)
    )
    for column, value in [
        (BECAlert.status, status),
        (EmailAnalysis.risk_level, risk_level),
        (EmailAnalysis.bec_type, bec_type),
        (BECAlert.assigned_to, assigned_to),
        (BECAlert.analysis_id, analysis_id),
    ]:
        if value is not None:
            statement = statement.where(column == value)
    return session.execute(statement).mappings().all()


@router.get("/{alert_id}", response_model=AlertDetailResponse)
def get_alert(alert_id: UUID, session: Database, _actor: Reader):
    alert = session.get(BECAlert, alert_id)
    if alert is None:
        raise HTTPException(404, "Alert not found")
    return {
        **{
            field: getattr(alert, field)
            for field in AlertDetailResponse.model_fields
            if field not in {"analysis", "assigned_to_name"}
        },
        "analysis": session.get(EmailAnalysis, alert.analysis_id),
        "assigned_to_name": session.get(User, alert.assigned_to).name
        if alert.assigned_to
        else None,
    }


@router.post("/{alert_id}/claim", response_model=AlertDetailResponse)
def claim_alert(alert_id: UUID, session: Database, actor: Writer, request: Request):
    review_alert(
        session,
        alert_id,
        operation="claim",
        actor=actor,
        peer=request.client.host if request.client else None,
    )
    return get_alert(alert_id, session, actor)


@router.post("/{alert_id}/release", response_model=AlertDetailResponse)
def release_alert(alert_id: UUID, session: Database, actor: Writer, request: Request):
    review_alert(
        session,
        alert_id,
        operation="release",
        actor=actor,
        peer=request.client.host if request.client else None,
    )
    return get_alert(alert_id, session, actor)


@router.post("/{alert_id}/resolve", response_model=AlertDetailResponse)
def resolve_alert(
    alert_id: UUID, body: AlertResolveRequest, session: Database, actor: Writer, request: Request
):
    review_alert(
        session,
        alert_id,
        operation="resolve",
        actor=actor,
        payload=body,
        peer=request.client.host if request.client else None,
    )
    return get_alert(alert_id, session, actor)
