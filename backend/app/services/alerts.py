from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BECAlert, EmailAnalysis, User
from app.models.enums import AnalysisStatus, Role
from app.schemas.alerts import AlertResolveRequest
from app.services.audit import AuditAction, record_alert_created, record_alert_review

ALERT_POLICY_VERSION = "alert-v1"
ALERT_THRESHOLD = 70


def ensure_alert_for_analysis(
    session: Session, analysis: EmailAnalysis, *, actor: User | None, peer: str | None = None
) -> BECAlert | None:
    """Ensure the alert in the caller's transaction; never commit separately."""
    if (
        analysis.status != AnalysisStatus.COMPLETED
        or analysis.risk_score is None
        or analysis.risk_score < ALERT_THRESHOLD
    ):
        return None
    # Also serialize callers using this helper outside analyze_email's Email lock.
    session.flush()
    session.execute(
        select(EmailAnalysis.id).where(EmailAnalysis.id == analysis.id).with_for_update()
    ).scalar_one()
    alert = session.scalar(select(BECAlert).where(BECAlert.analysis_id == analysis.id))
    if alert is None:
        alert = BECAlert(analysis_id=analysis.id)
        session.add(alert)
        session.flush()
        record_alert_created(session, actor=actor, alert_id=alert.id, peer=peer)
    return alert


def review_alert(
    session: Session,
    alert_id: UUID,
    *,
    operation: str,
    actor: User,
    payload: AlertResolveRequest | None = None,
    peer: str | None = None,
) -> BECAlert:
    """Serialize human decisions; commit mutation and minimal audit together."""
    alert = session.scalar(select(BECAlert).where(BECAlert.id == alert_id).with_for_update())
    if alert is None:
        raise HTTPException(404, "Alert not found")
    if operation == "resolve" and alert.status == "CLOSED":
        if payload and alert.verdict == payload.verdict and alert.resolution == payload.resolution:
            return alert
        raise HTTPException(409, "Alert already closed")
    if alert.status == "CLOSED":
        raise HTTPException(409, "Alert already closed")
    if operation == "claim":
        if alert.status == "UNDER_REVIEW":
            if alert.assigned_to == actor.id:
                return alert
            raise HTTPException(409, "Alert already assigned")
        alert.status, alert.assigned_to = "UNDER_REVIEW", actor.id
        action = AuditAction.BEC_ALERT_CLAIMED
    elif operation in {"release", "resolve"}:
        if operation == "release" and alert.status == "OPEN":
            return alert
        if alert.status != "UNDER_REVIEW":
            raise HTTPException(409, "Claim the alert before resolving")
        if actor.role == Role.ANALYST and alert.assigned_to != actor.id:
            raise HTTPException(403, "Forbidden")
        if operation == "release":
            alert.status, alert.assigned_to = "OPEN", None
            action = AuditAction.BEC_ALERT_RELEASED
        else:
            if payload is None:
                raise ValueError("Resolution required")
            alert.status = "CLOSED"
            alert.verdict, alert.resolution = payload.verdict, payload.resolution
            alert.closed_at = datetime.now(UTC)
            action = (
                AuditAction.BEC_ALERT_CONFIRMED
                if payload.verdict == "CONFIRMED_BEC"
                else AuditAction.BEC_ALERT_FALSE_POSITIVE
            )
    else:
        raise ValueError("Unknown review operation")
    record_alert_review(session, action, actor=actor, alert_id=alert.id, peer=peer)
    session.commit()
    session.refresh(alert)
    return alert
