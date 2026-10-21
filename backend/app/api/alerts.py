from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.emails import Database, Reader
from app.models import BECAlert, Email, EmailAnalysis
from app.schemas.alerts import AlertDetailResponse, AlertSummaryResponse

router = APIRouter(prefix="/api/alerts", tags=["BEC alerts"])


@router.get("", response_model=list[AlertSummaryResponse])
def list_alerts(
    session: Database,
    _actor: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    # Select queue fields explicitly: never load the email body or provider output.
    statement = (
        select(
            BECAlert.id,
            BECAlert.analysis_id,
            BECAlert.status,
            BECAlert.verdict,
            BECAlert.assigned_to,
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
        .order_by(BECAlert.created_at.desc(), BECAlert.id)
        .limit(limit)
        .offset(offset)
    )
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
            if field != "analysis"
        },
        "analysis": session.get(EmailAnalysis, alert.analysis_id),
    }
