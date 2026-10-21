from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BECAlert, EmailAnalysis, User
from app.models.enums import AnalysisStatus
from app.services.audit import record_alert_created

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
